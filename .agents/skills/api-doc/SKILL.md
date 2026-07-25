---
name: api-doc
description: Generate an OpenAPI specification from the Flask blueprints in this project and write it to `openapi.yaml`. Optionally updates a Swagger UI page if present.
disable-model-invocation: true
---

## Usage
```
Codex /skill api-doc
```
When invoked, the skill scans `app/api/v1/` for Flask route decorators, extracts HTTP methods, paths, parameters and docstrings, builds a compliant OpenAPI 3.0 document, and writes it to `openapi.yaml` at the repository root. If a `static/swagger.html` (or similar) exists, the file is refreshed to point at the new spec.

### What the skill does
1. Walks `app/api/v1/` looking for `@api_bp.route` (or any Blueprint) decorators.
2. Parses each function to collect:
   * HTTP method(s) (defaults to GET)
   * URL path (including any `<variable>` placeholders)
   * Summary from the function docstring
   * Simple 200‑OK response stub
3. Assembles a JSON OpenAPI 3.0 spec with `info.title` set to "MomentumScan API" and `info.version` taken from `config.VERSION` if available, otherwise "1.0.0".
4. Writes the pretty‑printed spec to `openapi.yaml`.
5. If a Swagger UI static file (`static/swagger.html` or `templates/swagger.html`) is present, updates the `<script>` tag to load the new `openapi.yaml`.

### Example implementation (Python)
```python
import json
import ast
from pathlib import Path

def generate_openapi():
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "MomentumScan API", "version": "1.0.0"},
        "paths": {}
    }
    for py_file in Path("app/api/v1").rglob("*.py"):
        tree = ast.parse(py_file.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for deco in node.decorator_list:
                    if isinstance(deco, ast.Call) and getattr(deco.func, "attr", "") == "route":
                        path = deco.args[0].s
                        methods = [kw.value.s for kw in deco.keywords if kw.arg == "methods"]
                        method = (methods[0] if methods else "GET").lower()
                        spec["paths"].setdefault(path, {})[method] = {
                            "summary": ast.get_docstring(node) or "",
                            "responses": {"200": {"description": "OK"}}
                        }
    Path("openapi.yaml").write_text(json.dumps(spec, indent=2))

if __name__ == "__main__":
    generate_openapi()
```


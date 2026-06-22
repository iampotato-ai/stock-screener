---
name: api-doc
description: Generates an OpenAPI/Swagger spec from the Flask blueprints in app/api/v1/*.py.
disable-model-invocation: true
---
# Usage
/api-doc
# What it does
1. Walks app/api/v1/ looking for @api_bp.route decorators.
2. Extracts HTTP method, path, and docstring.
3. Builds OpenAPI 3.0 JSON with info.title "MomentumScan API" and version "1.0.0".
4. Writes pretty‑printed openapi.json to repo root.
# Example implementation (Python)
```python
import os, json, ast, re
from pathlib import Path

def generate():
    spec = {"openapi": "3.0.0", "info": {"title": "MomentumScan API", "version": "1.0.0"}, "paths": {}}
    for file in Path("app/api/v1").rglob("*.py"):
        src = file.read_text()
        tree = ast.parse(src)
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
    Path("openapi.json").write_text(json.dumps(spec, indent=2))

if __name__ == "__main__":
    generate()
```

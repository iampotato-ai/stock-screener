import ast
import sys

def check_python_syntax(file_path):
    """Check Python syntax without executing the code."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            source = f.read()
        ast.parse(source)
        print(f"✅ Syntax OK: {file_path}")
        return True
    except SyntaxError as e:
        print(f"❌ Syntax Error in {file_path}: {e}")
        return False
    except Exception as e:
        print(f"❌ Error reading {file_path}: {e}")
        return False

if __name__ == "__main__":
    files_to_check = [
        "app.py",
        "app/__init__.py",
        "app/extensions.py",
        "config.py",
        "run.py",
        "smoke_test.py"
    ]

    all_good = True
    for file_path in files_to_check:
        full_path = f"C:\\Users\\91996\\Documents\\My Projects\\stock-screener\\{file_path}"
        try:
            if not check_python_syntax(full_path):
                all_good = False
        except FileNotFoundError:
            print(f"⚠️  File not found: {full_path}")
            all_good = False

    if all_good:
        print("\n🎉 All files have valid Python syntax!")
    else:
        print("\n❌ Some files have syntax errors!")
        sys.exit(1)
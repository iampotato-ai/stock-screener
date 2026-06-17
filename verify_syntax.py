#!/usr/bin/env python3
"""
Syntax verification script for newly created files.
"""
import ast
import sys
import os

def verify_syntax(file_path):
    """Verify Python syntax of a file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        ast.parse(content)
        print(f"[OK] Syntax OK: {file_path}")
        return True
    except SyntaxError as e:
        print(f"[ERROR] Syntax Error in {file_path}: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Error reading {file_path}: {e}")
        return False

def main():
    """Main verification function."""
    files_to_check = [
        "app/services/screener_service.py",
        "app/api/v1/screener.py",
        "tests/test_screener_service.py",
        "tests/test_screener_api.py"
    ]

    all_passed = True
    for file_path in files_to_check:
        if os.path.exists(file_path):
            if not verify_syntax(file_path):
                all_passed = False
        else:
            print(f"[ERROR] File not found: {file_path}")
            all_passed = False

    if all_passed:
        print("\n[SUCCESS] All files have valid syntax!")
        return 0
    else:
        print("\n[FAILURE] Some files have syntax errors!")
        return 1

if __name__ == "__main__":
    sys.exit(main())
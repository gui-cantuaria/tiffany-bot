import ast
import os

def check_ui_components():
    views = []
    modals = []
    buttons = []
    
    for root, dirs, files in os.walk('.'):
        if any(x in root for x in ['.venv', 'venv', '__pycache__', '.git', 'benchmark']):
            continue
        for file in files:
            if not file.endswith('.py'):
                continue
            path = os.path.join(root, file)
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            try:
                tree = ast.parse(content, filename=path)
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        for base in node.bases:
                            base_str = ast.unparse(base) if hasattr(ast, 'unparse') else ''
                            if 'View' in base_str or 'ui.View' in base_str:
                                views.append((path, node.name, node.lineno))
                            elif 'Modal' in base_str or 'ui.Modal' in base_str:
                                modals.append((path, node.name, node.lineno))
            except Exception:
                pass

    print(f"Found {len(views)} View classes and {len(modals)} Modal classes:")
    print("Views:")
    for v in views:
        print(f"  {v[0]}:{v[2]} -> {v[1]}")
    print("Modals:")
    for m in modals:
        print(f"  {m[0]}:{m[2]} -> {m[1]}")

if __name__ == '__main__':
    check_ui_components()

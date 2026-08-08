import ast
import os
import glob
import re

def analyze_sinks():
    sinks = {
        'subprocess': [],
        'eval_exec': [],
        'pickle_yaml': [],
        'http_requests': [],
        'raw_sql': [],
        'hardcoded_secrets': []
    }
    
    secret_pattern = re.compile(r'(?i)(api[_-]?key|secret[_-]?key|bot[_-]?token|password)\s*=\s*["\'][^"\'\s]{8,}["\']')
    
    for root, dirs, files in os.walk('.'):
        if any(x in root for x in ['.venv', 'venv', '__pycache__', '.git', 'benchmark']):
            continue
        for file in files:
            if not file.endswith('.py'):
                continue
            path = os.path.join(root, file)
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                
            # Secret regex check
            for match in secret_pattern.finditer(content):
                line_no = content[:match.start()].count('\n') + 1
                matched_str = match.group(0)
                # Filter out obvious safe example placeholders
                if any(x in matched_str.lower() for x in ['your_', 'example', 'placeholder', 'test', 'tiffany_lavalink']):
                    continue
                sinks['hardcoded_secrets'].append((path, line_no, matched_str[:25] + '...'))
                    
            try:
                tree = ast.parse(content, filename=path)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        # check eval/exec
                        if isinstance(node.func, ast.Name) and node.func.id in ('eval', 'exec'):
                            sinks['eval_exec'].append((path, node.lineno, node.func.id))
                        # check subprocess
                        elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == 'subprocess':
                            sinks['subprocess'].append((path, node.lineno, node.func.attr))
                        elif isinstance(node.func, ast.Name) and node.func.id in ('system', 'popen'):
                            sinks['subprocess'].append((path, node.lineno, node.func.id))
                        # check http requests
                        elif isinstance(node.func, ast.Attribute) and node.func.attr in ('get', 'post', 'request'):
                            if isinstance(node.func.value, ast.Name) and node.func.value.id in ('requests', 'aiohttp', 'session', 'http_client'):
                                sinks['http_requests'].append((path, node.lineno, node.func.attr))
            except Exception as e:
                pass
                
    print('Sinks analysis summary:')
    for k, v in sinks.items():
        print(f'{k}: {len(v)} occurrences')
        for item in v[:10]:
            print(f'  {item}')

if __name__ == '__main__':
    analyze_sinks()

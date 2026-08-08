import ast
import os
import glob
import re
import json

def redteam_scan():
    print("=== STARTING TIFFANY OS RED-TEAM SECURITY & I18N AUDIT ===")
    
    findings = []
    
    # 1. SECRET SCAN ACROSS ALL TRACKED FILES
    secret_patterns = [
        ("Discord Bot Token", re.compile(r"MTA[0-9A-Za-z_-]{23,25}\.[0-9A-Za-z_-]{6}\.[0-9A-Za-z_-]{27,38}")),
        ("Stripe Live Secret Key", re.compile(r"sk_live_[0-9a-zA-Z]{24,}")),
        ("OpenRouter API Key", re.compile(r"sk-or-v1-[0-9a-fA-F]{64}")),
        ("Hardcoded Password", re.compile(r"(?i)(password|secret_key|api_key)\s*=\s*['\"]([^'\"]{8,})['\"]")),
    ]
    
    scanned_files = 0
    for root, dirs, files in os.walk('.'):
        if any(x in root for x in ['.venv', 'venv', '__pycache__', '.git', 'benchmark']):
            continue
        for file in files:
            path = os.path.join(root, file)
            scanned_files += 1
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    
                for name, pat in secret_patterns:
                    for match in pat.finditer(content):
                        matched_val = match.group(0)
                        # Filter false positives
                        if any(safe in matched_val.lower() for safe in ['your_', 'example', 'placeholder', 'test', 'os.getenv', 'tiffany_lavalink']):
                            continue
                        line_no = content[:match.start()].count('\n') + 1
                        findings.append({
                            "id": "SEC-SECRET-01",
                            "domain": "Secrets",
                            "severity": "P0" if "sk_live" in matched_val or "sk-or-v1" in matched_val else "P2",
                            "file": path,
                            "line": line_no,
                            "desc": f"Possible active secret detected ({name})"
                        })
            except Exception:
                pass

    print(f"Scanned {scanned_files} files for secrets.")
    
    # 2. DANGEROUS SINKS & SQL INJECTION SCAN
    sql_concat_pattern = re.compile(r'(?i)(SELECT|INSERT|UPDATE|DELETE|FROM|WHERE)\s+.*%s|f["\'].*(SELECT|INSERT|UPDATE|DELETE|WHERE)')
    
    for root, dirs, files in os.walk('.'):
        if any(x in root for x in ['.venv', 'venv', '__pycache__', '.git', 'benchmark']):
            continue
        for file in files:
            if not file.endswith('.py'):
                continue
            path = os.path.join(root, file)
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                # Dynamic SQL check
                for match in sql_concat_pattern.finditer(content):
                    line_no = content[:match.start()].count('\n') + 1
                    findings.append({
                        "id": "SEC-SQL-01",
                        "domain": "Database",
                        "severity": "P0",
                        "file": path,
                        "line": line_no,
                        "desc": "Possible raw dynamic string formatting in SQL query"
                    })
            except Exception:
                pass

    # 3. WORKFLOW SECURITY SCAN
    workflow_files = glob.glob('.github/workflows/*.yml') + glob.glob('.github/workflows/*.yaml')
    for wf in workflow_files:
        with open(wf, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            if 'StrictHostKeyChecking=no' in content:
                findings.append({
                    "id": "SEC-CICD-01",
                    "domain": "CI/CD",
                    "severity": "P0",
                    "file": wf,
                    "line": 1,
                    "desc": "StrictHostKeyChecking=no present in workflow"
                })
            if 'pull_request_target' in content:
                findings.append({
                    "id": "SEC-CICD-02",
                    "domain": "CI/CD",
                    "severity": "P1",
                    "file": wf,
                    "line": 1,
                    "desc": "pull_request_target trigger used (potential secret leak from forks)"
                })

    print(f"Total Red-Team Findings: {len(findings)}")
    for f in findings:
        print(f"  [{f['severity']}] {f['id']} - {f['file']}:{f['line']} -> {f['desc']}")

if __name__ == '__main__':
    redteam_scan()

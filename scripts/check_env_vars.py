#!/usr/bin/env python3
"""
AI Service Environment Variables Reconciliation Script (READ-ONLY)
Scans codebase for environment variable references and reconciles them against
render.yaml, docs/DEPLOY.md, and .env.example.
"""
import os
import re
import sys
from pathlib import Path

def get_repo_root():
    return Path(__file__).resolve().parent.parent

def scan_ai_service_env_vars(repo_root):
    env_vars = {} # name -> { 'code': set(), 'default': None, 'prod_required': False }
    
    # Scan python files
    py_files = list(repo_root.glob("*.py")) + list(repo_root.glob("core/**/*.py")) + list(repo_root.glob("services/**/*.py"))
    
    # 1. Pydantic fields in config.py
    config_py = repo_root / "core" / "config.py"
    if config_py.exists():
        with open(config_py, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            for line_no, line in enumerate(lines, 1):
                m = re.match(r'^\s*([a-z0-9_]+)\s*:\s*[^=\n]+=\s*Field\(', line)
                if m:
                    field_name = m.group(1).upper()
                    # scan following lines for default=
                    default_val = None
                    for offset in range(0, 5):
                        if line_no - 1 + offset < len(lines):
                            target_line = lines[line_no - 1 + offset]
                            default_m = re.search(r'default\s*=\s*([^,\)\n]+)', target_line)
                            if default_m:
                                default_val = default_m.group(1).strip().strip("'\"")
                                break
                            if ")" in target_line:
                                break
                    env_vars[field_name] = {
                        'code': {f"core/config.py:{line_no}"},
                        'default': default_val,
                        'prod_required': default_val is None or "..." in str(default_val)
                    }

    # 2. os.environ / os.getenv
    for pf in py_files:
        with open(pf, "r", encoding="utf-8", errors="ignore") as f:
            for line_no, line in enumerate(f, 1):
                for m in re.finditer(r'os\.(?:environ\.get|getenv)\(\s*["\']([A-Za-z0-9_]+)["\'](?:\s*,\s*([^)]+))?\)', line):
                    var_name = m.group(1)
                    default_val = m.group(2).strip().strip("'\"") if m.group(2) else None
                    if var_name not in env_vars:
                        env_vars[var_name] = {
                            'code': set(),
                            'default': default_val,
                            'prod_required': default_val is None
                        }
                    rel_path = pf.relative_to(repo_root)
                    env_vars[var_name]['code'].add(f"{rel_path}:{line_no}")

    # Required variables enforced in main.py / dependencies
    for req in ["API_KEY"]:
        if req in env_vars:
            env_vars[req]['prod_required'] = True

    return env_vars

def parse_render_yaml(yaml_path):
    keys = set()
    if not yaml_path.exists():
        return keys
    with open(yaml_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line.startswith("- key:"):
                key = line.split(":", 1)[1].strip()
                keys.add(key)
    return keys

def parse_env_example(env_path):
    keys = set()
    if not env_path.exists():
        return keys
    with open(env_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key = line.split("=", 1)[0].strip()
                keys.add(key)
    return keys

def parse_deploy_md(md_path):
    keys = set()
    if not md_path.exists():
        return keys
    with open(md_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            for match in re.finditer(r'`([A-Z0-9_]{3,})`', line):
                keys.add(match.group(1))
    return keys

def main():
    root = get_repo_root()
    print(f"Scanning Repository: {root.name} ({root})")

    env_vars = scan_ai_service_env_vars(root)
    render_yaml_keys = parse_render_yaml(root / "render.yaml")
    env_example_keys = parse_env_example(root / ".env.example")
    deploy_md_keys = parse_deploy_md(root / "docs/DEPLOY.md")

    all_keys = sorted(set(env_vars.keys()) | render_yaml_keys | env_example_keys)

    headers = ["Variable", "In Code", "Default", "Prod Required", "render.yaml", "DEPLOY.md", ".env.example"]
    rows = []

    for k in all_keys:
        in_code = "Yes" if k in env_vars else "No"
        default = env_vars[k]['default'] if k in env_vars and env_vars[k]['default'] is not None else "-"
        prod_req = "YES" if k in env_vars and env_vars[k]['prod_required'] else "No"
        in_render = "Yes" if k in render_yaml_keys else "NO"
        in_deploy = "Yes" if k in deploy_md_keys else "NO"
        in_example = "Yes" if k in env_example_keys else "NO"
        rows.append([k, in_code, str(default), prod_req, in_render, in_deploy, in_example])

    col_widths = [max(len(row[i]) for row in ([headers] + rows)) for i in range(len(headers))]
    
    def format_row(row):
        return "| " + " | ".join(row[i].ljust(col_widths[i]) for i in range(len(row))) + " |"

    separator = "|-" + "-|-".join("-" * w for w in col_widths) + "-|"

    print("\n" + format_row(headers))
    print(separator)
    for r in rows:
        print(format_row(r))

if __name__ == "__main__":
    main()

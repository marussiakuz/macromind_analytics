#!/usr/bin/env python3
"""Preview first-commit files without git init in the working tree; never print secrets."""
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix='mma-git-check-') as tmp:
        subprocess.run(['git', 'init', '--bare', '-q', tmp], check=True)
        command = ['git', '--git-dir', tmp, '--work-tree', str(ROOT)]
        raw = subprocess.check_output(command + ['ls-files', '--others', '--exclude-standard', '-z'], cwd=ROOT)
        files = [p for p in raw.decode().split('\0') if p]
    forbidden = []
    for name in files:
        p = Path(name)
        if (name == 'venv' or p.name == '.env' or (p.name.startswith('.env.') and not p.name.endswith('.example'))
                or set(p.parts) & {'node_modules', '.venv', '__pycache__', '.playwright-cli', 'dist'}
                or p.suffix in {'.db', '.sqlite', '.sqlite3', '.dump', '.log'}
                or name.startswith('data/knowledge-objects/') or '/data/audit/' in name):
            forbidden.append(name)
    # Compare only against local secret values; neither values nor matching lines are printed.
    secrets = set()
    for env in ROOT.rglob('.env'):
        if any(x in env.parts for x in ('node_modules', '.venv')):
            continue
        for line in env.read_text(errors='replace').splitlines():
            key, sep, value = line.partition('=')
            value = value.strip().strip('\"\'')
            if sep and re.search(r'KEY|TOKEN|PASSWORD|SECRET', key, re.I) and len(value) >= 8:
                if not any(x in value.lower() for x in ('changeme', 'change-me', 'local_dev', 'your_', 'replace_')):
                    secrets.add(value)
    hits = []
    total = 0
    for name in files:
        path = ROOT / name
        if not path.is_file():
            continue
        total += path.stat().st_size
        if path.stat().st_size > 5_000_000:
            forbidden.append(name + ' (over 5 MB; review manually)')
            continue
        data = path.read_bytes()
        if b'\0' in data:
            continue
        text = data.decode(errors='replace')
        if any(secret in text for secret in secrets) or re.search(r'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----', text):
            hits.append(name)
    print(f'Candidate files: {len(files)}; total size: {total / 1024 / 1024:.2f} MiB')
    for label, names in [('Forbidden/generated files', forbidden), ('Possible secrets (filenames only)', hits)]:
        print(f'{label}: {len(names)}')
        for name in sorted(set(names)):
            print('  ' + name)
    print('Working tree .git created: no')
    print('This checks file selection and known local secrets, not a complete security audit or existing Git history.')
    return 1 if forbidden or hits else 0


if __name__ == '__main__':
    raise SystemExit(main())

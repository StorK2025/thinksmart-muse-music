"""Fail on credential/state artifacts; report paths only, never matching secrets."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {'.git', '__pycache__', '.venv', 'node_modules', 'dist', 'test-results'}
BAD_NAMES = {'sdk_token', 'pairing.json', 'identity.json', 'session-id', '.config.yaml', '.env'}
PATTERNS = [
    re.compile(r'mgst_[A-Za-z0-9_-]{40,}'),
    re.compile(r'-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----'),
    re.compile(r'(?:gh[opusr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})'),
    re.compile(r'(?:MUSIC_U|__csrf)\s*[=:]\s*["\x27]?[A-Za-z0-9%]{24,}'),
]


def main():
    failed = []
    for path in ROOT.rglob('*'):
        if any(p in EXCLUDED for p in path.relative_to(ROOT).parts) or not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if relative.as_posix() == 'docs/images/player-preview.png':
            continue  # Reviewed synthetic UI screenshot, no real account or song data.
        if path.name in BAD_NAMES or path.suffix in {'.sqlite', '.db', '.pem', '.img', '.bin', '.log'}:
            failed.append(str(relative) + ': state/binary file')
            continue
        if path.stat().st_size > 1024**2:
            failed.append(str(relative) + ': unexpectedly large file')
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except UnicodeError:
            failed.append(str(relative) + ': non-text file')
            continue
        for pattern in PATTERNS:
            if pattern.search(text):
                failed.append(str(relative) + ': possible credential')
                break
    for finding in failed:
        print(finding)
    if failed:
        return 1
    print('Public-source scan passed. Manual review is still required before publishing.')
    return 0


if __name__ == '__main__':
    sys.exit(main())

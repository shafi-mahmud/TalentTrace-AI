"""Create ignored, local synthetic Docker configuration. Never overwrite it."""
import argparse
import os
from pathlib import Path
import secrets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=5188)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Choose a loopback frontend port between 1024 and 65535.')
    root = Path(__file__).resolve().parents[1]
    target = root / 'data' / 'docker-demo.env'
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        parser.exit(1, 'Local Docker configuration already exists; nothing changed.\n')
    with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
        output.write('TALENTTRACE_DB_PASSWORD=' + secrets.token_hex(32) + '\n')
        output.write(f'TALENTTRACE_HTTP_PORT={args.port}\n')
    print('Created data/docker-demo.env. Values were not printed; keep this file private.')


if __name__ == '__main__':
    main()

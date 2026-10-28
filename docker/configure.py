"""Create ignored, local synthetic Docker configuration. Never overwrite it."""
import argparse
import os
from pathlib import Path
import secrets


def create_configuration(root, target, port):
    root, target = Path(root).resolve(), Path(target).resolve()
    if not 1024 <= port <= 65535:
        raise ValueError('invalid_port')
    if not target.is_relative_to(root / 'data') or target.suffix != '.env':
        raise ValueError('private_data_env_required')
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
        output.write('TALENTTRACE_DB_PASSWORD=' + secrets.token_hex(32) + '\n')
        output.write(f'TALENTTRACE_HTTP_PORT={port}\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=5188)
    parser.add_argument('--output', type=Path, help='New ignored .env path under this checkout data/; never overwritten.')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Choose a loopback frontend port between 1024 and 65535.')
    root = Path(__file__).resolve().parents[1]
    target = args.output or root / 'data' / 'docker-demo.env'
    try:
        create_configuration(root, target, args.port)
    except FileExistsError:
        parser.exit(1, 'Local Docker configuration already exists; nothing changed.\n')
    except ValueError:
        parser.exit(1, 'Choose a new .env path inside this checkout data/ directory.\n')
    print('Created private Docker configuration. Values were not printed; keep this file private.')


if __name__ == '__main__':
    main()

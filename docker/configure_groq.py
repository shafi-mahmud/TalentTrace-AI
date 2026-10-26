"""Create one private opt-in Groq profile. No database/provider requests or downloads."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def create_configuration(source, cache, target, port=5280):
    source, cache, target = Path(source), Path(cache), Path(target)
    if not source.is_file():
        raise ValueError('Source configuration file is absent.')
    values = dotenv_values(source)
    key = values.get('GROQ_API_KEY') or ''
    model = values.get('LLM_MODEL') or 'openai/gpt-oss-120b'
    if not key or len(key) > 2048 or any(c in key for c in '\r\n') or key.startswith('your_'):
        raise ValueError('A configured Groq key is required.')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,199}', model):
        raise ValueError('Invalid model configuration.')
    if not 1024 <= port <= 65535:
        raise ValueError('Invalid local port.')
    required = ('config.json', 'tokenizer.json', 'model.safetensors', 'modules.json')
    complete_cache = any(
        all((snapshot / name).is_file() for name in required)
        for snapshot in (cache / 'snapshots').glob('*')
    )
    if cache.name != 'models--BAAI--bge-small-en-v1.5' or not complete_cache:
        raise ValueError('Complete pre-existing BGE cache required; no download attempted.')
    target.mkdir(parents=True, exist_ok=False, mode=0o700)
    if os.name == 'nt':
        account = subprocess.check_output(['whoami'], text=True).strip()
        subprocess.run(
            ['icacls', str(target), '/inheritance:r', '/grant:r', account + ':(OI)(CI)F', '/q'],
            check=True, capture_output=True,
        )

    def write(name, body):
        fd = os.open(target / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            output.write(body)

    # Deliberate allowlist: never import the original DB, STT or other credentials.
    write('groq.env', 'GROQ_API_KEY=' + json.dumps(key) + '\nLLM_MODEL=' + json.dumps(model) + '\n')
    write(
        'compose.env',
        'COMPOSE_PROJECT_NAME=tt-groq-' + secrets.token_hex(6) + '\n'
        + 'TALENTTRACE_DB_PASSWORD=' + secrets.token_hex(32) + '\n'
        + f'TALENTTRACE_HTTP_PORT={port}\n'
        + f'TALENTTRACE_BROWSER_ORIGIN=http://groq-20261026.localhost:{port}\n'
        + 'TALENTTRACE_GROQ_ENV_FILE=' + json.dumps((target / 'groq.env').resolve().as_posix()) + '\n'
        + 'TALENTTRACE_BGE_CACHE=' + json.dumps(cache.resolve().as_posix()) + '\n',
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-env', type=Path, required=True)
    parser.add_argument('--bge-cache', type=Path, default=Path.home() / '.cache/huggingface/hub/models--BAAI--bge-small-en-v1.5')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/groq-runtime-20261026')
    parser.add_argument('--port', type=int, default=5280)
    args = parser.parse_args()
    try:
        create_configuration(args.source_env, args.bge_cache, args.output, args.port)
    except FileExistsError:
        parser.exit(1, 'Private configuration already exists; nothing overwritten.\n')
    except Exception:
        parser.exit(1, 'Groq configuration failed; check source/cache/storage prerequisites. Values were not printed.\n')
    print('Private allowlisted configuration created. No provider call or database operation performed.')


if __name__ == '__main__':
    main()

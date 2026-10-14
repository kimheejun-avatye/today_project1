"""Start an isolated PostgreSQL cluster, run integration tests, then stop it.

Does not register a service or open/modify an existing application database.
PG_BIN can point to another installation's bin directory.
"""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

backend = Path(__file__).resolve().parents[1]
bin_dir = Path(os.getenv('PG_BIN', '/opt/homebrew/opt/postgresql@17/bin'))
if not (bin_dir / 'initdb').exists():
    sys.exit('PostgreSQL bin directory missing. Set PG_BIN to the installed bin directory.')

with tempfile.TemporaryDirectory(prefix='haru-postgres-') as temp:
    path = Path(temp)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    subprocess.run([str(bin_dir/'initdb'), '-D', str(path/'data'), '-U', 'haru_test',
                    '-A', 'trust', '--locale=C', '-E', 'UTF8'], check=True, stdout=subprocess.DEVNULL)
    started = False
    try:
        subprocess.run([str(bin_dir/'pg_ctl'), '-D', str(path/'data'), '-l', str(path/'server.log'),
                        '-o', f'-h 127.0.0.1 -p {port} -k {temp}', '-w', 'start'], check=True)
        started = True
        env = {**os.environ, 'APP_ENV': 'development', 'APP_ORIGIN': 'http://localhost:5173',
               'APP_SECRET': 'postgres-test-only-secret-00000000000000000000',
               'DATABASE_URL': f'postgresql+psycopg://haru_test@127.0.0.1:{port}/postgres',
               'HARU_TEMP_POSTGRES': '1'}
        result = subprocess.run([sys.executable, '-m', 'pytest', 'tests/test_postgres.py', '-q'],
                                cwd=backend, env=env)
    finally:
        if started:
            subprocess.run([str(bin_dir/'pg_ctl'), '-D', str(path/'data'), '-m', 'fast', '-w', 'stop'], check=True)
    sys.exit(result.returncode)

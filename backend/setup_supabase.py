"""Save a private candidate URL; does not switch the live application database."""
from getpass import getpass
from pathlib import Path
import os
from dotenv import set_key
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parent

def main():
    password = getpass('Supabase DB password (hidden): ')
    if not password:
        raise SystemExit('No password entered; nothing changed.')
    url = URL.create('postgresql+psycopg',
        username='postgres.pryfzjqqrtbdbaolpuwe', password=password,
        host='aws-0-ap-northeast-2.pooler.supabase.com', port=5432,
        database='postgres', query={'sslmode': 'require', 'connect_timeout': '10'})
    path = ROOT / '.env'
    if not path.exists():
        path.touch(mode=0o600)
    os.chmod(path, 0o600)
    set_key(str(path), 'SUPABASE_DATABASE_URL', url.render_as_string(hide_password=False))
    os.chmod(path, 0o600)
    print('Candidate connection saved privately. DATABASE_URL is unchanged.')
    print('Return to the chat and say: password saved. Do not paste the password.')

if __name__ == '__main__':
    main()

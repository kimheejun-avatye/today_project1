"""Copy persistent records to an empty Supabase DB, validate, then opt-in switch.
Stop application writes before --apply. Default mode only checks connectivity/counts.
Credentials and record contents are never printed. Temporary auth state is omitted.
"""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
from dotenv import dotenv_values, set_key
from sqlalchemy import create_engine, select, func, text
from sqlalchemy.engine import make_url
from app.db.session import Base
from app import models  # noqa: F401 -- 이전할 테이블을 Base.metadata에 등록합니다.

ROOT = Path(__file__).resolve().parent
PERSISTENT = ('members', 'diaries', 'recurring_tasks', 'daily_tasks', 'comments')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--switch', action='store_true')
    args = parser.parse_args()
    if args.switch and not args.apply:
        raise SystemExit('--switch requires --apply')
    config = dotenv_values(ROOT / '.env', interpolate=False)
    raw = config.get('SUPABASE_DATABASE_URL')
    if not raw:
        raise SystemExit('Run setup_supabase.py first. No changes made.')
    url = make_url(raw)
    if url.get_backend_name() != 'postgresql' or url.host != 'aws-0-ap-northeast-2.pooler.supabase.com' or url.username != 'postgres.pryfzjqqrtbdbaolpuwe':
        raise SystemExit('Unexpected destination. No changes made.')
    source_path = ROOT / 'diary.db'
    source_db = sqlite3.connect(f'file:{source_path}?mode=ro', uri=True)
    # sqlite backup gives a coherent snapshot without printing any records.
    snapshot = sqlite3.connect(':memory:')
    source_db.backup(snapshot)
    source_db.close()
    source_engine = create_engine('sqlite://', creator=lambda: snapshot)
    target_engine = create_engine(url, pool_pre_ping=True)
    data = {}
    with source_engine.connect() as src:
        for name in PERSISTENT:
            data[name] = [dict(row) for row in src.execute(select(Base.metadata.tables[name])).mappings()]
    with target_engine.begin() as dst:
        if args.apply:
            names = ', '.join('public.' + name for name in sorted(Base.metadata.tables))
            dst.execute(text('LOCK TABLE ' + names + ' IN ACCESS EXCLUSIVE MODE'))
        for table in Base.metadata.sorted_tables:
            count = dst.scalar(select(func.count()).select_from(table))
            print(f'{table.name}: destination={count}, source_to_copy={len(data.get(table.name, []))}')
            if count:
                raise RuntimeError('Destination is not empty; merge is intentionally unsupported.')
        if not args.apply:
            print('Connection and empty-target check passed. No data or settings changed.')
            return
        backup_dir = ROOT / 'backups'
        backup_dir.mkdir(mode=0o700, exist_ok=True)
        backup = backup_dir / ('before-supabase-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.db')
        fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        with sqlite3.connect(backup) as saved:
            snapshot.backup(saved)
        for table in Base.metadata.sorted_tables:
            rows = data.get(table.name, [])
            if rows:
                dst.execute(table.insert(), rows)
            if table.name in PERSISTENT:
                actual = [dict(row) for row in dst.execute(select(table).order_by(table.c.id)).mappings()]
                expected = sorted(rows, key=lambda row: row['id'])
                if actual != expected:
                    raise RuntimeError('Read-back mismatch; transaction will roll back.')
                maximum = max((row['id'] for row in rows), default=0)
                dst.execute(text("SELECT setval(pg_get_serial_sequence(:tbl, 'id'), :value, :called)"),
                    {'tbl': 'public.' + table.name, 'value': max(maximum, 1), 'called': maximum > 0})
    print('Persistent records committed and read-back verified; source database retained.')
    if args.switch:
        path = ROOT / '.env'
        set_key(str(path), 'DATABASE_URL', raw)
        os.chmod(path, 0o600)
        print('DATABASE_URL switched. Restart backend; users must log in again.')

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # SQLAlchemy errors may contain record parameters or connection secrets.
        print('Migration stopped:', type(exc).__name__, '(details suppressed to protect private data).')
        raise SystemExit(1)

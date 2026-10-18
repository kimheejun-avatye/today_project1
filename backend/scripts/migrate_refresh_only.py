"""Explicit migration. Stop API first; back up and verify all non-auth rows.
Run from backend: .venv312/bin/python scripts/migrate_refresh_only.py
Re-running on the new schema is safe and does not end new logins.
"""
import sys, json, os
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core import config
from app.db.session import engine
from sqlalchemy import inspect, text


def migrate(connection, backup_dir=None):
    inspector = inspect(connection)
    tables = inspector.get_table_names()
    if "login_sessions" not in tables and {x["name"] for x in inspector.get_columns("refresh_tokens")} == {"id", "member_id", "digest", "expires_at"}:
        return {"already_migrated": True}
    if connection.dialect.name == "postgresql":
        connection.execute(text("SET LOCAL lock_timeout = '10s'"))
        connection.execute(text("SET LOCAL statement_timeout = '60s'"))
        quoted = ','.join(connection.dialect.identifier_preparer.quote(t) for t in tables)
        connection.exec_driver_sql("LOCK TABLE " + quoted + " IN ACCESS EXCLUSIVE MODE")
    def snapshot():
        return {t: [dict(r) for r in connection.execute(text("SELECT * FROM " + connection.dialect.identifier_preparer.quote(t))).mappings()] for t in tables}
    before = snapshot()
    if backup_dir:
        backup_dir.mkdir(parents=True, exist_ok=True)
        path = backup_dir / ("before-refresh-only-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as out:
            json.dump(before, out, ensure_ascii=False, default=str)
        print("Backup saved locally (private permissions).")
    if connection.dialect.name == "postgresql":
        sql = Path(__file__).resolve().parents[1] / "sql"
        connection.execute(text((sql / "006_refresh_only.sql").read_text()))
        connection.execute(text((sql / "003_auth_retention.sql").read_text()))
    else:
        connection.exec_driver_sql("DROP TABLE IF EXISTS refresh_tokens")
        connection.exec_driver_sql("DROP TABLE IF EXISTS login_sessions")
        connection.exec_driver_sql("CREATE TABLE refresh_tokens (id VARCHAR(36) PRIMARY KEY, member_id INTEGER NOT NULL UNIQUE REFERENCES members(id), digest VARCHAR(64) NOT NULL UNIQUE, expires_at INTEGER NOT NULL)")
        connection.exec_driver_sql("CREATE INDEX ix_refresh_tokens_expires_at ON refresh_tokens(expires_at)")
    preserved = {}
    for table, rows in before.items():
        if table in ("login_sessions", "refresh_tokens"):
            continue
        after = [dict(r) for r in connection.execute(text("SELECT * FROM " + connection.dialect.identifier_preparer.quote(table))).mappings()]
        canonical = lambda items: sorted(json.dumps(r, sort_keys=True, default=str) for r in items)
        if canonical(rows) != canonical(after):
            raise RuntimeError("Preservation check failed: " + table)
        preserved[table] = len(rows)
    assert not inspect(connection).has_table("login_sessions")
    return {"preserved_rows": preserved, "refresh_tokens": 0, "login_sessions_removed": True}


if __name__ == "__main__":
    with engine.begin() as connection:
        result = migrate(connection, Path(__file__).resolve().parents[1] / "backups")
    print(json.dumps(result))

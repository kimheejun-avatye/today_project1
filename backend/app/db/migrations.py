"""Schema helpers: additive startup upgrade and separately invoked column removal."""

from sqlalchemy import inspect, text


def ensure_nickname(engine):
    columns = {column["name"] for column in inspect(engine).get_columns("members")}
    additions = {
        "nickname": "VARCHAR(40)",
        "privacy_consent_version": "VARCHAR(60)",
        "privacy_consented_at": "INTEGER",
    }
    with engine.begin() as connection:
        for name, sql_type in additions.items():
            if name not in columns:
                connection.execute(
                    text(f"ALTER TABLE members ADD COLUMN {name} {sql_type}")
                )


def remove_unused_profile_columns(engine):
    """Explicit user-approved migration, never called automatically at API startup."""
    targets = {
        "members": ("birth_date", "phone", "created_at"),
        "login_sessions": ("created_at",),
    }
    with engine.begin() as connection:
        for table, names in targets.items():
            if not inspect(connection).has_table(table):
                continue
            existing = {
                column["name"] for column in inspect(connection).get_columns(table)
            }
            for name in names:
                if name in existing:
                    connection.execute(text(f"ALTER TABLE {table} DROP COLUMN {name}"))

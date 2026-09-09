"""
Alembic Environment Configuration — Magneetar

This project uses raw SQL migrations (not SQLAlchemy ORM models).
The env.py connects to the database and applies each pending raw-SQL
migration file from the versions directory directly, splitting each file
into individual statements using a robust SQL parser.

Usage:
  cd server
  alembic upgrade head                          # apply pending migrations
  alembic downgrade -1                          # revert last migration
  alembic revision -m "description" --sql      # create new migration
  alembic stamp head                           # mark current state (no-op migration)
"""

import os
import re
import sys
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, text

# Ensure the server directory is on the path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Imported after the sys.path bootstrap above — that ordering is the point
# of the layout here, so E402 is intentional and silenced inline.
from config import settings  # noqa: E402

# Alembic Config object
config = context.config

# Set the database URL from the environment
database_url = settings.DATABASE_URL
if not database_url:
    print(
        "WARNING: MT_DATABASE_URL not set. "
        "Alembic migrations target PostgreSQL. "
        "Set MT_DATABASE_URL in server/.env to run migrations."
    )
    database_url = "postgresql://localhost/magneetar"

config.set_main_option("sqlalchemy.url", database_url)


def _parse_sql_statements(sql_text: str) -> list[str]:
    """Split SQL text into individual statements, correctly handling:
    - Single-quoted strings: 'text'
    - Double-quoted identifiers: "text"
    - Dollar-quoted strings: $$text$$ or $tag$text$tag$
    - Line comments: -- text
    - Block comments: /* text */
    """
    stmts: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False
    in_dollar = False
    in_line = False
    in_block = False
    dollar_tag: str | None = None

    i = 0
    n = len(sql_text)
    while i < n:
        ch = sql_text[i]
        nxt = sql_text[i + 1] if i + 1 < n else ""

        # End of dollar-quoted string
        if in_dollar:
            if ch == "$" and nxt == "$" and i + 2 < n:
                j = i + 2
                while j < n and sql_text[j] == "$":
                    j += 1
                if j > i + 2:
                    tag = sql_text[i + 2 : j] if j > i + 2 else ""
                    expected = dollar_tag if dollar_tag else ""
                    if tag == expected or (dollar_tag is None and tag == ""):
                        current.append(sql_text[i : j + 1])
                        i = j
                        in_dollar = False
                        dollar_tag = None
                        continue
            current.append(ch)
            i += 1
            continue

        # Start of dollar-quoted string
        if not in_single and not in_double and not in_line and not in_block:
            if ch == "$" and nxt == "$":
                j = i + 2
                while j < n and sql_text[j] != "$":
                    j += 1
                if j < n and sql_text[j] == "$":
                    tag = sql_text[i + 2 : j] if j > i + 2 else ""
                    dollar_tag = tag
                    in_dollar = True
                    current.append(ch)
                    current.append(nxt)
                    i += 2
                    continue

        # Line comment start
        if not in_single and not in_double and not in_dollar and not in_block:
            if ch == "-" and nxt == "-":
                in_line = True
                current.append(ch)
                current.append(nxt)
                i += 2
                continue

        if in_line:
            current.append(ch)
            if ch == "\n":
                in_line = False
            i += 1
            continue

        # Block comment start
        if not in_single and not in_double and not in_dollar and not in_line:
            if ch == "/" and nxt == "*":
                in_block = True
                current.append(ch)
                current.append(nxt)
                i += 2
                continue

        if in_block:
            current.append(ch)
            if ch == "*" and nxt == "/":
                in_block = False
                current.append(nxt)
                i += 2
                continue
            i += 1
            continue

        # String/identifier start
        if not in_single and not in_double and not in_dollar and not in_line and not in_block:
            if ch == "'":
                in_single = True
                current.append(ch)
                i += 1
                continue
            if ch == '"':
                in_double = True
                current.append(ch)
                i += 1
                continue

        if in_single:
            current.append(ch)
            if ch == "\\" and i + 1 < n:
                i += 1
                current.append(sql_text[i])
            elif ch == "'":
                in_single = False
            i += 1
            continue

        if in_double:
            current.append(ch)
            if ch == "\\" and i + 1 < n:
                i += 1
                current.append(sql_text[i])
            elif ch == '"':
                in_double = False
            i += 1
            continue

        if in_dollar:
            current.append(ch)
            i += 1
            continue

        # Normal state
        current.append(ch)
        if ch == ";":
            stmt = "".join(current).strip()
            if stmt and not stmt.startswith("--") and not stmt.startswith("/*"):
                stmts.append(stmt)
            current = []
        i += 1

    if current:
        stmt = "".join(current).strip()
        if stmt and not stmt.startswith("--") and not stmt.startswith("/*"):
            stmts.append(stmt)

    return stmts


def _applied_revisions(connection) -> set:
    """Revisions already applied, according to the alembic_version table."""
    try:
        rows = connection.execute(text("SELECT version_num FROM alembic_version")).fetchall()
    except Exception:
        return set()
    return {row[0] for row in rows}


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — generate the SQL script without
    connecting to the database."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _versions_dir() -> Path:
    return Path(config.get_main_option("script_location", "alembic")) / "versions"


def _sql_files_in_order() -> list[Path]:
    """Return migration SQL files in filename order."""
    return sorted(_versions_dir().glob("*.sql"))


def _ddl_to_drops(ddl_statements: list[str]) -> list[str]:
    """Convert CREATE TABLE / CREATE INDEX statements into DROP
    statements (reverse order) for downgrade support.

    - CREATE TABLE IF NOT EXISTS <name> ... -> DROP TABLE IF EXISTS <name> CASCADE
    - CREATE INDEX IF NOT EXISTS <name> ... -> DROP INDEX IF EXISTS <name>
    """
    drops: list[str] = []
    for stmt in reversed(ddl_statements):
        s = stmt.strip().upper()
        if s.startswith("CREATE TABLE"):
            m = re.match(
                r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)",
                stmt,
                re.IGNORECASE,
            )
            if m:
                drops.append(f"DROP TABLE IF EXISTS {m.group(1)} CASCADE;")
        elif s.startswith("CREATE INDEX"):
            m = re.match(
                r"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+(\w+)",
                stmt,
                re.IGNORECASE,
            )
            if m:
                drops.append(f"DROP INDEX IF EXISTS {m.group(1)};")
    return drops


def _resolve_downgrade_target(command_rev: str, applied: set[str]) -> list[str]:
    """Given a downgrade revision argument (e.g. '-1', 'base', '001_base_schema')
    and the set of currently-applied revisions, return the list of revision ids
    to revert, in the order they should be reverted (most-recent first).
    """
    files = _sql_files_in_order()
    applied_in_order = [p.stem for p in files if p.stem in applied]

    if command_rev == "base":
        # Revert all applied revisions
        return list(reversed(applied_in_order))

    if command_rev == "-1":
        # Revert the most recent applied revision
        if not applied_in_order:
            return []
        return [applied_in_order[-1]]

    # Named revision: revert everything after (and including?) the target.
    # Alembic's convention: downgrade to revision X means X is the target
    # state; revert all revisions after X.
    if command_rev in applied_in_order:
        idx = applied_in_order.index(command_rev)
        return list(reversed(applied_in_order[idx + 1 :]))

    # Target not applied — nothing to revert
    return []


def run_migrations_online() -> None:
    """Run migrations in 'online' mode — connect to the database and apply
    or revert raw-SQL migration files from the versions directory.

    Supports both ``alembic upgrade head`` (apply pending migrations) and
    ``alembic downgrade -1`` (revert the most recent migration) by reading
    the command from ``context.config.cmd_opts`` and generating DROP statements
    for the downgrade path.
    """
    engine = create_engine(database_url)
    try:
        # Ensure the alembic_version bookkeeping table exists.
        with engine.connect() as connection:
            connection.execute(
                text("CREATE TABLE IF NOT EXISTS alembic_version " "(version_num VARCHAR(32) PRIMARY KEY)")
            )
            connection.execute(text("COMMIT"))
            applied = _applied_revisions(connection)

        cmd_name = context.config.cmd_opts.cmd[0].__name__

        if cmd_name == "downgrade":
            # Determine which revisions to revert.
            target_revs = _resolve_downgrade_target(context.config.cmd_opts.revision, applied)
            for rev_id in target_revs:
                p = next((f for f in _sql_files_in_order() if f.stem == rev_id), None)
                if p is None:
                    continue
                raw = p.read_text()
                stmts = _parse_sql_statements(raw)
                drops = _ddl_to_drops(stmts)
                with engine.connect() as conn:
                    conn.execute(text("BEGIN"))
                    for d in drops:
                        conn.execute(text(d))
                    conn.execute(
                        text("DELETE FROM alembic_version WHERE version_num = :v"),
                        {"v": rev_id},
                    )
                    conn.execute(text("COMMIT"))
            return

        # Default: upgrade — apply any pending migrations.
        for p in _sql_files_in_order():
            rev_id = p.stem
            if rev_id in applied:
                continue

            raw = p.read_text()
            stmts = _parse_sql_statements(raw)

            with engine.connect() as conn:
                conn.execute(text("BEGIN"))
                for stmt in stmts:
                    conn.execute(text(stmt))
                conn.execute(
                    text("INSERT INTO alembic_version (version_num) VALUES (:v)"),
                    {"v": rev_id},
                )
                conn.execute(text("COMMIT"))
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

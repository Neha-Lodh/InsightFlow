"""User accounts: SQLite storage with hashed passwords (no Flask dependency)."""
import os, re, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from werkzeug.security import check_password_hash, generate_password_hash

DB_PATH = Path(os.environ.get("INSIGHTFLOW_DB", Path(__file__).parent / "users.db"))
# On a host set DATABASE_URL (Supabase / Neon / any Postgres) so accounts survive redeploys.
# Without it, accounts are kept in a local SQLite file (fine for running on your own PC).
DATABASE_URL = (os.environ.get("DATABASE_URL") or "").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]
PG = bool(DATABASE_URL)
if PG:
    import psycopg2, psycopg2.extras
    INTEGRITY_ERRORS = (sqlite3.IntegrityError, psycopg2.IntegrityError)
else:
    INTEGRITY_ERRORS = (sqlite3.IntegrityError,)
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.]{3,30}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 8
# Used to spend the same time on unknown users as on real ones (prevents account probing).
_DUMMY_HASH = generate_password_hash("insightflow-dummy-password")
_ready = False


def _db():
    """Open a connection (creating the users table the first time)."""
    global _ready
    if PG:
        con = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        if not _ready:
            cur = con.cursor()
            cur.execute("""CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY, username TEXT NOT NULL, email TEXT NOT NULL,
                password_hash TEXT NOT NULL, created_at TEXT NOT NULL, last_login TEXT)""")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_username_lower ON users (lower(username))")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower ON users (lower(email))")
            con.commit(); _ready = True
        return con
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE COLLATE NOCASE,
        email TEXT NOT NULL UNIQUE COLLATE NOCASE,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        last_login TEXT)""")
    return con


def _q(con, sql, params=()):
    """Run a query on either database (write SQL with ? placeholders)."""
    if PG:
        cur = con.cursor(); cur.execute(sql.replace("?", "%s"), params); return cur
    return con.execute(sql, params)


def _public(row):
    return {"id": row["id"], "username": row["username"], "email": row["email"]} if row else None


def validate_registration(username, email, password, confirm=None):
    """Return a dict of {field: message}; empty when everything is valid."""
    errors = {}
    if not USERNAME_RE.match(username or ""):
        errors["username"] = "Username must be 3-30 characters: letters, numbers, dot or underscore."
    if not EMAIL_RE.match(email or "") or len(email) > 254:
        errors["email"] = "Enter a valid email address."
    pw = password or ""
    if len(pw) < MIN_PASSWORD:
        errors["password"] = f"Password must be at least {MIN_PASSWORD} characters."
    elif len(pw) > 128:
        errors["password"] = "Password must be at most 128 characters."
    elif pw.isdigit() or pw.isalpha():
        errors["password"] = "Use a mix of letters and numbers (or symbols)."
    if confirm is not None and confirm != password:
        errors["confirm"] = "Passwords do not match."
    return errors


def create_user(username, email, password):
    """Create an account. Returns (user, errors); errors is {} on success."""
    username, email = (username or "").strip(), (email or "").strip()
    errors = validate_registration(username, email, password)
    if errors:
        return None, errors
    con = _db()
    try:
        if _q(con, "SELECT 1 FROM users WHERE lower(username) = lower(?)", (username,)).fetchone():
            return None, {"username": "That username is already taken."}
        if _q(con, "SELECT 1 FROM users WHERE lower(email) = lower(?)", (email,)).fetchone():
            return None, {"email": "An account with that email already exists."}
        cur = _q(con, "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)" + (" RETURNING id" if PG else ""),
                 (username, email, generate_password_hash(password), datetime.now(timezone.utc).isoformat()))
        new_id = cur.fetchone()["id"] if PG else cur.lastrowid
        con.commit()
        return _public(_q(con, "SELECT * FROM users WHERE id = ?", (new_id,)).fetchone()), {}
    except INTEGRITY_ERRORS:  # two sign-ups racing for the same name/email
        con.rollback()
        return None, {"username": "That username or email is already registered."}
    finally:
        con.close()


def authenticate(identifier, password):
    """Check username-or-email + password. Returns the user dict or None."""
    identifier = (identifier or "").strip()
    con = _db()
    try:
        row = _q(con, "SELECT * FROM users WHERE lower(username) = lower(?) OR lower(email) = lower(?)", (identifier, identifier)).fetchone()
        ok = check_password_hash(row["password_hash"] if row else _DUMMY_HASH, password or "")
        if not (row and ok):
            return None
        _q(con, "UPDATE users SET last_login = ? WHERE id = ?", (datetime.now(timezone.utc).isoformat(), row["id"]))
        con.commit()
        return _public(row)
    finally:
        con.close()


def get_user(user_id):
    con = _db()
    try:
        return _public(_q(con, "SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())
    finally:
        con.close()
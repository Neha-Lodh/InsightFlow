"""User accounts: SQLite storage with hashed passwords (no Flask dependency)."""
import os, re, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from werkzeug.security import check_password_hash, generate_password_hash

DB_PATH = Path(os.environ.get("INSIGHTFLOW_DB", Path(__file__).parent / "users.db"))
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.]{3,30}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 8
# Used to spend the same time on unknown users as on real ones (prevents account probing).
_DUMMY_HASH = generate_password_hash("insightflow-dummy-password")


def _db():
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
        if con.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
            return None, {"username": "That username is already taken."}
        if con.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            return None, {"email": "An account with that email already exists."}
        cur = con.execute(
            "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (username, email, generate_password_hash(password), datetime.now(timezone.utc).isoformat()))
        con.commit()
        return _public(con.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()), {}
    except sqlite3.IntegrityError:  # two sign-ups racing for the same name/email
        return None, {"username": "That username or email is already registered."}
    finally:
        con.close()


def authenticate(identifier, password):
    """Check username-or-email + password. Returns the user dict or None."""
    identifier = (identifier or "").strip()
    con = _db()
    try:
        row = con.execute("SELECT * FROM users WHERE username = ? OR email = ?", (identifier, identifier)).fetchone()
        ok = check_password_hash(row["password_hash"] if row else _DUMMY_HASH, password or "")
        if not (row and ok):
            return None
        con.execute("UPDATE users SET last_login = ? WHERE id = ?", (datetime.now(timezone.utc).isoformat(), row["id"]))
        con.commit()
        return _public(row)
    finally:
        con.close()


def get_user(user_id):
    con = _db()
    try:
        return _public(con.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())
    finally:
        con.close()

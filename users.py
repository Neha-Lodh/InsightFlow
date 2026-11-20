"""Accounts database (SQLite). Passwords are hashed, never stored in plain text."""
import os, re, sqlite3
from pathlib import Path
from werkzeug.security import check_password_hash, generate_password_hash

DB_PATH = Path(os.environ.get("INSIGHTFLOW_DB", Path(__file__).parent / "users.db"))
USER_RE = re.compile(r"^[A-Za-z0-9_.]{3,30}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE COLLATE NOCASE,
        email TEXT NOT NULL UNIQUE COLLATE NOCASE,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    return c


def _public(row):
    return {"id": row["id"], "username": row["username"], "email": row["email"]} if row else None


def validate_registration(username, email, password, confirm):
    """Return {field: message}; empty dict means valid. Same rules as login.html."""
    e = {}
    if not USER_RE.match(username or ""):
        e["username"] = "3-30 characters: letters, numbers, dot or underscore."
    if not EMAIL_RE.match(email or ""):
        e["email"] = "Enter a valid email address."
    pw = password or ""
    if len(pw) < 8:
        e["password"] = "Password must be at least 8 characters."
    elif pw.isdigit() or pw.isalpha():
        e["password"] = "Use a mix of letters and numbers (or symbols)."
    if confirm != password:
        e["confirm"] = "Passwords do not match."
    return e


def create_user(username, email, password):
    """Return (user, errors). On success errors is {}."""
    username, email = (username or "").strip(), (email or "").strip()
    errs = validate_registration(username, email, password, password)
    if errs:
        return {}, errs
    with _conn() as c:
        if c.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            return {}, {"username": "That username is already taken."}
        if c.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            return {}, {"email": "An account with this email already exists."}
        cur = c.execute("INSERT INTO users(username,email,password_hash) VALUES(?,?,?)",
                        (username, email, generate_password_hash(password)))
        row = c.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
    return _public(row), {}


def authenticate(identifier, password):
    """Username or email + password -> user dict, or None."""
    ident = (identifier or "").strip()
    if not ident or not password:
        return None
    with _conn() as c:
        row = c.execute("SELECT * FROM users WHERE username=? OR email=?", (ident, ident)).fetchone()
    return _public(row) if row and check_password_hash(row["password_hash"], password) else None


def get_user(user_id):
    with _conn() as c:
        return _public(c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())

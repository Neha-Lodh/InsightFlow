"""Login, logout, registration routes + login_required decorator for the Flask app."""
import os, secrets, time
from functools import wraps
from pathlib import Path
from flask import Blueprint, jsonify, redirect, request, send_file, session, url_for
import users

bp = Blueprint("auth", __name__)
HERE = Path(__file__).parent
_FAILS = {}  # ip -> (count, first_time): simple brute-force throttle
MAX_FAILS, WINDOW = 8, 300


def load_secret_key():
    env = os.environ.get("SECRET_KEY")
    if env:
        return env
    f = HERE / ".secret_key"
    if f.exists() and f.read_text().strip():
        return f.read_text().strip()
    key = secrets.token_hex(32)
    try:
        f.write_text(key)
    except OSError:
        pass  # read-only disk: key lasts for this process only
    return key


def current_user():
    uid = session.get("uid")
    return users.get_user(uid) if uid else None


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if current_user():
            return fn(*a, **kw)
        if request.path.startswith("/api/"):
            return jsonify(error="Please sign in."), 401
        nxt = request.full_path.rstrip("?")
        return redirect(url_for("auth.login_page", next=nxt) if nxt != "/" else url_for("auth.login_page"))
    return wrapper


def _start(user, remember):
    session.clear()
    session["uid"] = user["id"]
    session.permanent = bool(remember)


def _throttled():
    n, t0 = _FAILS.get(request.remote_addr, (0, time.time()))
    if time.time() - t0 > WINDOW:
        _FAILS.pop(request.remote_addr, None)
        return False
    return n >= MAX_FAILS


@bp.get("/login")
def login_page():
    if current_user():
        return redirect("/")
    r = send_file(HERE / "login.html")
    r.headers["Cache-Control"] = "no-store"
    return r


@bp.post("/api/login")
def login():
    d = request.get_json(silent=True) or {}
    if _throttled():
        return jsonify(error="Too many attempts. Please wait a few minutes."), 429
    u = users.authenticate(d.get("identifier"), d.get("password"))
    if not u:
        n, t0 = _FAILS.get(request.remote_addr, (0, time.time()))
        _FAILS[request.remote_addr] = (n + 1, t0)
        return jsonify(error="Incorrect username/email or password."), 401
    _FAILS.pop(request.remote_addr, None)
    _start(u, d.get("remember"))
    return jsonify(user=u)


@bp.post("/api/register")
def register():
    d = request.get_json(silent=True) or {}
    errs = users.validate_registration((d.get("username") or "").strip(), (d.get("email") or "").strip(),
                                       d.get("password"), d.get("confirm"))
    if errs:
        return jsonify(error="Please fix the highlighted fields.", fields=errs), 400
    u, errs = users.create_user(d["username"], d["email"], d["password"])
    if errs:
        return jsonify(error="Please fix the highlighted fields.", fields=errs), 400
    _start(u, True)
    return jsonify(user=u), 201


@bp.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@bp.get("/api/me")
def me():
    u = current_user()
    return (jsonify(user=u), 200) if u else (jsonify(error="Please sign in."), 401)

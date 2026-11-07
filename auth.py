"""Flask authentication: /api/register, /api/login, /api/logout, /api/me."""
import os, secrets, time
from collections import defaultdict, deque
from functools import wraps
from pathlib import Path
from flask import Blueprint, jsonify, redirect, request, send_file, session, url_for
import users

bp = Blueprint("auth", __name__)
HERE = Path(__file__).parent


def load_secret_key():
    """SECRET_KEY env var on a host; otherwise a random key saved to .secret_key so local logins survive restarts."""
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    f = HERE / ".secret_key"
    if not f.exists():
        f.write_text(secrets.token_hex(32))
    return f.read_text().strip()


# ---- simple in-memory throttle (per process): 8 failed logins / 5 min, 10 sign-ups / hour per IP ----
_fails, _signups = defaultdict(deque), defaultdict(deque)


def _recent(q, window):
    now = time.time()
    while q and now - q[0] > window:
        q.popleft()
    return q


def _client_ip():
    return (request.headers.get("X-Forwarded-For", request.remote_addr) or "?").split(",")[0].strip()


def current_user():
    uid = session.get("uid")
    return users.get_user(uid) if uid else None


def login_required(view):
    """Pages redirect to /login; /api/* calls get a 401 JSON error."""
    @wraps(view)
    def wrapped(*a, **kw):
        if current_user() is None:
            if request.path.startswith("/api/"):
                return jsonify(error="Please log in first."), 401
            return redirect(url_for("auth.login_page"))
        return view(*a, **kw)
    return wrapped


def _start_session(user, remember):
    session.clear()  # drop any old session data (prevents session fixation)
    session["uid"] = user["id"]
    session.permanent = bool(remember)


def _json():
    # JSON-only endpoints: a cross-site <form> cannot send this content type, which blocks CSRF.
    if not request.is_json:
        return None
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


@bp.get("/login")
def login_page():
    if current_user():
        return redirect("/")
    r = send_file(HERE / "login.html")
    r.headers["Cache-Control"] = "no-store"
    return r


@bp.post("/api/register")
def register():
    data = _json()
    if data is None:
        return jsonify(error="Invalid request."), 400
    ip = _client_ip()
    if len(_recent(_signups[ip], 3600)) >= 10:
        return jsonify(error="Too many sign-ups from this network. Try again later."), 429
    errors = users.validate_registration(data.get("username"), data.get("email"), data.get("password"), data.get("confirm"))
    if errors:
        return jsonify(error=next(iter(errors.values())), fields=errors), 400
    user, errors = users.create_user(data.get("username"), data.get("email"), data.get("password"))
    if errors:
        return jsonify(error=next(iter(errors.values())), fields=errors), 409
    _signups[ip].append(time.time())
    _start_session(user, remember=True)  # new accounts are signed in straight away
    return jsonify(user=user), 201


@bp.post("/api/login")
def login():
    data = _json()
    if data is None:
        return jsonify(error="Invalid request."), 400
    ident = str(data.get("identifier") or "").strip().lower()
    key = (_client_ip(), ident)
    if len(_recent(_fails[key], 300)) >= 8:
        return jsonify(error="Too many failed attempts. Please wait a few minutes and try again."), 429
    user = users.authenticate(data.get("identifier"), data.get("password"))
    if not user:
        _fails[key].append(time.time())
        return jsonify(error="Incorrect username/email or password."), 401
    _fails.pop(key, None)
    _start_session(user, remember=data.get("remember"))
    return jsonify(user=user)


@bp.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@bp.get("/api/me")
def me():
    user = current_user()
    if not user:
        return jsonify(error="Not logged in."), 401
    return jsonify(user=user)

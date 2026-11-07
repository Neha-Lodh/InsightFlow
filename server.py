"""Run: python server.py   then open http://localhost:5000"""
import io, json, os
from pathlib import Path
import pandas as pd
from datetime import timedelta
from flask import Flask, jsonify, request, send_file, send_from_directory
import auth

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
HERE = Path(__file__).parent

# --- accounts / sessions ---
app.config.update(
    SECRET_KEY=auth.load_secret_key(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.environ.get("PORT")),  # hosted = HTTPS; local http://localhost keeps working
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),        # used when "Remember me" is ticked
)
app.register_blueprint(auth.bp)

@app.get("/assets/<path:name>")
def assets(name):  # public: the login page needs the logo
    return send_from_directory(HERE / "assets", name)

@app.get("/")
@auth.login_required
def index():
    r = send_file(HERE / "insightflow_ui.html")
    r.headers["Cache-Control"] = "no-store"  # always load the newest page
    return r

@app.post("/api/excel")
@auth.login_required
def excel():
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith((".xlsx", ".xls")):
        return jsonify(error="Please upload a .xlsx or .xls file."), 400
    try:
        df = pd.read_excel(io.BytesIO(f.read()))
    except Exception as e:
        return jsonify(error=f"Could not read the Excel file: {e}"), 400
    if df.empty:
        return jsonify(error="The first sheet has no data."), 400
    return jsonify(rows=json.loads(df.to_json(orient="records", date_format="iso")))

@app.errorhandler(413)
def too_big(_):
    return jsonify(error="File exceeds the 20 MB limit."), 413

if __name__ == "__main__":
    print("InsightFlow running at http://localhost:5000")
    # On your PC it listens only on this computer; on a host (PORT is set) it listens publicly.
    app.run(host="0.0.0.0" if os.environ.get("PORT") else "127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=False)

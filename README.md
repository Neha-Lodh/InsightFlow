# InsightFlow: AI Data Analyst
Upload -> Analyze -> Visualize -> Report

## Run (recommended: the web app)
    python -m venv venv
    venv\Scripts\activate            (Windows)   |   source venv/bin/activate  (Mac/Linux)
    python -m pip install -r requirements.txt
    python server.py
Open http://localhost:5000  (Excel .xlsx/.xls files are read by the Python server; CSV, JSON and TXT work in the browser).

## Accounts (login / registration)
The first time you open the app you are sent to a sign-in page. Click **Create account** to register
(username, email, password of 8+ characters with letters and numbers), then use **Log out** (top bar or Settings) to sign out.
Accounts are stored in a local SQLite file (`users.db`, passwords are hashed - never stored in plain text).
On a host set a `SECRET_KEY` environment variable (any long random string); locally one is generated for you in `.secret_key`.
Optional: `INSIGHTFLOW_DB` changes where the accounts file is stored. Free hosts such as Render wipe local files on redeploy,
so attach a persistent disk (or point `INSIGHTFLOW_DB` at one) if you need accounts to survive deployments.

## Alternative: Streamlit version
    python -m streamlit run app.py

## Deploy online
Upload the folder to GitHub (without venv), then create a Render web service:
build `pip install -r requirements-deploy.txt`, start `gunicorn server:app`.

## Files
- insightflow_ui.html  web interface (dashboard, 17 chart types, palettes, questions, reports)
- server.py            Flask server: serves the interface and reads Excel files
- login.html           sign-in / create-account page   |   auth.py, users.py: login, logout, registration, accounts database
- core.py / app.py     Python analysis engine and Streamlit interface
- assets/              logo files   |   make_sample.py, sample_sales.csv: sample data
Optional: set ANTHROPIC_API_KEY to let an LLM interpret questions (Streamlit version). No generated code is ever executed.

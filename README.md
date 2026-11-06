# InsightFlow: AI Data Analyst
Upload -> Analyze -> Visualize -> Report

## Run (recommended: the web app)
    python -m venv venv
    venv\Scripts\activate            (Windows)   |   source venv/bin/activate  (Mac/Linux)
    python -m pip install -r requirements.txt
    python server.py
Open http://localhost:5000  (Excel .xlsx/.xls files are read by the Python server; CSV, JSON and TXT work in the browser).

## Alternative: Streamlit version
    python -m streamlit run app.py

## Deploy online
Upload the folder to GitHub (without venv), then create a Render web service:
build `pip install -r requirements-deploy.txt`, start `gunicorn server:app`.

## Files
- insightflow_ui.html  web interface (dashboard, 17 chart types, palettes, questions, reports)
- server.py            Flask server: serves the interface and reads Excel files
- core.py / app.py     Python analysis engine and Streamlit interface
- assets/              logo files   |   make_sample.py, sample_sales.csv: sample data
Optional: set ANTHROPIC_API_KEY to let an LLM interpret questions (Streamlit version). No generated code is ever executed.

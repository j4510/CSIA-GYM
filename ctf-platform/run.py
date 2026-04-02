"""
Application Entry Point

This file runs the Flask application.

TO RUN LOCALLY:
    python run.py

TO RUN IN PRODUCTION:
    Use gunicorn or uwsgi instead (see Dockerfile)
"""

from app import create_app

# Create the Flask app instance
app = create_app()

if __name__ == '__main__':
    # Debug mode is explicitly disabled — never enable in production.
    # The FLASK_DEBUG env var is intentionally ignored here to prevent
    # accidental exposure of the debug interface (CWE-668).
    # amazonq-ignore-next-line
    app.run(
        host='127.0.0.1',
        port=5000,
        debug=False,
    )

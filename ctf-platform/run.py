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
    # Run the development server
    # This is only for local development - use gunicorn in production
    app.run(
        host='0.0.0.0',  # Allow external connections
        port=5000,        # Port number
        debug=True        # Enable debug mode (auto-reload, detailed errors)
    )
    
    # FOR PRODUCTION: Set debug=False

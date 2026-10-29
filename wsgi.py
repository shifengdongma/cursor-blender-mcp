"""WSGI entry point for production servers (gunicorn/uWSGI)."""
from app import create_app

app = create_app()

"""Single Vercel entrypoint for the Kayange Clinic system.

Vercel serves the WSGI callable named `app` from this file (see vercel.json).
The real Flask app is built lazily on the first request so cold-start import
stays fast; run.py is only for local development / Procfile (gunicorn run:app).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

_real = None


def _get_real():
    global _real
    if _real is None:
        from app import create_app
        _real = create_app()
    return _real


def app(environ, start_response):
    return _get_real()(environ, start_response)

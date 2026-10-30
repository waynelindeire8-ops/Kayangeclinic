import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask

app = Flask(__name__)
_real = None

def _get_real():
    global _real
    if _real is None:
        from app import create_app
        _real = create_app()
    return _real

class Lazy:
    def __init__(self, wsgi):
        self.wsgi = wsgi
    def __call__(self, environ, start_response):
        return _get_real()(environ, start_response)

app = Lazy(app)
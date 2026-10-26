import sys
import os
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

_flask_app = None
_startup_error = None

try:
    from app import create_app
    _flask_app = create_app()
except Exception:
    _startup_error = traceback.format_exc().encode()


def _application(environ, start_response):
    if _startup_error is not None:
        start_response('500 Internal Server Error',
                       [('Content-Type', 'text/plain; charset=utf-8')])
        return [_startup_error]
    try:
        return _flask_app(environ, start_response)
    except Exception:
        start_response('500 Internal Server Error',
                       [('Content-Type', 'text/plain; charset=utf-8')])
        return [traceback.format_exc().encode()]


app = _application
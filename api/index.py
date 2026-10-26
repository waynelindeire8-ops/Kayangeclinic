import sys
import os
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from app import create_app
    _flask_app = create_app()

    def app(environ, start_response):
        try:
            return _flask_app(environ, start_response)
        except Exception:
            body = traceback.format_exc().encode()
            start_response('500 Internal Server Error',
                           [('Content-Type', 'text/plain; charset=utf-8')])
            return [body]
except Exception:
    _tb = traceback.format_exc().encode()

    def app(environ, start_response):
        start_response('500 Internal Server Error',
                       [('Content-Type', 'text/plain; charset=utf-8')])
        return [_tb]
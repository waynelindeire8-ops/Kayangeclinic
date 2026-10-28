import sys
import os
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from app import create_app
    app = create_app()
except BaseException:
    err = traceback.format_exc()
    try:
        from flask import Flask
        app = Flask(__name__)

        @app.route("/", defaults={"path": ""})
        @app.route("/<path:path>")
        def boot_error(path):
            return f"<pre>{err}</pre>", 500
    except BaseException:
        def app(environ, start_response):
            start_response("500 ERROR", [("Content-Type", "text/plain")])
            return [err.encode()]
import traceback

try:
    from run import app
except Exception:
    err = traceback.format_exc()
    from flask import Flask
    app = Flask(__name__)

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def boot_error(path):
        return f"<pre>{err}</pre>", 500
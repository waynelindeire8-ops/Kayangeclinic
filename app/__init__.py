from flask import Flask, render_template, redirect
from flask_jwt_extended import JWTManager
from config import Config
import os, logging

jwt = JWTManager()
logger = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    jwt.init_app(app)

    from app.database import init_db
    init_db()

    # Vercel: restore from Supabase on cold start (ephemeral storage)
    if os.environ.get('VERCEL'):
        try:
            from app.backup import init_supabase_tables, restore_all, HAS_PG
            if HAS_PG:
                logger.info("Vercel: Initializing Supabase tables...")
                init_supabase_tables()
                logger.info("Vercel: Restoring data from Supabase...")
                results = restore_all()
                total = sum(v for v in results.values() if v > 0)
                logger.info(f"Vercel: Restored {total} rows from Supabase")
        except Exception as e:
            logger.error(f"Vercel restore failed: {e}")

    # Local: initial sync to Supabase on startup (backup local data)
    elif not os.environ.get('VERCEL'):
        try:
            from app.backup import sync_all, HAS_PG
            if HAS_PG:
                logger.info("Running initial backup sync to Supabase...")
                results = sync_all()
                synced = sum(v for v in results.values() if v > 0)
                logger.info(f"Initial backup sync complete: {synced} rows")
        except Exception as e:
            logger.warning(f"Initial backup sync failed: {e}")

    # Start background auto-sync (pushes SQLite to Supabase periodically)
    try:
        from app.backup import start_auto_sync
        start_auto_sync(app)
    except Exception as e:
        logger.warning(f"Auto-sync failed to start: {e}")

    @app.route('/help')
    def help_page():
        return render_template('help.html')

    @app.route('/')
    def index():
        return redirect('/dashboard')

    @app.route('/dashboard')
    def dashboard():
        return render_template('dashboard.html')

    return app

from urllib.parse import quote_plus
import os
import time

# Set Malawi time (CAT, UTC+2) for all datetime.now() / date.today() calls
os.environ['TZ'] = 'Africa/Blantyre'
try:
    time.tzset()
except AttributeError:
    pass  # Windows compat

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'kayange-secret-key-change-in-production')
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'kayange-jwt-secret-change-in-production')
    JWT_ACCESS_TOKEN_EXPIRES = 36000
    JWT_TOKEN_LOCATION = ['headers', 'cookies']
    JWT_COOKIE_CSRF_PROTECT = False
    JWT_ACCESS_COOKIE_NAME = 'access_token'
    JWT_COOKIE_SECURE = False
    JWT_COOKIE_SAMESITE = 'Lax'
    CALL_OUT_FEE = 20000
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads/patient_documents')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024

    if os.environ.get('VERCEL') or os.environ.get('RENDER'):
        DATABASE = '/tmp/kayange.db'
    else:
        DATABASE = os.path.join(BASE_DIR, 'kayange.db')

    DEBUG = not bool(os.environ.get('VERCEL') or os.environ.get('RENDER'))

    SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://xozdmkpkxholhukblfuv.supabase.co')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'sb_publishable_V2HZQ5gjJ0Nb7qmh9Pxziw__cR1DpWB')

    # Supabase Postgres. No credentials are hardcoded: set these as environment
    # variables / secrets (e.g. `fly secrets set ...`). If nothing is set, the
    # backup code refuses to connect instead of hammering the pooler with a bad
    # password (which triggers ECIRCUITBREAKER).
    SUPABASE_DB_HOST = os.environ.get('SUPABASE_DB_HOST', 'aws-0-eu-central-1.pooler.supabase.com')
    SUPABASE_DB_PORT = os.environ.get('SUPABASE_DB_PORT', '6543')
    SUPABASE_DB_USER = os.environ.get('SUPABASE_DB_USER', 'postgres.xozdmkpkxholhukblfuv')
    SUPABASE_DB_PASSWORD = os.environ.get('SUPABASE_DB_PASSWORD', '')
    SUPABASE_DB_URL = os.environ.get('SUPABASE_DB_URL') or (
        'postgresql://%s:%s@%s:%s/postgres?sslmode=require' % (
            quote_plus(SUPABASE_DB_USER), quote_plus(SUPABASE_DB_PASSWORD),
            SUPABASE_DB_HOST, SUPABASE_DB_PORT)
        if SUPABASE_DB_PASSWORD else ''
    )

    # OneDrive / Microsoft Graph
    ONEDRIVE_CLIENT_ID = os.environ.get('ONEDRIVE_CLIENT_ID', '')
    ONEDRIVE_CLIENT_SECRET = os.environ.get('ONEDRIVE_CLIENT_SECRET', '')
    ONEDRIVE_TENANT_ID = os.environ.get('ONEDRIVE_TENANT_ID', 'common')
    ONEDRIVE_REFRESH_TOKEN = os.environ.get('ONEDRIVE_REFRESH_TOKEN', '')
    ONEDRIVE_USER_EMAIL = os.environ.get('ONEDRIVE_USER_EMAIL', 'deannemolina159@gmail.com')
    ONEDRIVE_BACKUP_FOLDER = os.environ.get('ONEDRIVE_BACKUP_FOLDER', '/Kayange Clinic Backups')

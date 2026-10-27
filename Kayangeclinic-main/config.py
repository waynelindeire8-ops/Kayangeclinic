import os
import time

# Set Malawi time (CAT, UTC+2) for all datetime.now() / date.today() calls
os.environ['TZ'] = 'Africa/Blantyre'
try:
    time.tzset()
except AttributeError:
    pass  # Windows compat

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _neon_url():
    """Neon connection string from env (NEON_DATABASE_URL, falling back to DATABASE_URL).
    Always forces sslmode=require, which Neon needs."""
    url = (os.environ.get('NEON_DATABASE_URL') or os.environ.get('DATABASE_URL') or '').strip()
    if url.startswith('postgres://'):
        url = 'postgresql://' + url[len('postgres://'):]
    if url and 'sslmode=' not in url:
        url += ('&' if '?' in url else '?') + 'sslmode=require'
    return url



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

    # Neon Postgres. No credentials are hardcoded: set NEON_DATABASE_URL (or
    # DATABASE_URL) as an environment variable / secret, e.g.
    #   fly secrets set NEON_DATABASE_URL="postgresql://user:pass@ep-xxx-pooler.region.aws.neon.tech/neondb?sslmode=require"
    # If nothing is set, the sync code refuses to connect.
    NEON_DATABASE_URL = _neon_url()

    # OneDrive / Microsoft Graph
    ONEDRIVE_CLIENT_ID = os.environ.get('ONEDRIVE_CLIENT_ID', '')
    ONEDRIVE_CLIENT_SECRET = os.environ.get('ONEDRIVE_CLIENT_SECRET', '')
    ONEDRIVE_TENANT_ID = os.environ.get('ONEDRIVE_TENANT_ID', 'common')
    ONEDRIVE_REFRESH_TOKEN = os.environ.get('ONEDRIVE_REFRESH_TOKEN', '')
    ONEDRIVE_USER_EMAIL = os.environ.get('ONEDRIVE_USER_EMAIL', 'deannemolina159@gmail.com')
    ONEDRIVE_BACKUP_FOLDER = os.environ.get('ONEDRIVE_BACKUP_FOLDER', '/Kayange Clinic Backups')

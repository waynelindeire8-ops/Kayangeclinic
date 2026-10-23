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

    # Neon Postgres connection string; configure NEON_DATABASE_URL in the
    # deployment environment. DATABASE_URL is retained as a generic fallback.
    NEON_DATABASE_URL = (os.environ.get('NEON_DATABASE_URL') or os.environ.get('DATABASE_URL') or '').strip()
    if NEON_DATABASE_URL.startswith('postgres://'):
        NEON_DATABASE_URL = 'postgresql://' + NEON_DATABASE_URL[len('postgres://'):]
    if NEON_DATABASE_URL and 'sslmode=' not in NEON_DATABASE_URL:
        NEON_DATABASE_URL += ('&' if '?' in NEON_DATABASE_URL else '?') + 'sslmode=require'

    # OneDrive / Microsoft Graph
    ONEDRIVE_CLIENT_ID = os.environ.get('ONEDRIVE_CLIENT_ID', '')
    ONEDRIVE_CLIENT_SECRET = os.environ.get('ONEDRIVE_CLIENT_SECRET', '')
    ONEDRIVE_TENANT_ID = os.environ.get('ONEDRIVE_TENANT_ID', 'common')
    ONEDRIVE_REFRESH_TOKEN = os.environ.get('ONEDRIVE_REFRESH_TOKEN', '')
    ONEDRIVE_USER_EMAIL = os.environ.get('ONEDRIVE_USER_EMAIL', 'deannemolina159@gmail.com')
    ONEDRIVE_BACKUP_FOLDER = os.environ.get('ONEDRIVE_BACKUP_FOLDER', '/Kayange Clinic Backups')

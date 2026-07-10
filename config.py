import os

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

    if os.environ.get('VERCEL'):
        DATABASE = '/tmp/kayange.db'
    else:
        DATABASE = os.path.join(BASE_DIR, 'kayange.db')

    DEBUG = not bool(os.environ.get('VERCEL'))

    SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://xozdmkpkxholhukblfuv.supabase.co')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'sb_publishable_V2HZQ5gjJ0Nb7qmh9Pxziw__cR1DpWB')
    SUPABASE_DB_URL = os.environ.get(
        'SUPABASE_DB_URL',
        'postgresql://postgres:[himjim@1234@]@db.xozdmkpkxholhukblfuv.supabase.co:5432/postgres'
    )

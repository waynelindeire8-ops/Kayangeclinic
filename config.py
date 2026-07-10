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

    SUPABASE_DB_URL = os.environ.get('SUPABASE_DB_URL',
        'postgresql://postgres.xozdmkpkxholhukblfuv:himjim%401234%40@aws-0-eu-central-1.pooler.supabase.com:6543/postgres?sslmode=require'
    )
    SUPABASE_DB_HOST = os.environ.get('SUPABASE_DB_HOST', 'aws-0-eu-central-1.pooler.supabase.com')
    SUPABASE_DB_PORT = os.environ.get('SUPABASE_DB_PORT', '6543')
    SUPABASE_DB_USER = os.environ.get('SUPABASE_DB_USER', 'postgres.xozdmkpkxholhukblfuv')
    SUPABASE_DB_PASSWORD = os.environ.get('SUPABASE_DB_PASSWORD', 'himjim@1234@')

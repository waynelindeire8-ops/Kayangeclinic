import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'kayange-secret-key-change-in-production')
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'kayange-jwt-secret-change-in-production')
    JWT_ACCESS_TOKEN_EXPIRES = 36000
    DATABASE = os.path.join(BASE_DIR, 'kayange.db')
    DEBUG = True

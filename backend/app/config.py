import os
from datetime import timedelta


def _ensure_psycopg2_scheme(url: str | None) -> str | None:
    if not url:
        return url
    if url.startswith('postgres://'):
        return url.replace('postgres://', 'postgresql+psycopg2://', 1)
    if url.startswith('postgresql://'):
        return url.replace('postgresql://', 'postgresql+psycopg2://', 1)
    return url


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-prod')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'jwt-secret-key-change-in-prod')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=8)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads', 'announcements')
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024
    ALLOWED_MIME_TYPES = {
        'application/pdf',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'image/jpeg',
        'image/png',
        'text/plain',
    }


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = _ensure_psycopg2_scheme(os.getenv('DATABASE_URL', 'sqlite:///dev.db'))


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = _ensure_psycopg2_scheme(os.getenv('DATABASE_URL'))


_config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
}


def get_config(env=None):
    env = env or os.getenv('FLASK_ENV', 'development')
    return _config_map.get(env, DevelopmentConfig)

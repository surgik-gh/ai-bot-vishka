import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///ai_bot.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Session settings
    SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 86400  # 24 hours
    
    # GigaChat API (Сбер) - для текстовых запросов
    GIGA_API_KEY = os.environ.get('GIGA_API_KEY') or ''
    GIGA_AUTH_URL = os.environ.get('GIGA_AUTH_URL') or 'https://ngw.devices.sberbank.ru:9443/api/v2/oauth'
    GIGA_CHAT_URL = os.environ.get('GIGA_CHAT_URL') or 'https://gigachat.devices.sberbank.ru/api/v1/chat/completions'
    
    # Kandinsky API (Сбер) - для генерации изображений
    KANDINSKY_API_KEY = os.environ.get('KANDINSKY_API_KEY') or ''
    KANDINSKY_SECRET_KEY = os.environ.get('KANDINSKY_SECRET_KEY') or ''
    KANDINSKY_URL = os.environ.get('KANDINSKY_URL') or 'https://api-key.fusionbrain.ai/key/api/v1/text2image/run'
    KANDINSKY_STATUS_URL = os.environ.get('KANDINSKY_STATUS_URL') or 'https://api-key.fusionbrain.ai/key/api/v1/text2image/status'
    
    # Token settings
    INITIAL_TOKENS = 100
    DAILY_TOKENS = 20
    LESSON_COST = 10
    CORRECT_ANSWER_REWARD = 2
    WRONG_ANSWER_REWARD = 0
    
    # Upload settings
    UPLOAD_FOLDER = 'uploads'
    MAX_UPLOAD_SIZE = 16 * 1024 * 1024  # 16MB
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'svg', 'pdf'}
    
    # OAuth settings
    VK_APP_ID = os.environ.get('VK_APP_ID') or ''
    VK_APP_SECRET = os.environ.get('VK_APP_SECRET') or ''
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID') or ''
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET') or ''
    
    # Email verification
    VERIFICATION_CODE_EXPIRY = 10  # minutes
    
    # Email settings
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.gmail.com'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'false').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME') or ''
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD') or ''
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or MAIL_USERNAME
    MAIL_ASCII_ATTACHMENTS = False  # Поддержка UTF-8 в именах файлов


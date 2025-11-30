import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-secret-key-change-in-production"
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or "sqlite:///ai_bot.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Session settings
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() in ["true", "on", "1"]  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"  # Changed to Lax for GitHub Pages compatibility
    PERMANENT_SESSION_LIFETIME = 3600  # 1 hour

    # OpenRouter API - жестко заданный ключ
    OPENROUTER_API_KEY = "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"
    OPENROUTER_MODEL = "x-ai/grok-4.1-fast:free"

    # Token settings
    INITIAL_TOKENS = 100
    DAILY_TOKENS = 20
    LESSON_COST = 10
    CORRECT_ANSWER_REWARD = 2
    WRONG_ANSWER_REWARD = 0
    EXPERT_CHAT_COST = 2

    # Upload settings
    UPLOAD_FOLDER = "uploads"
    MAX_UPLOAD_SIZE = 16 * 1024 * 1024  # 16MB
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "svg", "pdf"}

    # OAuth settings
    GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID") or ""
    GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET") or ""
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID") or ""
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET") or ""

    # Email verification
    VERIFICATION_CODE_EXPIRY = 10  # minutes

    # Email settings
    MAIL_SERVER = os.environ.get("MAIL_SERVER") or "smtp.gmail.com"
    MAIL_PORT = int(os.environ.get("MAIL_PORT") or 587)
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() in ["true", "on", "1"]
    MAIL_USE_SSL = os.environ.get("MAIL_USE_SSL", "false").lower() in [
        "true",
        "on",
        "1",
    ]
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME") or ""
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD") or ""
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER") or MAIL_USERNAME
    MAIL_ASCII_ATTACHMENTS = False  # Support UTF-8 in filenames

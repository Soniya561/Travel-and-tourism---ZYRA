import os

class Config:
    # Change this in production, or set via environment variable
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")

    # Default: local SQLite DB. Override with DATABASE_URL env var.
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///app.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Flask-Limiter storage; memory is fine for dev
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")

    # Session cookie settings (tweak for production)
    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_HTTPONLY = True

    # Stripe
    STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "sk_test_...")  # Replace with actual test key

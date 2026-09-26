import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL

BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(BACKEND_DIR / ".env", override=False)


class Settings:
    DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
    DB_USER = os.getenv("DB_USER", "trashbox")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "trashbox")
    DB_PORT = int(os.getenv("DB_PORT", "5432"))

    @property
    def DATABASE_URI(self):
        override = os.getenv("DATABASE_URI")
        if override:
            return override
        return URL.create(
            "postgresql+psycopg2",
            username=self.DB_USER,
            password=self.DB_PASSWORD,
            host=self.DB_HOST,
            port=self.DB_PORT,
            database=self.DB_NAME,
        )

    WX_APP_ID = os.getenv("WX_APP_ID")
    WX_APP_SECRET = os.getenv("WX_APP_SECRET")
    BASE_URL = os.getenv("BASE_URL")

    UPLOAD_DIR = os.getenv("UPLOAD_DIR", str(BACKEND_DIR / "assets" / "posts"))
    IMG_DOMAIN = os.getenv("IMG_DOMAIN", "https://trashbox.tech")
    IMG_URL_PREFIX = "/assets/posts"

    STEAM_API_KEY = os.getenv("STEAM_API_KEY")

    JWT_SECRET = os.getenv("JWT_SECRET", "")
    JWT_TTL_SECONDS = int(os.getenv("JWT_TTL_SECONDS", 86400))
    WEB_ORIGIN = os.getenv("WEB_ORIGIN", "http://localhost:5174/radar").rstrip("/")
    RADAR_SCAN_INTERVAL_SECONDS = int(os.getenv("RADAR_SCAN_INTERVAL_SECONDS", 20))
    RADAR_SESSION_SECONDS = int(os.getenv("RADAR_SESSION_SECONDS", 600))


settings = Settings()

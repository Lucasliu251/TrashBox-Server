import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

class Settings:
    # 数据库
    DB_HOST = os.getenv("DB_HOST")
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_NAME = os.getenv("DB_NAME")
    DB_PORT = int(os.getenv("DB_PORT", 3306))

    # 微信
    WX_APP_ID = os.getenv("WX_APP_ID")
    WX_APP_SECRET = os.getenv("WX_APP_SECRET")

settings = Settings()
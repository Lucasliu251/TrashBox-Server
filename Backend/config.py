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

    # 域名
    BASE_URL = os.getenv("BASE_URL")

    # --- 文件存储配置 (新增) ---
    # 你的物理存储路径
    UPLOAD_DIR = "C:/Users/Administrator/Desktop/TrashBox/assets/posts"
    
    # 图片访问域名 (配合 Nginx/IIS 映射)
    # 假设你的 Nginx 把 /static/posts/ 映射到了上面的文件夹
    IMG_DOMAIN = "https://trashbox.tech" 
    IMG_URL_PREFIX = "/assets/posts"

settings = Settings()
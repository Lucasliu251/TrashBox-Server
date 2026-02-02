# database.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import pymysql
from config import settings

# 创建数据库连接配置
db_config = {
    'host': settings.DB_HOST,
    'user': settings.DB_USER,
    'password': settings.DB_PASSWORD,
    'database': settings.DB_NAME,
    'port': settings.DB_PORT,
    'cursorclass': pymysql.cursors.DictCursor,
    'autocommit': True
}
DB_URI = f"mysql+pymysql://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}?charset=utf8mb4"

# pool_recycle=3600 防止 MySQL 8小时断连问题
engine = create_engine(
    DB_URI, 
    pool_size=10, 
    max_overflow=20,
    pool_recycle=3600
)

# 这是一个依赖函数
# 任何 API 路由只要在参数里写了 db = Depends(get_db_connection)
# FastAPI 就会自动运行这个函数，把连接给它，用完自动关闭
def get_db_connection():
    connection = engine.connect()
    try:
        yield connection
    finally:
        connection.close()
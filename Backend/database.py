# database.py
from sqlalchemy import create_engine
from config import settings

# 本机 PostgreSQL；连接串由 config 从 .env 组装
DB_URI = settings.DATABASE_URI

# pool_recycle 回收空闲连接，避免被服务端断开后复用
engine = create_engine(
    DB_URI,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
)

# 这是一个依赖函数
# 任何 API 路由只要在参数里写了 db = Depends(get_db_connection)
# FastAPI 就会自动运行这个函数，把连接给它，用完自动关闭
def get_db_connection():
    """向 FastAPI / 脚本提供一条 SQLAlchemy 连接，用完关闭。

    @returns: 生成器，yield Connection
    @changelog
    - 2026-08-22: MySQL/pymysql 改为 PostgreSQL/psycopg2 (Author: KBot)
    """
    connection = engine.connect()
    try:
        yield connection
    finally:
        connection.close()

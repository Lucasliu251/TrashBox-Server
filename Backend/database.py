# database.py
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

# 这是一个依赖函数
# 任何 API 路由只要在参数里写了 db = Depends(get_db_connection)
# FastAPI 就会自动运行这个函数，把连接给它，用完自动关闭
def get_db_connection():
    connection = pymysql.connect(**db_config)
    try:
        yield connection  # 把连接给路由使用
    finally:
        connection.close() # 路由跑完了，这里自动关闭连接
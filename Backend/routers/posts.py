from fastapi import APIRouter, Depends, HTTPException, Body
from database import get_db_connection
from pydantic import BaseModel
import pymysql

router = APIRouter(prefix="/api/v1/posts", tags=["posts"])

# 定义接收前端数据的模型
class PostCreate(BaseModel):
    openid: str
    title: str
    content: str
    tag: str = "讨论"

# 1. 发布文章接口
@router.post("/")
async def create_post(post: PostCreate, db=Depends(get_db_connection)):
    try:
        with db.cursor() as cursor:
            # 插入文章
            sql = "INSERT INTO posts (uuid, title, content, tag) VALUES (%s, %s, %s, %s)"
            cursor.execute(sql, (post.openid, post.title, post.content, post.tag))
            db.commit()
            
            # 获取刚插入的文章ID
            post_id = cursor.lastrowid
            
        return {"code": 200, "message": "发布成功", "post_id": post_id}
    except Exception as e:
        print(f"发布失败: {e}")
        return {"code": 500, "message": str(e)}

# 2. 获取文章列表接口 (用于首页)
@router.get("/")
async def get_posts_list(limit: int = 20, db=Depends(get_db_connection)):
    try:
        with db.cursor() as cursor:
            # 连表查询，顺便把作者的头像和昵称也查出来！
            sql = """
                SELECT p.id, p.title, p.tag, p.views, p.created_at, 
                       u.nickname, u.avatar 
                FROM posts p
                LEFT JOIN users u ON p.uuid = u.uuid
                ORDER BY p.created_at DESC
                LIMIT %s
            """
            cursor.execute(sql, (limit,))
            posts = cursor.fetchall()
            
            # 格式化一下时间
            result = []
            for p in posts:
                result.append({
                    "id": p['id'],
                    "title": p['title'],
                    "tag": p['tag'],
                    "views": p['views'],
                    "date": p['created_at'].strftime("%Y-%m-%d"), # 简化时间
                    "author": p['nickname'] or "神秘玩家",
                    "avatar": p['avatar']
                })
                
        return {"code": 200, "data": result}
    except Exception as e:
        print(f"获取列表失败: {e}")
        return {"code": 500, "message": str(e)}
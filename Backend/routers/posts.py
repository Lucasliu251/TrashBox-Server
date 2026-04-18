import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
import re

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import text
from database import get_db_connection
from config import settings




router = APIRouter(prefix="/api/v1/posts", tags=["posts"])

# 定义接收前端数据的模型
class PostCreate(BaseModel):
    openid: str      # 作者 ID (对应数据库的 uuid)
    title: str       # 标题
    content: str     # 富文本 HTML 内容
    tag: str = "默认" # 分类标签



# 辅助函数：清洗HTML标签并提取纯文本
def clean_html(raw_html):
    if not raw_html:
        return ""
    # 1. 正则去除所有 <...> 标签
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    # 2. 去除连续的空白符、换行符，变成紧凑的一行
    return re.sub(r'\s+', ' ', cleantext).strip()

# 1. 发布文章接口
@router.post("/")
async def create_post(post: PostCreate, connection=Depends(get_db_connection)):
    # 简单校验
    if not post.title or not post.content:
        return {"code": 400, "message": "标题或内容不能为空"}
    # 校验用户身份
    if not post.openid:
        return {"code": 401, "message": "用户未登录或身份无效，无法发布"}

    try:
        sql = text("""
            INSERT INTO posts (uuid, title, content, tag, created_at) 
            VALUES (:uuid, :title, :content, :tag, NOW())
        """)
        
        result = connection.execute(sql, {
            "uuid": post.openid, 
            "title": post.title, 
            "content": post.content, 
            "tag": post.tag
        })
        connection.commit() 
        
        post_id = result.lastrowid
            
        return {"code": 200, "message": "发布成功", "post_id": post_id}
    except Exception as e:
        print(f"发布失败: {e}")
        # 生产环境建议记录日志，不要直接把错误返给前端
        return {"code": 500, "message": "服务器内部错误，发布失败"}

# 2. 获取文章列表接口 (用于首页)
@router.get("/")
async def get_posts_list(limit: int = 10, offset: int = 0, connection=Depends(get_db_connection)): # [修改]
    try:
        # [修改] 参数 :limit, :offset
        sql = text("""
            SELECT p.id, p.title, p.content, p.tag, p.views, p.created_at, 
                   u.nickname, u.avatar 
            FROM posts p
            LEFT JOIN users u ON p.uuid = u.uuid
            ORDER BY p.created_at DESC
            LIMIT :limit OFFSET :offset
        """)
        result = connection.execute(sql, {"limit": limit, "offset": offset}).fetchall()
        
        data_list = []
        for p in result:
            # [修改] SQLAlchemy Row 对象支持属性访问 (p.content)，比字典访问更方便
            content = p.content or ""
            cover_image = None
            match = re.search(r'<img.*?src="(.*?)".*?>', content)
            if match:
                cover_image = match.group(1)
            
            plain_text = clean_html(content)
            summary = plain_text[:12] + '...' if len(plain_text) > 12 else plain_text

            data_list.append({
                "id": p.id, # [修改] p['id'] -> p.id
                "title": p.title,
                "summary": summary,
                "tag": p.tag,
                "views": p.views,
                "date": p.created_at.strftime("%Y-%m-%d"),
                "author": p.nickname or "神秘玩家",
                "avatar": p.avatar,
                "cover": cover_image
            })
            
        has_more = len(result) == limit
            
        return {"code": 200, "data": data_list, "pagination": {"has_more": has_more, "next_offset": offset + limit}}
    except Exception as e:
        return {"code": 500, "message": str(e)}
    

# 3. 图片上传接口
@router.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    # A. 检查文件类型
    allowed_types = ["image/jpg", "image/jpeg", "image/png", "image/gif", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="仅支持上传图片 (JPG/PNG/GIF/WEBP)")
    
    # B. 准备保存路径
    # 使用 config.py 里的配置
    save_dir = Path(settings.UPLOAD_DIR)
    if not save_dir.exists():
        save_dir.mkdir(parents=True, exist_ok=True) # 自动创建文件夹
        
    # C. 生成唯一文件名 (时间戳_随机码.后缀)
    # 例: 20260109_a1b2c3d4.jpg
    timestamp = datetime.now().strftime("%Y%m%d")
    unique_id = uuid.uuid4().hex[:8]
    extension = Path(file.filename).suffix
    new_filename = f"{timestamp}_{unique_id}{extension}"
    
    file_path = save_dir / new_filename

    # D. 保存文件到磁盘
    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        print(f"Upload Error: {e}")
        raise HTTPException(status_code=500, detail="图片保存失败")

    # E. 返回访问链接
    # 拼接成: https://api.yourdomain.com/assets/posts/xxx.jpg
    full_url = f"{settings.IMG_DOMAIN}{settings.IMG_URL_PREFIX}/{new_filename}"
    
    return {
        "code": 200, 
        "message": "上传成功",
        "url": full_url,
        "alt": file.filename
    }

# 4. 获取文章详情接口
@router.get("/{post_id}")
async def get_post_detail(post_id: int, connection=Depends(get_db_connection)):
    try:
        # A. 获取文章完整内容
        sql_post = text("""
            SELECT p.*, u.nickname, u.avatar 
            FROM posts p
            LEFT JOIN users u ON p.uuid = u.uuid 
            WHERE p.id = :pid
        """)
        post_row = connection.execute(sql_post, {"pid": post_id}).fetchone()
        
        if not post_row:
            return {"code": 404, "message": "文章不存在"}

        # B. 获取评论列表
        sql_comments = text("""
            SELECT c.content, c.created_at, u.nickname, u.avatar
            FROM comments c
            LEFT JOIN users u ON c.uuid = u.uuid
            WHERE c.post_id = :pid
            ORDER BY c.created_at ASC
        """)
        comments_result = connection.execute(sql_comments, {"pid": post_id}).fetchall()
        
        # C. 增加浏览量
        connection.execute(text("UPDATE posts SET views = views + 1 WHERE id = :pid"), {"pid": post_id})
        connection.commit()
        
        # 组装数据
        # [修改] 将 SQLAlchemy Row 对象转换为字典 (使用 _mapping 属性)
        post_data = dict(post_row._mapping)
        
        comments_data = []
        for c in comments_result:
            comments_data.append({
                "content": c.content,
                "created_at": c.created_at,
                "nickname": c.nickname,
                "avatar": c.avatar
            })

        return {
            "code": 200, 
            "data": {
                "info": post_data,
                "comments": comments_data
            }
        }
    except Exception as e:
        return {"code": 500, "message": str(e)}
    
# 5. 发表评论接口
@router.post("/{post_id}/comment")
async def add_comment(post_id: str, item: dict, connection=Depends(get_db_connection)):
    try:
        sql = text("INSERT INTO comments (post_id, uuid, content) VALUES (:pid, :uid, :content)")
        connection.execute(sql, {
            "pid": post_id, 
            "uid": item['uuid'], 
            "content": item['content']
        })
        connection.commit()
        return {"code": 200, "message": "评论成功"}
    except Exception as e:
        return {"code": 500, "message": str(e)}
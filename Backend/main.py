# main.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from routers import users, posts, stats, friends # 导入子模块

app = FastAPI(title="TrashBox API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法 (GET, POST, OPTIONS)
    allow_headers=["*"],  # 允许所有 Header
)

# 挂载子路由
app.include_router(users.router)
app.include_router(posts.router)
# app.include_router(stats.router)
# app.include_router(friends.router)


# 全局异常捕获
@app.exception_handler(500)
async def internal_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": f"Internal Server Error: {str(exc)}"},
    )

try:
    app.include_router(users.router)
    print("✅ Users Router 加载成功")
except Exception as e:
    print(f"❌ Users Router 加载失败: {e}")

@app.get("/test")
def root():
    return {"message": "Server is running..."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=2026, log_level="info")
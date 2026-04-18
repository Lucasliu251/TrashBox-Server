# send_report.py
import asyncio
import httpx
import datetime
from sqlalchemy import text
from database import get_db_connection
from config import settings

# ================= 配置区 =================
# 必须和你微信后台完全一致
TEMPLATE_ID = "_JuPoyWJByf2jpbbbxMwqCtP7JCRBhseMtvG0Opr7Tg" 
API_BASE = "https://trashbox.tech"  # 你的后端地址

async def get_wx_access_token():
    """获取微信 Token"""
    url = f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={settings.WX_APP_ID}&secret={settings.WX_APP_SECRET}"
    async with httpx.AsyncClient() as client:
        res = await client.get(url)
        data = res.json()
        if "access_token" not in data:
            print(f"❌ 获取 Token 失败: {data}")
            return None
        return data["access_token"]

async def fetch_daily_rankings(date_str):
    """从后端 API 获取指定日期的榜单数据，并转为以 steam_id 为 Key 的字典"""
    url = f"{API_BASE}/api/v1/rankings/daily"
    print(f"📡 正在拉取榜单数据: {url}?date={date_str}")
    
    async with httpx.AsyncClient() as client:
        try:
            # 这里的 timeout 设置长一点，防止数据量大超时
            res = await client.get(url, params={"date": date_str}, timeout=10.0)
            if res.status_code == 200:
                data = res.json()
                if "rankings" in data:
                    # 转化为字典: { "7656xxx": {rank:1, nickname:"...", ...}, ... }
                    # 这样后面发消息时查找速度是 O(1)
                    return { item["steam_id"]: item for item in data["rankings"] }
            print(f"⚠️ API 返回异常: {res.text}")
            return {}
        except Exception as e:
            print(f"❌ 拉取榜单失败: {e}")
            return {}

async def send_daily_report():
    print(f"[{datetime.datetime.now()}] 开始执行日报推送...")

    # 1. 计算日期 (默认推昨天的)
    yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
    date_str = yesterday.strftime("%Y-%m-%d")
    update_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    # 2. 获取榜单数据
    ranking_map = await fetch_daily_rankings(date_str)
    if not ranking_map:
        print("📭 昨日无榜单数据，或 API 挂了，任务终止。")
        return

    # 3. 数据库连接
    conn_generator = get_db_connection()
    connection = next(conn_generator)

    try:
        # 4. 获取微信 Token
        token = await get_wx_access_token()
        if not token: return

        # 5. 查询订阅用户 (关键：同时查出 users 表里的 steam_id)
        # 我们需要 JOIN users 表，因为 subscriptions 表只有 openid
        sql = text("""
            SELECT s.openid, s.remaining_count, u.steam_id 
            FROM subscriptions s
            JOIN users u ON s.openid = u.uuid
            WHERE s.remaining_count > 0 AND s.template_id = :tid
        """)
        subscribers = connection.execute(sql, {"tid": TEMPLATE_ID}).fetchall()

        if not subscribers:
            print("📭 没有待推送的订阅用户")
            return

        print(f"📋 发现 {len(subscribers)} 位订阅者，准备匹配数据发送...")
        
        send_url = f"https://api.weixin.qq.com/cgi-bin/message/subscribe/send?access_token={token}"

        async with httpx.AsyncClient() as client:
            for sub in subscribers:
                openid = sub.openid
                steam_id = sub.steam_id
                
                # 6. 在榜单数据里找这个人
                player_data = ranking_map.get(steam_id)

                # 构造数据内容
                if player_data:
                    nickname = player_data.get('nickname', 'Unknown')
                    rank = player_data.get('rank', '-')
                    kd = player_data.get('daily_kd', '0.00')
                    adr = player_data.get('daily_adr', '0.0')
                    
                    # [修改点] 极简模式，确保不超过20字符
                    # 效果示例: "#5 KD:1.22 A:88"
                    try:
                        adr_val = int(float(adr)) # ADR 取整
                    except:
                        adr_val = adr
                        
                    data_change_str = f"#{rank} KD:{kd} A:{adr_val}"
                    
                    # 二次保险：如果还是太长，强行截断
                    if len(data_change_str) > 20:
                         data_change_str = data_change_str[:20]

                    remark_str = "昨日手感火热，快来看看详细数据！"
                else:
                    # 如果这人昨天没打 (榜单里没他)
                    # 策略：可以选择不发，也可以发一个“昨日无记录”
                    # 这里为了省次数，我们可以选择不发，或者发一个提示
                    # 既然用户订阅了，发一个提示比较好
                    nickname = "CSer" # 如果没拿到榜单数据，可能拿不到最新昵称，暂时写死或查库
                    data_change_str = "昨日无排名记录"
                    remark_str = "昨天没来打？今天记得上号！"
                    
                    # 如果你想“没打就不发”，把下面这就话取消注释：
                    # print(f"🚫 {steam_id} 昨日无数据，跳过推送")
                    # continue 

                # 7. 构造 Payload (对应你的模板)
                payload = {
                    "touser": openid,
                    "template_id": TEMPLATE_ID,
                    "page": f"pages/rank/rank", # 点击直接跳到他的个人数据页
                    "miniprogram_state": "formal",
                    "lang": "zh_CN",
                    "data": {
                        "character_string1": {"value": steam_id},       # 玩家ID (纯数字/字母)
                        "thing2": {"value": nickname[:20]},             # 玩家昵称 (截断防止超长报错)
                        "time3": {"value": update_time_str},            # 更新时间
                        "thing4": {"value": data_change_str},           # 数据变化
                        "thing5": {"value": remark_str}                 # 备注
                    }
                }

                try:
                    res = await client.post(send_url, json=payload)
                    res_data = res.json()

                    if res_data.get("errcode") == 0:
                        print(f"✅ 发送成功: {nickname} ({openid})")
                        # 扣除次数
                        connection.execute(
                            text("UPDATE subscriptions SET remaining_count = remaining_count - 1 WHERE openid = :oid AND template_id = :tid"), 
                            {"oid": openid, "tid": TEMPLATE_ID}
                        )
                        connection.commit()
                    else:
                        print(f"❌ 发送失败 {openid}: {res_data}")
                        
                except Exception as e:
                    print(f"⚠️ 网络异常 {openid}: {str(e)}")

    except Exception as e:
        print(f"🔥 脚本执行错误: {e}")
    finally:
        connection.close()
        print("🏁 任务结束")

if __name__ == "__main__":
    asyncio.run(send_daily_report())
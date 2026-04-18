# routers/player_stats.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from datetime import datetime, timedelta
from typing import List, Dict
from pydantic import BaseModel
from database import get_db_connection
from utils.rating_algo import calculate_trashbox_rating

router = APIRouter()

class HistoryItem(BaseModel):
    date: str
    Rating: float
    kills: int
    deaths: int
    kd: float
    mvp: int
    headshots: int
    dmg: int
    hsr: float
    adr: float
    rounds_played: int
    win_rate: float

class PlayerHistoryResponse(BaseModel):
    steam_id: str
    nickname: str 
    avatar: str | None = None
    style_tag: str | None = None
    summary: Dict
    history: List[HistoryItem]

@router.get("/api/v1/players/{steam_id}/history", response_model=PlayerHistoryResponse)
def get_player_history(
    steam_id: str, 
    days: int = Query(30, le=90),
    connection = Depends(get_db_connection)
):
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days + 1) # 多取一天算增量

    query = text("""
        SELECT record_date, nickname, total_kills, total_deaths, total_mvps, total_HS, total_damage, total_wins, total_rounds_played, total_time_played, total_money_earned, style_tag
        FROM daily
        WHERE steam_id = :sid AND record_date >= :s_date
        ORDER BY record_date ASC
    """)
    result = connection.execute(query, {"sid": steam_id, "s_date": start_date}).fetchall()

    # 2. 检查 users 表，看这个人是否注册过
    user_query = text("SELECT nickname, avatar FROM users WHERE steam_id = :sid")
    user_row = connection.execute(user_query, {"sid": steam_id}).fetchone()

    # 获取全服平均数据 ---
    # 查最新的一条记录
    sql_avg = text("""
        SELECT avg_kpr, avg_spr, avg_adr, avg_hsr, avg_mpr, avg_wr 
        FROM server_avg_stats 
        ORDER BY date DESC 
        LIMIT 1
    """)
    row_avg = connection.execute(sql_avg).fetchone()
    

    history_list = []
    
    # 错位相减
    for i in range(1, len(result)):
        curr = result[i]
        prev = result[i-1]

        d_kills = max(0, curr.total_kills - prev.total_kills)
        d_deaths = max(0, curr.total_deaths - prev.total_deaths)
        d_dmg = max(0, curr.total_damage - prev.total_damage)
        d_wins = max(0, curr.total_wins - prev.total_wins)
        d_rounds = max(0, curr.total_rounds_played - prev.total_rounds_played)
        d_HS = max(0, curr.total_HS - prev.total_HS)
        d_MVP = max(0, curr.total_mvps - prev.total_mvps)
        d_ADR = round(d_dmg / d_rounds, 2) if d_rounds > 0 else 0
        d_kd = round(d_kills / d_deaths, 2) if d_deaths > 0 else d_kills
        d_HSR = round((d_HS / d_kills) * 100, 2) if d_kills > 0 else 0
        d_WR = round((d_wins / d_rounds) * 100, 2) if d_rounds > 0 else 0
        d_Rating = round(calculate_trashbox_rating(d_kills, d_deaths, d_dmg, d_MVP, d_rounds), 2)

        # 异常熔断  
        if d_rounds > 1000:
                d_rounds = 0

        name = curr.nickname if curr.nickname else "Unknown"

        history_list.append({
            "date": str(curr.record_date),
            "Rating": d_Rating,
            "kills": d_kills,
            "deaths": d_deaths,
            "kd": d_kd,
            "mvp": d_MVP,
            "dmg": d_dmg,
            "headshots": d_HS,
            "hsr": d_HSR,
            "adr": d_ADR,
            "rounds_played": d_rounds,
            "win_rate": d_WR,
        })



    # 3. 决定最终返回的昵称和头像
    final_nickname = None
    final_avatar = None

    if user_row:
        # A. 如果注册过，优先用 users 表的数据
        final_nickname = user_row.nickname
        final_avatar = user_row.avatar
    else:
        # B. 如果 users 表没数据（未注册），或者字段为空
        final_nickname = name
        final_avatar = None
    

    # 计算总计
    total_k = sum(x['kills'] for x in history_list)
    total_d = sum(x['deaths'] for x in history_list)
    total_rounds = sum(x['rounds_played'] for x in history_list)
    total_wins = sum(int(x['rounds_played'] * x['win_rate'] / 100) for x in history_list)
    total_dmg = sum(x['dmg'] for x in history_list)
    avg_WR = round((total_wins / total_rounds) * 100, 2) if total_rounds > 0 else 0
    avg_kd = round(total_k / total_d, 2) if total_d > 0 else 0
    avg_ADR = round(total_dmg / total_rounds, 2) if total_rounds > 0 else 0
    avg_HSR = round((sum(x['headshots'] for x in history_list) / total_k) * 100, 2) if total_k > 0 else 0
    avg_MPR = round(sum(x['mvp'] for x in history_list) / total_rounds, 3) if total_rounds > 0 else 0
    avg_KPR = round(total_k / total_rounds, 3) if total_rounds > 0 else 0
    avg_SPR = round((total_rounds - total_d) / total_rounds, 3) if total_rounds > 0 else 0
    avg_Rating = round(calculate_trashbox_rating(total_k, total_d, total_dmg, sum(x['mvp'] for x in history_list), total_rounds), 2)

    if row_avg:
        server_avg = {
            "kpr": float(row_avg.avg_kpr),
            "spr": float(row_avg.avg_spr),
            "adr": float(row_avg.avg_adr),
            "hsr": float(row_avg.avg_hsr),
            "mpr": float(row_avg.avg_mpr),
            "wr":  float(row_avg.avg_wr)
        }

    return {
        "steam_id": steam_id,
        "nickname": final_nickname,
        "avatar": final_avatar,
        "style_tag": curr.style_tag if curr.style_tag else None,
        "summary": {
            "avg_Rating": avg_Rating,
            "period_kills": total_k,
            "period_deaths": total_d,
            "period_dmg": total_dmg,
            "avg_kd": avg_kd,
            "avg_ADR": avg_ADR,
            "avg_WR": avg_WR,
            "avg_HSR": avg_HSR,
            "avg_MPR": avg_MPR,
            "avg_KPR": avg_KPR,
            "avg_SPR": avg_SPR,
            "time_played": curr.total_time_played,
            "money_earned": curr.total_money_earned,
            "server_avg": server_avg if row_avg else None,
            "days_tracked": len(history_list)
        },
        "history": history_list
    }
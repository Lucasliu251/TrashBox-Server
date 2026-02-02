# routers/daily_rank.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from datetime import datetime, timedelta
from typing import List
from pydantic import BaseModel
from database import get_db_connection

router = APIRouter()

# 定义返回模型
class RankItem(BaseModel):
    rank: int
    nickname: str
    avatar: str | None = None
    steam_id: str

    daily_kills: int
    daily_deaths: int
    daily_damage: int
   
    daily_mvp: int
    daily_headshots: int

    daily_kd: float
    daily_adr: float
    daily_hsr: float


class DailyRankingResponse(BaseModel):
    date: str
    rankings: List[RankItem]


@router.get("/api/v1/rankings/daily", response_model=DailyRankingResponse)
def get_daily_ranking(
    date: str = Query(..., description="日期格式 YYYY-MM-DD"),
    connection = Depends(get_db_connection)
):
    # 1. 计算日期范围
    target_date = datetime.strptime(date, "%Y-%m-%d").date()
    prev_date = target_date - timedelta(days=1)

    # 2. 一次性查出两天的数据
    query = text("""
        SELECT steam_id, nickname, record_date, total_kills, total_deaths, total_mvps, total_HS, total_damage, total_rounds_played
        FROM daily 
        WHERE record_date IN (:t_date, :p_date)
    """)
    result = connection.execute(query, {"t_date": target_date, "p_date": prev_date}).fetchall()

    # 3. 数据重组 (按 SteamID 分组)
    data_map = {}
    # 获取所有涉及的 steam_id 以便查询昵称
    steam_ids = set()
    
    for row in result:
        s_id = row.steam_id
        steam_ids.add(s_id)
        if s_id not in data_map: data_map[s_id] = {}
        data_map[s_id][str(row.record_date)] = row

    user_info_map = {}
    if steam_ids:
        # 将 set 转为 tuple 供 SQL IN 查询使用
        ids_tuple = tuple(steam_ids)
        user_query = text("SELECT steam_id, nickname, avatar FROM users WHERE steam_id IN :ids")
        user_rows = connection.execute(user_query, {"ids": ids_tuple}).fetchall()
        
        # 构建查找表
        for u_row in user_rows:
            user_info_map[u_row.steam_id] = {
                "nickname": u_row.nickname,
                "avatar": u_row.avatar
            }
    
    # 4. 计算每日数据
    rank_list = []
    for steam_id in steam_ids:
        records = data_map.get(steam_id, {})
        current = records.get(str(target_date))
        prev = records.get(str(prev_date))

        if not current: continue

        prev_kills = prev.total_kills if prev else 0
        prev_deaths = prev.total_deaths if prev else 0
        prev_mvps = prev.total_mvps if prev else 0
        prev_hs = prev.total_HS if prev else 0
        prev_dmg = prev.total_damage if prev else 0
        prev_rounds = prev.total_rounds_played if prev else 0

        d_kills = current.total_kills - prev_kills
        d_deaths = current.total_deaths - prev_deaths
        d_mvp = current.total_mvps - prev_mvps
        d_hs = current.total_HS - prev_hs
        d_dmg = current.total_damage - prev_dmg
        d_rounds = current.total_rounds_played - prev_rounds

        d_kd = round(d_kills / d_deaths, 2) if d_deaths > 0 else d_kills
        d_HSR = round((d_hs / d_kills) * 100, 2) if d_kills > 0 else 0.0
        d_ADR = round(d_dmg / d_rounds, 2) if d_rounds > 0 else 0.0

        # 确定昵称和头像 
        # 获取该 ID 对应的注册信息 (可能为空)
        reg_info = user_info_map.get(steam_id, {})
        
        # A. 昵称逻辑：注册昵称 > 游戏内昵称 > Unknown
        game_nickname = current.nickname if current.nickname else (prev.nickname if prev else "Unknown")
        final_nickname = reg_info.get("nickname") or game_nickname

        # B. 头像逻辑：注册头像 > DiceBear 自动生成
        reg_avatar = reg_info.get("avatar")
        final_avatar = reg_avatar if reg_avatar else None

        rank_list.append({
            "nickname": final_nickname, 
            "avatar": final_avatar,
            "steam_id": steam_id,
            "daily_kills": d_kills,
            "daily_deaths": d_deaths,
            "daily_kd": d_kd,
            "daily_adr": d_ADR,
            "daily_hsr": d_HSR,
            "daily_headshots": d_hs,
            "daily_damage": d_dmg,
            "daily_mvp": d_mvp,
        })

    # 6. 排序
    rank_list.sort(key=lambda x: x['daily_kd'], reverse=True)
    
    # 7. 注入排名
    for i, item in enumerate(rank_list):
        item['rank'] = i + 1

    return {"date": date, "rankings": rank_list}
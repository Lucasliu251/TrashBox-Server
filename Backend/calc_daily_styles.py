import sys
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import text
from database import get_db_connection
from utils.clustering_algo import analyze_player_styles

def calculate_styles_for_date(date_str):
    print(f"[{datetime.now()}] 🚀 开始计算 {date_str} 的玩家风格聚类...")
    
    # --- 1. 获取数据库连接 (手动管理生成器) ---
    db_gen = get_db_connection()
    db = next(db_gen)
    
    try:
        # --- 2. 准备日期范围 ---
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        prev_date = target_date - timedelta(days=1)
        
        print(f"📅 正在拉取数据: {target_date} (今日) vs {prev_date} (昨日)")

        # --- 3. 一次性查出两天的数据 (累计值) ---
        # 这里需要查出所有参与了这两天记录的玩家
        query_sql = text("""
            SELECT 
                steam_id, 
                record_date, 
                total_kills, 
                total_deaths, 
                total_mvps, 
                total_HS, 
                total_damage, 
                total_rounds_played, 
                total_wins
            FROM daily 
            WHERE record_date IN (:t_date, :p_date)
        """)
        
        rows = db.execute(query_sql, {"t_date": target_date, "p_date": prev_date}).fetchall()
        
        if not rows:
            print(f"⚠️ 未找到 {target_date} 的数据，跳过计算。")
            return

        # --- 4. 数据重组 (按 SteamID 分组) ---
        # 格式: user_data = { 'steam_id': { 'today': row, 'yesterday': row } }
        user_data_map = {}
        for row in rows:
            sid = row.steam_id
            if sid not in user_data_map:
                user_data_map[sid] = {}
            
            # 判断是今天还是昨天的数据
            r_date = row.record_date
            if isinstance(r_date, datetime):
                r_date = r_date.date()
                
            if r_date == target_date:
                user_data_map[sid]['today'] = row
            elif r_date == prev_date:
                user_data_map[sid]['yesterday'] = row

        # --- 5. 计算当日增量 (Delta) ---
        clustering_input = []
        
        for sid, records in user_data_map.items():
            # 必须同时有今天和昨天的数据才能算出增量
            # (如果是新用户第一天，没有昨天数据，暂时无法计算当日风格，跳过)
            if 'today' not in records or 'yesterday' not in records:
                continue
            
            today = records['today']
            yesterday = records['yesterday']
            
            # 计算差值 (增量)
            d_rounds = today.total_rounds_played - yesterday.total_rounds_played
            
            # 过滤：如果今天没打满 5 回合，数据不稳定，不参与聚类
            if d_rounds < 5:
                continue
                
            d_kills = today.total_kills - yesterday.total_kills
            d_deaths = today.total_deaths - yesterday.total_deaths
            d_damage = today.total_damage - yesterday.total_damage
            d_mvps = today.total_mvps - yesterday.total_mvps
            d_wins = today.total_wins - yesterday.total_wins
            d_hs = today.total_HS - yesterday.total_HS 
            
            # 构造算法需要的特征 (比率)
            player_data = {
                "steam_id": sid,
                "kpr": d_kills / d_rounds,
                "spr": (d_rounds - d_deaths) / d_rounds,
                "adr": d_damage / d_rounds,
                "hsr": d_hs / max(1, d_kills), # 爆头率
                "mpr": d_mvps / d_rounds,
                "wr":  d_wins / d_rounds
            }
            clustering_input.append(player_data)

        print(f"📋 有效活跃玩家: {len(clustering_input)} 人 (已剔除场次不足者)")

        if not clustering_input:
            print("⚠️ 今日有效玩家数据不足，无法聚类。")
            return

        # --- 6. 调用聚类算法 ---
        print(f"🧠 正在执行 K-Means 聚类分析...")
        style_results = analyze_player_styles(clustering_input)

        # 6.5 计算全服平均数据
        df_daily = pd.DataFrame(clustering_input)
        
        # 计算平均值 (保留3位小数)
        daily_avg = {
            "kpr": round(df_daily['kpr'].mean(), 3),
            "spr": round(df_daily['spr'].mean(), 3),
            "adr": round(df_daily['adr'].mean(), 2),
            "hsr": round(df_daily['hsr'].mean(), 3),
            "mpr": round(df_daily['mpr'].mean(), 3),
            "wr":  round(df_daily['wr'].mean(), 3),
            "count": len(df_daily)
        }
        
        print(f"   平均 KPR: {daily_avg['kpr']}, ADR: {daily_avg['adr']}")

        # 3. 存入 server_avg_stats 表 (如果当天已存在则更新)
        # 使用 UPSERT 语法 (MySQL: ON DUPLICATE KEY UPDATE)
        insert_avg_sql = text("""
            INSERT INTO server_avg_stats 
            (date, avg_kpr, avg_spr, avg_adr, avg_hsr, avg_mpr, avg_wr, active_players)
            VALUES (:date, :kpr, :spr, :adr, :hsr, :mpr, :wr, :count)
            ON DUPLICATE KEY UPDATE
            avg_kpr=:kpr, avg_spr=:spr, avg_adr=:adr, avg_hsr=:hsr, avg_mpr=:mpr, avg_wr=:wr, active_players=:count
        """)
        
        db.execute(insert_avg_sql, {
            "date": target_date,
            **daily_avg
        })
        print("✅ 全服平均数据已存档")
        
        # --- 7. 批量回写数据库 ---
        print(f"💾 正在更新 {len(style_results)} 名玩家的 style_tag...")
        
        # 确保你的 daily 表已经有了 style_tag 字段！
        update_sql = text("""
            UPDATE daily
            SET style_tag = :tag
            WHERE steam_id = :sid AND record_date = :t_date
        """)
        
        count = 0
        for sid, tag in style_results.items():
            db.execute(update_sql, {"tag": tag, "sid": sid, "t_date": target_date})
            count += 1
            
        db.commit()
        print(f"✅ 成功更新 {count} 条记录！风格计算完成。")

    except Exception as e:
        print(f"🔥 计算过程中发生错误: {e}")
        db.rollback() # 出错回滚
    finally:
        # --- 8. 正确关闭连接 ---
        # 这一步非常重要，手动触发生成器的清理逻辑
        try:
            next(db_gen, None)
        except StopIteration:
            pass
        # 或者显式关闭 (取决于 get_db_connection 的实现，通常 next() 触发 finally 即可)
        # 如果 get_db_connection 是 yield db，这里需要确保 db.close() 被调用

if __name__ == "__main__":
    # 默认计算今天 (假设是在晚上运行) 或者昨天
    if len(sys.argv) > 1:
        target_date = sys.argv[1]
    else:
        # 默认计算昨天的（因为通常是算过去一天的日报）
        yesterday = datetime.now()
        target_date = yesterday.strftime("%Y-%m-%d")
        
    calculate_styles_for_date(target_date)
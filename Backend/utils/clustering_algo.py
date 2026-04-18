import pandas as pd
import numpy as np
import requests
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans

def analyze_player_styles(players_data):
    """
    执行玩家风格聚类分析 (向量相似度匹配版)
    """
    if not players_data or len(players_data) < 5:
        return {p['steam_id']: '新' for p in players_data}

    # 1. 数据准备
    df = pd.DataFrame(players_data)
    # 核心特征
    features = ['kpr', 'spr', 'adr', 'hsr', 'mpr', 'wr']
    df[features] = df[features].fillna(0)
    X = df[features]

    # 2. 数据标准化 (Z-Score)
    # 这一步后，0 代表平均水平，+1 代表高于平均一个标准差，-1 代表低于平均一个标准差
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # 3. K-Means 聚类
    n_clusters = min(8, len(players_data) // 2) # 稍微增加簇的数量以捕捉细分风格
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    df['cluster'] = kmeans.fit_predict(X_scaled)

    # 获取聚类中心 (在标准化空间下的坐标)
    centers = kmeans.cluster_centers_

    # 4. 定义“标签原型向量” (The Archetypes)
    # 这里的数值代表 Z-Score (标准差)。
    #  1.5 = 显著高
    #  0.5 = 稍微高
    #  0   = 平均
    # -1.5 = 显著低
    # 顺序对应 features: ['kpr', 'spr', 'adr', 'hsr', 'mpr', 'wr']
    
    archetypes = {
        #               KPR,  SPR,  ADR,  HSR,  MPR,  WR
        "狠": np.array([1.5,  0.5,  1.5,  0.0,  0.5,  0.5]),  # 数据碾压
        "准": np.array([0.5,  0.0,  0.0,  2.0,  0.0,  0.0]),  # 只有爆头特别突出
        "六": np.array([-0.5, 1.5,  0.0,  0.0,  0.0,  0.0]),  # 存活极高，输出低
        "混": np.array([-0.8, 0.0, -0.8,  0.0, -0.5,  0.8]),  # 数据差但胜率高
        "牢": np.array([1.2,  0.0,  1.2,  0.0,  0.5, -1.2]),  # 数据好但胜率极低 (SVP)
        "巧": np.array([0.0,  0.5,  0.0,  0.0,  0.5,  1.5]),  # 胜率极高，其他平均
        "莽": np.array([1.2, -1.2,  0.8,  0.0,  0.0,  0.0]),  # KPR高，存活极低 (一换一)
        "力": np.array([0.2,  0.0,  1.5,  0.0,  0.0,  0.0]),  # ADR 显著高于 KPR (助攻王)
        "崩": np.array([-1.2, -1.2, -1.2, 0.0, -1.0, -1.0]),  # 全线崩盘
        "钥": np.array([0.8,  0.0,  0.8,  0.0,  2.0,  0.5]),  # MVP 极高
        "浪": np.array([0.5, -1.5,  0.5,  0.0,  0.0, -0.5]),  # 数据还行但死得太多
        "凡": np.array([0.0,  0.0,  0.0,  0.0,  0.0,  0.0])   # 一切都是平均值
    }

    # 5. 计算相似度并分配标签
    # 我们计算每个“聚类中心”到所有“原型向量”的距离，选最近的。
    
    cluster_label_map = {}
    
    # 记录哪些标签已经被分配了，尽量不重复 (可选策略)
    # 但如果是通过相似度匹配，重复也是合理的（比如有两波人都很菜，都叫“崩”）
    
    for i, center_vec in enumerate(centers):
        best_label = "凡"
        min_dist = float('inf')
        
        # 遍历所有原型，找最像的
        for label, ideal_vec in archetypes.items():
            # 计算欧氏距离 (Euclidean Distance)
            # 距离越小，越接近原型
            dist = np.linalg.norm(center_vec - ideal_vec)
            
            # 你也可以加权，比如这一行：让 WR (index 5) 的权重变大，防止“牢”被误判
            # weights = np.array([1, 1, 1, 1, 1, 1.5])
            # dist = np.linalg.norm((center_vec - ideal_vec) * weights)

            if dist < min_dist:
                min_dist = dist
                best_label = label
        
        cluster_label_map[i] = best_label

    # 6. 映射结果
    result = {}
    for index, row in df.iterrows():
        sid = row['steam_id']
        cid = row['cluster']
        result[sid] = cluster_label_map[cid]

    return result

if __name__ == "__main__":
    # 1. 设置 API 地址和参数
    api_url = "https://trashbox.tech/api/v1/rankings/daily"
    params = {
        "date": "2026-01-29" # 你指定的日期
    }

    print(f"📡 正在从 {api_url} 获取数据...")

    try:
        # 2. 发起请求
        response = requests.get(api_url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            # 假设 API 返回结构是 { "rankings": [ ... ] }
            # 如果是其他结构，请根据实际情况调整
            rankings_list = data.get('rankings', [])
            
            print(f"✅ 获取成功，共 {len(rankings_list)} 条记录")

            # 3. 数据转换 (Data Transformation)
            # API 返回的是总数(daily_kills等)，我们需要转为比率(kpr等)
            formatted_data = []

            for player in rankings_list:
                # 获取基础数据，防止 None
                rounds = player.get('daily_rounds', 0)
                
                # 过滤掉回合数太少的玩家（比如只打了一两局，数据不稳定，会干扰聚类）
                if rounds < 5: 
                    continue

                kills = player.get('daily_kills', 0)
                deaths = player.get('daily_deaths', 0)
                adr = player.get('daily_adr', 0.0)
                # 假设 API 里有 daily_hs_rate (0-1 或 0-100)，如果没有就用 hs/kills 算
                hs_rate = player.get('daily_hs_rate', 0.0) 
                # 如果 API 返回的是百分比(如 45.5)，视情况转为 0.455，或者保持不变。
                # 这里的逻辑假设你的原型向量是基于 StandardScalar 的，所以绝对数值大小不影响，只要单位统一即可。
                
                mvps = player.get('daily_mvp', 0)
                wins = player.get('daily_wins', 0)

                # 构建特征字典
                p_data = {
                    'steam_id': player.get('steam_id'),
                    'kpr': kills / rounds,
                    'spr': (rounds - deaths) / rounds, # 存活率
                    'adr': adr,                        # ADR 本身就是平均值
                    'hsr': hs_rate,                    # 爆头率
                    'mpr': mvps / rounds,
                    'wr': wins / rounds                # 胜率
                }
                formatted_data.append(p_data)

            # 4. 执行聚类
            if len(formatted_data) > 0:
                print("🧠 开始分析玩家风格...")
                style_results = analyze_player_styles(formatted_data)
                
                print("\n>>> 分析结果:")
                print(f"{'Steam ID':<20} | {'风格':<4} | {'KPR':<5} | {'ADR':<5} | {'WR':<5}")
                print("-" * 50)
                
                # 为了展示效果，把原始数据也打出来对比一下
                for p in formatted_data:
                    sid = p['steam_id']
                    if sid in style_results:
                        tag = style_results[sid]
                        print(f"{sid:<20} | {tag:<4} | {p['kpr']:.2f}  | {p['adr']:.1f}  | {p['wr']:.2f}")
            else:
                print("⚠️ 有效玩家数据不足 (清洗后为0)")

        else:
            print(f"❌ API 请求失败: {response.status_code} - {response.text}")

    except Exception as e:
        print(f"🔥 发生错误: {e}")
def calculate_trashbox_rating(kills, deaths, dmg, mvps, rounds):
    """
    计算自定义 Rating (TrashBox Rating v1)
    范围: 0.0 - 3.5 (通常在 0.4 - 2.5 之间)
    """
    if rounds == 0:
        return 0.0

    # --- 1. 计算基础每回合数据 (Per Round Stats) ---
    kpr = min(kills / rounds, 5.0)  # 击杀率，封顶 3.0
    dpr = min(deaths / rounds, 1.0)  # 死亡率，封顶 1.0
    adr = min(dmg / rounds, 500)  # CS2 中平均 ADR 大约在 70-80，130 已经是非常高的水平了
    mpr = min(mvps / rounds, 1.0)
    
    # 存活率 (Survived Per Round)
    # 存活回合数 = 总回合 - 死亡回合
    # 注意：在极少数情况下（如甚至没死过），DPR=0，SPR=1
    spr = 1 - dpr  # 存活率 = 1 - 死亡率

    # --- 2. 定义基准常数 (CS2 综合平均水平) ---
    AVG_KPR = 0.67
    AVG_SPR = 0.33  # 约等于 (1 - 0.67)
    AVG_ADR = 74.0
    AVG_MPR = 0.10  # 稍微提高一点MVP的要求

    # --- 3. 计算各分项得分 (Sub-Ratings) ---
    # 逻辑：(个人数据 / 平均数据) = 得分系数
    # 1.0 代表平均水平
    
    kill_rating = kpr / AVG_KPR
    
    # 生存分：我们要奖励存活。
    # 这里用一种平滑算法：(存活率 / 平均存活率)
    survival_rating = spr / AVG_SPR
    
    damage_rating = adr / AVG_ADR
    
    mvp_rating = mpr / AVG_MPR


    # --- 4. 加权求和 (Weights) ---
    # 权重分配策略：
    # 击杀 (Kill): 35% - 最直接的贡献
    # 伤害 (Dmg):  23% - 极其重要，特别是对于那些打残血但没拿到头的人
    # 生存 (Surv): 22% - 活着才有输出，防止送人头
    # MVP (Imp):   20% - 奖励关键局胜者
    
    raw_rating = (
        (kill_rating * 0.35) + 
        (damage_rating * 0.23) + 
        (survival_rating * 0.22) + 
        (mvp_rating * 0.20)
    )

    # --- 5. 修正与钳制 ---
    # 微调系数：为了让数据看起来更像 HLTV (平均值靠近 1.05 左右)，可以加一个小的 bias
    final_rating = round(raw_rating, 2)

    # 封顶与保底 (防止数据溢出，虽然很难溢出)
    if final_rating > 3.5: final_rating = 3.5
    if final_rating < 0.0: final_rating = 0.0

    return final_rating

# --- 测试用例 ---
# 1. 普通玩家 (数据平平)
# print(f"普通人: {calculate_trashbox_rating(73, 58, 9540, 11, 82)}") 
# # KPR=0.75, DPR=0.75, ADR=75, MPR=0.1
# # 预期: 1.0 左右

# # 2. 大哥 (炸鱼)
# print(f"炸鱼哥: {calculate_trashbox_rating(19, 4, 1986, 6, 14)}")
# # KPR=1.5, DPR=0.25, ADR=175, MPR=0.4
# # 预期: 2.0 以上

# # 3. 究极老六 (保枪战神: 没杀人，没死，没伤害)
# print(f"负KD 高伤害:   {calculate_trashbox_rating(89, 71, 12469, 15, 106)}")
# # 预期: 分数应该很低，虽然存活高，但没有击杀和伤害支撑
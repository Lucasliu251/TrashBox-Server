import requests
import re
from fastapi import HTTPException, Depends, APIRouter
from Backend.database import get_db_connection

STEAM_API_KEY = "你的_STEAM_API_KEY"  # 建议放入 config.py


@router.post("/bind")
async def bind_user(data: UserBindModel, connection=Depends(get_db_connection)):
    try:
        # 自动清洗和转换用户输入
        real_steam_id = resolve_steam_id(data.steam_id_input)
        
        # ... 后续绑定逻辑，存入 real_steam_id ...
        
    except HTTPException as he:
        raise he
    except Exception as e:
        return {"code": 400, "message": "无法识别该 ID，请尝试直接输入 7656 开头的数字 ID"}

def resolve_steam_id(input_str: str) -> str:
    input_str = input_str.strip()
    
    # 情况 1: 用户直接输入了 17 位 SteamID64
    if input_str.isdigit() and len(input_str) == 17:
        return input_str
        
    # 情况 2: 用户输入了包含 profiles 的链接
    # 例如: https://steamcommunity.com/profiles/76561198888888888/
    profile_pattern = r"steamcommunity\.com/profiles/(\d{17})"
    match = re.search(profile_pattern, input_str)
    if match:
        return match.group(1)
        
    # 情况 3: 用户输入了自定义 URL (Vanity URL)
    # 例如: https://steamcommunity.com/id/lucasliu251/ 或 纯名字 lucasliu251
    vanity_name = None
    
    # 尝试从链接提取名字
    vanity_pattern = r"steamcommunity\.com/id/([^/]+)"
    match_vanity = re.search(vanity_pattern, input_str)
    
    if match_vanity:
        vanity_name = match_vanity.group(1)
    elif not input_str.isdigit() and "/" not in input_str: 
        # 假设用户只输了自定义id的名字，没输链接
        vanity_name = input_str
        
    if vanity_name:
        # 调用 Steam API 将自定义名字转为 ID64
        try:
            url = "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001/"
            params = {
                "key": STEAM_API_KEY,
                "vanityurl": vanity_name
            }
            res = requests.get(url, params=params, timeout=5)
            data = res.json()
            
            if data['response']['success'] == 1:
                return data['response']['steamid']
            else:
                raise ValueError("无法解析该自定义ID")
        except Exception as e:
            print(f"Steam API Error: {e}")
            raise HTTPException(status_code=400, detail="解析Steam ID失败，请检查网络或直接输入数字ID")

    raise HTTPException(status_code=400, detail="无效的 Steam ID 格式")
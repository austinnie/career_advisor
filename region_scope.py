"""城市/地区 → 国家代码映射。用于匹配层判断静态观测是否与用户地域兼容。

本模块是配置数据。未映射的城市返回 None，调用方按"无法确定"处理，
不默认任何国家——与 R1「无证据不填充」一致。
"""
from __future__ import annotations


# 覆盖 demo 与常见城市；未列出的城市需人工扩展
CITY_TO_COUNTRY: dict[str, str] = {
    # 中国
    "北京": "CN", "上海": "CN", "广州": "CN", "深圳": "CN",
    "杭州": "CN", "成都": "CN", "武汉": "CN", "西安": "CN",
    "南京": "CN", "重庆": "CN", "苏州": "CN", "天津": "CN",
    "中国": "CN", "CN": "CN",
    # 美国
    "纽约": "US", "旧金山": "US", "西雅图": "US", "波士顿": "US",
    "洛杉矶": "US", "美国": "US", "US": "US",
    # 日本 (新增)
    "日本": "JP", "东京": "JP", "大阪": "JP", "广岛": "JP", 
    "名古屋": "JP", "京都": "JP", "日本广岛县东广岛市": "JP", "広島": "JP",
    # 欧洲
    "伦敦": "EU", "柏林": "EU", "巴黎": "EU", "EU": "EU",
}


def regions_to_scope(regions: list[str] | None) -> set[str]:
    """将用户填写的地域列表映射到国家代码集合。

    无法映射的城市被忽略（不默认国家）。
    返回空集表示「无法确定用户的国别范围」——调用方必须保守处理，
    不得将空集视为"全球通用"。
    """
    if not regions:
        return set()
    scopes: set[str] = set()
    for r in regions:
        r = (r or "").strip()
        country = CITY_TO_COUNTRY.get(r)
        if country:
            scopes.add(country)
    return scopes


def is_observation_eligible(prospect_region: str, user_scopes: set[str]) -> bool:
    """观测是否与用户地域兼容。

    - prospect_region == "global" → 任何情况下兼容
    - 用户国别范围为空 → 保守返回 False
      （用户未告知地域时不使用任何地域特定数值，避免隐性假设）
    - 否则要求 prospect_region 在 user_scopes 中
    """
    if prospect_region == "global":
        return True
    if not user_scopes:
        return False
    return prospect_region in user_scopes
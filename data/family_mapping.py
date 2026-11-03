"""受控职业族映射。单一职责：定义 SOC 大类 → 本系统 20 个职业族 的静态映射。
本模块是配置数据，不是业务逻辑；变更需版本化并在 CI 中冻结。"""

FAMILY_VERSION = "families-v1.0"

CONTROLLED_FAMILIES = frozenset([
    "信息技术与数字技术", "工程与制造", "商业与行政管理", "金融与会计",
    "健康服务", "教育与培训", "法律与公共安全", "科学研究",
    "艺术设计与传媒", "社会服务", "销售与客户服务", "供应链与物流",
    "建筑与房地产", "农业与环境", "交通与运维", "人力资源",
    "市场营销与公关", "体育与休闲", "旅游与酒店", "其他专业服务",
])

# O*NET-SOC 前两位 = SOC Major Group
SOC_MAJOR_GROUP_TO_FAMILY = {
    "11": "商业与行政管理",   # Management
    "13": "金融与会计",       # Business and Financial Operations
    "15": "信息技术与数字技术",  # Computer and Mathematical
    "17": "工程与制造",       # Architecture and Engineering
    "19": "科学研究",         # Life, Physical, and Social Science
    "21": "社会服务",         # Community and Social Service
    "23": "法律与公共安全",   # Legal
    "25": "教育与培训",       # Educational Instruction and Library
    "27": "艺术设计与传媒",   # Arts, Design, Entertainment, Sports, and Media
    "29": "健康服务",         # Healthcare Practitioners and Technical
    "31": "健康服务",         # Healthcare Support
    "33": "法律与公共安全",   # Protective Service
    "35": "旅游与酒店",       # Food Preparation and Serving Related
    "37": "其他专业服务",     # Building and Grounds Cleaning and Maintenance
    "39": "社会服务",         # Personal Care and Service
    "41": "销售与客户服务",   # Sales and Related
    "43": "商业与行政管理",   # Office and Administrative Support
    "45": "农业与环境",       # Farming, Fishing, and Forestry
    "47": "建筑与房地产",     # Construction and Extraction
    "49": "工程与制造",       # Installation, Maintenance, and Repair
    "51": "工程与制造",       # Production
    "53": "交通与运维",       # Transportation and Material Moving
}


def family_for_soc(soc_code: str) -> str | None:
    """未映射的 major group 返回 None，调用方必须跳过该职业，不得兜底到某个族。"""
    major = soc_code.split("-", 1)[0]
    return SOC_MAJOR_GROUP_TO_FAMILY.get(major)


# O*NET importance 量表的静态归一化。量表本身是 0.0–7.0；
# critical 阈值按阶段 4 契约的 1–5 量表定义（≥4），因此必须在映射时重缩放。
ONET_IMPORTANCE_MIN = 0.0
ONET_IMPORTANCE_MAX = 7.0
ONET_CRITICAL_THRESHOLD_1_5 = 4.0


def onet_importance_to_1_5(raw: float) -> float:
    if raw < ONET_IMPORTANCE_MIN:
        raw = ONET_IMPORTANCE_MIN
    if raw > ONET_IMPORTANCE_MAX:
        raw = ONET_IMPORTANCE_MAX
    return 1.0 + (raw - ONET_IMPORTANCE_MIN) * 4.0 / (ONET_IMPORTANCE_MAX - ONET_IMPORTANCE_MIN)


# O*NET 的 Work Context CX 量表为 1–5，映射到 0–100
def onet_cx_to_0_100(raw: float) -> float:
    if raw < 1.0:
        raw = 1.0
    if raw > 5.0:
        raw = 5.0
    return (raw - 1.0) * 25.0


# O*NET 兴趣量表（OI）为 1–7，映射到 0–100
def onet_oi_to_0_100(raw: float) -> float:
    if raw < 1.0:
        raw = 1.0
    if raw > 7.0:
        raw = 7.0
    return (raw - 1.0) * (100.0 / 6.0)
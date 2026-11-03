"""种子职业库。仅供演示/测试，非生产数据。occupation_family 取自受控的 20 族列表。"""
from ..models import Occupation


FAMILIES = [
    "信息技术与数字技术", "工程与制造", "商业与行政管理", "金融与会计",
    "健康服务", "教育与培训", "法律与公共安全", "科学研究",
    "艺术设计与传媒", "社会服务", "销售与客户服务", "供应链与物流",
    "建筑与房地产", "农业与环境", "交通与运维", "人力资源",
    "市场营销与公关", "体育与休闲", "旅游与酒店", "其他专业服务",
]


def load_seed_occupations() -> list[Occupation]:
    return [
        Occupation(
            occupation_id="CN-2022-2-02-10-08",
            preferred_name="软件工程师",
            occupation_family="信息技术与数字技术",
            taxonomy_refs={"cn_dadian_2022": {"major_group": "2", "detailed_code": "2-02-10-08"},
                           "onet_soc_2018": {"soc_code": "15-1252.00", "data_level": True}},
            riasec_profile={"R": 30, "I": 85, "A": 40, "S": 35, "E": 45, "C": 70},
            skill_vector=[
                {"skill_id": "programming_python", "importance": 5, "critical": True},
                {"skill_id": "algorithms",         "importance": 4, "critical": True},
                {"skill_id": "database_sql",       "importance": 4, "critical": False},
                {"skill_id": "git_versioning",     "importance": 3, "critical": False},
            ],
            typical_requirements={"entry_education": "bachelor", "work_experience": "none", "job_zone": 4},
            work_context={"indoor_vs_outdoor": 95, "teamwork_vs_independent": 60, "job_autonomy": 75},
            entry_barriers={"license_required": False, "minimum_degree_hard_requirement": "bachelor"},
        ),
        Occupation(
            occupation_id="CN-2022-2-02-10-01",
            preferred_name="数据分析师",
            occupation_family="信息技术与数字技术",
            taxonomy_refs={"onet_soc_2018": {"soc_code": "15-2051.00", "data_level": True}},
            riasec_profile={"R": 25, "I": 80, "A": 30, "S": 40, "E": 40, "C": 75},
            skill_vector=[
                {"skill_id": "database_sql",         "importance": 5, "critical": True},
                {"skill_id": "statistics",           "importance": 4, "critical": True},
                {"skill_id": "spreadsheet_excel",    "importance": 4, "critical": False},
                {"skill_id": "programming_python",   "importance": 3, "critical": False},
            ],
            typical_requirements={"entry_education": "bachelor", "work_experience": "none", "job_zone": 4},
            work_context={"indoor_vs_outdoor": 95, "teamwork_vs_independent": 55, "job_autonomy": 60},
            entry_barriers={"license_required": False},
        ),
        Occupation(
            occupation_id="CN-2022-3-01-05-02",
            preferred_name="行政专员",
            occupation_family="商业与行政管理",
            taxonomy_refs={},
            riasec_profile={"R": 15, "I": 30, "A": 25, "S": 65, "E": 50, "C": 85},
            skill_vector=[
                {"skill_id": "spreadsheet_excel",     "importance": 4, "critical": False},
                {"skill_id": "written_communication", "importance": 4, "critical": True},
                {"skill_id": "document_management",   "importance": 3, "critical": False},
            ],
            typical_requirements={"entry_education": "associate", "work_experience": "none", "job_zone": 2},
            work_context={"indoor_vs_outdoor": 95, "teamwork_vs_independent": 70, "job_autonomy": 40},
            entry_barriers={"license_required": False},
        ),
        Occupation(
            occupation_id="CN-2022-4-01-02-03",
            preferred_name="护士",
            occupation_family="健康服务",
            taxonomy_refs={},
            riasec_profile={"R": 40, "I": 55, "A": 20, "S": 90, "E": 40, "C": 60},
            skill_vector=[
                {"skill_id": "patient_care",          "importance": 5, "critical": True},
                {"skill_id": "medical_documentation", "importance": 4, "critical": True},
                {"skill_id": "team_coordination",     "importance": 4, "critical": False},
            ],
            typical_requirements={"entry_education": "associate", "work_experience": "none", "job_zone": 3},
            work_context={"indoor_vs_outdoor": 90, "teamwork_vs_independent": 85, "job_autonomy": 50},
            entry_barriers={"license_required": True, "license_note": "需通过护士执业资格考试"},
        ),
        Occupation(
            occupation_id="CN-NEW-TEST-NO-SKILL",
            preferred_name="某新兴职业（测试用）",
            occupation_family="其他专业服务",
            taxonomy_refs={},
            riasec_profile=None,
            skill_vector=None,              # 无技能字段 → 不进匹配空间
            typical_requirements=None,
            work_context=None,
            entry_barriers={"license_required": "unknown"},
            data_quality_flags=["no_skill_vector"],
        ),
    ]
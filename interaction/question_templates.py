"""追问模板库。静态审核文本，不由 LLM 生成（阶段 6 契约 §3.1）。
本模块只定义模板；选取与排序在 question_selector.py。"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class QuestionTemplate:
    template_id: str
    target_fields: tuple[str, ...]
    question_text: str
    input_type: str               # open_text | single_choice | multi_choice
    options: tuple[str, ...] = ()
    priority: int = 9             # 越小越优先


# 阶段 6 契约 §3.3 的 8 个模板，逐字落地
TEMPLATES: tuple[QuestionTemplate, ...] = (
    QuestionTemplate(
        template_id="T_RIASEC_OPEN",
        target_fields=("/interests_riasec/R", "/interests_riasec/I",
                       "/interests_riasec/A", "/interests_riasec/S",
                       "/interests_riasec/E", "/interests_riasec/C"),
        question_text="能再描述一两件你最近做过的、觉得投入或比较擅长的事吗？"
                      "可以是工作、学习或业余活动。",
        input_type="open_text", priority=0,
    ),
    QuestionTemplate(
        template_id="T_SKILL_OPEN",
        target_fields=("/skills",),
        question_text="能列举 2—3 项你在学习或工作中反复用到的技能、工具或方法吗？",
        input_type="open_text", priority=0,
    ),
    QuestionTemplate(
        template_id="T_EDU_YEARS",
        target_fields=("/hard_constraints/max_education_investment_years",),
        question_text="你未来几年内，愿意为学历提升投入的最长时间是多少？",
        input_type="single_choice",
        options=("不接受额外学习投入", "1 年以内", "2—3 年", "4 年及以上"),
        priority=1,
    ),
    QuestionTemplate(
        template_id="T_LICENSE",
        target_fields=("/hard_constraints/license_obtainable",),
        question_text="部分职业需要考取执照或资质证书。你是否愿意为此投入时间与费用？",
        input_type="single_choice",
        options=("愿意", "不愿意", "取决于具体职业"),
        priority=1,
    ),
    QuestionTemplate(
        template_id="T_REGION",
        target_fields=("/hard_constraints/region",),
        question_text="你希望在哪个城市或地区工作？",
        input_type="multi_choice",
        options=("北京", "上海", "广州", "深圳", "杭州", "成都", "不限", "其他"),
        priority=1,
    ),
    QuestionTemplate(
        template_id="T_ECON",
        target_fields=("/hard_constraints/economic_pressure_period",),
        question_text="你需要在多长时间内开始有收入？",
        input_type="single_choice",
        options=("3 个月内", "6 个月内", "1 年内", "1 年以上或不着急"),
        priority=1,
    ),
    QuestionTemplate(
        template_id="T_VALUES",
        target_fields=("/values_weights/salary", "/values_weights/stability",
                       "/values_weights/growth", "/values_weights/autonomy",
                       "/values_weights/social_impact"),
        question_text="在找工作这件事上，以下哪一项对你最重要？",
        input_type="single_choice",
        options=("薪资", "稳定性", "成长性", "自主性", "社会价值", "说不清"),
        priority=2,
    ),
    QuestionTemplate(
        template_id="T_WORKSTYLE",
        target_fields=("/work_style_preferences/indoor_outdoor",
                       "/work_style_preferences/team_independent",
                       "/work_style_preferences/travel_tolerance"),
        question_text="你更希望工作以什么方式进行？",
        input_type="multi_choice",
        options=("多数时间室内", "多数时间户外", "团队协作多",
                 "独立完成多", "能接受频繁出差"),
        priority=3,
    ),
)

SKIP_HINT = "不回答也可以，该项将标记为『你未提供』，匹配时按中性处理，结果中会标注。"
"""端到端演示：L1 stub → L2 → L3 → L4 stub → 校验。"""
from datetime import datetime, timezone

from career_advisor.models import (UserProfile, EvidenceValue, Prospect,
                                    IndicatorType, FieldProvenance)
from career_advisor.data.seeds import load_seed_occupations
from career_advisor.matching.config import ScoringConfig
from career_advisor.matching.engine import match
from career_advisor.coverage import build_coverage, DISCLAIMER, LICENSE_NOTE
from career_advisor.explanation.input_builder import build_explanation_input
from career_advisor.explanation.generator import StubExplanationGenerator
from career_advisor.explanation.validator import validate
from career_advisor.profile.extractor import StubProfileExtractor
from career_advisor.data.seed_loader import snapshot_exists as _snapshot_exists

def make_demo_profile() -> UserProfile:
    return UserProfile(
        profile_id="demo-1",
        hard_constraints={
            "region": EvidenceValue(["杭州"], "目前在杭州，暂时不想离开", "explicit"),
            "education_level": EvidenceValue("bachelor", "本科读的是汉语言文学", "explicit"),
            "license_obtainable": EvidenceValue.missing(),
            "max_education_investment_years": EvidenceValue.missing(),
            "economic_pressure_period": EvidenceValue.missing(),
        },
        interests_riasec={
            "I": EvidenceValue(80, "经常钻研技术问题", "inferred"),
            "C": EvidenceValue(70, "用 Excel 做报表", "inferred"),
            "S": EvidenceValue(60, "沟通协调比较多", "inferred"),
        },
        skills=[
            {"skill_id": "programming_python", "proficiency": "advanced",
             "evidence": "work_experience", "source_span": "实习做过 Python 后端"},
            {"skill_id": "spreadsheet_excel", "proficiency": "intermediate",
             "evidence": "work_experience", "source_span": "用 Excel 做报表"},
        ],
        values_weights={
            "salary": EvidenceValue(0.5, "希望收入稳定", "inferred"),
            "stability": EvidenceValue(0.8, "希望稳定一点", "explicit"),
        },
        exclusions=[],
        missing_fields=[
            "/hard_constraints/license_obtainable",
            "/hard_constraints/max_education_investment_years",
            "/hard_constraints/economic_pressure_period",
            "/interests_riasec/R", "/interests_riasec/A", "/interests_riasec/E",
            "/values_weights/growth", "/values_weights/autonomy",
            "/values_weights/social_impact",
        ],
    )


def make_demo_prospects() -> list[Prospect]:
    now = datetime.now(timezone.utc)
    return [
        Prospect(occupation_id="CN-2022-2-02-10-08",
                 source_name="BLS National Employment Matrix",
                 issuing_authority="U.S. Bureau of Labor Statistics",
                 publication_year=2025, data_year_or_horizon="2024-2034", region="US",
                 indicator_type=IndicatorType.EMPLOYMENT_CHANGE_RATE.value,
                 indicator_value=17.9, indicator_unit="percent",
                 confidence_note="BLS 10-year projection; not a forecast of the future.",
                 provenance=FieldProvenance("BLS-EP-2024-2034",
                                            "https://data.bls.gov/...", now,
                                            "Employment Percent Change, 2024-2034",
                                            "row 42")),
        Prospect(occupation_id="CN-2022-2-02-10-08",
                 source_name="BLS National Employment Matrix",
                 issuing_authority="U.S. Bureau of Labor Statistics",
                 publication_year=2025, data_year_or_horizon="as_of_2024", region="US",
                 indicator_type=IndicatorType.MEDIAN_WAGE.value,
                 indicator_value=133080, indicator_unit="currency_usd",
                 provenance=FieldProvenance("BLS-EP-2024-2034",
                                            "https://data.bls.gov/...", now,
                                            "Median Wage", "row 42")),
    ]


def run_demo():
    profile = make_demo_profile()
    occupations = load_seed_occupations()
    print(f"=== 职业库 ===")
    print(f"  来源: {'快照' if _snapshot_exists() else '手工种子（回退）'}")
    print(f"  总数: {len(occupations)}")
    if _snapshot_exists():
        families = {o.occupation_family for o in occupations}
        with_skills = sum(1 for o in occupations if o.skill_vector)
        print(f"  覆盖族数: {len(families)} / 20")
        print(f"  含技能向量: {with_skills}")
    else:
        print(f"  提示: 未发现 O*NET 快照。运行 "
              f"`python -m career_advisor.data.build_snapshot --onet-dir <路径>` "
              f"以加载真实 O*NET 职业库。")
    print()
    prospects = make_demo_prospects()
    cfg = ScoringConfig()

    result = match(profile, occupations, prospects, cfg)
    print(f"=== 匹配状态: {result.status} ===")
    print(f"配置哈希: {result.scoring_config_hash}")
    print(f"画像哈希: {result.input_profile_hash}\n")

    for item in result.ranked_items:
        print(f"[{item.rank}] {item.occupation_name} ({item.occupation_family})  "
              f"总分 {item.total_score}")
        for k, s in item.sub_scores.items():
            print(f"    {k}: raw={s.raw} w={s.weight_effective} c={s.contribution} "
                  f"{'[不可用]' if not s.available else ''}")
        for ev in item.hard_constraint_eval:
            if ev.status in ("unknown", "soft_penalty"):
                print(f"    [硬约束·{ev.constraint}] {ev.status}: {ev.detail}")
        if item.unmatched_critical_skills:
            print(f"    未命中关键技能: {item.unmatched_critical_skills}")

    print("\n=== 被排除 ===")
    for e in result.excluded_candidates:
        print(f"  {e.occupation_id}: {e.reason_code} — {e.reason_detail}")

    print("\n=== 多样性 ===", result.diversity_report)

    cov = build_coverage(occupations).__dict__
    print("\n=== 覆盖边界 ===")
    print(f"  可匹配职业数: {cov['matchable_occupation_count']} / {cov['total_occupation_count']}")
    print(f"  抽样说明: {cov['sampling_note']}")

    # 对 Top-1 生成解释并校验
    if result.ranked_items:
        generator = StubExplanationGenerator()
        first = result.ranked_items[0]
        occ = next(o for o in occupations if o.occupation_id == first.occupation_id)
        occ_prospects = [p for p in prospects if p.occupation_id == occ.occupation_id]
        exp_input = build_explanation_input(
            first, occ, profile, occ_prospects, cov,
            {"no_data_phrase": "暂无可靠数据",
             "no_trend_phrase": "该职业暂无可靠的前景数据，以下内容不含趋势判断"})
        output = generator.generate(exp_input)
        violations = validate(output, exp_input)
        print(f"\n=== 校验 [{first.occupation_name}] ===")
        print(f"  违规: {violations if violations else '无'}")

    print()
    print(DISCLAIMER)
    if any(item.hard_constraint_eval for item in result.ranked_items):
        print(LICENSE_NOTE)


def run_insufficient_demo():
    """演示 profile_insufficient 分支：L1 stub 抽取出全 null 画像时的行为。"""
    print("\n=== 演示：L1 Stub 返回全 null 画像 ===")
    profile = StubProfileExtractor().extract("我想找个工作。")
    result = match(profile, load_seed_occupations(), [], ScoringConfig())
    print(f"状态: {result.status}")
    print(f"ranked_items: {result.ranked_items}")
    print(f"missing_fields（交互层据此追问，前 5 项）:")
    for f in result.missing_fields[:5]:
        print(f"  - {f}")
    print(f"  ... 共 {len(result.missing_fields)} 项")

ANSWER_VALUES = {
    "T_RIASEC_OPEN": {
        "/interests_riasec/I": 70,
        "/interests_riasec/C": 65,
        "/interests_riasec/S": 55,
    },
    "T_SKILL_OPEN": {
        "/skills": [
            {"skill_id": "spreadsheet_excel", "proficiency": "intermediate",
             "evidence": "self_report", "source_span": "演示输入"},
        ],
    },
    "T_EDU_YEARS": {"/hard_constraints/max_education_investment_years": 0},
    "T_LICENSE":   {"/hard_constraints/license_obtainable": True},
    "T_REGION":    {"/hard_constraints/region": ["杭州"]},
    "T_ECON":      {"/hard_constraints/economic_pressure_period": "within_1y"},
    "T_VALUES":    {"/values_weights/salary": 0.7,
                    "/values_weights/stability": 0.8},
    "T_WORKSTYLE": {"/work_style_preferences/indoor_outdoor": "indoor"},
}

def run_full_interaction_demo():
    """完整链路：L1 → P2 修正 → P3 追问 → L2 → L4 → P6 查询。"""
    from career_advisor.interaction.state_machine import ClarifyStateMachine
    from career_advisor.interaction.profile_review import ProfileReviewer
    from career_advisor.interaction.excluded_query import (
        group_excluded, diversity_rejected, lookup_occupation)

    print("\n" + "=" * 60)
    print("=== 演示：完整交互链路 ===")
    print("=" * 60)

    # 1. L1 Stub
    profile = StubProfileExtractor().extract("我想找个工作。")
    print(f"\n[L1] 抽取出 {len(profile.missing_fields)} 个缺失字段")

    # 2. P2 修正：模拟用户在抽取结果确认页补充一个字段
    reviewer = ProfileReviewer(profile)
    # 实际场景：用户发现 L1 没抽到某字段，主动修正/补充
    print(f"[P2] 用户未做修正")

    # 3. P3 追问：3 轮
    sm = ClarifyStateMachine(reviewer.finalize()).start()
    round_no = 1
    while not sm.is_done() and round_no <= 3:
        qs = sm.current_questions()
        if not qs:
            break
        print(f"\n[P3·第 {round_no} 轮] 追问 {len(qs)} 个问题：")
        for q in qs:
            print(f"  Q({q.template_id}): {q.question_text}")
            print(f"     输入类型: {q.input_type}  选项: {q.options or '无'}")
            print(f"     提示: 跳过将标记为『你未提供』")

        # 只回答本轮第一个；其余跳过
        first = qs[0]
        answer = ANSWER_VALUES.get(first.template_id)
        if answer is not None:
            sm.answer(first.template_id, answer)
            print(f"  → 用户回答 {first.template_id}: {answer}")
        else:
            sm.skip(first.template_id)
            print(f"  → 用户跳过 {first.template_id}（无预设答案）")

        for q in qs[1:]:
            sm.skip(q.template_id)
            print(f"  → 用户跳过 {q.template_id}")
        round_no += 1

    final_profile = sm.session.profile
    print(f"\n[P3 汇总] 已回答/跳过记录: {len(sm.session.history)} 条")
    print(f"[P3 汇总] 字段状态分布: ", end="")
    from collections import Counter
    print(dict(Counter(final_profile.field_status.values())))

    # 4. L2 匹配
    occupations = load_seed_occupations()
    prospects = make_demo_prospects()
    cfg = ScoringConfig()
    result = match(final_profile, occupations, prospects, cfg)
    print(f"\n[L2] 状态: {result.status}，Top-N: {len(result.ranked_items)}")

    # 5. P6 查询
    print(f"\n[P6] 被排除职业（按原因分组）:")
    for code, items in group_excluded(result).items():
        print(f"  {code}:")
        for item in items:
            print(f"    - {item['occupation_id']}: {item['label']} — {item['detail']}")

    div = diversity_rejected(result)
    if div:
        print(f"\n[P6] 因多样性约束挤出:")
        for d in div:
            print(f"  - {d['occupation_id']} ({d['occupation_family']}) 分 {d['total_score']}")

    print(f"\n[P6] 未收录职业查询「脱口秀演员」:")
    print(f"  {lookup_occupation('脱口秀演员', occupations)}")


def run_education_gate_demo():
    """演示修复后的学历硬门槛：用户 bachelor + 投入上限 0 年，
    遇 master 要求的职业应被硬过滤。"""
    from career_advisor.models import Occupation

    profile = make_demo_profile()
    # 构造一个要求 master 的合成职业
    master_occ = Occupation(
        occupation_id="TEST-MASTER-REQ",
        preferred_name="算法研究员（测试用）",
        occupation_family="科学研究",
        riasec_profile={"R": 30, "I": 95, "A": 40, "S": 30, "E": 40, "C": 70},
        skill_vector=[{"skill_id": "statistics", "importance": 5, "critical": True}],
        typical_requirements={"entry_education": "master", "job_zone": 5},
        entry_barriers={"license_required": False},
    )
    profile.hard_constraints["max_education_investment_years"] = \
        EvidenceValue(0, "不想再读书", "explicit")

    result = match(profile, [master_occ], [], ScoringConfig())
    print(f"\n=== 演示：学历硬门槛 ===")
    print(f"用户 education_level=bachelor, max_education_investment_years=0")
    print(f"职业要求: master")
    for e in result.excluded_candidates:
        print(f"  {e.occupation_id}: {e.reason_code} — {e.reason_detail}")


if __name__ == "__main__":
    run_demo()
    run_insufficient_demo()
    run_full_interaction_demo()
    run_education_gate_demo()
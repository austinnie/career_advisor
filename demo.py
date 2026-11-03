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


def make_demo_profile() -> UserProfile:
    return UserProfile(
        profile_id="demo-1",
        hard_constraints={
            "region": EvidenceValue(["杭州"], "目前在杭州，暂时不想离开", "explicit"),
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


if __name__ == "__main__":
    run_demo()
    run_insufficient_demo()
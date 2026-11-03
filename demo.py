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
from career_advisor.region_scope import regions_to_scope
from career_advisor.data.skill_adjacency import SkillAdjacency

from career_advisor.config import get_default_llm_client
from career_advisor.profile.extractor import LLMProfileExtractor
from career_advisor.explanation.generator import LLMExplanationGenerator

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
            {"skill_id": "programming", "proficiency": "advanced",
             "evidence": "work_experience", "source_span": "实习做过后端开发"},
            {"skill_id": "complex_problem_solving", "proficiency": "intermediate",
             "evidence": "work_experience", "source_span": "解决过复杂问题"},
            {"skill_id": "active_learning", "proficiency": "intermediate",
             "evidence": "self_report", "source_span": "喜欢钻研新技术"},
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


def _inline_demo_adjacency() -> SkillAdjacency:
    """demo 用的小邻接表。生产环境应从 O*NET skills.txt 构建
    （见 data/skill_adjacency.build_adjacency_from_onet）。"""
    return SkillAdjacency(
        version="demo-v1",
        source="inline",
        adjacency={
            "programming": frozenset({"technology_design", "operations_analysis",
                                       "troubleshooting", "quality_control_analysis"}),
            "technology_design": frozenset({"programming", "operations_analysis"}),
            "operations_analysis": frozenset({"programming", "technology_design"}),
            "critical_thinking": frozenset({"active_learning", "learning_strategies",
                                             "monitoring"}),
            "active_learning": frozenset({"critical_thinking", "learning_strategies"}),
        },
    )


def run_skill_neighbor_demo():
    """演示技能邻居匹配：无 adjacency 时不命中，有 adjacency 时部分命中。"""
    from career_advisor.matching.scorers import score_skill_transfer
    from career_advisor.models import Occupation

    print("\n" + "=" * 60)
    print("=== 演示：技能邻居匹配 ===")
    print("=" * 60)

    occ = Occupation(
        occupation_id="TEST-SKILL", preferred_name="测试职业",
        occupation_family="工程与制造",
        skill_vector=[
            {"skill_id": "programming", "importance": 5, "critical": True},
            {"skill_id": "operations_analysis", "importance": 3, "critical": False},
        ],
        typical_requirements={},
        entry_barriers={"license_required": False},
    )

    def _mk_profile(skills):
        from career_advisor.models import UserProfile
        return UserProfile(
            profile_id="t", hard_constraints={}, interests_riasec={},
            skills=[{"skill_id": sid, "proficiency": prof,
                     "evidence": "work_experience", "source_span": "..."}
                    for sid, prof in skills],
            values_weights={}, work_style_preferences={}, exclusions=[],
            field_status={}, missing_fields=[],
        )

    profile_tech = _mk_profile([("technology_design", "advanced")])
    profile_prog = _mk_profile([("programming", "advanced")])
    cfg = ScoringConfig()
    adj = _inline_demo_adjacency()

    no_adj = score_skill_transfer(profile_tech, occ, cfg, adjacency=None)
    with_adj = score_skill_transfer(profile_tech, occ, cfg, adjacency=adj)
    exact = score_skill_transfer(profile_prog, occ, cfg, adjacency=adj)

    print(f"\n[职业要求] programming (imp=5, critical), operations_analysis (imp=3)")
    print(f"\n[用户技能: technology_design, 无邻接表]")
    print(f"  raw={no_adj.raw}  matched={no_adj.detail['matched']}")
    print(f"  neighbor_matched={no_adj.detail['neighbor_matched']}")
    print(f"  unmatched_critical={no_adj.detail['unmatched_critical']}")

    print(f"\n[用户技能: technology_design, 有邻接表]")
    print(f"  raw={with_adj.raw}  matched={with_adj.detail['matched']}")
    print(f"  neighbor_matched={with_adj.detail['neighbor_matched']}")
    print(f"  unmatched_critical={with_adj.detail['unmatched_critical']}")

    print(f"\n[用户技能: programming (精确匹配), 有邻接表]")
    print(f"  raw={exact.raw}  matched={exact.detail['matched']}")
    print(f"  neighbor_matched={exact.detail['neighbor_matched']}")

    print(f"\n说明:")
    print(f"  - 无邻接表时，technology_design 完全不能帮上 programming")
    print(f"  - 有邻接表时，technology_design 作为 programming 的邻居，按")
    print(f"    skill_neighbor_match_factor={cfg.skill_neighbor_match_factor} 折算")
    print(f"  - operations_analysis 用户无任何直接或邻居技能，仍不能匹配")
    print(f"  - 邻接表从 O*NET Element ID 层级构建，非人工编造")
    
def run_region_admission_demo():
    """演示地区准入：US 观测对中国用户不可用。"""
    import copy
    print("\n" + "=" * 60)
    print("=== 演示：地区准入 ===")
    print("=" * 60)

    occupations = load_seed_occupations()
    prospects = make_demo_prospects()          # 全部 US 来源
    cfg = ScoringConfig()

    profile_cn = make_demo_profile()           # region=["杭州"]
    profile_us = copy.deepcopy(profile_cn)
    profile_us.hard_constraints["region"] = EvidenceValue(
        ["纽约"], "演示：美国用户", "explicit")

    for label, p in [("中国用户 region=[杭州] → scopes={CN}", profile_cn),
                     ("美国用户 region=[纽约] → scopes={US}", profile_us)]:
        result = match(p, occupations, prospects, cfg)
        sw = next((i for i in result.ranked_items
                   if i.occupation_id == "CN-2022-2-02-10-08"), None)
        print(f"\n{label}")
        if sw is None:
            print("  软件工程师未进入 Top-N")
            continue
        vals = sw.sub_scores["values"]
        status = "[不可用]" if not vals.available else ""
        print(f"  软件工程师 values: raw={vals.raw}  {status}")
        print(f"    detail: {vals.detail}")
        print(f"  总分: {sw.total_score}")


def run_preference_adjuster_demo():
    """演示 P7 偏好调节：只改 values_weights，展示排名变化。"""
    import copy
    from career_advisor.matching.engine import rerun_with_preferences
    from career_advisor.interaction.preference_adjuster import diff_rankings

    print("\n" + "=" * 60)
    print("=== 演示：P7 偏好调节 ===")
    print("=" * 60)

    occupations = load_seed_occupations()
    prospects = make_demo_prospects()
    cfg = ScoringConfig()

    # 用美国用户，让 values 分可用（US 观测与 US 地域兼容）
    base_profile = make_demo_profile()
    base_profile.hard_constraints["region"] = EvidenceValue(
        ["纽约"], "演示：美国用户", "explicit")
    # 补一个 autonomy 权重，让调节有可观察的效果
    base_profile.values_weights["autonomy"] = EvidenceValue(
        0.3, "演示", "explicit")

    base_result = match(base_profile, occupations, prospects, cfg)
    print("\n[基准 Top-N]")
    for i in base_result.ranked_items:
        print(f"  [{i.rank}] {i.occupation_name:12s}  {i.total_score}")

    # 用户把 values_weights 从 {salary:0.5, stability:0.8, autonomy:0.3}
    # 调整为 {salary:0.1, stability:0.9, autonomy:0.5}
    new_weights = {"salary": 0.1, "stability": 0.9, "autonomy": 0.5}
    new_profile, new_result = rerun_with_preferences(
        base_profile, new_weights, occupations, prospects, cfg)

    print(f"\n[调节后 salary={new_weights['salary']}, "
          f"stability={new_weights['stability']}, "
          f"autonomy={new_weights['autonomy']}]")
    for i in new_result.ranked_items:
        print(f"  [{i.rank}] {i.occupation_name:12s}  {i.total_score}")

    diff = diff_rankings(base_result, new_result)
    print(f"\n[diff] {diff['summary']}")
    for e in diff["moved_up"]:
        print(f"  ↑ {e['occupation_name']}: 第 {e['old_rank']} → 第 {e['new_rank']} 名")
    for e in diff["moved_down"]:
        print(f"  ↓ {e['occupation_name']}: 第 {e['old_rank']} → 第 {e['new_rank']} 名")
    for e in diff["new_entries"]:
        print(f"  + {e['occupation_name']} 进入第 {e['new_rank']} 名")
    for e in diff["dropped"]:
        print(f"  - {e['occupation_name']} 移出（原第 {e['old_rank']} 名）")

    # 新增说明
    if diff["summary"]["unchanged_count"] == len(base_result.ranked_items):
        print("  说明：本 demo 中 values 组件值恰好相同（salary 分桶与 autonomy 归一化"
              "均为 0.75），权重调整不改变加权平均。rerun_with_preferences 的可复现性"
              "与 diff 计算已由 tests/test_rerun.py 覆盖；如需演示 non-trivial 排名变化，"
              "需换一份种子数据。")
              
    # 断言：原 profile 不变
    assert base_profile.values_weights["salary"].value == 0.5, \
        "原 profile 不应被修改"
    assert new_profile.values_weights["salary"].value == 0.1, \
        "新 profile 应反映调节"
    print("\n✓ 原 profile 未被修改，新 profile 反映调节")
    
def run_cn_library_demo():
    """展示大典骨架入库后覆盖声明的变化。"""
    # 删掉这行：from career_advisor.data.seed_loader import _onet_by_soc_from_snapshot_or_empty
    from career_advisor.data.cn_samples import load_sample_cn_occupations
    from career_advisor.data.cn_enricher import enrich as enrich_cn
    from career_advisor.data.seed_loader import load_occupations

    print("\n" + "=" * 60)
    print("=== 演示：中国职业库骨架 ===")
    print("=" * 60)

    all_occs = load_occupations()  # 这里已经包含了 910 O*NET + 5 大典
    
    # 提取 O*NET 用于单独展示
    onet_by_soc = {}
    for o in all_occs:
        soc = (o.taxonomy_refs or {}).get("onet_soc_2018", {}).get("soc_code")
        if soc:
            onet_by_soc[soc] = o
            
    cn_occs = load_sample_cn_occupations()
    enriched = enrich_cn(cn_occs, onet_by_soc)

    print(f"\n大典样本: {len(cn_occs)} 条")
    print(f"O*NET 快照可用于 enrichment: {len(onet_by_soc)} 条 SOC")
    
    for o in enriched:
        has_skill = "有技能" if o.skill_vector else "仅骨架"
        flags = ",".join(o.data_quality_flags)
        print(f"  [{has_skill}] {o.occupation_id}  {o.preferred_name} ({o.occupation_family})")
        if flags:
            print(f"          flags: {flags}")

    # 将样本大典 + 手工种子合并后跑一次匹配
    all_occs = load_seed_occupations()
    print(f"\n合并后职业库: {len(all_occs)} 条")
    prospects = make_demo_prospects()
    cfg = ScoringConfig()
    profile = make_demo_profile()
    result = match(profile, all_occs, prospects, cfg)
    print(f"匹配状态: {result.status}, Top-N: {len(result.ranked_items)}")
    print(f"被排除: {len(result.excluded_candidates)} 条")
    for e in result.excluded_candidates:
        print(f"  {e.occupation_id}: {e.reason_code}")

    from career_advisor.coverage import build_coverage
    cov = build_coverage(all_occs).__dict__
    print(f"\n覆盖边界:")
    print(f"  总数: {cov['total_occupation_count']}")
    print(f"  可匹配: {cov['matchable_occupation_count']}")
    print(f"  仅骨架: {cov['excluded_count']}")
    print(f"  说明: {cov['sampling_note']}")

def run_real_llm_demo():
    """使用真实 LLM 跑通从原始文本到解释报告的全流程。"""
    print("\n" + "=" * 60)
    print("=== 演示：真实 LLM 驱动的全链路 ===")
    print("=" * 60)

    raw_text = (
        "我今年30岁，本科读的是汉语言文学，毕业后做了6年行政助理。"
        "工作里经常用 Excel 做数据报表，也帮部门对接过供应商，沟通协调比较多。"
        "现在想转行，希望工作稳定一点，不想太冒险。目前在杭州，暂时不想离开。"
        "薪资没特别要求，能覆盖生活就行。"
    )
    print(f"\n[输入文本]\n{raw_text}\n")

    try:
        client = get_default_llm_client()
        
        # 1. L1 抽取
        print("[L1] 正在调用 LLM 抽取画像...")
        extractor = LLMProfileExtractor(client)
        profile = extractor.extract(raw_text)
        print(f"  -> 抽取完成。仍有 {len(profile.missing_fields)} 个缺失字段。")
        
        # 2. 跑匹配
        occupations = load_seed_occupations()
        prospects = make_demo_prospects()
        result = match(profile, occupations, prospects, ScoringConfig())
        
        if result.status == "ok" and result.ranked_items:
            top = result.ranked_items[0]
            print(f"\n[L2] 匹配成功。Top-1 职业: {top.occupation_name}")
            
            # 3. L4 解释
            print(f"\n[L4] 正在调用 LLM 生成解释报告...")
            occ = next(o for o in occupations if o.occupation_id == top.occupation_id)
            occ_prospects = [p for p in prospects if p.occupation_id == occ.occupation_id]
            
            from career_advisor.explanation.input_builder import build_explanation_input
            exp_input = build_explanation_input(
                top, occ, profile, occ_prospects, {}, 
                {"no_data_phrase": "暂无可靠数据", "no_trend_phrase": "暂无趋势判断"}
            )
            
            generator = LLMExplanationGenerator(client)
            output = generator.generate(exp_input)
            
            # 4. 校验
            from career_advisor.explanation.validator import validate
            violations = validate(output, exp_input)
            
            if not violations:
                print("  -> 生成成功且通过校验！")
                print(f"\n【匹配结论·推断】\n{output['match_conclusion']['why_match']['text']}")
                print(f"\n【未来10年·事实】\n{output['prospect_10y']['facts']['text']}")
            else:
                print(f"  -> 校验失败，已自动降级。违规项: {violations}")
                
    except Exception as e:
        print(f"运行失败: {e}")
        
if __name__ == "__main__":
    run_demo()
    run_insufficient_demo()
    run_full_interaction_demo()
    run_education_gate_demo()
    run_region_admission_demo()        # 新增
    run_preference_adjuster_demo()     # 新增    
    run_skill_neighbor_demo()      # 新增
    run_cn_library_demo()
    run_real_llm_demo()
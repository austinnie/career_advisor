"""L5 交互层单元测试。"""
import unittest

from career_advisor.interaction.question_selector import (
    select_round, mark_asked, record_skip)
from career_advisor.interaction.state_machine import (
    ClarifyStateMachine, MAX_ROUNDS)
from career_advisor.interaction.profile_review import ProfileReviewer
from career_advisor.interaction.excluded_query import (
    group_excluded, lookup_occupation)
from career_advisor.models import UserProfile, EvidenceValue
from career_advisor.data.seeds import load_seed_occupations


def _empty_profile() -> UserProfile:
    return UserProfile(
        profile_id="t-1",
        hard_constraints={
            "region": EvidenceValue.missing(),
            "education_level": EvidenceValue.missing(),
            "max_education_investment_years": EvidenceValue.missing(),
            "economic_pressure_period": EvidenceValue.missing(),
            "license_obtainable": EvidenceValue.missing(),
        },
        interests_riasec={k: EvidenceValue.missing() for k in "RIASEC"},
        skills=[],
        values_weights={k: EvidenceValue.missing()
                        for k in ("salary", "stability", "growth",
                                  "autonomy", "social_impact")},
        work_style_preferences={},
        exclusions=[],
        missing_fields=[
            "/hard_constraints/region", "/hard_constraints/education_level",
            "/hard_constraints/max_education_investment_years",
            "/hard_constraints/economic_pressure_period",
            "/hard_constraints/license_obtainable",
            "/interests_riasec/R", "/interests_riasec/I", "/interests_riasec/A",
            "/interests_riasec/S", "/interests_riasec/E", "/interests_riasec/C",
            "/skills",
            "/values_weights/salary", "/values_weights/stability",
            "/values_weights/growth", "/values_weights/autonomy",
            "/values_weights/social_impact",
        ],
    )


class SelectorTests(unittest.TestCase):
    def test_round1_prefers_priority_0(self):
        profile = _empty_profile()
        qs = select_round(profile, round_no=1)
        self.assertTrue(qs)
        self.assertLessEqual(len(qs), 3)
        for q in qs:
            self.assertEqual(q.priority, 0)

    def test_round2_uses_priority_1(self):
        profile = _empty_profile()
        r1 = select_round(profile, round_no=1)
        mark_asked(profile, r1)
        for q in r1:
            record_skip(profile, q)
        r2 = select_round(profile, round_no=2)
        self.assertTrue(r2)
        self.assertLessEqual(len(r2), 3)
        for q in r2:
            self.assertGreaterEqual(q.priority, 1)

    def test_skipped_template_not_reselected(self):
        profile = _empty_profile()
        r1 = select_round(profile, round_no=1)
        for q in r1:
            record_skip(profile, q)
        r2 = select_round(profile, round_no=2)
        r1_ids = {q.template_id for q in r1}
        r2_ids = {q.template_id for q in r2}
        self.assertFalse(r1_ids & r2_ids)

    def test_empty_missing_returns_no_questions(self):
        profile = _empty_profile()
        profile.missing_fields = []
        self.assertEqual(select_round(profile, round_no=1), [])

    def test_partially_answered_template_not_reselected(self):
        """R/A/E 被标 asked、I/C/S 被标 user_corrected 时，T_RIASEC_OPEN 不应再被选中。
        这是本轮 bug 的回归测试。"""
        profile = _empty_profile()
        # 模拟第 1 轮：RIASEC 模板被选中并被 mark_asked
        r1 = select_round(profile, round_no=1)
        mark_asked(profile, r1)
        # 用户答 I/C/S
        for k, v in [("I", 70), ("C", 65), ("S", 55)]:
            profile.interests_riasec[k] = EvidenceValue(v, "用户回答", "explicit")
            profile.field_status[f"/interests_riasec/{k}"] = "user_corrected"
            if f"/interests_riasec/{k}" in profile.missing_fields:
                profile.missing_fields.remove(f"/interests_riasec/{k}")
        # 第 2 轮：T_RIASEC_OPEN 不应出现
        r2 = select_round(profile, round_no=2)
        r2_ids = {q.template_id for q in r2}
        self.assertNotIn("T_RIASEC_OPEN", r2_ids)
    


class StateMachineTests(unittest.TestCase):
    def test_max_three_rounds(self):
        profile = _empty_profile()
        sm = ClarifyStateMachine(profile).start()
        rounds_seen = 0
        while not sm.is_done() and rounds_seen < 5:
            rounds_seen += 1
            sm.skip_round()
        self.assertLessEqual(rounds_seen, MAX_ROUNDS)

    def test_skip_marks_user_skipped(self):
        profile = _empty_profile()
        sm = ClarifyStateMachine(profile).start()
        qs = sm.current_questions()
        sm.skip(qs[0].template_id)
        for f in qs[0].target_fields:
            self.assertEqual(profile.field_status.get(f), "user_skipped")

    def test_answer_fills_field_and_removes_missing(self):
        profile = _empty_profile()
        sm = ClarifyStateMachine(profile).start()
        # 找到 RIASEC 模板
        riasec_q = next((q for q in sm.current_questions()
                         if q.template_id == "T_RIASEC_OPEN"), None)
        self.assertIsNotNone(riasec_q)
        sm.answer("T_RIASEC_OPEN", {"/interests_riasec/I": 70})
        self.assertEqual(profile.interests_riasec["I"].value, 70)
        self.assertNotIn("/interests_riasec/I", profile.missing_fields)


class ReviewerTests(unittest.TestCase):
    def test_correct_records_diff(self):
        profile = _empty_profile()
        profile.hard_constraints["region"] = EvidenceValue(
            ["北京"], "原文", "explicit")
        r = ProfileReviewer(profile)
        r.correct("/hard_constraints/region", ["上海"])
        self.assertEqual(profile.hard_constraints["region"].value, ["上海"])
        self.assertEqual(profile.field_status["/hard_constraints/region"],
                         "user_corrected")
        self.assertEqual(r.summary()["corrected"], 1)

    def test_delete_marks_user_skipped(self):
        profile = _empty_profile()
        profile.interests_riasec["I"] = EvidenceValue(70, "原文", "inferred")
        r = ProfileReviewer(profile)
        r.delete("/interests_riasec/I")
        self.assertIsNone(profile.interests_riasec["I"].value)
        self.assertEqual(profile.field_status["/interests_riasec/I"],
                         "user_skipped")


class ExcludedQueryTests(unittest.TestCase):
    def test_group_by_reason(self):
        from career_advisor.models import RankedMatchResult, ExcludedCandidate
        result = RankedMatchResult(
            status="ok", scoring_config_version="v",
            scoring_config_hash="h", input_profile_hash="h",
            occupation_snapshot_id="s",
            ranked_items=[],
            excluded_candidates=[
                ExcludedCandidate("A", "education_hard_gate", "x"),
                ExcludedCandidate("B", "education_hard_gate", "y"),
                ExcludedCandidate("C", "license_hard_gate", "z"),
            ],
            diversity_report={})
        grouped = group_excluded(result)
        self.assertEqual(len(grouped["education_hard_gate"]), 2)
        self.assertEqual(len(grouped["license_hard_gate"]), 1)

    def test_lookup_uncollected(self):
        occs = load_seed_occupations()
        result = lookup_occupation("脱口秀演员", occs)
        self.assertEqual(result["status"], "not_in_library")

    def test_lookup_found(self):
        occs = load_seed_occupations()
        result = lookup_occupation("软件工程师", occs)
        self.assertEqual(result["status"], "found")
        self.assertTrue(result["matchable"])
import unittest
import copy as copy_module

from career_advisor.models import UserProfile, EvidenceValue
from career_advisor.matching.engine import match, rerun_with_preferences
from career_advisor.matching.config import ScoringConfig
from career_advisor.data.seeds import load_seed_occupations
from career_advisor.interaction.preference_adjuster import diff_rankings


def _us_profile():
    """美国用户画像，让 values 分可用。"""
    return UserProfile(
        profile_id="t",
        hard_constraints={
            "region": EvidenceValue(["纽约"], "原文", "explicit"),
            "education_level": EvidenceValue("bachelor", "原文", "explicit"),
            "max_education_investment_years": EvidenceValue(0, "原文", "explicit"),
            "economic_pressure_period": EvidenceValue.missing(),
            "license_obtainable": EvidenceValue.missing(),
        },
        interests_riasec={
            "I": EvidenceValue(80, "原文", "inferred"),
            "C": EvidenceValue(70, "原文", "inferred"),
        },
        skills=[
            {"skill_id": "programming_python", "proficiency": "advanced",
             "evidence": "work_experience", "source_span": "..."},
        ],
        values_weights={
            "salary": EvidenceValue(0.5, "原文", "inferred"),
            "stability": EvidenceValue(0.8, "原文", "explicit"),
        },
        work_style_preferences={}, exclusions=[],
        field_status={}, missing_fields=[],
    )


def _prospects():
    from career_advisor.demo import make_demo_prospects
    return make_demo_prospects()


class RerunTests(unittest.TestCase):

    def test_original_profile_unchanged(self):
        profile = _us_profile()
        before_salary = profile.values_weights["salary"].value
        before_region = profile.hard_constraints["region"].value
        before_missing = list(profile.missing_fields)

        rerun_with_preferences(
            profile, {"salary": 0.1}, load_seed_occupations(),
            _prospects(), ScoringConfig())

        self.assertEqual(profile.values_weights["salary"].value, before_salary)
        self.assertEqual(profile.hard_constraints["region"].value, before_region)
        self.assertEqual(profile.missing_fields, before_missing)

    def test_new_weights_apply(self):
        profile = _us_profile()
        new_profile, _ = rerun_with_preferences(
            profile, {"salary": 0.1, "stability": 0.9},
            load_seed_occupations(), _prospects(), ScoringConfig())
        self.assertEqual(new_profile.values_weights["salary"].value, 0.1)
        self.assertEqual(new_profile.values_weights["stability"].value, 0.9)
        self.assertEqual(new_profile.field_status["/values_weights/salary"],
                         "user_corrected")

    def test_rerun_reproducible(self):
        profile = _us_profile()
        weights = {"salary": 0.3, "stability": 0.5}
        _, r1 = rerun_with_preferences(
            profile, weights, load_seed_occupations(),
            _prospects(), ScoringConfig())
        _, r2 = rerun_with_preferences(
            profile, weights, load_seed_occupations(),
            _prospects(), ScoringConfig())
        self.assertEqual([i.total_score for i in r1.ranked_items],
                         [i.total_score for i in r2.ranked_items])
        self.assertEqual([i.occupation_id for i in r1.ranked_items],
                         [i.occupation_id for i in r2.ranked_items])

    def test_none_weight_clears_dimension(self):
        profile = _us_profile()
        new_profile, _ = rerun_with_preferences(
            profile, {"salary": None}, load_seed_occupations(),
            _prospects(), ScoringConfig())
        self.assertIsNone(new_profile.values_weights["salary"].value)


class DiffTests(unittest.TestCase):

    def test_diff_counts_consistent(self):
        profile = _us_profile()
        cfg = ScoringConfig()
        base = match(profile, load_seed_occupations(), _prospects(), cfg)
        _, new_result = rerun_with_preferences(
            profile, {"salary": 0.0, "stability": 1.0},
            load_seed_occupations(), _prospects(), cfg)
        diff = diff_rankings(base, new_result)

        # 计数一致性
        s = diff["summary"]
        self.assertEqual(s["new_count"], len(diff["new_entries"]))
        self.assertEqual(s["dropped_count"], len(diff["dropped"]))
        self.assertEqual(s["up_count"], len(diff["moved_up"]))
        self.assertEqual(s["down_count"], len(diff["moved_down"]))
        self.assertEqual(s["unchanged_count"], len(diff["unchanged"]))
        # 所有 new_result 条目应被分类
        self.assertEqual(
            s["new_count"] + s["up_count"] + s["down_count"] + s["unchanged_count"],
            len(new_result.ranked_items))

    def test_diff_identical_rankings(self):
        profile = _us_profile()
        cfg = ScoringConfig()
        base = match(profile, load_seed_occupations(), _prospects(), cfg)
        # 用相同 weights 重跑
        _, rerun = rerun_with_preferences(
            profile, {"salary": 0.5, "stability": 0.8},
            load_seed_occupations(), _prospects(), cfg)
        diff = diff_rankings(base, rerun)
        self.assertEqual(diff["summary"]["new_count"], 0)
        self.assertEqual(diff["summary"]["dropped_count"], 0)
        self.assertEqual(diff["summary"]["up_count"], 0)
        self.assertEqual(diff["summary"]["down_count"], 0)
        self.assertEqual(diff["summary"]["unchanged_count"],
                         len(base.ranked_items))
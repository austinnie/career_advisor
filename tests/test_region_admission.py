import unittest
from datetime import datetime, timezone

from career_advisor.models import (
    UserProfile, EvidenceValue, Prospect, IndicatorType, FieldProvenance)
from career_advisor.matching.engine import match, index_static_observations
from career_advisor.matching.config import ScoringConfig
from career_advisor.data.seeds import load_seed_occupations


def _prospect(occ_id, indicator, value, unit, region):
    now = datetime.now(timezone.utc)
    return Prospect(
        occupation_id=occ_id,
        source_name="TestSource",
        issuing_authority="TestAuthority",
        publication_year=2025,
        data_year_or_horizon="as_of_2024",
        region=region,
        indicator_type=indicator,
        indicator_value=value,
        indicator_unit=unit,
        provenance=FieldProvenance("test", "test", now, "col", "row"),
    )


def _profile_cn():
    return UserProfile(
        profile_id="t",
        hard_constraints={
            "region": EvidenceValue(["杭州"], "原文", "explicit"),
            "education_level": EvidenceValue.missing(),
            "max_education_investment_years": EvidenceValue.missing(),
            "economic_pressure_period": EvidenceValue.missing(),
            "license_obtainable": EvidenceValue.missing(),
        },
        interests_riasec={
            "I": EvidenceValue(80, "原文", "inferred"),
            "C": EvidenceValue(70, "原文", "inferred"),
        },
        skills=[{"skill_id": "programming", "proficiency": "advanced",
                 "evidence": "work_experience", "source_span": "..."}],
        values_weights={"salary": EvidenceValue(0.5, "原文", "inferred")},
        work_style_preferences={}, exclusions=[],
        field_status={}, missing_fields=[],
    )


class IndexFilterTests(unittest.TestCase):

    def test_index_filters_us_obs_for_cn_scope(self):
        p = [_prospect("X", IndicatorType.MEDIAN_WAGE.value,
                       100000, "currency_usd", "US")]
        idx = index_static_observations(p, user_scopes={"CN"})
        self.assertNotIn("X", idx)

    def test_index_keeps_us_obs_for_us_scope(self):
        p = [_prospect("X", IndicatorType.MEDIAN_WAGE.value,
                       100000, "currency_usd", "US")]
        idx = index_static_observations(p, user_scopes={"US"})
        self.assertIn("X", idx)
        self.assertEqual(idx["X"]["median_wage"], 100000)

    def test_index_global_obs_always_kept(self):
        p = [_prospect("X", IndicatorType.EMPLOYMENT_SIZE_CURRENT.value,
                       50000, "persons", "global")]
        idx = index_static_observations(p, user_scopes={"CN"})
        self.assertIn("X", idx)

    def test_index_no_check_when_scopes_none(self):
        """user_scopes=None 保持向后兼容，不做地区检查。"""
        p = [_prospect("X", IndicatorType.MEDIAN_WAGE.value,
                       100000, "currency_usd", "US")]
        idx = index_static_observations(p, user_scopes=None)
        self.assertIn("X", idx)


class MatchRegionAdmissionTests(unittest.TestCase):

    def test_cn_user_rejects_us_observations(self):
        """中国用户画像 + 仅 US 观测 → values 分不可用。"""
        occupations = load_seed_occupations()
        prospects = [
            _prospect("CN-2022-2-02-10-08", IndicatorType.MEDIAN_WAGE.value,
                      133080, "currency_usd", "US"),
        ]
        result = match(_profile_cn(), occupations, prospects, ScoringConfig())
        sw = next((i for i in result.ranked_items
                   if i.occupation_id == "CN-2022-2-02-10-08"), None)
        self.assertIsNotNone(sw)
        self.assertFalse(sw.sub_scores["values"].available)

    def test_cn_user_accepts_cn_observations(self):
        """中国用户画像 + CN 观测 → values 分可用。"""
        occupations = load_seed_occupations()
        prospects = [
            _prospect("CN-2022-2-02-10-08", IndicatorType.MEDIAN_WAGE.value,
                      30000, "currency_cny", "CN"),
        ]
        result = match(_profile_cn(), occupations, prospects, ScoringConfig())
        sw = next((i for i in result.ranked_items
                   if i.occupation_id == "CN-2022-2-02-10-08"), None)
        self.assertIsNotNone(sw)
        self.assertTrue(sw.sub_scores["values"].available)
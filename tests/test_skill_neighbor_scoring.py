import unittest

from career_advisor.data.skill_adjacency import SkillAdjacency
from career_advisor.matching.config import ScoringConfig
from career_advisor.matching.scorers import score_skill_transfer
from career_advisor.models import Occupation, UserProfile


def _occ():
    return Occupation(
        occupation_id="T", preferred_name="T", occupation_family="工程与制造",
        skill_vector=[
            {"skill_id": "programming", "importance": 5, "critical": True},
            {"skill_id": "operations_analysis", "importance": 3, "critical": False},
        ],
        typical_requirements={},
        entry_barriers={"license_required": False},
    )


def _profile(skills):
    return UserProfile(
        profile_id="p", hard_constraints={}, interests_riasec={},
        skills=[{"skill_id": sid, "proficiency": prof,
                 "evidence": "work_experience", "source_span": "..."}
                for sid, prof in skills],
        values_weights={}, work_style_preferences={}, exclusions=[],
        field_status={}, missing_fields=[],
    )


def _adjacency():
    return SkillAdjacency(
        version="test", source="test",
        adjacency={"programming": frozenset({"technology_design"}),
                   "technology_design": frozenset({"programming"})},
    )


class BackwardCompatTests(unittest.TestCase):
    def test_no_adjacency_exact_match_unchanged(self):
        """adjacency=None 时，精确匹配行为与之前完全一致。"""
        cfg = ScoringConfig()
        s = score_skill_transfer(_profile([("programming", "advanced")]),
                                  _occ(), cfg, adjacency=None)
        # programming 权重 5/8，exact 1.0，advanced 0.9
        expected = round(5 / 8 * 1.0 * 0.9, 6)
        self.assertEqual(s.raw, expected)
        self.assertEqual(s.detail["matched"], ["programming"])
        self.assertEqual(s.detail["neighbor_matched"], [])
        self.assertEqual(s.detail["unmatched_critical"], [])

    def test_no_adjacency_unmatched_critical(self):
        """adjacency=None 时，无精确匹配的关键技能记入 unmatched_critical。"""
        cfg = ScoringConfig()
        s = score_skill_transfer(_profile([("technology_design", "advanced")]),
                                  _occ(), cfg, adjacency=None)
        self.assertEqual(s.raw, 0.0)
        self.assertIn("programming", s.detail["unmatched_critical"])


class NeighborMatchTests(unittest.TestCase):
    def test_neighbor_match_produces_partial_score(self):
        cfg = ScoringConfig()
        s = score_skill_transfer(_profile([("technology_design", "advanced")]),
                                  _occ(), cfg, adjacency=_adjacency())
        # programming 邻居命中：imp 5/8 × neighbor_factor 0.5 × advanced 0.9
        expected = round(5 / 8 * 0.5 * 0.9, 6)
        self.assertEqual(s.raw, expected)
        self.assertIn("programming(neighbor)", s.detail["neighbor_matched"])
        self.assertEqual(s.detail["unmatched_critical"], [])

    def test_exact_match_still_beats_neighbor(self):
        """精确匹配产生的分数应高于邻居匹配。"""
        cfg = ScoringConfig()
        exact = score_skill_transfer(_profile([("programming", "advanced")]),
                                      _occ(), cfg, adjacency=_adjacency())
        neighbor = score_skill_transfer(_profile([("technology_design", "advanced")]),
                                         _occ(), cfg, adjacency=_adjacency())
        self.assertGreater(exact.raw, neighbor.raw)

    def test_neighbor_factor_zero_disables(self):
        """skill_neighbor_match_factor=0.0 时邻居匹配不贡献分数。"""
        from dataclasses import replace
        cfg = replace(ScoringConfig(), skill_neighbor_match_factor=0.0)
        s = score_skill_transfer(_profile([("technology_design", "advanced")]),
                                  _occ(), cfg, adjacency=_adjacency())
        # 仍会记入 neighbor_matched，但贡献为 0
        self.assertEqual(s.raw, 0.0)
        self.assertIn("programming(neighbor)", s.detail["neighbor_matched"])

    def test_reproducible(self):
        cfg = ScoringConfig()
        s1 = score_skill_transfer(_profile([("technology_design", "advanced")]),
                                   _occ(), cfg, adjacency=_adjacency())
        s2 = score_skill_transfer(_profile([("technology_design", "advanced")]),
                                   _occ(), cfg, adjacency=_adjacency())
        self.assertEqual(s1.raw, s2.raw)
        self.assertEqual(s1.detail, s2.detail)

    def test_best_neighbor_proficiency_picked(self):
        """多个邻居命中时，取最高熟练度。"""
        cfg = ScoringConfig()
        s = score_skill_transfer(
            _profile([("technology_design", "expert")]),
            _occ(), cfg, adjacency=_adjacency())
        expected = round(5 / 8 * 0.5 * 1.0, 6)
        self.assertEqual(s.raw, expected)
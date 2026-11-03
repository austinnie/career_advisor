import unittest

from career_advisor.coverage import build_coverage
from career_advisor.models import Occupation


def _occ(oid, has_skills, source="cn_dadian"):
    refs = {"cn_dadian_2022": {"detailed_code": oid}} if source == "cn_dadian" \
        else {"onet_soc_2018": {"soc_code": oid}}
    return Occupation(
        occupation_id=oid, preferred_name=oid, occupation_family="工程与制造",
        taxonomy_refs=refs,
        skill_vector=[{"skill_id": "x", "importance": 3, "critical": False}] if has_skills else None,
    )


class CoverageTests(unittest.TestCase):
    def test_counts_separate(self):
        occs = [_occ("a", True), _occ("b", False), _occ("c", False, source="onet")]
        cov = build_coverage(occs)
        self.assertEqual(cov.total_occupation_count, 3)
        self.assertEqual(cov.matchable_occupation_count, 1)
        self.assertEqual(cov.excluded_count, 2)
        self.assertIn("已收录 3", cov.sampling_note)
        self.assertIn("1 个具备结构化技能字段", cov.sampling_note)

    def test_empty_library(self):
        cov = build_coverage([])
        self.assertEqual(cov.total_occupation_count, 0)
        self.assertEqual(cov.matchable_occupation_count, 0)
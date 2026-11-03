import unittest
from dataclasses import dataclass

from career_advisor.data.cn_onet_crosswalk import CROSSWALK
from career_advisor.data.cn_enricher import enrich
from career_advisor.data.cn_samples import load_sample_cn_occupations
from career_advisor.models import Occupation


def _fake_onet(soc, skills):
    return Occupation(
        occupation_id=f"ONET-{soc}", preferred_name="fake", occupation_family="工程与制造",
        taxonomy_refs={"onet_soc_2018": {"soc_code": soc}},
        skill_vector=skills,
        riasec_profile={"I": 80, "C": 70},
        work_context={"job_autonomy": 75},
        typical_requirements={"entry_education": "bachelor", "job_zone": 4},
        entry_barriers={"license_required": "unknown"},
    )


class CrosswalkTests(unittest.TestCase):
    def test_every_entry_has_required_fields(self):
        for code, m in CROSSWALK.items():
            self.assertTrue(m.source, f"{code} missing source")
            self.assertIn(m.confidence, ("high", "medium", "low"))
            self.assertRegex(m.reviewed_at, r"^\d{4}-\d{2}-\d{2}$")


class EnrichmentTests(unittest.TestCase):
    def test_matched_occupation_gains_skills(self):
        cn = load_sample_cn_occupations()
        sw = next(o for o in cn if "软件工程师" in o.preferred_name)
        onet = {"15-1252.00": _fake_onet("15-1252.00",
                                         [{"skill_id": "programming", "importance": 5,
                                           "critical": True}])}
        enriched = enrich(cn, onet)
        sw2 = next(o for o in enriched if "软件工程师" in o.preferred_name)
        self.assertIsNotNone(sw2.skill_vector)
        self.assertIsNotNone(sw2.riasec_profile)
        self.assertEqual(sw2.riasec_profile["I"], 80)
        # license 保持 unknown，不因 O*NET 而推断
        self.assertEqual(sw2.entry_barriers["license_required"], "unknown")
        self.assertTrue(any("cn_onet_crosswalk:high" in f
                            for f in sw2.data_quality_flags))

    def test_unmapped_occupation_unchanged(self):
        cn = [Occupation(
            occupation_id="CN-2022-X", preferred_name="未映射职业",
            occupation_family="其他专业服务",
            taxonomy_refs={"cn_dadian_2022": {"detailed_code": "9-99-99-99"}},
            skill_vector=None,
        )]
        enriched = enrich(cn, {})
        self.assertIsNone(enriched[0].skill_vector)

    def test_mapped_but_no_onet_snapshot_unchanged(self):
        cn = [Occupation(
            occupation_id="CN-2022-2-02-10-08", preferred_name="软件工程师",
            occupation_family="信息技术与数字技术",
            taxonomy_refs={"cn_dadian_2022": {"detailed_code": "2-02-10-08"}},
            skill_vector=None,
        )]
        enriched = enrich(cn, {})  # 空快照
        self.assertIsNone(enriched[0].skill_vector)
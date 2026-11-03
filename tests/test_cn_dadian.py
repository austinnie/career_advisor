import tempfile, unittest
from pathlib import Path

from career_advisor.data.cn_dadian_adapter import (
    CnDadianAdapter, family_for_cn_medium_group)
from career_advisor.data.cn_samples import load_sample_cn_occupations


class AdapterTests(unittest.TestCase):
    def test_parse_sample(self):
        occs = load_sample_cn_occupations()
        self.assertGreater(len(occs), 0)
        sw = next(o for o in occs if "软件工程师" in o.preferred_name)
        self.assertEqual(sw.occupation_family, "信息技术与数字技术")
        self.assertIsNone(sw.skill_vector)
        self.assertIsNone(sw.riasec_profile)
        self.assertEqual(sw.entry_barriers["license_required"], "unknown")
        self.assertIn("cn_dadian_skeleton_only", sw.data_quality_flags)

    def test_missing_column_raises(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "bad.csv"
            bad.write_text("major_group,medium_group\n1,2\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                CnDadianAdapter().normalize_occupations(
                    CnDadianAdapter().fetch(csv_path=str(bad)))

    def test_unmapped_medium_group_skipped(self):
        adapter = CnDadianAdapter()
        payload = adapter.fetch_from_string(
            "major_group,medium_group,minor_group,detailed_code,name,description\n"
            "9,未知中类,99,9-99-99-99,X,某描述\n")
        self.assertEqual(adapter.normalize_occupations(payload), [])

    def test_family_mapping_known(self):
        self.assertEqual(family_for_cn_medium_group("信息传输、软件和信息技术服务人员"),
                         "信息技术与数字技术")

    def test_family_mapping_unknown(self):
        self.assertIsNone(family_for_cn_medium_group("未知中类"))
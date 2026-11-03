"""O*NET 适配器单元测试。使用合成 txt 文件，不依赖真实下载。"""
import tempfile, unittest
from pathlib import Path

from career_advisor.data.onet_adapter import ONetOccupationAdapter


def _write(directory: Path, name: str, content: str):
    (directory / name).write_text(content, encoding="utf-8")


class ONetAdapterTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        # 头部字段与真实 O*NET 格式一致
        _write(self.dir, "occupation_data.txt",
               "O*NET-SOC Code\tTitle\tDescription\tAlternate Titles\n"
               "15-1252.00\tSoftware Developers\t...\tProgrammer\n")
        _write(self.dir, "skills.txt",
               "O*NET-SOC Code\tElement ID\tElement Name\tScale ID\tData Value\n"
               "15-1252.00\t2.A.1.a\tProgramming\tIM\t5.0\n"
               "15-1252.00\t2.A.1.a\tProgramming\tLV\t6.0\n"
               "15-1252.00\t2.B.1.a\tComplex Problem Solving\tIM\t4.5\n")
        _write(self.dir, "interests.txt",
               "O*NET-SOC Code\tElement ID\tElement Name\tScale ID\tData Value\n"
               "15-1252.00\t1.1\tRealistic\tOI\t2.0\n"
               "15-1252.00\t1.2\tInvestigative\tOI\t6.5\n"
               "15-1252.00\t1.3\tArtistic\tOI\t2.5\n"
               "15-1252.00\t1.4\tSocial\tOI\t3.0\n"
               "15-1252.00\t1.5\tEnterprising\tOI\t4.0\n"
               "15-1252.00\t1.6\tConventional\tOI\t5.0\n")
        _write(self.dir, "work_context.txt",
               "O*NET-SOC Code\tElement ID\tElement Name\tScale ID\tData Value\n"
               "15-1252.00\t4.A.1.a.1\tIndoors, Environmentally Controlled\tCX\t4.8\n"
               "15-1252.00\t4.A.2.a.2\tWork With Work Group or Team\tCX\t4.0\n"
               "15-1252.00\t4.A.3.a.1\tFreedom to Make Decisions\tCX\t4.5\n")
        _write(self.dir, "job_zones.txt",
               "O*NET-SOC Code\tJob Zone\n15-1252.00\t4\n")

    def test_normalize_extracts_all_fields(self):
        adapter = ONetOccupationAdapter()
        payload = adapter.fetch(onet_dir=str(self.dir))
        occs = adapter.normalize_occupations(payload)
        self.assertEqual(len(occs), 1)
        o = occs[0]
        self.assertEqual(o.occupation_id, "ONET-15-1252.00")
        self.assertEqual(o.occupation_family, "信息技术与数字技术")
        self.assertEqual(o.riasec_profile["I"], 91.67)   # 6.5 → ~91.67
        self.assertEqual(o.typical_requirements["job_zone"], "4")
        self.assertEqual(o.work_context["indoor_vs_outdoor"], 95.0)   # 4.8 → 95
        # 技能映射：两门技能，Programming importance=5.0 → 1-5 量表 = 1+5*4/7 ≈ 3.86
        skill_ids = {s["skill_id"] for s in o.skill_vector}
        self.assertIn("programming", skill_ids)
        self.assertIn("complex_problem_solving", skill_ids)
        # license_required 恒为 unknown
        self.assertEqual(o.entry_barriers["license_required"], "unknown")

    def test_missing_required_file_raises(self):
        (self.dir / "work_context.txt").unlink()
        with self.assertRaises(FileNotFoundError):
            ONetOccupationAdapter().fetch(onet_dir=str(self.dir))

    def test_unmapped_major_group_is_skipped(self):
        _write(self.dir, "occupation_data.txt",
               "O*NET-SOC Code\tTitle\tDescription\tAlternate Titles\n"
               "99-9999.00\tUnknown\t...\tUnknown\n")
        _write(self.dir, "skills.txt",
               "O*NET-SOC Code\tElement ID\tElement Name\tScale ID\tData Value\n"
               "99-9999.00\t2.A.1.a\tX\tIM\t5.0\n")
        adapter = ONetOccupationAdapter()
        occs = adapter.normalize_occupations(adapter.fetch(onet_dir=str(self.dir)))
        self.assertEqual(occs, [])

    def test_no_prospects_contributed(self):
        adapter = ONetOccupationAdapter()
        self.assertEqual(adapter.normalize_prospects(adapter.fetch(onet_dir=str(self.dir))), [])
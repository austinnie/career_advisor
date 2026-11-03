import tempfile
import unittest
from pathlib import Path

from career_advisor.data.skill_adjacency import (
    SkillAdjacency, build_adjacency_from_onet, save_adjacency, load_adjacency)


_SKILLS_TSV = (
    "O*NET-SOC Code\tElement ID\tElement Name\tScale ID\tData Value\n"
    # 2.B.3 Technical Skills 分组
    "15-1252.00\t2.B.3.b\tTechnology Design\tIM\t4.0\n"
    "15-1252.00\t2.B.3.e\tProgramming\tIM\t5.0\n"
    "15-1252.00\t2.B.3.a\tOperations Analysis\tIM\t3.5\n"
    # 2.B.2 Complex Problem Solving 单技能组（无兄弟）
    "15-1252.00\t2.B.2.a\tComplex Problem Solving\tIM\t5.0\n"
    # 2.A.2 Process Skills 分组
    "15-1252.00\t2.A.2.a\tCritical Thinking\tIM\t4.0\n"
    "15-1252.00\t2.A.2.b\tActive Learning\tIM\t4.0\n"
)


class BuildAdjacencyTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "skills.txt").write_text(_SKILLS_TSV, encoding="utf-8")

    def test_programming_has_siblings(self):
        adj = build_adjacency_from_onet(self.dir)
        neighbors = adj.neighbors("programming")
        self.assertIn("technology_design", neighbors)
        self.assertIn("operations_analysis", neighbors)

    def test_symmetry(self):
        adj = build_adjacency_from_onet(self.dir)
        self.assertTrue(adj.has_neighbor("programming", "technology_design"))
        self.assertTrue(adj.has_neighbor("technology_design", "programming"))

    def test_single_skill_group_has_no_neighbors(self):
        adj = build_adjacency_from_onet(self.dir)
        self.assertEqual(adj.neighbors("complex_problem_solving"), frozenset())

    def test_cross_group_not_neighbors(self):
        """programming（2.B.3）与 critical_thinking（2.A.2）不同父组，不互为邻居。"""
        adj = build_adjacency_from_onet(self.dir)
        self.assertNotIn("critical_thinking", adj.neighbors("programming"))

    def test_process_skills_group(self):
        adj = build_adjacency_from_onet(self.dir)
        self.assertTrue(adj.has_neighbor("critical_thinking", "active_learning"))

    def test_missing_file_raises(self):
        (self.dir / "skills.txt").unlink()
        with self.assertRaises(FileNotFoundError):
            build_adjacency_from_onet(self.dir)


class RoundTripTests(unittest.TestCase):
    def test_save_and_load(self):
        adj = SkillAdjacency(
            version="v1", source="test",
            adjacency={"a": frozenset({"b", "c"}),
                       "b": frozenset({"a"}),
                       "c": frozenset({"a"})})
        path = Path(tempfile.mkdtemp()) / "adj.json"
        save_adjacency(adj, path)
        loaded = load_adjacency(path)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.version, "v1")
        self.assertEqual(loaded.neighbors("a"), frozenset({"b", "c"}))
        self.assertEqual(loaded.neighbors("b"), frozenset({"a"}))

    def test_load_missing_returns_none(self):
        path = Path(tempfile.mkdtemp()) / "nonexistent.json"
        self.assertIsNone(load_adjacency(path))
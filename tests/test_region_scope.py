import unittest
from career_advisor.region_scope import regions_to_scope, is_observation_eligible


class RegionScopeTests(unittest.TestCase):

    def test_cn_city_maps_to_cn(self):
        self.assertEqual(regions_to_scope(["杭州", "北京"]), {"CN"})

    def test_us_city_maps_to_us(self):
        self.assertEqual(regions_to_scope(["纽约", "旧金山"]), {"US"})

    def test_mixed_countries(self):
        self.assertEqual(regions_to_scope(["杭州", "纽约"]), {"CN", "US"})

    def test_unmapped_city_ignored(self):
        self.assertEqual(regions_to_scope(["火星"]), set())

    def test_empty_returns_empty(self):
        self.assertEqual(regions_to_scope(None), set())
        self.assertEqual(regions_to_scope([]), set())

    def test_eligible_matching_region(self):
        self.assertTrue(is_observation_eligible("CN", {"CN"}))
        self.assertTrue(is_observation_eligible("US", {"US"}))

    def test_eligible_global(self):
        self.assertTrue(is_observation_eligible("global", {"CN"}))
        self.assertTrue(is_observation_eligible("global", set()))

    def test_not_eligible_mismatched(self):
        self.assertFalse(is_observation_eligible("US", {"CN"}))
        self.assertFalse(is_observation_eligible("CN", {"US"}))

    def test_not_eligible_empty_scope(self):
        # 用户未提供地域 → 保守不用任何地域特定数值
        self.assertFalse(is_observation_eligible("US", set()))
        self.assertFalse(is_observation_eligible("CN", set()))
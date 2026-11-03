"""ScoringConfig。全部参数冻结，哈希纳入结果。"""
from __future__ import annotations
import hashlib, json
from dataclasses import dataclass, asdict, field


@dataclass(frozen=True)
class ScoringConfig:
    version: str = "scoring-v1.0"

    dimension_weights: dict[str, float] = field(
        default_factory=lambda: {"interest": 0.40, "skill_transfer": 0.40, "values": 0.20})

    interest_min_available_dims: int = 2
    skill_exact_match_factor: float = 1.0
    skill_neighbor_match_factor: float = 0.5
    skill_critical_importance_threshold: int = 4
    skill_proficiency_factors: dict[str, float] = field(
        default_factory=lambda: {"beginner": 0.4, "intermediate": 0.7,
                                 "advanced": 0.9, "expert": 1.0})
    missing_critical_beta: float = 0.15
    license_unknown_soft_penalty: float = 0.05
    education_unknown_soft_penalty: float = 0.03
    economic_pressure_soft_penalty: float = 0.05

    # 学历年限映射（配置数据，非代码常量）
    education_years: dict[str, int] = field(
        default_factory=lambda: {"high_school": 0, "associate": 2,
                                 "bachelor": 4, "master": 6, "phd": 9})

    # 分桶边界（版本化静态配置；不可运行时从数据派生）
    wage_buckets: list[tuple[float, float]] = field(
        default_factory=lambda: [(0, 50_000, 0.2), (50_000, 100_000, 0.5),
                                 (100_000, 150_000, 0.75), (150_000, float("inf"), 1.0)])
    size_buckets: list[tuple[float, float]] = field(
        default_factory=lambda: [(0, 10_000, 0.2), (10_000, 100_000, 0.5),
                                 (100_000, 1_000_000, 0.75), (1_000_000, float("inf"), 1.0)])

    top_n: int = 10
    min_families: int = 3
    score_precision: int = 4

    def max_per_family(self) -> int:
        return max(1, (self.top_n + self.min_families - 1) // self.min_families)

    def hash(self) -> str:
        payload = json.dumps(self._as_hashable(asdict(self)),
                             sort_keys=True, ensure_ascii=False, default=str)
        return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _as_hashable(obj):
        if isinstance(obj, dict):
            return {k: ScoringConfig._as_hashable(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [ScoringConfig._as_hashable(v) for v in obj]
        if isinstance(obj, float) and obj == float("inf"):
            return "Infinity"
        return obj
"""数据模型。所有数值字段缺失时为 None；None 是合法值，不是错误。"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class IndicatorType(str, Enum):
    # 观测类（可进入匹配层白名单）
    MEDIAN_WAGE = "median_wage"
    EMPLOYMENT_SIZE_CURRENT = "employment_size_current"
    # 预测类（仅进入解释层，绝不进入匹配层）
    EMPLOYMENT_CHANGE_RATE = "employment_change_rate"
    JOB_GROWTH_COUNT = "job_growth_count"
    ANNUAL_OPENINGS = "annual_openings"
    AUTOMATION_EXPOSURE = "automation_exposure"
    DEMAND_DRIVER = "demand_driver"
    RECRUITMENT_DEMAND_SIGNAL = "recruitment_demand_signal"


# 匹配层只允许读取这两类当前观测指标
MATCH_WHITELISTED_INDICATORS = frozenset({
    IndicatorType.MEDIAN_WAGE.value,
    IndicatorType.EMPLOYMENT_SIZE_CURRENT.value,
})


@dataclass(frozen=True)
class FieldProvenance:
    """字段级溯源三元组。NormalizedProspect 的强制字段。"""
    source_id: str
    source_url_or_file: str
    retrieved_at: datetime
    original_field_name: Optional[str] = None
    original_record_locator: Optional[str] = None


@dataclass
class Occupation:
    occupation_id: str
    preferred_name: str
    occupation_family: str           # 受控词表；空值不入库
    taxonomy_refs: dict = field(default_factory=dict)
    riasec_profile: Optional[dict[str, float]] = None   # {"R":..,"I":..,...}
    skill_vector: Optional[list[dict]] = None            # None → 不进匹配空间
    typical_requirements: Optional[dict] = None
    work_context: Optional[dict] = None
    entry_barriers: Optional[dict] = None                # {"license_required": bool|"unknown"}
    data_quality_flags: list[str] = field(default_factory=list)


@dataclass
class Prospect:
    occupation_id: str
    source_name: str
    issuing_authority: str
    publication_year: int
    data_year_or_horizon: str        # 观测用 "as_of_YYYY"，预测用 "YYYY-YYYY"
    region: str
    indicator_type: str
    indicator_value: Optional[float] = None              # 无数据 → None，禁止 0/NaN
    indicator_unit: Optional[str] = None
    qualitative_value: Optional[str] = None
    confidence_note: Optional[str] = None
    freshness_status: str = "CURRENT"                    # CURRENT | HISTORICAL_REFERENCE_ONLY
    provenance: Optional[FieldProvenance] = None

    @property
    def has_reliable_data(self) -> bool:
        return self.indicator_value is not None or self.qualitative_value is not None


# ============ 用户画像 ============

class FieldStatus(str, Enum):
    EXTRACTED = "extracted"
    USER_CONFIRMED = "user_confirmed"
    USER_CORRECTED = "user_corrected"
    USER_SKIPPED = "user_skipped"
    MISSING = "missing"


@dataclass
class EvidenceValue:
    """所有抽取字段的包装。value != None 时 evidence 必须非空。"""
    value: Any
    evidence: Optional[str] = None
    confidence: Optional[str] = None     # explicit | inferred | weak

    def __post_init__(self):
        if self.value is not None and not self.evidence:
            raise ValueError(
                f"EvidenceValue with non-null value requires evidence; got value={self.value!r}"
            )

    @classmethod
    def missing(cls) -> "EvidenceValue":
        return cls(value=None, evidence=None, confidence=None)


@dataclass
class UserProfile:
    profile_id: str
    hard_constraints: dict[str, EvidenceValue] = field(default_factory=dict)
    interests_riasec: dict[str, EvidenceValue] = field(default_factory=dict)
    skills: list[dict] = field(default_factory=list)     # [{skill_id, proficiency, evidence, source_span}]
    values_weights: dict[str, EvidenceValue] = field(default_factory=dict)
    work_style_preferences: dict[str, EvidenceValue] = field(default_factory=dict)
    exclusions: list[dict] = field(default_factory=list)
    field_status: dict[str, str] = field(default_factory=dict)  # json_pointer -> FieldStatus
    missing_fields: list[str] = field(default_factory=list)


# ============ 匹配结果 ============

@dataclass(frozen=True)
class SubScore:
    raw: Optional[float]
    weight_effective: float
    contribution: float
    available: bool
    detail: dict = field(default_factory=dict)


@dataclass(frozen=True)
class HardConstraintEval:
    constraint: str
    status: str                       # pass | soft_penalty | unknown | exclude
    detail: str = ""


@dataclass
class RankedItem:
    rank: int
    occupation_id: str
    occupation_name: str
    occupation_family: str
    total_score: float
    sub_scores: dict[str, SubScore]
    penalties_total: float
    hard_constraint_eval: list[HardConstraintEval]
    matched_skills: list[str]
    unmatched_critical_skills: list[str]


@dataclass
class ExcludedCandidate:
    occupation_id: str
    reason_code: str                 # education_hard_gate | license_hard_gate | explicit_exclusion | missing_skill_vector
    reason_detail: str


@dataclass
class RankedMatchResult:
    status: str                      # ok | profile_insufficient
    scoring_config_version: str
    scoring_config_hash: str
    input_profile_hash: str
    occupation_snapshot_id: str
    ranked_items: list[RankedItem]
    excluded_candidates: list[ExcludedCandidate]
    diversity_report: dict
    missing_fields: list[str] = field(default_factory=list)
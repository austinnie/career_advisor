"""L1 画像抽取接口。LLM 客户端可注入；测试用 StubProfileExtractor。"""
from __future__ import annotations
import json, uuid
from abc import ABC, abstractmethod
from typing import Protocol

from ..models import UserProfile, EvidenceValue, FieldStatus
from .evidence_validator import validate_and_downgrade
from .prompts import (L1_SYSTEM_PROMPT, L1_USER_TEMPLATE,
                      L1_INCREMENTAL_SYSTEM_PROMPT, L1_INCREMENTAL_USER_TEMPLATE)


class LLMClient(Protocol):
    def generate_json(self, system_prompt: str, user_prompt: str, schema: dict) -> dict:
        ...


class ProfileExtractor(ABC):
    @abstractmethod
    def extract(self, raw_text: str, prior_profile: UserProfile | None = None,
                target_fields: list[str] | None = None) -> UserProfile:
        """全量抽取（target_fields=None）或增量抽取（target_fields 指定）。"""


# ============ LLM 实现 ============

class LLMProfileExtractor(ProfileExtractor):
    def __init__(self, client: LLMClient, prompt_version: str = "l1-v1.0"):
        self.client = client
        self.prompt_version = prompt_version

    def extract(self, raw_text, prior_profile=None, target_fields=None) -> UserProfile:
        if target_fields and prior_profile is not None:
            return self._extract_incremental(raw_text, prior_profile, target_fields)
        return self._extract_full(raw_text)

    def _extract_full(self, raw_text: str) -> UserProfile:
        payload = self.client.generate_json(
            system_prompt=L1_SYSTEM_PROMPT,
            user_prompt=L1_USER_TEMPLATE.format(raw_text=raw_text),
            schema=_USER_PROFILE_SCHEMA,
        )
        profile = _payload_to_profile(payload)
        return validate_and_downgrade(profile)

    def _extract_incremental(self, raw_text: str, prior: UserProfile,
                             target_fields: list[str]) -> UserProfile:
        existing = _profile_to_payload(prior)
        payload = self.client.generate_json(
            system_prompt=L1_INCREMENTAL_SYSTEM_PROMPT,
            user_prompt=L1_INCREMENTAL_USER_TEMPLATE.format(
                existing_json=json.dumps(existing, ensure_ascii=False, default=str),
                new_answer=raw_text,
                target_fields=target_fields,
            ),
            schema=_INCREMENTAL_SCHEMA,
        )
        merged = _merge_incremental(prior, payload, target_fields)
        return validate_and_downgrade(merged)


# ============ Stub 实现（本地测试/无 LLM 环境） ============

_ALL_RIASEC = "RIASEC"
_ALL_VALUES = ("salary", "stability", "growth", "autonomy", "social_impact")


class StubProfileExtractor(ProfileExtractor):
    """确定性 stub。返回全 null 画像，用于测试 profile_insufficient 分支与端到端。"""

    def extract(self, raw_text, prior_profile=None, target_fields=None) -> UserProfile:
        if target_fields and prior_profile is not None:
            for tf in target_fields:
                prior_profile.field_status[tf] = FieldStatus.MISSING.value
            return prior_profile
        return UserProfile(
            profile_id=_new_profile_id(),
            hard_constraints={
                "region": EvidenceValue.missing(),
                "max_education_investment_years": EvidenceValue.missing(),
                "economic_pressure_period": EvidenceValue.missing(),
                "license_obtainable": EvidenceValue.missing(),
            },
            interests_riasec={k: EvidenceValue.missing() for k in _ALL_RIASEC},
            skills=[],
            values_weights={k: EvidenceValue.missing() for k in _ALL_VALUES},
            work_style_preferences={},
            exclusions=[],
            missing_fields=[
                "/hard_constraints/region",
                "/hard_constraints/max_education_investment_years",
                "/hard_constraints/economic_pressure_period",
                "/hard_constraints/license_obtainable",
                *[f"/interests_riasec/{k}" for k in _ALL_RIASEC],
                "/skills",
                *[f"/values_weights/{k}" for k in _ALL_VALUES],
            ],
        )


# ============ 内部工具 ============

def _new_profile_id() -> str:
    return f"prof-{uuid.uuid4().hex[:12]}"


def _safe_ev(node) -> EvidenceValue:
    """构造 EvidenceValue 时做安全降级：value 非空但 evidence 为空 → 返回 missing。"""
    if not isinstance(node, dict):
        return EvidenceValue.missing()
    value = node.get("value")
    evidence = node.get("evidence")
    if value is None or not evidence:
        return EvidenceValue.missing()
    return EvidenceValue(value=value, evidence=evidence,
                         confidence=node.get("confidence"))


def _payload_to_profile(payload: dict) -> UserProfile:
    hc = payload.get("hard_constraints") or {}
    ir = payload.get("interests_riasec") or {}
    vw = payload.get("values_weights") or {}
    ws = payload.get("work_style_preferences") or {}
    return UserProfile(
        profile_id=_new_profile_id(),
        hard_constraints={
            "region": _safe_ev(hc.get("region")),
            "max_education_investment_years": _safe_ev(hc.get("max_education_investment_years")),
            "economic_pressure_period": _safe_ev(hc.get("economic_pressure_period")),
            "license_obtainable": _safe_ev(hc.get("license_obtainable")),
        },
        interests_riasec={k: _safe_ev(ir.get(k)) for k in _ALL_RIASEC},
        skills=[s for s in (payload.get("skills") or [])
                if isinstance(s, dict) and s.get("skill_id") and s.get("source_span")],
        values_weights={k: _safe_ev(vw.get(k)) for k in _ALL_VALUES},
        work_style_preferences={k: _safe_ev(v) for k, v in ws.items()},
        exclusions=[e for e in (payload.get("exclusions") or [])
                    if isinstance(e, dict) and e.get("source_span")],
        missing_fields=sorted(payload.get("missing_fields") or []),
    )


def _profile_to_payload(profile: UserProfile) -> dict:
    return {
        "hard_constraints": {k: {"value": v.value, "evidence": v.evidence}
                             for k, v in profile.hard_constraints.items()},
        "interests_riasec": {k: {"value": v.value, "evidence": v.evidence}
                             for k, v in profile.interests_riasec.items()},
        "skills": profile.skills,
        "values_weights": {k: {"value": v.value, "evidence": v.evidence}
                           for k, v in profile.values_weights.items()},
        "work_style_preferences": {k: {"value": v.value, "evidence": v.evidence}
                                   for k, v in profile.work_style_preferences.items()},
        "exclusions": profile.exclusions,
    }


def _merge_incremental(prior: UserProfile, payload: dict, target_fields: list[str]) -> UserProfile:
    """只覆盖 target_fields 指向的字段；其他字段保持不变。"""
    fields = payload.get("fields") or {}
    merged = prior  # 就地修改（副本语义由调用方保证：每次抽取产生新 profile）
    for pointer, ev_node in fields.items():
        ev = _safe_ev(ev_node)
        if pointer.startswith("/hard_constraints/"):
            key = pointer.rsplit("/", 1)[-1]
            if key in merged.hard_constraints:
                merged.hard_constraints[key] = ev
        elif pointer.startswith("/interests_riasec/"):
            key = pointer.rsplit("/", 1)[-1]
            if key in merged.interests_riasec:
                merged.interests_riasec[key] = ev
        elif pointer.startswith("/values_weights/"):
            key = pointer.rsplit("/", 1)[-1]
            if key in merged.values_weights:
                merged.values_weights[key] = ev
        elif pointer.startswith("/work_style_preferences/"):
            key = pointer.rsplit("/", 1)[-1]
            merged.work_style_preferences[key] = ev
    # 清理 missing_fields 中已被填值的项
    still_missing = []
    for f in prior.missing_fields:
        if not _is_field_still_missing(merged, f):
            continue
        still_missing.append(f)
    merged.missing_fields = still_missing
    return merged


def _is_field_still_missing(profile: UserProfile, pointer: str) -> bool:
    parts = pointer.strip("/").split("/")
    if len(parts) != 2:
        return True
    container, key = parts
    if container == "hard_constraints":
        return profile.hard_constraints.get(key, EvidenceValue.missing()).value is None
    if container == "interests_riasec":
        return profile.interests_riasec.get(key, EvidenceValue.missing()).value is None
    if container == "values_weights":
        return profile.values_weights.get(key, EvidenceValue.missing()).value is None
    return True


# 简化的 JSON schema 声明（生产应使用 pydantic / jsonschema 完整 schema）
_USER_PROFILE_SCHEMA = {"type": "object", "required": ["missing_fields"]}
_INCREMENTAL_SCHEMA = {"type": "object", "required": ["fields", "missing_fields"]}
"""L1 画像抽取接口。LLM 客户端可注入；测试用 StubProfileExtractor。"""
from __future__ import annotations
import json, uuid
from abc import ABC, abstractmethod
from typing import Protocol

from ..models import UserProfile, EvidenceValue, FieldStatus
from .evidence_validator import validate_and_downgrade
from .prompts import (L1_SYSTEM_PROMPT, L1_USER_TEMPLATE,
                      L1_INCREMENTAL_SYSTEM_PROMPT, L1_INCREMENTAL_USER_TEMPLATE)


import re

def _preprocess_resume(raw_text: str) -> str:
    """对超长简历进行脱水。
    保留头部（个人信息/核心优势）、教育资格模块，截断中间冗长的项目细节。
    如果总长度小于 3000 字，则原样返回。
    """
    if len(raw_text) < 3000:
        return raw_text

    # 1. 提取头部（通常是个人信息、联系方式、核心优势）
    head = raw_text[:800]

    # 2. 提取教育与资格模块（通常是简历的最后一部分）
    edu_keywords = ["教育", "学历", "资格", "语言", "Education", "Qualifications"]
    edu_idx = -1
    for kw in edu_keywords:
        idx = raw_text.rfind(kw)
        if idx != -1 and idx > len(raw_text) // 2: # 确保在简历后半部分
            edu_idx = idx
            break
            
    tail = ""
    if edu_idx != -1:
        tail = raw_text[edu_idx:edu_idx+800]
        
    # 3. 提取中段的关键工作经历标题（保留前两份工作的前 300 字）
    # 简单粗暴法：头部 + 工作经历的开头部分 + 尾部
    mid = raw_text[800:1800]
    
    compressed = (
        f"【简历头部/核心摘要】\n{head}\n\n"
        f"【近期工作经历（节选）】\n{mid}\n\n"
        f"【教育背景与资格】\n{tail}\n\n"
        f"【系统提示：原简历过长已压缩，请重点提取上述模块中的信息】"
    )
    return compressed
    
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

        # 1. 先脱水！
        compressed_text = _preprocess_resume(raw_text)
        
        payload = self.client.generate_json(
            system_prompt=L1_SYSTEM_PROMPT,
            user_prompt=L1_USER_TEMPLATE.format(raw_text=compressed_text), # 使用压缩后的文本
            schema={},
        )
        import json
        print(f"\n[DEBUG-L1] 原始返回:\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n")
        
        profile = _payload_to_profile(payload)
        
        # ============ 正则兜底机制 ============
        import re
        # 1. 兜底学历
        if profile.hard_constraints.get("education_level", EvidenceValue.missing()).value is None:
            if re.search(r"(本科|学士|Bachelor)", raw_text, re.IGNORECASE):
                profile.hard_constraints["education_level"] = EvidenceValue("bachelor", "正则兜底匹配", "inferred")
            elif re.search(r"(硕士|Master)", raw_text, re.IGNORECASE):
                profile.hard_constraints["education_level"] = EvidenceValue("master", "正则兜底匹配", "inferred")
            elif re.search(r"(博士|PhD|Doctor)", raw_text, re.IGNORECASE):
                profile.hard_constraints["education_level"] = EvidenceValue("phd", "正则兜底匹配", "inferred")

        # 2. 兜底地域
        if profile.hard_constraints.get("region", EvidenceValue.missing()).value is None:
            if re.search(r"日本|东京|大阪|广岛|Tokyo|Osaka", raw_text):
                profile.hard_constraints["region"] = EvidenceValue(["日本"], "正则兜底匹配", "inferred")
            elif re.search(r"北京|上海|广州|深圳|杭州", raw_text):
                cities = re.findall(r"(北京|上海|广州|深圳|杭州)", raw_text)
                profile.hard_constraints["region"] = EvidenceValue(list(set(cities)), "正则兜底匹配", "inferred")

        # 3. 兜底工作年限
        if profile.years_experience is None:
            year_match = re.search(r"(\d+)\s*年", raw_text)
            if year_match:
                try:
                    profile.years_experience = float(year_match.group(1))
                except ValueError:
                    pass
        # ====================================

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
                "education_level": EvidenceValue.missing(),
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
                "/hard_constraints/education_level",
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
            "education_level": _safe_ev(hc.get("education_level")),
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
        missing_fields=sorted([
            f for f in (payload.get("missing_fields") or []) 
            if not f.startswith("/exclusions")
        ]),
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
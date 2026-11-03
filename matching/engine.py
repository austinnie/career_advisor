"""匹配层编排器。只做流程编排，不含算法实现。"""
from __future__ import annotations
import hashlib, json
from ..models import (UserProfile, Occupation, Prospect, RankedItem,
                      RankedMatchResult, ExcludedCandidate,
                      MATCH_WHITELISTED_INDICATORS)
from .config import ScoringConfig
from . import hard_filter, scorers, diversity


def index_static_observations(prospects: list[Prospect]) -> dict[str, dict[str, float | None]]:
    """按 (occ_id) 聚合白名单观测指标。多记录时按
    (data_year_or_horizon DESC, source_priority ASC) 取第一条。
    本实现暂以 data_year_or_horizon 字符串降序近似（as_of_2024 > as_of_2023）。"""
    index: dict[str, dict[str, float | None]] = {}
    # 白名单断言：任何非白名单记录直接丢弃，不降级使用
    valid = []
    for p in prospects:
        if p.indicator_type not in MATCH_WHITELISTED_INDICATORS:
            continue
        if not p.data_year_or_horizon.startswith("as_of_"):
            continue
        valid.append(p)
    valid.sort(key=lambda p: (p.occupation_id, p.indicator_type,
                              -int(p.data_year_or_horizon[6:]), p.source_name))
    for p in valid:
        slot = index.setdefault(p.occupation_id, {})
        slot.setdefault(p.indicator_type, p.indicator_value)
    return index


def has_minimum_signal(profile: UserProfile, cfg: ScoringConfig) -> bool:
    dims = sum(1 for ev in profile.interests_riasec.values() if ev.value is not None)
    return dims >= cfg.interest_min_available_dims or len(profile.skills) >= 2


def match(profile: UserProfile, occupations: list[Occupation],
          prospects: list[Prospect], cfg: ScoringConfig,
          occupation_snapshot_id: str = "occ-snapshot-v1") -> RankedMatchResult:
    cfg_hash = cfg.hash()
    profile_hash = _hash_profile(profile)

    if not has_minimum_signal(profile, cfg):
        return RankedMatchResult(
            status="profile_insufficient", scoring_config_version=cfg.version,
            scoring_config_hash=cfg_hash, input_profile_hash=profile_hash,
            occupation_snapshot_id=occupation_snapshot_id,
            ranked_items=[], excluded_candidates=[], diversity_report={},
            missing_fields=profile.missing_fields)

    static_index = index_static_observations(prospects)

    candidates, excluded = [], []
    for occ in occupations:
        if occ.skill_vector is None:
            excluded.append(ExcludedCandidate(
                occ.occupation_id, "missing_skill_vector",
                "该职业缺少结构化技能字段，未参与匹配"))
            continue
        if not occ.occupation_family:
            excluded.append(ExcludedCandidate(
                occ.occupation_id, "missing_skill_vector",
                "该职业缺少职业族标注，未参与匹配"))
            continue
        ev = hard_filter.evaluate(profile, occ, cfg)
        if ev.action == "exclude":
            excluded.append(ExcludedCandidate(
                occ.occupation_id, ev.reason_code, ev.reason_detail))
            continue
        candidates.append((occ, ev))

    ranked: list[RankedItem] = []
    for occ, ev in candidates:
        subs = {
            "interest":       scorers.score_interest(profile, occ, cfg),
            "skill_transfer": scorers.score_skill_transfer(profile, occ, cfg),
            "values":         scorers.score_values(profile, occ,
                                                   static_index.get(occ.occupation_id, {}), cfg),
        }
        eff = _renormalize_weights(cfg.dimension_weights, {k: v.available for k, v in subs.items()})
        subs_final = {}
        for k, s in subs.items():
            w = eff[k]
            contribution = round((s.raw or 0.0) * w, 8)
            subs_final[k] = type(s)(
                raw=s.raw, weight_effective=round(w, 6),
                contribution=contribution, available=s.available, detail=s.detail)

        missing_crit = subs["skill_transfer"].detail.get("unmatched_critical", [])
        mc_penalty = round(
            cfg.missing_critical_beta * (
                len(missing_crit) / max(1, len(occ.skill_vector or []))), 8)
        total_penalty = round(ev.soft_penalty + mc_penalty, 8)
        total = round(sum(s.contribution for s in subs_final.values()) - total_penalty,
                      cfg.score_precision)

        ranked.append(RankedItem(
            rank=0, occupation_id=occ.occupation_id,
            occupation_name=occ.preferred_name,
            occupation_family=occ.occupation_family,
            total_score=total, sub_scores=subs_final,
            penalties_total=total_penalty,
            hard_constraint_eval=list(ev.evals),
            matched_skills=subs["skill_transfer"].detail.get("matched", []),
            unmatched_critical_skills=missing_crit))

    ranked.sort(key=lambda r: (-r.total_score, r.occupation_id))
    selected, _rejected, report = diversity.select(
        ranked, cfg.top_n, cfg.max_per_family(), cfg.min_families)
    for i, item in enumerate(selected, start=1):
        item.rank = i

    return RankedMatchResult(
        status="ok", scoring_config_version=cfg.version,
        scoring_config_hash=cfg_hash, input_profile_hash=profile_hash,
        occupation_snapshot_id=occupation_snapshot_id,
        ranked_items=selected, excluded_candidates=excluded,
        diversity_report=report)


def _renormalize_weights(configured: dict[str, float], available: dict[str, bool]) -> dict[str, float]:
    avail = [k for k, a in available.items() if a]
    if not avail:
        n = len(configured)
        return {k: 1.0 / n for k in configured}
    s = sum(configured[k] for k in avail)
    return {k: (configured[k] / s if k in avail else 0.0) for k in configured}


def _hash_profile(profile: UserProfile) -> str:
    payload = {
        "hard_constraints": {k: ev.value for k, ev in profile.hard_constraints.items()},
        "interests_riasec": {k: ev.value for k, ev in profile.interests_riasec.items()},
        "skills": sorted((s["skill_id"], s.get("proficiency")) for s in profile.skills),
        "values_weights": {k: ev.value for k, ev in profile.values_weights.items()},
        "exclusions": sorted(
            (e.get("type", ""), e.get("value", "")) for e in profile.exclusions),
    }
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()
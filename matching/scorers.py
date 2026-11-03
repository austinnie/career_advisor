"""三个独立 scorer。每个只做一件事。"""
from __future__ import annotations
import math
from ..models import Occupation, UserProfile, SubScore
from .config import ScoringConfig

from typing import Protocol


class _AdjacencyProtocol(Protocol):
    def neighbors(self, skill_id: str) -> frozenset[str]: ...
    
def score_interest(profile: UserProfile, occ: Occupation, cfg: ScoringConfig) -> SubScore:
    available = {d: ev.value for d, ev in profile.interests_riasec.items()
                 if ev.value is not None}
    if len(available) < cfg.interest_min_available_dims or not occ.riasec_profile:
        return SubScore(raw=None, weight_effective=0.0, contribution=0.0,
                        available=False, detail={"reason": "insufficient_riasec_dims"})
    dims = list(available.keys())
    u = [available[d] / 100.0 for d in dims]
    o = [occ.riasec_profile.get(d, 0) / 100.0 for d in dims]
    nu = math.sqrt(sum(x * x for x in u)) or 1e-9
    no = math.sqrt(sum(x * x for x in o)) or 1e-9
    cos = sum(a * b for a, b in zip(u, o)) / (nu * no)
    cos = max(0.0, min(1.0, cos))
    return SubScore(raw=round(cos, 6), weight_effective=0.0, contribution=0.0,
                    available=True,
                    detail={"dims_used": dims, "cosine": round(cos, 6)})

def score_skill_transfer(profile: UserProfile, occ: Occupation,
                          cfg: ScoringConfig,
                          adjacency: "_AdjacencyProtocol | None" = None) -> SubScore:
    if not occ.skill_vector:
        return SubScore(raw=None, weight_effective=0.0, contribution=0.0,
                        available=False, detail={"reason": "no_skill_vector"})
    user_map = {s["skill_id"]: s for s in profile.skills}
    total_w = sum(r["importance"] for r in occ.skill_vector) or 1
    raw = 0.0
    matched, neighbor_matched, unmatched_critical = [], [], []

    for r in occ.skill_vector:
        w = r["importance"] / total_w
        sid = r["skill_id"]
        if sid in user_map:
            prof = user_map[sid].get("proficiency", "beginner")
            cov = cfg.skill_exact_match_factor * cfg.skill_proficiency_factors.get(prof, 0.4)
            matched.append(sid)
            raw += w * cov
            continue

        # 邻居匹配（仅在传入 adjacency 时生效）
        best_neighbor_prof = None
        if adjacency is not None:
            best_neighbor_prof = _best_neighbor_proficiency(user_map, sid, adjacency)

        if best_neighbor_prof is not None:
            cov = (cfg.skill_neighbor_match_factor
                   * cfg.skill_proficiency_factors.get(best_neighbor_prof, 0.4))
            neighbor_matched.append(f"{sid}(neighbor)")
            raw += w * cov
        elif (r.get("critical")
              and r["importance"] >= cfg.skill_critical_importance_threshold):
            unmatched_critical.append(sid)

    return SubScore(raw=round(raw, 6), weight_effective=0.0, contribution=0.0,
                    available=True,
                    detail={"matched": matched,
                            "neighbor_matched": neighbor_matched,
                            "unmatched_critical": unmatched_critical})


def _best_neighbor_proficiency(user_map: dict, target_skill: str,
                                adjacency: "_AdjacencyProtocol") -> str | None:
    """在职业技能的邻居中寻找用户已具备的技能，返回最高熟练度。
    未命中返回 None。"""
    neighbors = adjacency.neighbors(target_skill)
    if not neighbors:
        return None
    rank = {"beginner": 0, "intermediate": 1, "advanced": 2, "expert": 3}
    best_rank = -1
    best_prof = None
    for sid, skill in user_map.items():
        if sid in neighbors:
            prof = skill.get("proficiency", "beginner")
            r = rank.get(prof, 0)
            if r > best_rank:
                best_rank = r
                best_prof = prof
    return best_prof
    

def score_values(profile: UserProfile, occ: Occupation,
                 static_obs: dict[str, float | None], cfg: ScoringConfig) -> SubScore:
    """只读取白名单观测指标 + Occ.work_context.job_autonomy。"""
    weights = {k: ev.value for k, ev in profile.values_weights.items()
               if ev.value is not None and ev.value > 0}
    if not weights:
        return SubScore(raw=None, weight_effective=0.0, contribution=0.0,
                        available=False, detail={"reason": "no_value_weights"})

    components: dict[str, float] = {}
    unavailable: list[str] = []

    if "salary" in weights and static_obs.get("median_wage") is not None:
        components["salary"] = _bucket(static_obs["median_wage"], cfg.wage_buckets)
    elif "salary" in weights:
        unavailable.append("salary_no_data")

    if "stability" in weights and static_obs.get("employment_size_current") is not None:
        components["stability"] = _bucket(static_obs["employment_size_current"], cfg.size_buckets)
    elif "stability" in weights:
        unavailable.append("stability_no_data")

    if "autonomy" in weights and (occ.work_context or {}).get("job_autonomy") is not None:
        components["autonomy"] = (occ.work_context["job_autonomy"] or 0) / 100.0
    elif "autonomy" in weights:
        unavailable.append("autonomy_no_data")

    # growth / social_impact 永远不可用（前者需预测数据、后者无来源字段）
    for v in ("growth", "social_impact"):
        if v in weights:
            unavailable.append(f"{v}_not_supported")

    if not components:
        return SubScore(raw=None, weight_effective=0.0, contribution=0.0,
                        available=False, detail={"reason": "no_available_value_components",
                                                 "unavailable": unavailable})

    total_w = sum(weights[k] for k in components)
    num = sum(weights[k] * components[k] for k in components)
    raw = num / total_w if total_w > 0 else 0.0
    return SubScore(raw=round(raw, 6), weight_effective=0.0, contribution=0.0,
                    available=True,
                    detail={"components": {k: round(v, 4) for k, v in components.items()},
                            "unavailable": unavailable})


def _bucket(value: float, buckets: list[tuple[float, float, float]]) -> float:
    for lo, hi, score in buckets:
        if lo <= value < hi:
            return score
    return 0.0
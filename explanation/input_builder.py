"""从 RankedMatchResult + Prospect 数据组装 ExplanationInput。"""
from ..models import (RankedItem, Occupation, UserProfile, Prospect,
                      RankedMatchResult, MATCH_WHITELISTED_INDICATORS)


def build_explanation_input(item: RankedItem, occ: Occupation, profile: UserProfile,
                            prospects_for_occ: list[Prospect],
                            coverage: dict, render_config: dict) -> dict:
    return {
        "occupation": {
            "occupation_id": occ.occupation_id,
            "occupation_name": occ.preferred_name,
            "occupation_family": occ.occupation_family,
            "core_tasks": None,
            "typical_requirements": occ.typical_requirements,
            "license_required": (occ.entry_barriers or {}).get("license_required"),
            "license_note": (occ.entry_barriers or {}).get("license_note"),
            "work_context": occ.work_context,
        },
        "match": {
            "rank": item.rank,
            "total_score": item.total_score,
            "sub_scores": {k: {"raw": s.raw, "weight_effective": s.weight_effective,
                               "contribution": s.contribution, "available": s.available}
                           for k, s in item.sub_scores.items()},
            "penalties": {"total": item.penalties_total},
            "hard_constraint_eval": [
                {"constraint": e.constraint, "status": e.status, "detail": e.detail}
                for e in item.hard_constraint_eval],
            "matched_skills": item.matched_skills,
            "unmatched_critical_skills": item.unmatched_critical_skills,
        },
        "profile": _project_profile(profile),
        "prospects": _project_prospects(prospects_for_occ),
        "coverage": coverage,
        "render_config": render_config,
    }


def _project_profile(profile: UserProfile) -> dict:
    """只投影有 evidence 的字段。"""
    return {
        "skills_with_evidence": profile.skills,
        "years_experience": profile.years_experience,
        "riasec_with_evidence": {k: {"value": v.value, "evidence": v.evidence}
                                 for k, v in profile.interests_riasec.items()
                                 if v.value is not None and v.evidence},
        "values_with_evidence": {k: {"value": v.value, "evidence": v.evidence}
                                 for k, v in profile.values_weights.items()
                                 if v.value is not None and v.evidence},
        "constraints_with_evidence": {k: {"value": v.value, "evidence": v.evidence}
                                      for k, v in profile.hard_constraints.items()
                                      if v.value is not None and v.evidence},
        "exclusions_with_evidence": profile.exclusions,
    }


def _project_prospects(prospects: list[Prospect]) -> list[dict]:
    if not prospects:
        return [{
            "indicator_type": "employment_change_rate",
            "indicator_value": None, "indicator_unit": None,
            "qualitative_value": None, "source_name": "NONE",
            "issuing_authority": "NONE", "publication_year": 0,
            "data_year_or_horizon": "NONE", "region": "CN",
            "confidence_note": None, "freshness_status": None,
            "status": "no_reliable_data",
        }]
    out = []
    for p in prospects:
        out.append({
            "indicator_type": p.indicator_type,
            "indicator_value": p.indicator_value,
            "indicator_unit": p.indicator_unit,
            "qualitative_value": p.qualitative_value,
            "source_name": p.source_name,
            "issuing_authority": p.issuing_authority,
            "publication_year": p.publication_year,
            "data_year_or_horizon": p.data_year_or_horizon,
            "region": p.region,
            "confidence_note": p.confidence_note,
            "freshness_status": p.freshness_status,
            "status": "available" if p.has_reliable_data else "no_reliable_data",
        })
    return out
"""P6 被排除职业查询 + 未收录职业查询。只读 RankedMatchResult，不重算。"""
from __future__ import annotations
from ..models import RankedMatchResult, Occupation


REASON_LABELS = {
    "education_hard_gate": "因学历投入年限超出你的上限",
    "license_hard_gate":   "因你表示不愿意/不能获取执照",
    "explicit_exclusion":  "因你的明确排除",
    "missing_skill_vector": "因该职业缺少可用的技能字段，未参与匹配",
}


def group_excluded(result: RankedMatchResult) -> dict[str, list[dict]]:
    """按 reason_code 分组返回被排除职业。"""
    grouped: dict[str, list[dict]] = {}
    for e in result.excluded_candidates:
        grouped.setdefault(e.reason_code, []).append({
            "occupation_id": e.occupation_id,
            "label": REASON_LABELS.get(e.reason_code, e.reason_code),
            "detail": e.reason_detail,
        })
    return grouped


def diversity_rejected(result: RankedMatchResult) -> list[dict]:
    """因多样性约束被挤出 Top-N 的候选（阶段 6 契约 P6 第二组）。"""
    return (result.diversity_report or {}).get("rejected_by_diversity") or []


def lookup_occupation(query: str, occupations: list[Occupation]) -> dict:
    """未收录职业查询。若职业不在库中，明确返回 not_in_library。"""
    q = (query or "").strip().lower()
    if not q:
        return {"status": "empty_query"}
    for o in occupations:
        if q in o.preferred_name.lower() or q == o.occupation_id.lower():
            return {
                "status": "found",
                "occupation_id": o.occupation_id,
                "preferred_name": o.preferred_name,
                "occupation_family": o.occupation_family,
                "matchable": o.skill_vector is not None,
            }
    return {
        "status": "not_in_library",
        "query": query,
        "library_size": len(occupations),
        "note": "该职业不在当前职业库中；可查看覆盖边界声明了解库内范围。",
    }
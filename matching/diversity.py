"""多样性选取。单一职责：从已排序候选中按族配额选出 Top-N。"""
from __future__ import annotations


def select(ranked: list, n: int, max_per_family: int, min_families: int) -> tuple[list, list, dict]:
    selected, family_count = [], {}
    rejected = []
    for c in ranked:
        fam = c.occupation_family
        if family_count.get(fam, 0) < max_per_family:
            selected.append(c)
            family_count[fam] = family_count.get(fam, 0) + 1
            if len(selected) == n:
                break
        else:
            rejected.append(c)

    underfilled = len(selected) < n
    report = {
        "applied": True,
        "max_per_family": max_per_family,
        "min_families": min_families,
        "family_distribution": family_count,
        "underfilled": underfilled,
        "actual_families": len(family_count),
        "rejected_by_diversity": [
            {"occupation_id": c.occupation_id, "occupation_family": c.occupation_family,
             "total_score": c.total_score} for c in rejected
        ],
    }
    if underfilled:
        report["underfill_reason"] = (
            f"候选池中仅有 {len(family_count)} 个职业族的 {len(selected)} 个职业满足约束，"
            f"不足 {n} 条；未从未入选族中硬凑无关职业。")
    return selected, rejected, report
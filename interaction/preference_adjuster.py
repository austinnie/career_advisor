"""P7 偏好调节的排名 diff 计算。不重算匹配，只比较两次 RankedMatchResult。"""
from __future__ import annotations
from ..models import RankedMatchResult


def diff_rankings(old: RankedMatchResult, new: RankedMatchResult) -> dict:
    """返回排名变化。

    结构
    ----
    - new_entries : 新进入 Top-N（含 new_rank）
    - dropped     : 移出 Top-N（含 old_rank）
    - moved_up    : 排名上升（按 rank 变化从大到小）
    - moved_down  : 排名下降
    - unchanged   : 排名不变
    - summary     : 各类计数
    """
    old_ranks = {i.occupation_id: i.rank for i in old.ranked_items}
    new_ranks = {i.occupation_id: i.rank for i in new.ranked_items}
    old_names = {i.occupation_id: i.occupation_name for i in old.ranked_items}
    new_names = {i.occupation_id: i.occupation_name for i in new.ranked_items}

    new_entries = [
        {"occupation_id": oid, "occupation_name": new_names[oid],
         "new_rank": new_ranks[oid]}
        for oid in new_ranks if oid not in old_ranks
    ]
    dropped = [
        {"occupation_id": oid, "occupation_name": old_names[oid],
         "old_rank": old_ranks[oid]}
        for oid in old_ranks if oid not in new_ranks
    ]

    moved_up, moved_down, unchanged = [], [], []
    for oid in new_ranks:
        if oid not in old_ranks:
            continue
        old_r, new_r = old_ranks[oid], new_ranks[oid]
        delta = old_r - new_r      # 正数 = 排名上升（rank 数字变小）
        entry = {"occupation_id": oid, "occupation_name": new_names[oid],
                 "old_rank": old_r, "new_rank": new_r, "delta": delta}
        if delta > 0:
            moved_up.append(entry)
        elif delta < 0:
            moved_down.append(entry)
        else:
            unchanged.append(entry)

    moved_up.sort(key=lambda e: (-e["delta"], e["occupation_id"]))
    moved_down.sort(key=lambda e: (e["delta"], e["occupation_id"]))
    new_entries.sort(key=lambda e: e["new_rank"])
    dropped.sort(key=lambda e: e["old_rank"])

    return {
        "new_entries": new_entries,
        "dropped": dropped,
        "moved_up": moved_up,
        "moved_down": moved_down,
        "unchanged": unchanged,
        "summary": {
            "new_count": len(new_entries),
            "dropped_count": len(dropped),
            "up_count": len(moved_up),
            "down_count": len(moved_down),
            "unchanged_count": len(unchanged),
        },
    }
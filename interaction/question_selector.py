"""追问选择器。单一职责：从 missing_fields 中选出本轮要问的 ≤3 个问题。
拆分为 3 个函数，每个只做一件事（阶段 6 审计 5.5 的修复）。"""
from __future__ import annotations
from ..models import UserProfile
from .question_templates import TEMPLATES, QuestionTemplate


def select_round(profile: UserProfile, round_no: int,
                 max_per_round: int = 3) -> list[QuestionTemplate]:
    """round_no ∈ {1, 2, 3}。返回本轮要问的模板列表（已去重）。"""
    if round_no < 1 or round_no > 3:
        return []

    candidates = _eligible_templates(profile)
    if not candidates:
        return []

    # 阶段 6 契约：第 1 轮优先解除 profile_insufficient
    if round_no == 1 and not _has_minimum_signal(profile):
        return [t for t in candidates if t.priority == 0][:max_per_round]

    # 第 2、3 轮：按优先级排序后取前 N
    return candidates[:max_per_round]


def _eligible_templates(profile: UserProfile) -> list[QuestionTemplate]:
    """逐个字段判断「是否还有可问的 target」。

    模板可选当且仅当存在一个 target 字段 f，同时满足：
      - f 仍在 missing_fields 中（尚无值）
      - f 的 status 不是 asked / user_skipped（未被问过或用户未跳过）
    """
    missing = set(profile.missing_fields)
    eligible: list[QuestionTemplate] = []
    for t in TEMPLATES:
        has_actionable = False
        for f in t.target_fields:
            if f not in missing:
                continue                      # 该字段已有值
            st = profile.field_status.get(f)
            if st in ("asked", "user_skipped"):
                continue                      # 已问过或用户已跳过
            has_actionable = True
            break
        if has_actionable:
            eligible.append(t)
    eligible.sort(key=lambda t: (t.priority, t.template_id))
    return eligible


def _has_minimum_signal(profile: UserProfile) -> bool:
    """与 L2 engine.has_minimum_signal 同构，但本函数只看画像，不依赖 cfg。"""
    riasec_available = sum(1 for ev in profile.interests_riasec.values()
                          if ev.value is not None)
    return riasec_available >= 2 or len(profile.skills) >= 2


def mark_asked(profile: UserProfile, templates: list[QuestionTemplate]) -> None:
    """本轮被问到的模板中，未被跳过的字段标记为 asked。
    跳过的字段标记为 user_skipped（由 record_skip 单独处理）。"""
    for t in templates:
        for f in t.target_fields:
            if profile.field_status.get(f) == "user_skipped":
                continue
            profile.field_status.setdefault(f, "asked")


def record_skip(profile: UserProfile, template: QuestionTemplate) -> None:
    """用户跳过某模板 → 其所有 target 标记 user_skipped。"""
    for f in template.target_fields:
        profile.field_status[f] = "user_skipped"
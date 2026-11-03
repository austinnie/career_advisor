"""L1 输出校验器。降级字段而非重试。"""
from ..models import UserProfile, EvidenceValue


def validate_and_downgrade(profile: UserProfile) -> UserProfile:
    """遍历所有 EvidenceValue；value 非空但 evidence 为空 → 强制降级。"""
    def _walk(container: dict, path: str) -> list[str]:
        downgraded = []
        for k, ev in list(container.items()):
            if not isinstance(ev, EvidenceValue):
                continue
            if ev.value is not None and not ev.evidence:
                container[k] = EvidenceValue.missing()
                downgraded.append(f"{path}/{k}")
        return downgraded

    downgraded = []
    downgraded += _walk(profile.hard_constraints, "/hard_constraints")
    downgraded += _walk(profile.interests_riasec, "/interests_riasec")
    downgraded += _walk(profile.values_weights, "/values_weights")
    downgraded += _walk(profile.work_style_preferences, "/work_style_preferences")

    # 技能：source_span 必须非空
    valid_skills = []
    for i, s in enumerate(profile.skills):
        if not s.get("source_span"):
            downgraded.append(f"/skills/{i}")
            continue
        valid_skills.append(s)
    profile.skills = valid_skills

    profile.missing_fields = sorted(set(profile.missing_fields) | set(downgraded))
    for f in downgraded:
        profile.field_status[f] = "user_skipped"
    return profile
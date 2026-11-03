"""硬约束评估。单一职责：返回 (action, reason_code, penalty, evals)。"""
from __future__ import annotations
from dataclasses import dataclass

from ..models import Occupation, UserProfile, EvidenceValue, HardConstraintEval
from .config import ScoringConfig


@dataclass(frozen=True)
class HardEvalResult:
    action: str                        # "pass" | "exclude"
    reason_code: str = ""
    reason_detail: str = ""
    soft_penalty: float = 0.0
    evals: tuple[HardConstraintEval, ...] = ()


def evaluate(profile: UserProfile, occ: Occupation, cfg: ScoringConfig) -> HardEvalResult:
    evals: list[HardConstraintEval] = []
    soft_penalty = 0.0

    # ---- 显式排除项 ----
    for exc in profile.exclusions:
        if exc.get("type") == "occupation_family" and exc["value"] == occ.occupation_family:
            return HardEvalResult("exclude", "explicit_exclusion",
                                  f"用户明确排除职业族「{occ.occupation_family}」")
        if exc.get("type") == "occupation" and exc["value"] == occ.occupation_id:
            return HardEvalResult("exclude", "explicit_exclusion",
                                  f"用户明确排除职业「{occ.preferred_name}」")

    # ---- 学历硬门槛 ----
    edu_ev: EvidenceValue = profile.hard_constraints.get("max_education_investment_years", EvidenceValue.missing())
    user_edu_level = _user_education_level(profile)
    req_edu = (occ.typical_requirements or {}).get("entry_education")

    if req_edu and user_edu_level is not None:
        req_years = cfg.education_years.get(req_edu, 0)
        user_years = cfg.education_years.get(user_edu_level, 0)
        if edu_ev.value is not None:
            additional = max(0, req_years - user_years)
            if additional > edu_ev.value:
                return HardEvalResult(
                    "exclude", "education_hard_gate",
                    f"该职业要求 {req_edu}（≈{req_years}年），你已投入 {user_years} 年，"
                    f"额外需 {additional} 年，超出你的上限 {edu_ev.value} 年")
            evals.append(HardConstraintEval("education", "pass",
                                            f"额外需 {additional} 年 ≤ 上限 {edu_ev.value} 年"))
        else:
            soft_penalty += cfg.education_unknown_soft_penalty
            evals.append(HardConstraintEval(
                "education", "unknown",
                f"未提供学历投入上限，仅对学历要求高于你的职业施加 {cfg.education_unknown_soft_penalty} 软降权"))

    # ---- 执照硬门槛 ----
    lic_ev = profile.hard_constraints.get("license_obtainable", EvidenceValue.missing())
    lic_req = (occ.entry_barriers or {}).get("license_required")
    if lic_req is True:
        if lic_ev.value is False:
            return HardEvalResult("exclude", "license_hard_gate",
                                  "该职业需要执照/资质，用户明确表示不可获取")
        if lic_ev.value is None:
            soft_penalty += cfg.license_unknown_soft_penalty
            evals.append(HardConstraintEval(
                "license", "unknown",
                f"该职业需要执照/资质，你未确认是否愿意获取；施加 {cfg.license_unknown_soft_penalty} 软降权，请自行核实当地政策"))
        else:
            evals.append(HardConstraintEval("license", "pass", "你已确认可获取执照"))
    elif lic_req == "unknown":
        soft_penalty += cfg.license_unknown_soft_penalty
        evals.append(HardConstraintEval(
            "license", "unknown",
            "职业执照要求 unknown，无法判断；请自行核实当地政策"))
    else:
        evals.append(HardConstraintEval("license", "pass", "该职业通常无需执照"))

    # ---- 经济承压 ----
    econ = profile.hard_constraints.get("economic_pressure_period", EvidenceValue.missing())
    job_zone = (occ.typical_requirements or {}).get("job_zone")
    if econ.value == "immediate" and isinstance(job_zone, int) and job_zone >= 4:
        soft_penalty += cfg.economic_pressure_soft_penalty
        evals.append(HardConstraintEval(
            "economic_pressure", "soft_penalty",
            f"你需要立即有收入，但该职业准备周期较长（Job Zone {job_zone}）"))

    # ---- 地域 ----
    evals.append(HardConstraintEval(
        "region", "unknown",
        "职业库无地域可用性字段，请结合你所在地区的就业市场核实"))

    return HardEvalResult("pass", soft_penalty=soft_penalty, evals=tuple(evals))


def _user_education_level(profile: UserProfile) -> str | None:
    """从画像中获取用户当前最高学历。画像当前契约未包含此字段时返回 None。"""
    # 阶段 4 契约中没有显式 education_level；未来应在 hard_constraints 中增加。
    # 当前保守返回 None，由 soft_penalty 路径处理。
    return None
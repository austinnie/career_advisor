"""从 O*NET 快照向大典职业补充属性（依 crosswalk）。"""
from __future__ import annotations
import dataclasses

from ..models import Occupation
from .cn_onet_crosswalk import CROSSWALK, CnOnetMapping


def enrich(
    cn_occupations: list[Occupation],
    onet_by_soc: dict[str, Occupation],
    crosswalk: dict[str, CnOnetMapping] | None = None,
) -> list[Occupation]:
    """对每条大典职业：
    - 若 crosswalk 中无映射 → 原样返回（skill_vector 保持 None）
    - 若映射存在但 O*NET 快照中没有对应 SOC → 原样返回
    - 否则复制 skill_vector / riasec_profile / work_context / typical_requirements；
      license_required 保持 "unknown"（O*NET 无此字段，不做推断）
    """
    cw = crosswalk if crosswalk is not None else CROSSWALK
    out: list[Occupation] = []
    for occ in cn_occupations:
        code = (occ.taxonomy_refs or {}).get("cn_dadian_2022", {}).get("detailed_code")
        mapping = cw.get(code) if code else None
        if mapping is None:
            out.append(occ)
            continue
        onet = onet_by_soc.get(mapping.onet_soc)
        if onet is None:
            out.append(occ)
            continue

        new_flags = list(occ.data_quality_flags)
        new_flags.append(f"cn_onet_crosswalk:{mapping.confidence}")
        out.append(dataclasses.replace(
            occ,
            skill_vector=onet.skill_vector,
            riasec_profile=onet.riasec_profile,
            work_context=onet.work_context,
            typical_requirements=onet.typical_requirements,
            data_quality_flags=new_flags,
        ))
    return out
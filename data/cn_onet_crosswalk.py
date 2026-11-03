"""大典细类码 → O*NET SOC 人工映射表。

来源限制
--------
人社部与 O*NET 之间没有官方对照表。本表为**人工语义比对**结果，
每条映射必带：
  - source        : 比对依据（大典描述 vs O*NET 职业描述）
  - confidence    : high / medium / low
  - reviewed_at   : 最近一次人工审核日期

生产部署要求
------------
- 本表扩充必须经过人工审核
- confidence=low 的映射仍可参与评分，但在结果中必须由交互层标注
- 未列入本表的大典职业 → skill_vector 保持 None → 进入 missing_skill_vector 排除路径
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class CnOnetMapping:
    detailed_code: str
    onet_soc: str
    source: str
    confidence: str           # high | medium | low
    reviewed_at: str          # ISO 8601


CROSSWALK: dict[str, CnOnetMapping] = {
    m.detailed_code: m for m in [
        CnOnetMapping(
            detailed_code="2-02-10-08",
            onet_soc="15-1252.00",                  # Software Developers
            source="大典职业描述与 O*NET 15-1252 任务描述人工比对",
            confidence="high",
            reviewed_at="2024-01-01",
        ),
        CnOnetMapping(
            detailed_code="2-02-10-07",
            onet_soc="15-2051.00",                  # Data Scientists
            source="大典「数据分析师」与 O*NET Data Scientists 人工比对",
            confidence="high",
            reviewed_at="2024-01-01",
        ),
        CnOnetMapping(
            detailed_code="2-02-10-05",
            onet_soc="15-1211.00",                  # Computer Systems Analysts
            source="大典「信息系统分析工程技术人员」与 O*NET 人工比对",
            confidence="medium",
            reviewed_at="2024-01-01",
        ),
        CnOnetMapping(
            detailed_code="3-01-05-02",
            onet_soc="43-6014.00",                  # Secretaries and Administrative Assistants
            source="大典「行政专员」与 O*NET Secretaries 人工比对",
            confidence="medium",
            reviewed_at="2024-01-01",
        ),
        CnOnetMapping(
            detailed_code="2-05-02-01",
            onet_soc="29-1141.00",                  # Registered Nurses
            source="大典「护士」与 O*NET Registered Nurses 人工比对",
            confidence="high",
            reviewed_at="2024-01-01",
        ),
    ]
}
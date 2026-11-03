"""覆盖边界声明。数量从职业库动态查询，不可由 LLM 或常量生成。"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date


TAXONOMY_VERSIONS = [
    {"name": "中华人民共和国职业分类大典", "version": "2022",
     "source": "人力资源和社会保障部", "status": "锚定中国职业；细类数量需人工核实"},
    {"name": "O*NET-SOC", "version": "2018 SOC / O*NET 30.x",
     "occupational_titles": 1016, "data_level_occupations": 923,
     "source": "U.S. DOL"},
    {"name": "ISCO-08 / ESCO", "version": "ISCO-08 / ESCO v1.2.1",
     "structure": "10 major / 43 sub-major / 130 minor / 436 unit groups",
     "skills_count_approx": 13890, "source": "European Commission"},
]

NOT_COVERED = [
    {"category": "新兴职业",
     "handling": ("人社部自 2019 年建立新职业发布制度以来累计发布的新职业，"
                  "尚未完成 O*NET/ESCO 技能描述映射或大典细类码校准的，不进入匹配空间。"
                  "输出标注为『未收录』，不以任何形式估算其前景或匹配分。")},
    {"category": "无结构化技能字段的职业",
     "handling": "不进入匹配打分空间；在覆盖声明中列出并注明原因。"},
    {"category": "地区前景缺口",
     "handling": ("中国职业若无官方 10 年期预测，Prospect 中对应 indicator_value 为 NULL，"
                  "渲染为『暂无可靠数据』。")},
]


@dataclass(frozen=True)
class CoverageDeclaration:
    taxonomy_versions: list[dict]
    matchable_occupation_count: int          # 必须来自数据层实查
    total_occupation_count: int
    excluded_count: int
    sampling_note: str
    not_covered: list[dict]
    data_snapshot_date: str


def build_coverage(occupations) -> CoverageDeclaration:
    """从职业库实查生成。审计缺陷 4.1—4.4 的修复点。"""
    total = len(occupations)
    matchable = sum(1 for o in occupations if o.skill_vector is not None
                    and o.occupation_family)
    excluded = total - matchable
    sampling_note = (
        f"全量入库 {total} 个职业；其中 {matchable} 个具有 skill_vector 与 occupation_family，"
        f"可参与匹配；{excluded} 个因缺少结构化技能字段或族标注未参与匹配。"
    ) if total else "职业库为空，覆盖声明不成立。"
    return CoverageDeclaration(
        taxonomy_versions=TAXONOMY_VERSIONS,
        matchable_occupation_count=matchable,
        total_occupation_count=total,
        excluded_count=excluded,
        sampling_note=sampling_note,
        not_covered=NOT_COVERED,
        data_snapshot_date=date.today().isoformat(),
    )


DISCLAIMER = "本结果为辅助决策参考，不构成就业承诺或投资建议。"
LICENSE_NOTE = "该职业可能涉及执照/资质要求，请自行核实当地最新政策。"
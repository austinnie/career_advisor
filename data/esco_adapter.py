"""ESCO 技能邻接表构建器。产出静态资产 skills_adjacency.json。

所需 ESCO 下载文件：
  skills_en.csv
  broaderRelationsSkillPillar_en.csv
下载：https://esco.ec.europa.eu/en/use-esco/download

本模块不修改匹配层；邻接表供后续阶段接入 score_skill_transfer 使用。
"""
from __future__ import annotations
import csv, json
from collections import defaultdict
from pathlib import Path


def build_adjacency(skills_csv: Path, relations_csv: Path,
                    output_path: Path) -> dict:
    """返回 {skill_uri: [sibling_uris]} 并写入 output_path。
    兄弟关系 = 共享同一父节点（不区分父节点是 Skill 还是 SkillGroup）。"""
    skill_uris: set[str] = set()
    with skills_csv.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            uri = row.get("conceptUri", "").strip()
            if uri:
                skill_uris.add(uri)

    parent_of: dict[str, str] = {}
    with relations_csv.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            child = row.get("conceptUri", "").strip()
            parent = row.get("broaderUri", "").strip()
            if child and parent and child in skill_uris:
                parent_of.setdefault(child, parent)

    by_parent: dict[str, list[str]] = defaultdict(list)
    for child, parent in parent_of.items():
        by_parent[parent].append(child)

    adjacency: dict[str, list[str]] = {}
    for parent, children in by_parent.items():
        for child in children:
            adjacency[child] = sorted(c for c in children if c != child)

    payload = {
        "version": "esco-skill-adjacency-v1",
        "skill_count": len(skill_uris),
        "mapped_skill_count": len(adjacency),
        "adjacency": adjacency,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload
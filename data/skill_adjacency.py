"""O*NET 技能邻接表构建与加载。兼容 CSV 与 TXT 格式。"""
from __future__ import annotations
import csv
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path

ADJACENCY_VERSION = "onet-skill-adjacency-v1"

@dataclass(frozen=True)
class SkillAdjacency:
    version: str
    source: str
    adjacency: dict[str, frozenset[str]]

    def neighbors(self, skill_id: str) -> frozenset[str]:
        return self.adjacency.get(skill_id, frozenset())

    def has_neighbor(self, skill_id: str, other: str) -> bool:
        return other in self.neighbors(skill_id)

def _parent_of(element_id: str) -> str:
    parts = element_id.rsplit(".", 1)
    return parts[0] if len(parts) == 2 else element_id

def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")

def build_adjacency_from_onet(onet_dir: Path) -> SkillAdjacency:
    onet_dir = Path(onet_dir)
    
    # 自动寻找新版或旧版技能文件
    skills_path = None
    for filename in ["essential_skills.csv", "skills.csv", "essential_skills.txt", "skills.txt"]:
        p = onet_dir / filename
        if p.exists():
            skills_path = p
            break
            
    if not skills_path:
        raise FileNotFoundError(f"未找到 essential_skills.csv 或 skills.txt in {onet_dir}")

    text = skills_path.read_text(encoding="utf-8-sig", errors="replace")
    first_line = text.splitlines()[0] if text else ""
    delimiter = "\t" if "\t" in first_line else ","
    
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)

    element_to_name: dict[str, str] = {}
    for row in reader:
        if row.get("Scale ID", "").strip() != "IM":
            continue
        eid = row.get("Element ID", "").strip()
        name = row.get("Element Name", "").strip()
        if eid and name:
            element_to_name.setdefault(eid, name)

    by_parent: dict[str, list[str]] = {}
    for eid in element_to_name:
        by_parent.setdefault(_parent_of(eid), []).append(eid)

    adjacency: dict[str, set[str]] = {}
    for children in by_parent.values():
        if len(children) < 2:
            continue
        sids = [_slug(element_to_name[c]) for c in children]
        for i, sid in enumerate(sids):
            for j, other in enumerate(sids):
                if i != j and sid != other:
                    adjacency.setdefault(sid, set()).add(other)

    return SkillAdjacency(
        version=ADJACENCY_VERSION,
        source="ONET-31.0",
        adjacency={k: frozenset(v) for k, v in adjacency.items()},
    )

def save_adjacency(adjacency: SkillAdjacency, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": adjacency.version,
        "source": adjacency.source,
        "skill_count": len(adjacency.adjacency),
        "adjacency": {k: sorted(v) for k, v in adjacency.adjacency.items()},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

def load_adjacency(path: Path) -> SkillAdjacency | None:
    path = Path(path)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return SkillAdjacency(
        version=payload["version"],
        source=payload["source"],
        adjacency={k: frozenset(v) for k, v in payload["adjacency"].items()},
    )
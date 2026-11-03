"""O*NET 技能邻接表构建与加载。

邻接规则：共享同一父前缀的 Element ID 对应技能互为邻居（hops=1）。
示例：2.B.3.e (Programming) 与 2.B.3.b (Technology Design) 共享 2.B.3 → 互为邻居。
"""
from __future__ import annotations
import json, re
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
    skills_path = Path(onet_dir) / "skills.txt"
    if not skills_path.exists():
        raise FileNotFoundError(f"skills.txt not found in {onet_dir}")

    lines = skills_path.read_text(encoding="utf-8", errors="replace").splitlines()
    header = lines[0].split("\t")
    i_elem_id = header.index("Element ID")
    i_elem_name = header.index("Element Name")
    i_scale = header.index("Scale ID")

    element_to_name: dict[str, str] = {}
    for line in lines[1:]:
        if not line.strip():
            continue
        p = line.split("\t")
        if p[i_scale].strip() != "IM":
            continue
        eid = p[i_elem_id].strip()
        name = p[i_elem_name].strip()
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
        source="ONET-30.x",
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
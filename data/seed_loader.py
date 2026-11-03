"""职业库加载器。优先读取快照；快照不存在时回退到手工种子。
快照通过 build_snapshot() 从 O*NET 构建，构建过程可重复、可审计。"""
from __future__ import annotations
import json, logging
from dataclasses import asdict
from pathlib import Path

from ..models import Occupation
from .onet_adapter import ONetOccupationAdapter
from .skill_adjacency import (SkillAdjacency, build_adjacency_from_onet,
                               save_adjacency, load_adjacency)

from .cn_samples import load_sample_cn_occupations
from .cn_enricher import enrich as enrich_cn

logger = logging.getLogger(__name__)


SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "occupations.json"
SKILLS_ADJACENCY_PATH = Path(__file__).parent / "snapshots" / "skills_adjacency.json"

def snapshot_exists() -> bool:
    """供 demo / 交互层判断当前使用的是快照还是手工回退数据。"""
    return SNAPSHOT_PATH.exists()
    
def load_occupations() -> list[Occupation]:
    """加载优先级：
    1. O*NET 快照存在 → 返回快照
    2. 否则：大典样本 + enrichment（若有 O*NET 快照可跨源），
       与手工种子合并（大典职业排在前面）
    3. 大典样本不可用时 → 纯手工种子
    """
    if SNAPSHOT_PATH.exists():
        return _load_snapshot(SNAPSHOT_PATH)

    logger.info("O*NET snapshot not found; falling back to CN samples + hand seeds")
    try:
        cn_occs = load_sample_cn_occupations()
    except Exception as exc:
        logger.warning("CN sample load failed: %s; falling back to hand seeds only", exc)
        return _load_hand_seeded()

    # 尝试从手工种子中提取 O*NET 职业用于 enrichment。
    # 若无快照，enrich 无跨源可补，大典职业保持骨架。
    onet_by_soc = _onet_by_soc_from_snapshot_or_empty()
    cn_enriched = enrich_cn(cn_occs, onet_by_soc)

    hand = _load_hand_seeded()
    # 若手工种子中有与大典同 occupation_id 的（如 CN-2022-2-02-10-08），
    # 手工种子优先——它是人工精标过的，覆盖骨架
    hand_ids = {o.occupation_id for o in hand}
    merged = [o for o in cn_enriched if o.occupation_id not in hand_ids]
    merged.extend(hand)
    return merged


def _onet_by_soc_from_snapshot_or_empty() -> dict[str, Occupation]:
    if not SNAPSHOT_PATH.exists():
        return {}
    import json
    payload = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    out: dict[str, Occupation] = {}
    for item in payload["occupations"]:
        occ = Occupation(**item)
        soc = (occ.taxonomy_refs or {}).get("onet_soc_2018", {}).get("soc_code")
        if soc:
            out[soc] = occ
    return out


def _load_snapshot(path: Path) -> list[Occupation]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [Occupation(**item) for item in payload["occupations"]]


def build_snapshot(onet_dir: str, output_path: Path | None = None,
                   min_skills_per_occupation: int = 3) -> dict:
    """从 O*NET 目录构建快照。返回统计信息。
    若 O*NET 目录缺失必需文件 → FileNotFoundError 向上抛，不静默回退。"""
    target = output_path or SNAPSHOT_PATH
    adapter = ONetOccupationAdapter()
    payload = adapter.fetch(onet_dir=onet_dir)
    occupations = adapter.normalize_occupations(payload)
    filtered = [o for o in occupations
                if o.skill_vector and len(o.skill_vector) >= min_skills_per_occupation]

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({
            "version": "occupation-snapshot-v1",
            "source_id": adapter.source_id,
            "source_url_or_file": payload.source_url_or_file,
            "retrieved_at": payload.retrieved_at.isoformat(),
            "family_mapping_version": "families-v1.0",
            "total_parsed": len(occupations),
            "kept_after_filter": len(filtered),
            "min_skills_per_occupation": min_skills_per_occupation,
            "occupations": [asdict(o) for o in filtered],
        }, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    stats = {"parsed": len(occupations), "kept": len(filtered),
             "path": str(target)}
    logger.info("Snapshot built: %s", stats)

    # 同步构建技能邻接表
    try:
        adjacency = build_adjacency_from_onet(Path(onet_dir))
        save_adjacency(adjacency, SKILLS_ADJACENCY_PATH)
        stats["adjacency_skill_count"] = len(adjacency.adjacency)
    except FileNotFoundError:
        logger.warning("skills.txt not available; skipping adjacency build")
        stats["adjacency_skill_count"] = 0
        
    return stats


def _load_hand_seeded() -> list[Occupation]:
    # 原有 5 条手工种子，原样保留
    from .seeds import _hand_seeded_data
    return _hand_seeded_data()

def load_skill_adjacency() -> SkillAdjacency | None:
    """加载技能邻接表。不存在时返回 None（调用方退化为精确匹配）。"""
    return load_adjacency(SKILLS_ADJACENCY_PATH)
    
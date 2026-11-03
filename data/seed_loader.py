"""职业库加载器。支持 O*NET 快照 + 大典样本的合并。"""
from __future__ import annotations
import json, logging
from dataclasses import asdict
from pathlib import Path

from ..models import Occupation
from .onet_adapter import ONetOccupationAdapter
from .cn_samples import load_sample_cn_occupations
from .cn_enricher import enrich as enrich_cn
from .skill_adjacency import (SkillAdjacency, build_adjacency_from_onet,
                               save_adjacency, load_adjacency)

logger = logging.getLogger(__name__)

SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "occupations.json"
SKILLS_ADJACENCY_PATH = Path(__file__).parent / "snapshots" / "skills_adjacency.json"


def snapshot_exists() -> bool:
    return SNAPSHOT_PATH.exists()


def load_occupations() -> list[Occupation]:
    if SNAPSHOT_PATH.exists():
        onet_occs = _load_snapshot(SNAPSHOT_PATH)
        try:
            # 加载大典样本并通过 crosswalk 增强
            cn_occs = load_sample_cn_occupations()
            onet_by_soc = {}
            for o in onet_occs:
                soc = (o.taxonomy_refs or {}).get("onet_soc_2018", {}).get("soc_code")
                if soc:
                    onet_by_soc[soc] = o
            
            cn_enriched = enrich_cn(cn_occs, onet_by_soc)
            
            # 合并策略：大典优先，去除 O*NET 中的重复项（如果 ID 一样的话）
            cn_ids = {o.occupation_id for o in cn_enriched}
            merged = cn_enriched + [o for o in onet_occs if o.occupation_id not in cn_ids]
            logger.info("Merged %d CN occupations with %d O*NET occupations", len(cn_enriched), len(onet_occs))
            return merged
        except Exception as e:
            logger.warning("Failed to load/merge CN occupations: %s", e)
            return onet_occs

    logger.info("O*NET snapshot not found; falling back to hand seeds.")
    from .seeds import _hand_seeded_data
    return _hand_seeded_data()


def _load_snapshot(path: Path) -> list[Occupation]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [Occupation(**item) for item in payload["occupations"]]


def build_snapshot(onet_dir: str, output_path: Path | None = None,
                   min_skills_per_occupation: int = 3) -> dict:
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
    
    # 构建邻接表
    try:
        adjacency = build_adjacency_from_onet(Path(onet_dir))
        save_adjacency(adjacency, SKILLS_ADJACENCY_PATH)
        stats = {"parsed": len(occupations), "kept": len(filtered), "path": str(target), "adjacency_count": len(adjacency.adjacency)}
    except FileNotFoundError as e:
        logger.warning("Skill adjacency build failed: %s", e)
        stats = {"parsed": len(occupations), "kept": len(filtered), "path": str(target), "adjacency_count": 0}

    logger.info("Snapshot built: %s", stats)
    return stats


def load_skill_adjacency() -> SkillAdjacency | None:
    return load_adjacency(SKILLS_ADJACENCY_PATH)
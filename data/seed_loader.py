"""职业库加载器。优先读取快照；快照不存在时回退到手工种子。
快照通过 build_snapshot() 从 O*NET 构建，构建过程可重复、可审计。"""
from __future__ import annotations
import json, logging
from dataclasses import asdict
from pathlib import Path

from ..models import Occupation
from .onet_adapter import ONetOccupationAdapter


logger = logging.getLogger(__name__)


SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "occupations.json"

def snapshot_exists() -> bool:
    """供 demo / 交互层判断当前使用的是快照还是手工回退数据。"""
    return SNAPSHOT_PATH.exists()
    
def load_occupations() -> list[Occupation]:
    if SNAPSHOT_PATH.exists():
        return _load_snapshot(SNAPSHOT_PATH)
    logger.info("Occupation snapshot not found at %s; falling back to hand-seeded.",
                SNAPSHOT_PATH)
    return _load_hand_seeded()


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
    return stats


def _load_hand_seeded() -> list[Occupation]:
    # 原有 5 条手工种子，原样保留
    from .seeds import _hand_seeded_data
    return _hand_seeded_data()
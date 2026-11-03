"""O*NET 职业适配器。兼容 O*NET 31.0 格式，合并 Essential 与 Software Skills。"""
from __future__ import annotations
import csv
import io
import re
from datetime import datetime, timezone
from pathlib import Path

from ..models import Occupation
from .adapters import DataSourceAdapter, RawPayload, SourceCategory
from .family_mapping import (family_for_soc, onet_importance_to_1_5,
                              onet_cx_to_0_100, onet_oi_to_0_100,
                              ONET_CRITICAL_THRESHOLD_1_5)

_RIASEC_LABELS = {
    "Realistic": "R", "Investigative": "I", "Artistic": "A",
    "Social": "S", "Enterprising": "E", "Conventional": "C",
}

_WORK_CONTEXT_KEYS = {
    "Indoors, Environmentally Controlled": ("indoor_vs_outdoor", "indoor"),
    "Work With Work Group or Team":        ("teamwork_vs_independent", "team"),
    "Freedom to Make Decisions":           ("job_autonomy", "autonomy"),
}

# 必需文件（software_skills 为非必需，存在则读取）
_REQUIRED_BASES = ["occupation_data", "essential_skills", "career_interest_types", "work_context", "job_zones"]


class ONetOccupationAdapter(DataSourceAdapter):
    source_id = "ONET-31.0"
    source_category = SourceCategory.TAXONOMY
    expected_refresh_days = 90

    def fetch(self, onet_dir: str, **params) -> RawPayload:
        onet_path = Path(onet_dir)
        missing = []
        resolved_paths = {}
        
        for base in _REQUIRED_BASES + ["software_skills", "education"]:
            found = None
            for ext in [".csv", ".txt"]:
                p = onet_path / f"{base}{ext}"
                if p.exists():
                    found = p
                    break
            if found:
                resolved_paths[base] = found
            elif base in _REQUIRED_BASES:
                missing.append(base)

        if missing:
            raise FileNotFoundError(f"O*NET required files missing in {onet_dir}: {missing}")

        return RawPayload(
            source_id=self.source_id,
            retrieved_at=datetime.now(timezone.utc),
            source_url_or_file=str(onet_path.resolve()),
            content={"dir": str(onet_path), "paths": resolved_paths},
            content_type="onet_directory",
        )

    def normalize_prospects(self, payload: RawPayload) -> list:
        return []

    def normalize_occupations(self, payload: RawPayload) -> list[Occupation]:
        paths = payload.content["paths"]

        occupations = _parse_tsv(paths["occupation_data"], required_cols=["O*NET-SOC Code", "Title"])
        interests = _parse_interests(paths["career_interest_types"])
        
        # 合并 Essential Skills 和 Software Skills
        skills = _parse_skills(paths["essential_skills"])
        if "software_skills" in paths:
            software_skills = _parse_skills(paths["software_skills"])
            for soc, sw_list in software_skills.items():
                skills.setdefault(soc, []).extend(sw_list)

        work_context = _parse_work_context(paths["work_context"])
        job_zones = _parse_kv(paths["job_zones"], "O*NET-SOC Code", "Job Zone")
        
        education = {}
        if "education" in paths:
            education = _parse_education(paths["education"])

        results: list[Occupation] = []
        for soc, info in occupations.items():
            skill_list = skills.get(soc, [])
            if not skill_list:
                continue
            family = family_for_soc(soc)
            if family is None:
                continue
            
            results.append(Occupation(
                occupation_id=f"ONET-{soc}",
                preferred_name=info["title"],
                occupation_family=family,
                taxonomy_refs={"onet_soc_2018": {"soc_code": soc, "data_level": True}},
                riasec_profile=interests.get(soc),
                skill_vector=skill_list,
                typical_requirements={
                    "entry_education": education.get(soc),
                    "job_zone": job_zones.get(soc),
                },
                work_context=work_context.get(soc),
                entry_barriers={"license_required": "unknown", "license_note": None},
            ))
        return results

# ============ 内部解析器 ============

def _read_delimited(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    first_line = text.splitlines()[0] if text else ""
    delimiter = "\t" if "\t" in first_line else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    return list(reader)

def _parse_tsv(path: Path, required_cols: list[str]) -> dict[str, dict]:
    rows = _read_delimited(path)
    if not rows: return {}
    out: dict[str, dict] = {}
    for row in rows:
        soc = (row.get("O*NET-SOC Code") or "").strip()
        if not soc: continue
        out[soc] = {"title": (row.get("Title") or "").strip()}
    return out

def _parse_interests(path: Path) -> dict[str, dict[str, float]]:
    rows = _read_delimited(path)
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        if row.get("Scale ID", "").strip() != "OI": continue
        dim = _RIASEC_LABELS.get(row.get("Element Name", "").strip())
        if not dim: continue
        try: score = onet_oi_to_0_100(float(row.get("Data Value", "")))
        except (ValueError, TypeError): continue
        out.setdefault(row.get("O*NET-SOC Code", "").strip(), {})[dim] = round(score, 2)
    return out

def _parse_skills(path: Path) -> dict[str, list[dict]]:
    rows = _read_delimited(path)
    out: dict[str, list[dict]] = {}
    for row in rows:
        if row.get("Scale ID", "").strip() not in ("IM", "LV"): continue
        # 只取 IM (Importance) 避免重复
        if row.get("Scale ID", "").strip() != "IM": continue
        
        try: raw = float(row.get("Data Value", ""))
        except (ValueError, TypeError): continue
        
        # Software Skills 没有 Importance，通常固定为 3.0 或 5.0
        if "Software Skills" in path.name or "software_skills" in path.name:
            raw = 5.0
            
        importance = round(onet_importance_to_1_5(raw), 2)
        skill_name = row.get("Element Name", "").strip()
        skill_id = _normalize_skill_id(skill_name)
        if not skill_id: continue
        
        out.setdefault(row.get("O*NET-SOC Code", "").strip(), []).append({
            "skill_id": skill_id,
            "importance": importance,
            "critical": importance >= ONET_CRITICAL_THRESHOLD_1_5,
        })
    return out

def _parse_work_context(path: Path) -> dict[str, dict]:
    rows = _read_delimited(path)
    out: dict[str, dict] = {}
    for row in rows:
        if row.get("Scale ID", "").strip() != "CX": continue
        spec = _WORK_CONTEXT_KEYS.get(row.get("Element Name", "").strip())
        if not spec: continue
        key, _ = spec
        try: v = onet_cx_to_0_100(float(row.get("Data Value", "")))
        except (ValueError, TypeError): continue
        out.setdefault(row.get("O*NET-SOC Code", "").strip(), {})[key] = round(v, 2)
    return out

def _parse_kv(path: Path, key_col: str, val_col: str) -> dict[str, str]:
    rows = _read_delimited(path)
    out: dict[str, str] = {}
    for row in rows:
        k, v = (row.get(key_col) or "").strip(), (row.get(val_col) or "").strip()
        if k and v: out[k] = v
    return out

def _parse_education(path: Path) -> dict[str, str]:
    rows = _read_delimited(path)
    out: dict[str, str] = {}
    for row in rows:
        if row.get("Scale ID", "").strip() != "RL": continue
        soc = (row.get("O*NET-SOC Code") or "").strip()
        if soc and soc not in out:
            level = (row.get("Element Name") or "").strip().lower()
            if "doctoral" in level or "post-doctoral" in level: out[soc] = "phd"
            elif "master" in level: out[soc] = "master"
            elif "bachelor" in level: out[soc] = "bachelor"
            elif "associate" in level: out[soc] = "associate"
            elif "high school" in level: out[soc] = "high_school"
            else: out[soc] = "unknown"
    return out

def _normalize_skill_id(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
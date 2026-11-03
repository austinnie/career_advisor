"""O*NET 职业适配器。从 O*NET 数据库 txt 文件构建 Occupation 记录。

数据文件下载：https://www.onetcenter.org/database.html
所需文件（放入同一目录）：
  occupation_data.txt, skills.txt, interests.txt,
  work_context.txt, job_zones.txt
可选文件：
  education.txt, task_statements.txt

本适配器不贡献 Prospect（O*NET 无 10 年期就业预测）。
字段缺失一律为 None；不填默认值。
"""
from __future__ import annotations
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

_REQUIRED_FILES = ["occupation_data.txt", "skills.txt", "interests.txt",
                   "work_context.txt", "job_zones.txt"]


class ONetOccupationAdapter(DataSourceAdapter):
    source_id = "ONET-30.x"
    source_category = SourceCategory.TAXONOMY
    expected_refresh_days = 90

    def fetch(self, onet_dir: str, **params) -> RawPayload:
        onet_path = Path(onet_dir)
        missing = [f for f in _REQUIRED_FILES if not (onet_path / f).exists()]
        if missing:
            raise FileNotFoundError(
                f"O*NET required files missing in {onet_dir}: {missing}. "
                f"Download from https://www.onetcenter.org/database.html")
        # 只保留路径，不读入内存；解析在 normalize_occupations 中逐文件进行
        return RawPayload(
            source_id=self.source_id,
            retrieved_at=datetime.now(timezone.utc),
            source_url_or_file=str(onet_path.resolve()),
            content={"dir": str(onet_path)},
            content_type="onet_directory",
        )

    def normalize_prospects(self, payload: RawPayload) -> list:
        return []  # O*NET 不贡献 Prospect

    def normalize_occupations(self, payload: RawPayload) -> list[Occupation]:
        root = Path(payload.content["dir"])

        occupations = _parse_tsv(root / "occupation_data.txt",
                                 required_cols=["O*NET-SOC Code", "Title"])
        interests = _parse_interests(root / "interests.txt")
        skills = _parse_skills(root / "skills.txt")
        work_context = _parse_work_context(root / "work_context.txt")
        job_zones = _parse_kv(root / "job_zones.txt", "O*NET-SOC Code", "Job Zone")
        education = (_parse_education(root / "education.txt")
                     if (root / "education.txt").exists() else {})

        results: list[Occupation] = []
        for soc, info in occupations.items():
            skill_list = skills.get(soc, [])
            if not skill_list:
                continue                       # 无技能 → 不进匹配空间
            family = family_for_soc(soc)
            if family is None:
                continue                       # 未映射的 major group → 跳过
            data_level = soc.endswith(".00") or soc.endswith(".01")

            riasec = interests.get(soc)
            results.append(Occupation(
                occupation_id=f"ONET-{soc}",
                preferred_name=info["title"],
                occupation_family=family,
                taxonomy_refs={"onet_soc_2018": {"soc_code": soc,
                                                 "data_level": data_level}},
                riasec_profile=riasec,
                skill_vector=skill_list,
                typical_requirements={
                    "entry_education": education.get(soc),
                    "job_zone": job_zones.get(soc),
                    "work_experience": None,     # O*NET 此字段在独立文件；暂不解析
                },
                work_context=work_context.get(soc),
                entry_barriers={
                    "license_required": "unknown",  # O*NET 无执照字段；不做推断
                    "license_note": None,
                },
                data_quality_flags=[] if riasec and work_context.get(soc) else [
                    flag for flag in
                    (["no_riasec"] if not riasec else [])
                    + (["no_work_context"] if not work_context.get(soc) else [])
                ],
            ))
        return results


# ============ 内部解析器 ============

def _open_tsv(path: Path):
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def _parse_tsv(path: Path, required_cols: list[str]) -> dict[str, dict]:
    lines = _open_tsv(path)
    header = lines[0].split("\t")
    missing = [c for c in required_cols if c not in header]
    if missing:
        raise ValueError(f"{path.name} missing columns: {missing}")
    idx = {c: header.index(c) for c in required_cols}
    out: dict[str, dict] = {}
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split("\t")
        soc = parts[idx["O*NET-SOC Code"]].strip()
        if not soc:
            continue
        out[soc] = {"title": parts[idx["Title"]].strip()}
    return out


def _parse_interests(path: Path) -> dict[str, dict[str, float]]:
    lines = _open_tsv(path)
    header = lines[0].split("\t")
    i_soc = header.index("O*NET-SOC Code")
    i_elem = header.index("Element Name")
    i_scale = header.index("Scale ID")
    i_val = header.index("Data Value")
    out: dict[str, dict[str, float]] = {}
    for line in lines[1:]:
        if not line.strip():
            continue
        p = line.split("\t")
        if p[i_scale].strip() != "OI":
            continue
        dim = _RIASEC_LABELS.get(p[i_elem].strip())
        if not dim:
            continue
        try:
            score = onet_oi_to_0_100(float(p[i_val]))
        except ValueError:
            continue
        out.setdefault(p[i_soc].strip(), {})[dim] = round(score, 2)
    return out


def _parse_skills(path: Path) -> dict[str, list[dict]]:
    lines = _open_tsv(path)
    header = lines[0].split("\t")
    i_soc = header.index("O*NET-SOC Code")
    i_elem_name = header.index("Element Name")
    i_scale = header.index("Scale ID")
    i_val = header.index("Data Value")
    out: dict[str, list[dict]] = {}
    for line in lines[1:]:
        if not line.strip():
            continue
        p = line.split("\t")
        if p[i_scale].strip() != "IM":
            continue
        try:
            raw = float(p[i_val])
        except ValueError:
            continue
        importance = round(onet_importance_to_1_5(raw), 2)
        skill_name = p[i_elem_name].strip()
        skill_id = _normalize_skill_id(skill_name)
        if not skill_id:
            continue
        out.setdefault(p[i_soc].strip(), []).append({
            "skill_id": skill_id,
            "importance": importance,
            "critical": importance >= ONET_CRITICAL_THRESHOLD_1_5,
            "provenance_original_name": skill_name,
        })
    return out


def _parse_work_context(path: Path) -> dict[str, dict]:
    lines = _open_tsv(path)
    header = lines[0].split("\t")
    i_soc = header.index("O*NET-SOC Code")
    i_elem = header.index("Element Name")
    i_scale = header.index("Scale ID")
    i_val = header.index("Data Value")
    out: dict[str, dict] = {}
    for line in lines[1:]:
        if not line.strip():
            continue
        p = line.split("\t")
        if p[i_scale].strip() != "CX":
            continue
        elem = p[i_elem].strip()
        spec = _WORK_CONTEXT_KEYS.get(elem)
        if spec is None:
            continue
        key, _ = spec
        try:
            v = onet_cx_to_0_100(float(p[i_val]))
        except ValueError:
            continue
        out.setdefault(p[i_soc].strip(), {})[key] = round(v, 2)
    return out


def _parse_kv(path: Path, key_col: str, val_col: str) -> dict[str, str]:
    lines = _open_tsv(path)
    header = lines[0].split("\t")
    if key_col not in header or val_col not in header:
        return {}
    ik, iv = header.index(key_col), header.index(val_col)
    out: dict[str, str] = {}
    for line in lines[1:]:
        if not line.strip():
            continue
        p = line.split("\t")
        k, v = p[ik].strip(), p[iv].strip()
        if k and v:
            out[k] = v
    return out


def _parse_education(path: Path) -> dict[str, str]:
    """O*NET education.txt 有 Element Name 列（如 'Bachelor's Degree'），
    以及 Scale ID='RL' 的必需等级。取 Element Name 作为 entry_education。"""
    lines = _open_tsv(path)
    header = lines[0].split("\t")
    i_soc = header.index("O*NET-SOC Code")
    i_elem = header.index("Element Name")
    i_scale = header.index("Scale ID")
    out: dict[str, str] = {}
    for line in lines[1:]:
        if not line.strip():
            continue
        p = line.split("\t")
        if p[i_scale].strip() != "RL":
            continue
        soc = p[i_soc].strip()
        level = p[i_elem].strip()
        if soc and soc not in out:
            out[soc] = _normalize_education_level(level)
    return out


def _normalize_education_level(onet_label: str) -> str:
    label = onet_label.lower()
    if "doctoral" in label or "post-doctoral" in label:
        return "phd"
    if "master" in label:
        return "master"
    if "bachelor" in label or "post-baccalaureate" in label:
        return "bachelor"
    if "associate" in label:
        return "associate"
    if "high school" in label or "less than high school" in label:
        return "high_school"
    return "unknown"


def _normalize_skill_id(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s
"""L4 输出校验器。拆分为多个独立函数，不合并为一个巨型函数。"""
from __future__ import annotations
import re
from dataclasses import dataclass

FORBIDDEN_PHRASES = ["前景广阔", "未来可期", "大有可为", "朝阳行业",
                     "前景无限", "钱途", "高薪保障", "包就业"]

ALLOWED_ENTRY_PATH_REFS = {
    "occupation.typical_requirements.entry_education",
    "occupation.typical_requirements.work_experience",
    "occupation.typical_requirements.job_zone",
    "occupation.license_required",
    "match.matched_skills",
    "match.unmatched_critical_skills",
}

_VALID_TAGS = {"事实", "推断", "预测"}


@dataclass(frozen=True)
class Violation:
    code: str
    detail: str


def validate(output: dict, explanation_input: dict) -> list[Violation]:
    vs: list[Violation] = []
    vs += _check_sections(output)
    vs += _check_scores(output, explanation_input)
    vs += _check_citations(output, explanation_input)
    vs += _check_numbers_whitelist(output, explanation_input)
    vs += _check_tags(output)
    vs += _check_no_data_case(output, explanation_input)
    vs += _check_counter_scenarios(output)
    vs += _check_forbidden_phrases(output)
    vs += _check_entry_path(output)
    vs += _check_historical_prefix(output, explanation_input)
    return vs


def _check_sections(output: dict) -> list[Violation]:
    vs = []
    for sec in ("facts", "inference", "prediction"):
        node = (output.get("prospect_10y") or {}).get(sec)
        if not node or not node.get("text"):
            vs.append(Violation("SECTION_MISSING", sec))
    return vs


def _check_scores(output: dict, inp: dict) -> list[Violation]:
    vs = []
    src = inp["match"]
    block = output.get("match_conclusion", {}).get("scores_block", {})
    if block.get("rank") != src["rank"]:
        vs.append(Violation("SCORE_MUTATED", "rank"))
    if not _float_equal(block.get("total_score"), src["total_score"]):
        vs.append(Violation("SCORE_MUTATED", "total_score"))
    for k in ("interest", "skill_transfer", "values"):
        s_block = (block.get("sub_scores") or {}).get(k, {})
        s_src = src["sub_scores"].get(k, {})
        for field in ("raw", "weight_effective", "contribution"):
            if not _float_equal(s_block.get(field), s_src.get(field)):
                vs.append(Violation("SCORE_MUTATED", f"{k}.{field}"))
    return vs


def _check_citations(output: dict, inp: dict) -> list[Violation]:
    vs = []
    prospect_by_key = {(p["indicator_type"], p["source_name"], p["publication_year"], p["region"]): p
                       for p in inp["prospects"] if p.get("status") == "available"}
    for c in (output.get("prospect_10y", {}).get("facts", {}).get("citations") or []):
        key = (c.get("indicator_type"), c.get("source_name"),
               c.get("publication_year"), c.get("region"))
        p = prospect_by_key.get(key)
        if p is None:
            vs.append(Violation("CITATION_NOT_IN_SOURCE", str(key)))
            continue
        if not _float_equal(c.get("value"), p.get("indicator_value")):
            vs.append(Violation("CITATION_VALUE_MUTATED",
                                f"{key}: expected {p.get('indicator_value')} got {c.get('value')}"))
        if c.get("unit") != p.get("indicator_unit"):
            vs.append(Violation("CITATION_UNIT_MUTATED", str(key)))
    return vs


# ============ 替换原 _check_numbers_whitelist 与新增 _iter_natural_language_text ============

def _check_numbers_whitelist(output: dict, inp: dict) -> list[Violation]:
    """只对自然语言字段做数值白名单检查。
    结构字段（occupation_id / occupation_family / taxonomy_refs 等）不扫描，
    避免 CN-2022-2-02-10-08 这类 ID 被误判为数据值。"""
    allowed = _build_allowed_numbers(inp)
    vs = []
    for section, text in _iter_natural_language_text(output):
        if _is_connective_only(text):
            continue
        for token in _extract_numbers(text):
            n = _normalize_number(token)
            if n in allowed:
                continue
            if 1 <= float(n) <= 10 and _is_index_context(text, token):
                continue
            vs.append(Violation("NUMBER_NOT_FROM_INPUT", f"{section}: {token}"))
    return vs


def _iter_natural_language_text(output: dict):
    """白名单式遍历自然语言字段。新增 LLM 输出字段时必须显式加入，
    强制人工审查该字段是否应受「数值不改写」约束。"""
    fixed_paths = [
        ("match_conclusion", "why_match", "text"),
        ("match_conclusion", "conflicts", "text"),
        ("prospect_10y", "facts", "text"),
        ("prospect_10y", "inference", "text"),
        ("prospect_10y", "prediction", "text"),
        ("entry_path", "text"),
    ]
    for path in fixed_paths:
        node = output
        for p in path:
            if not isinstance(node, dict):
                node = None
                break
            node = node.get(p)
        if isinstance(node, str):
            yield ".".join(path), node

    # 推断链
    chain = (output.get("prospect_10y", {}).get("inference", {})
             .get("derivation_chain") or [])
    for i, item in enumerate(chain):
        if isinstance(item, str):
            yield f"prospect_10y.inference.derivation_chain[{i}]", item

    # 反面情形
    counters = (output.get("prospect_10y", {}).get("prediction", {})
                .get("counter_scenarios") or [])
    for i, item in enumerate(counters):
        if isinstance(item, str):
            yield f"prospect_10y.prediction.counter_scenarios[{i}]", item

    # 外部预测语句
    preds = (output.get("prospect_10y", {}).get("prediction", {})
             .get("institution_predictions") or [])
    for i, p in enumerate(preds):
        if isinstance(p, dict) and isinstance(p.get("statement"), str):
            yield f"prospect_10y.prediction.institution_predictions[{i}].statement", p["statement"]

    # 硬约束警示详情
    alerts = (output.get("match_conclusion", {}).get("hard_constraint_alerts") or [])
    for i, a in enumerate(alerts):
        if isinstance(a, dict) and isinstance(a.get("detail"), str):
            yield f"match_conclusion.hard_constraint_alerts[{i}].detail", a["detail"]

def _check_tags(output: dict) -> list[Violation]:
    vs = []
    for path in (("match_conclusion", "why_match"), ("match_conclusion", "conflicts"),
                 ("prospect_10y", "facts"), ("prospect_10y", "inference"),
                 ("prospect_10y", "prediction")):
        node = output
        for p in path:
            node = (node or {}).get(p, {})
        tag = node.get("tag")
        if tag not in _VALID_TAGS:
            vs.append(Violation("TAG_INVALID", ".".join(path)))
    # why_match / conflicts 必须为「推断」
    for p in ("why_match", "conflicts"):
        if output.get("match_conclusion", {}).get(p, {}).get("tag") != "推断":
            vs.append(Violation("TAG_INVALID", f"match_conclusion.{p} must be 推断"))
    return vs


def _check_no_data_case(output: dict, inp: dict) -> list[Violation]:
    if not inp["prospects"] or any(p.get("status") != "no_reliable_data" for p in inp["prospects"]):
        return []
    vs = []
    facts = output.get("prospect_10y", {}).get("facts", {})
    if facts.get("text") != "该职业暂无可靠的前景数据，以下内容不含趋势判断":
        vs.append(Violation("NO_DATA_PHRASE_MISSING", ""))
    if facts.get("citations"):
        vs.append(Violation("NO_DATA_BUT_HAS_CITATIONS", ""))
    inference = output.get("prospect_10y", {}).get("inference", {})
    if not (inference.get("text") or "").startswith("由于缺乏前景数据"):
        vs.append(Violation("NO_DATA_INFERENCE_PREFIX_MISSING", ""))
    pred = output.get("prospect_10y", {}).get("prediction", {})
    if pred.get("institution_predictions"):
        vs.append(Violation("NO_DATA_BUT_HAS_PREDICTION", ""))
    return vs


def _check_counter_scenarios(output: dict) -> list[Violation]:
    pred = output.get("prospect_10y", {}).get("prediction", {})
    if pred.get("institution_predictions") and not pred.get("counter_scenarios"):
        return [Violation("PREDICTION_WITHOUT_COUNTER_SCENARIO", "")]
    return []


def _check_forbidden_phrases(output: dict) -> list[Violation]:
    vs = []
    for section, text in _iter_text(output):
        for phrase in FORBIDDEN_PHRASES:
            if phrase in text:
                vs.append(Violation("FORBIDDEN_PHRASE", f"{section}: {phrase}"))
    return vs


def _check_entry_path(output: dict) -> list[Violation]:
    refs = (output.get("entry_path") or {}).get("based_on") or []
    return [Violation("ENTRY_PATH_REF_NOT_ALLOWED", r)
            for r in refs if r not in ALLOWED_ENTRY_PATH_REFS]


def _check_historical_prefix(output: dict, inp: dict) -> list[Violation]:
    """若任一引文对应 HISTORICAL_REFERENCE_ONLY，facts.text 中必须出现提示语。"""
    if any(p.get("freshness_status") == "HISTORICAL_REFERENCE_ONLY" for p in inp["prospects"]):
        facts_text = output.get("prospect_10y", {}).get("facts", {}).get("text") or ""
        if "历史数据，仅供参考" not in facts_text:
            return [Violation("HISTORICAL_PREFIX_MISSING", "")]
    return []


# ============ 内部工具 ============

def _float_equal(a, b) -> bool:
    if a is None and b is None: return True
    if a is None or b is None: return False
    # 允许极小的浮点精度误差，避免 LLM 输出 0.4500 导致被误判
    return abs(float(a) - float(b)) < 1e-4


def _iter_text(output: dict):
    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                yield from walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                yield from walk(v, f"{path}[{i}]")
        elif isinstance(node, str):
            yield path, node
    yield from walk(output, "$")


def _extract_numbers(text: str) -> list[str]:
    return re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", text)


def _normalize_number(token: str) -> str:
    return token.replace(",", "")


def _is_connective_only(text: str) -> bool:
    stripped = re.sub(r"\d+(?:,\d{3})*(?:\.\d+)?", "", text).strip()
    stripped = re.sub(r"[，。；：、！？,.;:!?\s]+", "", stripped)
    return len(stripped) < 4


def _is_index_context(text: str, token: str) -> bool:
    idx = text.find(token)
    if idx < 0: return False
    window = text[max(0, idx - 6):idx + len(token) + 6]
    return any(kw in window for kw in ("第", "个", "条", "位", "名"))


def _build_allowed_numbers(inp: dict) -> set[str]:
    allowed: set[str] = set()
    m = inp["match"]
    allowed.add(_normalize_number(str(m["total_score"])))
    allowed.add(str(m["rank"]))
    allowed.add("10")  # <--- 新增这一行，放行 "未来 10 年" 这种常识性常量
    for s in m["sub_scores"].values():
        for f in ("raw", "weight_effective", "contribution"):
            if s.get(f) is not None:
                allowed.add(_normalize_number(str(s[f])))
    if m.get("penalties", {}).get("total") is not None:
        allowed.add(_normalize_number(str(m["penalties"]["total"])))
    for p in inp["prospects"]:
        if p.get("status") != "available": continue
        if p.get("indicator_value") is not None:
            allowed.add(_normalize_number(str(p["indicator_value"])))
        allowed.add(str(p.get("publication_year")))
        for y in re.findall(r"\d{4}", p.get("data_year_or_horizon", "") or ""):
            allowed.add(y)
    return allowed
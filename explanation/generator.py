"""L4 解释生成接口。代码强制接管 JSON 结构，具备极强的容错清洗能力。"""
from __future__ import annotations
import json, logging
from abc import ABC, abstractmethod
from typing import Protocol, Any

from .validator import validate
from .fallback import render_fallback
from .prompts import L4_SYSTEM_PROMPT, L4_USER_TEMPLATE

logger = logging.getLogger(__name__)

class LLMClient(Protocol):
    def generate_json(self, system_prompt: str, user_prompt: str, schema: dict) -> dict: ...

class ExplanationGenerator(ABC):
    @abstractmethod
    def generate(self, explanation_input: dict) -> dict: ...

def _safe_dict(val: Any) -> dict:
    """如果模型返回了 list, str, None，强制变成空字典"""
    if isinstance(val, dict):
        return val
    return {}

def _safe_str(val: Any) -> str:
    """如果模型返回了 None，强制变成空字符串"""
    if isinstance(val, str):
        return val
    return str(val) if val is not None else ""

class LLMExplanationGenerator(ExplanationGenerator):
    def __init__(self, client: LLMClient, max_attempts: int = 2,
                 prompt_version: str = "l4-v1.0"):
        self.client = client
        self.max_attempts = max_attempts
        self.prompt_version = prompt_version

    def generate(self, explanation_input: dict) -> dict:
        occupation_id = explanation_input["occupation"]["occupation_id"]
        inp = explanation_input
        m = inp["match"]
        
        has_data = any(p.get("status") == "available" for p in inp["prospects"])
        
        for attempt in range(1, self.max_attempts + 1):
            try:
                raw_output = self.client.generate_json(
                    system_prompt=L4_SYSTEM_PROMPT,
                    user_prompt=L4_USER_TEMPLATE.format(
                        input_json=json.dumps(inp, ensure_ascii=False, default=str)),
                    schema={},
                )
                
                # 最外层必须是 dict
                if not isinstance(raw_output, dict):
                    raise ValueError("LLM 返回的不是一个 JSON 对象")

                output = {}
                output["occupation_id"] = occupation_id
                
                # ================= 强制清洗 match_conclusion =================
                mc = _safe_dict(raw_output.get("match_conclusion"))
                output["match_conclusion"] = {
                    "scores_block": {
                        "rank": m["rank"],
                        "total_score": m["total_score"],
                        "sub_scores": m["sub_scores"],
                        "penalties_total": m.get("penalties", {}).get("total", 0)
                    },
                    "why_match": {
                        "tag": "推断",
                        "text": _safe_str(_safe_dict(mc.get("why_match")).get("text", "基于技能和兴趣的匹配。")),
                        "evidence_refs": _safe_dict(mc.get("why_match")).get("evidence_refs", [])
                    },
                    "conflicts": {
                        "tag": "推断",
                        "text": _safe_str(_safe_dict(mc.get("conflicts")).get("text", "无重大冲突。")),
                        "conflict_refs": _safe_dict(mc.get("conflicts")).get("conflict_refs", [])
                    },
                    "hard_constraint_alerts": [
                        {"constraint": e["constraint"], "status": e["status"], "prominent": True, "detail": e["detail"]}
                        for e in m.get("hard_constraint_eval", []) if e["status"] in ("unknown", "soft_penalty")
                    ]
                }

                # ================= 强制清洗 entry_path =================
                ep = _safe_dict(raw_output.get("entry_path"))
                output["entry_path"] = {
                    "text": _safe_str(ep.get("text", "请参考职业要求。")),
                    "based_on": ["occupation.typical_requirements", "occupation.license_required"]
                }

                # ================= 强制清洗 prospect_10y =================
                p10y = _safe_dict(raw_output.get("prospect_10y"))
                output["prospect_10y"] = {}
                
                if not has_data:
                    output["prospect_10y"]["facts"] = {
                        "tag": "事实", 
                        "text": "该职业暂无可靠的前景数据，以下内容不含趋势判断", 
                        "citations": []
                    }
                    inf_text = _safe_str(_safe_dict(p10y.get("inference")).get("text", "由于缺乏前景数据，以下推断仅基于职业任务性质。"))
                    if not inf_text.startswith("由于缺乏前景数据"):
                        inf_text = "由于缺乏前景数据，以下推断仅基于职业任务性质：" + inf_text
                    output["prospect_10y"]["inference"] = {
                        "tag": "推断",
                        "text": inf_text,
                        "derivation_chain": ["occupation.core_tasks"]
                    }
                    output["prospect_10y"]["prediction"] = {
                        "tag": "预测", 
                        "text": "暂无外部机构对该职业的 10 年期预测。", 
                        "institution_predictions": [], 
                        "counter_scenarios": []
                    }
                else:
                    f = _safe_dict(p10y.get("facts"))
                    output["prospect_10y"]["facts"] = {
                        "tag": "事实",
                        "text": _safe_str(f.get("text", "见数据源")),
                        "citations": f.get("citations", []) if isinstance(f.get("citations"), list) else []
                    }
                    i = _safe_dict(p10y.get("inference"))
                    output["prospect_10y"]["inference"] = {
                        "tag": "推断",
                        "text": _safe_str(i.get("text", "基于数据推断。")),
                        "derivation_chain": i.get("derivation_chain", ["prospects"]) if isinstance(i.get("derivation_chain"), list) else []
                    }
                    p = _safe_dict(p10y.get("prediction"))
                    output["prospect_10y"]["prediction"] = {
                        "tag": "预测",
                        "text": _safe_str(p.get("text", "暂无机构预测。")),
                        "institution_predictions": p.get("institution_predictions", []) if isinstance(p.get("institution_predictions"), list) else [],
                        "counter_scenarios": p.get("counter_scenarios", []) if isinstance(p.get("counter_scenarios"), list) else []
                    }
                    
            except Exception as exc:
                logger.warning("L4 LLM call failed (attempt %d): %s", attempt, exc)
                continue
                
            violations = validate(output, inp)
            if not violations:
                return output
                
            logger.warning(
                "L4 validation failed (attempt %d, occ=%s): %s",
                attempt, occupation_id,
                [f"{v.code}:{v.detail}" for v in violations],
            )
            
        logger.warning("L4 falling back to template for occ=%s", occupation_id)
        return render_fallback(explanation_input)

class StubExplanationGenerator(ExplanationGenerator):
    def generate(self, explanation_input: dict) -> dict:
        return render_fallback(explanation_input)
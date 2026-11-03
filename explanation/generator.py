"""L4 解释生成接口。代码强制接管 JSON 结构，LLM 只负责写自然语言段落。"""
from __future__ import annotations
import json, logging
from abc import ABC, abstractmethod
from typing import Protocol

from .validator import validate
from .fallback import render_fallback
from .prompts import L4_SYSTEM_PROMPT, L4_USER_TEMPLATE

logger = logging.getLogger(__name__)

class LLMClient(Protocol):
    def generate_json(self, system_prompt: str, user_prompt: str, schema: dict) -> dict: ...

class ExplanationGenerator(ABC):
    @abstractmethod
    def generate(self, explanation_input: dict) -> dict: ...

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
        
        # 判断是否全无数据
        has_data = any(p.get("status") == "available" for p in inp["prospects"])
        
        for attempt in range(1, self.max_attempts + 1):
            try:
                output = self.client.generate_json(
                    system_prompt=L4_SYSTEM_PROMPT,
                    user_prompt=L4_USER_TEMPLATE.format(
                        input_json=json.dumps(inp, ensure_ascii=False, default=str)),
                    schema={},
                )
                
                # ================= 强制清洗与结构补全 =================
                # 1. 强制覆写 scores_block
                output["occupation_id"] = occupation_id
                output["match_conclusion"] = output.get("match_conclusion", {})
                output["match_conclusion"]["scores_block"] = {
                    "rank": m["rank"],
                    "total_score": m["total_score"],
                    "sub_scores": m["sub_scores"],
                    "penalties_total": m.get("penalties", {}).get("total", 0)
                }
                if "why_match" not in output["match_conclusion"]:
                    output["match_conclusion"]["why_match"] = {"text": "基于技能和兴趣的匹配。"}
                if "conflicts" not in output["match_conclusion"]:
                    output["match_conclusion"]["conflicts"] = {"text": "无重大冲突。"}
                
                output["match_conclusion"]["why_match"]["tag"] = "推断"
                output["match_conclusion"]["conflicts"]["tag"] = "推断"
                output["match_conclusion"]["hard_constraint_alerts"] = [
                    {"constraint": e["constraint"], "status": e["status"], "prominent": True, "detail": e["detail"]}
                    for e in m.get("hard_constraint_eval", []) if e["status"] in ("unknown", "soft_penalty")
                ]

                # 2. 强制覆写 entry_path
                occ = inp["occupation"]

                output["entry_path"] = {
                    "text": output.get("entry_path", {}).get("text", "请参考职业要求。"),
                    "based_on": ["occupation.typical_requirements", "occupation.license_required"]
                }

                # 3. 强制处理 prospect_10y
                if "prospect_10y" not in output:
                    output["prospect_10y"] = {}
                p10y = output["prospect_10y"]
                
                if not has_data:
                    # 没有数据时，完全由代码生成固定结构，防止模型胡说
                    p10y["facts"] = {
                        "tag": "事实", 
                        "text": "该职业暂无可靠的前景数据，以下内容不含趋势判断", 
                        "citations": []
                    }
                    p10y["inference"] = {
                        "tag": "推断",
                        "text": p10y.get("inference", {}).get("text", "由于缺乏前景数据，以下推断仅基于职业任务性质。"),
                        "derivation_chain": ["occupation.core_tasks"]
                    }
                    if not str(p10y["inference"]["text"]).startswith("由于缺乏前景数据"):
                        p10y["inference"]["text"] = "由于缺乏前景数据，以下推断仅基于职业任务性质：" + p10y["inference"]["text"]
                        
                    p10y["prediction"] = {
                        "tag": "预测", 
                        "text": "暂无外部机构对该职业的 10 年期预测。", 
                        "institution_predictions": [], 
                        "counter_scenarios": []
                    }
                else:
                    # 有数据时，补全标签
                    if "facts" not in p10y: p10y["facts"] = {"text": "见数据源", "citations": []}
                    p10y["facts"]["tag"] = "事实"
                    if "citations" not in p10y["facts"]: p10y["facts"]["citations"] = []
                    
                    if "inference" not in p10y: p10y["inference"] = {"text": "基于数据推断。", "derivation_chain": ["prospects"]}
                    p10y["inference"]["tag"] = "推断"
                    
                    if "prediction" not in p10y: p10y["prediction"] = {"text": "暂无机构预测。", "institution_predictions": [], "counter_scenarios": []}
                    p10y["prediction"]["tag"] = "预测"
                    
            except Exception as exc:
                logger.warning("L4 LLM call failed (attempt %d): %s", attempt, exc)
                continue
                
            # 4. 移除 LLM 幻觉生成的 entry_path based_on 污染
            if "based_on" in output.get("entry_path", {}):
                output["entry_path"]["based_on"] = ["occupation.typical_requirements", "occupation.license_required"]

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
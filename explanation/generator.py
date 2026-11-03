"""L4 解释生成接口。校验失败两次自动降级为模板（无 LLM）。"""
from __future__ import annotations
import json, logging
from abc import ABC, abstractmethod
from typing import Protocol

from .validator import validate
from .fallback import render_fallback
from .prompts import L4_SYSTEM_PROMPT, L4_USER_TEMPLATE


logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    def generate_json(self, system_prompt: str, user_prompt: str, schema: dict) -> dict:
        ...


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
        for attempt in range(1, self.max_attempts + 1):
            try:
                output = self.client.generate_json(
                    system_prompt=L4_SYSTEM_PROMPT,
                    user_prompt=L4_USER_TEMPLATE.format(
                        input_json=json.dumps(explanation_input, ensure_ascii=False, default=str)),
                    schema=_EXPLANATION_SCHEMA,
                )
            except Exception as exc:
                logger.warning("L4 LLM call failed (attempt %d): %s", attempt, exc)
                continue
            violations = validate(output, explanation_input)
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
    """确定性降级。用于本地测试与无 LLM 环境。直接返回模板输出，保证通过校验。"""
    def generate(self, explanation_input: dict) -> dict:
        return render_fallback(explanation_input)


_EXPLANATION_SCHEMA = {"type": "object", "required":
                       ["occupation_id", "match_conclusion", "prospect_10y", "entry_path"]}
"""LLM 客户端。兼容 OpenAI, DeepSeek, Ollama 以及任何兼容 OpenAI 接口的 API。"""
import json
import logging
from typing import Protocol
from openai import OpenAI

logger = logging.getLogger(__name__)

class LLMClient(Protocol):
    def generate_json(self, system_prompt: str, user_prompt: str, schema: dict) -> dict:
        ...

class OpenAICompatibleClient:
    def __init__(self, api_key: str, base_url: str, model: str):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def generate_json(self, system_prompt: str, user_prompt: str, schema: dict) -> dict:
        # 强行在 system prompt 末尾加入 JSON 要求，提升小模型的遵循度
        enhanced_system = (
            f"{system_prompt}\n\n"
            "You MUST output ONLY valid JSON. Do not include markdown blocks like ```json."
        )
        
        kwargs = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": enhanced_system},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.0, 
        }
        
        # 如果是 DeepSeek 或 OpenAI，尝试使用 JSON mode
        # 如果是本地 Ollama，大多数模型不支持 response_format，强行传入会报错
        if "localhost" not in str(self.client.base_url) and "127.0.0.1" not in str(self.client.base_url):
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = self.client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content.strip()
            
            # 清理可能存在的 markdown 代码块标记
            if content.startswith("```json"):
                content = content[7:-3].strip()
            elif content.startswith("```"):
                content = content[3:-3].strip()
                
            return json.loads(content)
            
        except Exception as e:
            logger.error("LLM API call failed: %s", e)
            raise
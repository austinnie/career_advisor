"""读取环境变量配置 LLM"""
import os
from dotenv import load_dotenv
from .llm_client import OpenAICompatibleClient

load_dotenv()

def get_default_llm_client():
    """根据 .env 中的 LLM_PROVIDER 选择引擎。"""
    provider = os.getenv("LLM_PROVIDER", "deepseek").lower()

    if provider == "deepseek":
        key = os.getenv("DEEPSEEK_API_KEY")
        if not key:
            raise ValueError("LLM_PROVIDER 为 deepseek，但未配置 DEEPSEEK_API_KEY")
        return OpenAICompatibleClient(
            api_key=key,
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        )
        
    elif provider == "agnes":
        key = os.getenv("AGNES_API_KEY")
        if not key:
            raise ValueError("LLM_PROVIDER 为 agnes，但未配置 AGNES_API_KEY")
        return OpenAICompatibleClient(
            api_key=key,
            base_url=os.getenv("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1"),
            model=os.getenv("AGNES_TEXT_MODEL", "agnes-2.5-flash")
        )
        
    elif provider == "ollama":
        # Ollama 不需要真实 key，但不能为空
        return OpenAICompatibleClient(
            api_key="ollama",
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
            model=os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
        )
        
    else:
        raise ValueError(f"未知的 LLM_PROVIDER: {provider}")
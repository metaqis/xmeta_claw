"""LLM 客户端封装"""
from openai import AsyncOpenAI

from app.core.config import get_settings

settings = get_settings()

client = AsyncOpenAI(
    api_key=settings.LLM_API_KEY,
    base_url=settings.LLM_BASE_URL,
)

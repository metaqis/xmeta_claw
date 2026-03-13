"""基础爬虫客户端，带重试和日志"""
import asyncio
from typing import Any, Optional

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.config import get_settings

settings = get_settings()

HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36",
}


class CrawlerClient:
    def __init__(self):
        self.base_url = settings.CRAWLER_API_BASE
        self.delay = settings.CRAWLER_REQUEST_DELAY

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    )
    async def post(self, path: str, json_data: dict, timeout: float = 30.0) -> Optional[dict]:
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=timeout) as client:
            logger.debug(f"POST {url} body={json_data}")
            resp = await client.post(url, json=json_data, headers=HEADERS)
            resp.raise_for_status()
            data = resp.json()
            logger.debug(f"Response status={resp.status_code}")
            await asyncio.sleep(self.delay)
            return data

    async def post_safe(self, path: str, json_data: dict) -> Optional[dict]:
        """不抛异常版本，返回 None 表示失败"""
        try:
            return await self.post(path, json_data)
        except Exception as e:
            logger.error(f"请求失败 {path}: {e}")
            return None


crawler_client = CrawlerClient()

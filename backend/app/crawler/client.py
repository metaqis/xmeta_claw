"""基础爬虫客户端，带重试、连接池、UA轮转和反封策略"""
import asyncio
import random
from typing import Optional

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.config import get_settings

settings = get_settings()

# ── UA 池：移动端 + 桌面端混合 ──────────────────────────────────────
USER_AGENTS = [
    # Android Chrome
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; Redmi Note 11) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; HUAWEI P60) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; V2254A) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    # iOS Safari
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    # Desktop Chrome
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

# ── Accept-Language 池 ──────────────────────────────────────────────
ACCEPT_LANGUAGES = [
    "zh-CN,zh;q=0.9,en;q=0.8",
    "zh-CN,zh;q=0.9",
    "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "zh-Hans-CN;q=1,en-US;q=0.9",
]


def _random_headers() -> dict:
    """每次请求生成随机 headers 组合"""
    return {
        "Content-Type": "application/json",
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": random.choice(ACCEPT_LANGUAGES),
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
    }


def _jitter_delay(base: float) -> float:
    """在基础延迟上加 ±40% 随机抖动，避免固定频率"""
    jitter = base * random.uniform(-0.4, 0.4)
    return max(0.1, base + jitter)


class CrawlerClient:
    """带连接池的异步爬虫客户端"""

    def __init__(self):
        self.base_url = settings.CRAWLER_API_BASE
        self.delay = settings.CRAWLER_REQUEST_DELAY
        proxy = (settings.CRAWLER_PROXY or "").strip()
        self.proxy = proxy or None
        self._client: Optional[httpx.AsyncClient] = None
        self._lock = asyncio.Lock()
        # 并发控制信号量
        self._semaphore = asyncio.Semaphore(settings.CRAWLER_CONCURRENCY)

    async def _get_client(self) -> httpx.AsyncClient:
        """懒初始化持久化连接池客户端"""
        if self._client is None or self._client.is_closed:
            async with self._lock:
                if self._client is None or self._client.is_closed:
                    kwargs = {
                        "timeout": httpx.Timeout(30.0, connect=10.0),
                        "limits": httpx.Limits(
                            max_connections=20,
                            max_keepalive_connections=10,
                            keepalive_expiry=30,
                        ),
                        "trust_env": False,
                        "follow_redirects": True,
                    }
                    if self.proxy:
                        kwargs["proxies"] = self.proxy
                    self._client = httpx.AsyncClient(**kwargs)
        return self._client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    )
    async def post(self, path: str, json_data: dict, timeout: float = 30.0) -> Optional[dict]:
        url = f"{self.base_url}{path}"
        client = await self._get_client()
        async with self._semaphore:
            logger.debug(f"POST {url} body={json_data}")
            resp = await client.post(url, json=json_data, headers=_random_headers(), timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            await asyncio.sleep(_jitter_delay(self.delay))
            return data

    async def post_safe(self, path: str, json_data: dict) -> Optional[dict]:
        """不抛异常版本，返回 None 表示失败"""
        try:
            return await self.post(path, json_data)
        except Exception as e:
            logger.error(f"请求失败 {path}: {e}")
            return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    )
    async def get(self, path: str, timeout: float = 30.0) -> Optional[dict]:
        url = f"{self.base_url}{path}"
        client = await self._get_client()
        async with self._semaphore:
            logger.debug(f"GET {url}")
            resp = await client.get(url, headers=_random_headers(), timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            await asyncio.sleep(_jitter_delay(self.delay))
            return data

    async def get_safe(self, path: str) -> Optional[dict]:
        """GET 不抛异常版本，返回 None 表示失败"""
        try:
            return await self.get(path)
        except Exception as e:
            logger.error(f"GET 请求失败 {path}: {e}")
            return None

    async def close(self):
        """关闭客户端连接池"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


crawler_client = CrawlerClient()

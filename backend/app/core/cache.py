"""轻量 Redis 缓存层，用于高频 API 结果缓存"""
import json
from typing import Any, Optional

from loguru import logger
from redis.asyncio import Redis

from app.core.config import get_settings

settings = get_settings()

_redis: Optional[Redis] = None


async def get_redis() -> Optional[Redis]:
    """懒初始化 Redis 连接"""
    global _redis
    if _redis is not None:
        return _redis
    try:
        _redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        await _redis.ping()
        return _redis
    except Exception as e:
        logger.warning(f"Redis 连接失败，缓存将被跳过: {e}")
        _redis = None
        return None


async def close_redis():
    """关闭 Redis 连接"""
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def cache_get(key: str) -> Optional[str]:
    """从缓存获取值，失败时静默返回 None"""
    r = await get_redis()
    if r is None:
        return None
    try:
        return await r.get(key)
    except Exception as e:
        logger.debug(f"Redis GET 失败 {key}: {e}")
        return None


async def cache_set(key: str, value: str, ttl: int = 300) -> None:
    """设置缓存值 (默认 TTL 5 分钟)，失败时静默"""
    r = await get_redis()
    if r is None:
        return
    try:
        await r.set(key, value, ex=ttl)
    except Exception as e:
        logger.debug(f"Redis SET 失败 {key}: {e}")


def make_cache_key(prefix: str, **kwargs: Any) -> str:
    """构建缓存 key：前缀 + 排序后的参数"""
    parts = [f"{k}={v}" for k, v in sorted(kwargs.items()) if v is not None and v != ""]
    return f"agent:{prefix}:{'|'.join(parts)}" if parts else f"agent:{prefix}"

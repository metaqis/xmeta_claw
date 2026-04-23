"""微信公众号 API 客户端"""

import json
import time
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from app.core.config import get_settings

settings = get_settings()

_BASE = "https://api.weixin.qq.com"
_token_cache: dict[str, Any] = {"token": "", "expires": 0}


class WeChatMPClient:
    """微信公众平台 API 封装"""

    def __init__(self):
        self.app_id: str = settings.WECHAT_APP_ID
        self.app_secret: str = settings.WECHAT_APP_SECRET
        self._client = httpx.AsyncClient(timeout=30)

    async def close(self):
        await self._client.aclose()

    # ---------- access_token ----------

    async def get_access_token(self) -> str:
        now = time.time()
        if _token_cache["token"] and _token_cache["expires"] > now + 60:
            return _token_cache["token"]

        resp = await self._client.get(
            f"{_BASE}/cgi-bin/token",
            params={
                "grant_type": "client_credential",
                "appid": self.app_id,
                "secret": self.app_secret,
            },
        )
        data = resp.json()
        if "access_token" not in data:
            raise RuntimeError(f"获取 access_token 失败: {data}")
        _token_cache["token"] = data["access_token"]
        _token_cache["expires"] = now + data.get("expires_in", 7200)
        return _token_cache["token"]

    # ---------- 上传图片（文章内图片，返回 URL） ----------

    async def upload_image(self, file_path: str) -> str:
        token = await self.get_access_token()
        path = Path(file_path)
        with open(path, "rb") as f:
            resp = await self._client.post(
                f"{_BASE}/cgi-bin/media/uploadimg",
                params={"access_token": token},
                files={"media": (path.name, f, "image/png")},
            )
        data = resp.json()
        if "url" not in data:
            raise RuntimeError(f"上传图片失败: {data}")
        logger.info(f"图片已上传: {path.name} -> {data['url']}")
        return data["url"]

    # ---------- 上传永久素材（封面图，返回 media_id） ----------

    async def upload_material(self, file_path: str) -> str:
        token = await self.get_access_token()
        path = Path(file_path)
        with open(path, "rb") as f:
            resp = await self._client.post(
                f"{_BASE}/cgi-bin/material/add_material",
                params={"access_token": token, "type": "image"},
                files={"media": (path.name, f, "image/png")},
            )
        data = resp.json()
        if "media_id" not in data:
            raise RuntimeError(f"上传永久素材失败: {data}")
        logger.info(f"永久素材已上传: {path.name} -> {data['media_id']}")
        return data["media_id"]

    # ---------- 创建草稿 ----------

    async def create_draft(
        self,
        title: str,
        content_html: str,
        cover_media_id: str,
        digest: str = "",
        author: str = "metaclawbot",
    ) -> str:
        token = await self.get_access_token()
        # 微信公众号字段限制（官方文档）:
        # title ≤ 32字, author ≤ 16字, digest ≤ 64字节, content < 2万字符 & < 1MB
        # digest 按字节截断（中文3字节/字，64字节≈21个中文字）
        def _truncate_bytes(s: str, max_bytes: int) -> str:
            enc = s.encode("utf-8")
            if len(enc) <= max_bytes:
                return s
            return enc[:max_bytes].decode("utf-8", errors="ignore")

        safe_title = title[:32]
        safe_digest = _truncate_bytes(digest, 64) if digest else ""
        safe_author = author[:16]
        content_bytes = len(content_html.encode("utf-8")) if content_html else 0
        if content_bytes > 1_000_000:
            logger.warning(f"content 大小 {content_bytes} 字节超过 1MB 限制，将被截断")
        if len(content_html) > 20000:
            logger.warning(f"content 长度 {len(content_html)} 字符超过 2万字符限制")
        logger.info(
            f"草稿参数: title={len(safe_title)}字/{repr(safe_title)}, "
            f"digest={len(safe_digest)}字, author={len(safe_author)}字, "
            f"content={len(content_html)}字符/{content_bytes}字节"
        )
        article = {
            "title": safe_title,
            "author": safe_author,
            "digest": safe_digest,
            "content": content_html,
            "thumb_media_id": cover_media_id,
            "need_open_comment": 1,
            "only_fans_can_comment": 0,
        }
        body = json.dumps({"articles": [article]}, ensure_ascii=False).encode("utf-8")
        resp = await self._client.post(
            f"{_BASE}/cgi-bin/draft/add",
            params={"access_token": token},
            content=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        data = resp.json()
        if "media_id" not in data:
            raise RuntimeError(
                f"创建草稿失败: {data} | "
                f"参数: title={len(safe_title)}字, digest={len(safe_digest)}字, "
                f"content={len(content_html)}字符/{content_bytes}字节"
            )
        logger.info(f"草稿已创建: media_id={data['media_id']}")
        return data["media_id"]

    @property
    def is_configured(self) -> bool:
        return bool(self.app_id and self.app_secret)


wechat_client = WeChatMPClient()

import asyncio
import base64
import hashlib
import json
import time
from typing import Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.config import get_settings

settings = get_settings()

ALPHABET_64 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz+/"


def to_base64_64(n: int, alphabet: str = ALPHABET_64) -> str:
    if n <= 0:
        return alphabet[0]
    out = []
    while n > 0:
        n, r = divmod(n, 64)
        out.append(alphabet[r])
    return "".join(reversed(out))


def make_ts(now_ms: Optional[int] = None) -> str:
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    return to_base64_64(now_ms)


def build_sign_content(operation_type: str, request_body: bytes, ts: str) -> str:
    request_data_b64 = base64.b64encode(request_body).decode("utf-8")
    return f"Operation-Type={operation_type}&Request-Data={request_data_b64}&Ts={ts}"


def md5_hex_lower(text: str, secret: str = "") -> str:
    return hashlib.md5((text + secret).encode("utf-8")).hexdigest()


def _encode_payload(payload_obj: Any) -> bytes:
    return json.dumps(payload_obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class AntFansClient:
    def __init__(self):
        self.base_url = (settings.ANTFANS_API_BASE or "https://mgs-normal.antfans.com").rstrip("/")
        self.sign_secret = (settings.ANTFANS_SIGN_SECRET or "").strip()
        self.did = (settings.ANTFANS_DID or "").strip()
        self.app_id = (settings.ANTFANS_APP_ID or "").strip()
        self.workspace_id = (settings.ANTFANS_WORKSPACE_ID or "").strip()
        self.product_version = (settings.ANTFANS_PRODUCT_VERSION or "").strip()
        self.product_id = (settings.ANTFANS_PRODUCT_ID or "").strip()
        self.x_app_sys_id = (settings.ANTFANS_X_APP_SYS_ID or "").strip()
        self.sign_type = (settings.ANTFANS_SIGN_TYPE or "0").strip()
        self.extra_headers = settings.ANTFANS_EXTRA_HEADERS or {}

        self._client: Optional[httpx.AsyncClient] = None
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(settings.ANTFANS_CONCURRENCY)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            async with self._lock:
                if self._client is None or self._client.is_closed:
                    self._client = httpx.AsyncClient(
                        timeout=httpx.Timeout(30.0, connect=10.0),
                        limits=httpx.Limits(
                            max_connections=20,
                            max_keepalive_connections=10,
                            keepalive_expiry=30,
                        ),
                        trust_env=False,
                        follow_redirects=True,
                    )
        return self._client

    def build_headers(
        self,
        operation_type: str,
        body: bytes,
        ts: Optional[str] = None,
        sign: Optional[str] = None,
    ) -> dict[str, str]:
        real_ts = ts or make_ts()
        sign_content = build_sign_content(operation_type, body, real_ts)
        if sign is not None:
            real_sign = sign
        elif self.sign_secret:
            real_sign = md5_hex_lower(sign_content, self.sign_secret)
        else:
            real_sign = ""

        host = self.base_url.replace("https://", "").replace("http://", "")
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Operation-Type": operation_type,
            "Platform": "ANDROID",
            "AppId": self.app_id,
            "WorkspaceId": self.workspace_id,
            "productVersion": self.product_version,
            "productId": self.product_id,
            "Version": "2",
            "Did": self.did,
            "Ts": real_ts,
            "Sign": real_sign,
            "signType": self.sign_type,
            "x-app-sys-Id": self.x_app_sys_id,
            "Accept": "application/json",
            "User-Agent": "Android_Ant_Client",
            "Host": host,
        }
        headers.update(self.extra_headers)
        return headers

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    )
    async def post_mgw(
        self,
        operation_type: str,
        payload_obj: Any,
        ts: Optional[str] = None,
        sign: Optional[str] = None,
        timeout: float = 20.0,
    ) -> httpx.Response:
        url = f"{self.base_url}/mgw.htm"
        body = _encode_payload(payload_obj)
        headers = self.build_headers(operation_type=operation_type, body=body, ts=ts, sign=sign)
        client = await self._get_client()
        async with self._semaphore:
            return await client.post(url, content=body, headers=headers, timeout=timeout)

    async def post_mgw_safe(
        self,
        operation_type: str,
        payload_obj: Any,
        ts: Optional[str] = None,
        sign: Optional[str] = None,
        timeout: float = 20.0,
    ) -> dict[str, Any]:
        try:
            resp = await self.post_mgw(
                operation_type=operation_type,
                payload_obj=payload_obj,
                ts=ts,
                sign=sign,
                timeout=timeout,
            )
            text = resp.text
            try:
                data = resp.json() if text else None
            except Exception:
                data = None
            return {"status": resp.status_code, "text": text, "json": data}
        except Exception as e:
            return {"status": 0, "text": str(e), "json": None}

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


antfans_client = AntFansClient()


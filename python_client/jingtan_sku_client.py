import base64
import hashlib
import json
import time
import urllib.error
import urllib.request
from typing import Callable, Dict, Optional

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


class JingtanSkuClient:
    def __init__(
        self,
        base_url: str,
        operation_type: str,
        did: str,
        app_id: str,
        workspace_id: str,
        product_version: str,
        product_id: str,
        x_app_sys_id: str,
        sign_type: str = "0",
        signer: Optional[Callable[[str], str]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.operation_type = operation_type
        self.did = did
        self.app_id = app_id
        self.workspace_id = workspace_id
        self.product_version = product_version
        self.product_id = product_id
        self.x_app_sys_id = x_app_sys_id
        self.sign_type = sign_type
        self.signer = signer
        self.extra_headers = extra_headers or {}

    def build_headers(self, body: bytes, ts: Optional[str] = None, sign: Optional[str] = None) -> Dict[str, str]:
        real_ts = ts or make_ts()
        sign_content = build_sign_content(self.operation_type, body, real_ts)
        real_sign = sign if sign is not None else (self.signer(sign_content) if self.signer else "")
        headers = {
            "Content-Type": "application/json",
            "Operation-Type": self.operation_type,
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
            "Host": self.base_url.replace("https://", "").replace("http://", ""),
        }
        headers.update(self.extra_headers)
        return headers

    def query_sku_wiki(self, page_num: int = 1, page_size: int = 20, timeout: int = 15) -> Dict:
        payload_obj = [{"pageNum": page_num, "pageSize": page_size}]
        payload = json.dumps(payload_obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = self.build_headers(payload)
        req = urllib.request.Request(
            url=f"{self.base_url}/mgw.htm",
            data=payload,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return {
                    "status": resp.status,
                    "headers": dict(resp.headers.items()),
                    "text": body,
                    "json": json.loads(body) if body else None,
                }
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", errors="replace")
            return {
                "status": e.code,
                "headers": dict(e.headers.items()) if e.headers else {},
                "text": text,
                "json": None,
            }
        except urllib.error.URLError as e:
            return {
                "status": 0,
                "headers": {},
                "text": str(e),
                "json": None,
            }


def build_default_client(sign_secret: str, cookie: str = "", x_device_utdid: str = "abtToO7CtX8DAP2YUJu3pHSY") -> JingtanSkuClient:
    did = f"TEMP-{x_device_utdid}"
    extra_headers = {
        "x-source": "fans",
        "x-platform": "Android",
        "x-device-utdid": x_device_utdid,
        "Cookie": cookie,
        "Accept-Language": "zh-Hans",
    }
    return JingtanSkuClient(
        base_url="https://mgs-normal.antfans.com",
        operation_type="com.antgroup.antchain.mymobileprod.common.service.facade.scope.social.querySkuWiki",
        did=did,
        app_id="ALIPUB059F038311550",
        workspace_id="prod",
        product_version="1.8.5.241219194812",
        product_id="ALIPUB059F038311550_ANDROID",
        x_app_sys_id="com.antfans.fans",
        sign_type="0",
        signer=lambda content: md5_hex_lower(content, sign_secret),
        extra_headers=extra_headers,
    )

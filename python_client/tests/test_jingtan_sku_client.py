import base64
import json
import os
import unittest

from python_client.jingtan_sku_client import build_sign_content
from python_client.jingtan_sku_client import build_default_client
from python_client.jingtan_sku_client import md5_hex_lower
from python_client.jingtan_sku_client import to_base64_64


class JingtanSkuClientTests(unittest.TestCase):
    def test_to_base64_64(self):
        self.assertEqual(to_base64_64(0), "0")
        self.assertEqual(to_base64_64(63), "/")
        self.assertEqual(to_base64_64(64), "10")

    def test_build_sign_content(self):
        operation_type = "com.antgroup.antchain.mymobileprod.common.service.facade.scope.social.querySkuWiki"
        payload = b'[{"pageNum":1,"pageSize":20}]'
        ts = "Pq5V+7k"
        got = build_sign_content(operation_type, payload, ts)
        req_b64 = base64.b64encode(payload).decode("utf-8")
        expected = f"Operation-Type={operation_type}&Request-Data={req_b64}&Ts={ts}"
        self.assertEqual(got, expected)

    def test_build_headers_contains_required_fields(self):
        client = build_default_client(sign_secret="demo-secret", cookie="c=1")
        body = b'[{"pageNum":1,"pageSize":20}]'
        headers = client.build_headers(body, ts="Pq5V+7k")
        self.assertEqual(headers["Version"], "2")
        self.assertEqual(headers["Operation-Type"], "com.antgroup.antchain.mymobileprod.common.service.facade.scope.social.querySkuWiki")
        self.assertEqual(headers["Ts"], "Pq5V+7k")
        self.assertEqual(headers["signType"], "0")
        self.assertTrue(bool(headers["Sign"]))
        self.assertEqual(headers["Cookie"], "c=1")

    def test_md5_hex_lower(self):
        self.assertEqual(md5_hex_lower("abc"), "900150983cd24fb0d6963f7d28e17f72")

    def test_live_query_if_enabled(self):
        run_live = os.getenv("RUN_LIVE_TEST", "0") == "1"
        if not run_live:
            self.skipTest("RUN_LIVE_TEST!=1")
        sign_secret = os.getenv("SIGN_SECRET", "")
        cookie = os.getenv("API_COOKIE", "")
        self.assertTrue(sign_secret)
        client = build_default_client(sign_secret=sign_secret, cookie=cookie)
        result = client.query_sku_wiki(page_num=1, page_size=20, timeout=20)
        self.assertIn("status", result)
        self.assertIn(result["status"], {200, 401, 403, 405, 429, 500})
        if result["status"] == 200 and result["json"] is not None:
            self.assertIn("bizStatusCode", result["json"])


if __name__ == "__main__":
    unittest.main()

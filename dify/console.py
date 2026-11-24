"""Dify 控制台 API 小客户端（用于自动化部署配置，仅面向本机自部署的 Dify）。

凭据从 E:\\dify\\ADMIN_CREDENTIALS.txt 或环境变量 DIFY_ADMIN_EMAIL / DIFY_ADMIN_PASSWORD 读取。
"""
from __future__ import annotations

import base64
import os
import re
from pathlib import Path

import requests

from zhibei.config import settings

CONSOLE = settings.dify_console_base
CRED_FILE = Path(os.getenv("DIFY_CRED_FILE", r"E:\dify\ADMIN_CREDENTIALS.txt"))


class Console:
    def __init__(self):
        email, pw = os.getenv("DIFY_ADMIN_EMAIL"), os.getenv("DIFY_ADMIN_PASSWORD")
        if not (email and pw):
            text = CRED_FILE.read_text(encoding="utf-8")
            email = re.search(r"邮箱：(\S+)", text).group(1)
            pw = re.search(r"密码：(\S+)", text).group(1)
        self.s = requests.Session()
        r = self.s.post(f"{CONSOLE}/login", json={
            "email": email, "password": base64.b64encode(pw.encode()).decode(), "remember_me": True})
        r.raise_for_status()

    @property
    def _headers(self):
        return {"X-CSRF-Token": self.s.cookies.get("csrf_token", "")}

    def req(self, method: str, path: str, **kw):
        r = self.s.request(method, f"{CONSOLE}{path}", headers=self._headers, timeout=120, **kw)
        if not r.ok:
            raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:500]}")
        if not r.content:
            return {}
        try:
            return r.json()
        except ValueError:  # 如导出 DSL 时直接返回 YAML 文本
            return {"data": r.text}

    def get(self, path, **kw):
        return self.req("GET", path, **kw)

    def post(self, path, **kw):
        return self.req("POST", path, **kw)

    def patch(self, path, **kw):
        return self.req("PATCH", path, **kw)

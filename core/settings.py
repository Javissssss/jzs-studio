# -*- coding: utf-8 -*-
"""Settings page backend: read/write a whitelisted set of keys in .env.
Secrets are never returned to the client — only whether they are set."""

import os
import re

from . import config

FIELDS = {
    # key: (label, secret)
    "JZS_BRAND": ("栏目名（印在文章/卡片上）", False),
    "JZS_LLM_BASE_URL": ("写作 API · Base URL", False),
    "JZS_LLM_API_KEY": ("写作 API · Key", True),
    "JZS_LLM_MODEL": ("写作 API · 模型", False),
    "JZS_IMG_BASE_URL": ("生图 API · Base URL", False),
    "JZS_IMG_API_KEY": ("生图 API · Key", True),
    "JZS_IMG_MODEL": ("生图 API · 模型", False),
    "JZS_IMG_SIZE": ("生图尺寸", False),
    "JZS_CODEX_CMD": ("Codex 命令", False),
    "JZS_CODEX_MODEL": ("Codex 模型", False),
    "PEXELS_API_KEY": ("Pexels 图库 Key", True),
    "ATTRACTOR_API_KEY": ("写作视角 · 宏观数据 Key（可选）", True),
    "JZS_WX_APPID": ("公众号 AppID", False),
    "JZS_WX_SECRET": ("公众号 AppSecret", True),
    "JZS_WX_AUTHOR": ("公众号作者名", False),
}
ENV_PATH = os.path.join(config.PRODUCT_ROOT, ".env")


def public():
    out = []
    for k, (label, secret) in FIELDS.items():
        v = os.environ.get(k, "")
        out.append({"key": k, "label": label, "secret": secret,
                    "value": "" if secret else v, "set": bool(v)})
    return out


def _clean(v):
    v = str(v).strip()
    if "\n" in v or "\r" in v:
        raise ValueError("值不能包含换行")
    return v


def update(values, path=None):
    """values: {KEY: value}. Empty string for a secret = keep; "-" = clear."""
    path = path or ENV_PATH
    changes = {}
    for k, v in (values or {}).items():
        if k not in FIELDS or v is None:
            continue
        v = _clean(v)
        if FIELDS[k][1]:
            if v == "":
                continue  # keep existing secret
            if v == "-":
                v = ""
        changes[k] = v
    if not changes:
        return
    lines = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    done = set()
    for i, line in enumerate(lines):
        m = re.match(r"\s*([A-Z0-9_]+)\s*=", line)
        if m and m.group(1) in changes:
            lines[i] = f"{m.group(1)}={changes[m.group(1)]}"
            done.add(m.group(1))
    lines += [f"{k}={v}" for k, v in changes.items() if k not in done]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    for k, v in changes.items():
        if v:
            os.environ[k] = v
        else:
            os.environ.pop(k, None)

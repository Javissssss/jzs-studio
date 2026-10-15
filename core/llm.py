# -*- coding: utf-8 -*-
"""Built-in writer: send the brief to any OpenAI-compatible chat API and get
the full dual-platform draft back. Pure stdlib, no SDK.

Config (env or .env):
  JZS_LLM_BASE_URL  e.g. https://api.deepseek.com/v1 | https://dashscope.aliyuncs.com/compatible-mode/v1
  JZS_LLM_API_KEY
  JZS_LLM_MODEL     e.g. deepseek-chat | qwen-plus | moonshot-v1-32k | gpt-4o-mini
"""

import json
import os
import urllib.error
import urllib.request

from . import config

SYSTEM_TPL = (
    "你是「{brand}」公众号的主笔。严格按用户简报的文风、结构和「输出格式」写作，"
    "必须输出全部标记块（===WECHAT_START=== 等），公众号正文写满 2500 字以上；"
    "不要自己写「目录」和「约N字读完N分钟」，排版器会自动生成；"
    "不要输出与稿件无关的解释。"
)


def settings():
    return {
        "base_url": (os.environ.get("JZS_LLM_BASE_URL") or "").rstrip("/"),
        "api_key": os.environ.get("JZS_LLM_API_KEY") or "",
        "model": os.environ.get("JZS_LLM_MODEL") or "",
    }


def is_configured():
    s = settings()
    return bool(s["base_url"] and s["api_key"] and s["model"])


def public_info():
    s = settings()
    return {"configured": is_configured(), "model": s["model"]}


def write_draft(brief_md, timeout=300):
    """Return the model's full text. Raises RuntimeError with a readable message."""
    s = settings()
    if not is_configured():
        raise RuntimeError("未配置写作模型：在 .env 里填写 JZS_LLM_BASE_URL / JZS_LLM_API_KEY / JZS_LLM_MODEL")
    url = s["base_url"] + "/chat/completions"
    payload = {
        "model": s["model"],
        "messages": [{"role": "system", "content": SYSTEM_TPL.format(brand=config.brand())}, {"role": "user", "content": brief_md}],
        "temperature": 0.7,
        "max_tokens": 8000,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + s["api_key"]},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"模型接口返回 {e.code}：{detail}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"连不上模型接口：{e.reason}") from None
    except TimeoutError:
        raise RuntimeError(f"模型超过 {timeout} 秒没有返回，可换更快的模型或重试") from None
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("模型返回格式无法识别：" + json.dumps(data, ensure_ascii=False)[:300]) from None
    if not (text or "").strip():
        raise RuntimeError("模型返回了空内容")
    return text

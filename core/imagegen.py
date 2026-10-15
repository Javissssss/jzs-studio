# -*- coding: utf-8 -*-
"""AI image generation via any OpenAI-compatible /images/generations endpoint
(OpenAI gpt-image-1 / dall-e-3, 豆包 Seedream, SiliconFlow, 智谱 CogView ...).

Config (env or .env):
  JZS_IMG_BASE_URL  e.g. https://api.openai.com/v1 | https://ark.cn-beijing.volces.com/api/v3
  JZS_IMG_API_KEY
  JZS_IMG_MODEL     e.g. gpt-image-1 | doubao-seedream-3-0-t2i-250415 | Kwai-Kolors/Kolors
  JZS_IMG_SIZE      default 1024x1024
"""

import base64
import json
import os
import urllib.error
import urllib.request

from . import config


def settings():
    return {
        "base_url": (os.environ.get("JZS_IMG_BASE_URL") or "").rstrip("/"),
        "api_key": os.environ.get("JZS_IMG_API_KEY") or "",
        "model": os.environ.get("JZS_IMG_MODEL") or "",
        "size": os.environ.get("JZS_IMG_SIZE") or "1024x1024",
    }


def is_configured():
    s = settings()
    return bool(s["base_url"] and s["api_key"] and s["model"])


def public_info():
    return {"configured": is_configured(), "model": settings()["model"]}


def build_prompt(entry, title=""):
    cap = entry.get("caption") or ""
    key = entry.get("key") or ""
    subject = key if entry.get("type") == "MOOD" else cap
    return (
        f"为公众号文章《{title}》配一张横版插图。画面内容：{cap or subject}。"
        f"主体参考：{subject}。风格：现代编辑插画，构图干净、留白充足、柔和暖色调，"
        "高质量细节。画面中不要出现任何文字、水印或 logo。"
    )


def _ext(data):
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return ".png"


def generate(prompt, out_base, timeout=240):
    """Generate one image, save to out_base + ext. Returns file path."""
    s = settings()
    if not is_configured():
        raise RuntimeError("未配置生图接口：在设置里填写 生图 Base URL / API Key / 模型")
    payload = {"model": s["model"], "prompt": prompt, "size": s["size"], "n": 1}
    req = urllib.request.Request(
        s["base_url"] + "/images/generations",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + s["api_key"]},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"生图接口返回 {e.code}：{e.read().decode('utf-8', 'replace')[:300]}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"连不上生图接口：{e.reason}") from None
    except TimeoutError:
        raise RuntimeError(f"生图超过 {timeout} 秒没返回") from None
    try:
        item = data["data"][0]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("生图返回格式无法识别：" + json.dumps(data, ensure_ascii=False)[:300]) from None
    if item.get("b64_json"):
        raw = base64.b64decode(item["b64_json"])
    elif item.get("url"):
        try:
            with urllib.request.urlopen(item["url"], timeout=120) as r:
                raw = r.read()
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"图片下载失败：{e}") from None
    else:
        raise RuntimeError("生图返回里没有图片")
    path = out_base + _ext(raw)
    with open(path, "wb") as f:
        f.write(raw)
    return path


_ = config  # keep import for future shared tokens

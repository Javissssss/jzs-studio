# -*- coding: utf-8 -*-
"""Product-wide paths and constants. Zero hardcoded user paths."""

import os
import sys

# Product root = parent of core/
CORE_DIR = os.path.dirname(os.path.abspath(__file__))
PRODUCT_ROOT = os.path.dirname(CORE_DIR)


def _load_dotenv(path):
    """Minimal .env loader (KEY=VALUE lines). Real env vars win."""
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip().strip('"').strip("'")
            if k.strip() and v and k.strip() not in os.environ:
                os.environ[k.strip()] = v


_load_dotenv(os.path.join(PRODUCT_ROOT, ".env"))

# Embedded skill package (single source of truth for scripts/templates/references)
SKILL_DIR = os.path.join(PRODUCT_ROOT, "skill", "jzs-content-publisher")
SCRIPTS_DIR = os.path.join(SKILL_DIR, "scripts")
TEMPLATES_DIR = os.path.join(SKILL_DIR, "templates")
REFERENCES_DIR = os.path.join(SKILL_DIR, "references")
FIGURE_TPL_DIR = os.path.join(TEMPLATES_DIR, "figure")

# Runtime workspace (per-project state + outputs)
# override with JZS_WORKSPACE to keep drafts outside the repo
WORKSPACE_DIR = os.environ.get("JZS_WORKSPACE") or os.path.join(PRODUCT_ROOT, "workspace")

# Web static dir
WEB_DIR = os.path.join(PRODUCT_ROOT, "web")

# Python executable for subprocess calls to skill scripts
PYTHON = sys.executable or "python"

# Design tokens (brick-red / rice-white) - shared with templates
TOKENS = {
    "bg": "#FAF9F5",
    "fg": "#141413",
    "muted": "#87867F",
    "border": "#E3DACC",
    "accent": "#C96442",
    "accent_d": "#B04A3F",
}

# Pipeline stages in order
STAGES = [
    "topic",  # 1 选题
    "brief",  # 2 创作简报
    "draft",  # 3 回填稿件
    "media",  # 4 配图
    "render",  # 5 排版
    "review",  # 6 终稿确认
    "publish",  # 7 存草稿
    "done",  # 8 归档
]

STAGE_LABELS = {
    "topic": "选题",
    "brief": "创作简报",
    "draft": "回填稿件",
    "media": "配图制作",
    "render": "排版渲染",
    "review": "终稿确认",
    "publish": "存草稿",
    "done": "完成归档",
}

# Finance topics must carry a disclaimer (brief + rendered footer share this)
FINANCE_KEYWORDS = (
    "美联储", "利率", "汇率", "黄金", "国债", "收益率", "通胀", "股", "基金",
    "楼市", "房价", "降息", "加息", "财经", "经济", "投资", "理财",
)
FINANCE_DISCLAIMER = "行情为已发生的客观描述，不构成任何买卖推荐。"


def is_finance(text):
    t = (text or "").lower()
    return any(k in t for k in FINANCE_KEYWORDS)


# Human checkpoints (must wait for user)
CHECKPOINTS = {"topic", "review"}


def project_dir(project_id):
    return os.path.join(WORKSPACE_DIR, project_id)


def ensure_dirs():
    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    os.makedirs(WEB_DIR, exist_ok=True)

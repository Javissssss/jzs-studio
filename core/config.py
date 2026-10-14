# -*- coding: utf-8 -*-
"""Product-wide paths and constants. Zero hardcoded user paths."""

import os
import sys

# Product root = parent of core/
CORE_DIR = os.path.dirname(os.path.abspath(__file__))
PRODUCT_ROOT = os.path.dirname(CORE_DIR)

# Embedded skill package (single source of truth for scripts/templates/references)
SKILL_DIR = os.path.join(PRODUCT_ROOT, "skill", "jzs-content-publisher")
SCRIPTS_DIR = os.path.join(SKILL_DIR, "scripts")
TEMPLATES_DIR = os.path.join(SKILL_DIR, "templates")
REFERENCES_DIR = os.path.join(SKILL_DIR, "references")
FIGURE_TPL_DIR = os.path.join(TEMPLATES_DIR, "figure")

# Runtime workspace (per-project state + outputs)
WORKSPACE_DIR = os.path.join(PRODUCT_ROOT, "workspace")

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

# Human checkpoints (must wait for user)
CHECKPOINTS = {"topic", "review"}


def project_dir(project_id):
    return os.path.join(WORKSPACE_DIR, project_id)


def ensure_dirs():
    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    os.makedirs(WEB_DIR, exist_ok=True)

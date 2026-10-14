# -*- coding: utf-8 -*-
"""Project state management. Each project = one article creation run.
State persisted to workspace/<id>/state.json."""

import json
import os
import time
import uuid

from . import config


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def new_project(title="untitled"):
    """Create a new project, return its state dict."""
    pid = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    pdir = config.project_dir(pid)
    os.makedirs(pdir, exist_ok=True)
    os.makedirs(os.path.join(pdir, "output"), exist_ok=True)
    state = {
        "id": pid,
        "title": title,
        "stage": "topic",
        "created": _now(),
        "updated": _now(),
        "topic": {},  # selected topic card
        "candidates": [],  # scored candidates
        "brief": {},  # generated brief meta
        "draft": {},  # filled drafts {wechat_md, xhs_md, xhs_title, xhs_tags}
        "media": {},  # generated media manifest
        "render": {},  # rendered html path etc
        "publish": {},  # publish receipts
        "log": [],
    }
    save(pid, state)
    return state


def load(pid):
    path = os.path.join(config.project_dir(pid), "state.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save(pid, state):
    pdir = config.project_dir(pid)
    os.makedirs(pdir, exist_ok=True)
    state["updated"] = _now()
    with open(os.path.join(pdir, "state.json"), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return state


def list_projects():
    config.ensure_dirs()
    out = []
    for name in sorted(os.listdir(config.WORKSPACE_DIR), reverse=True):
        pdir = os.path.join(config.WORKSPACE_DIR, name)
        spath = os.path.join(pdir, "state.json")
        if os.path.isdir(pdir) and os.path.exists(spath):
            try:
                with open(spath, "r", encoding="utf-8") as f:
                    s = json.load(f)
                out.append(
                    {
                        "id": s.get("id", name),
                        "title": s.get("title", ""),
                        "stage": s.get("stage", ""),
                        "stage_label": config.STAGE_LABELS.get(s.get("stage", ""), ""),
                        "updated": s.get("updated", ""),
                    }
                )
            except Exception:
                continue
    return out


def set_stage(pid, stage):
    state = load(pid)
    if state is None:
        return None
    if stage not in config.STAGES:
        raise ValueError(f"unknown stage: {stage}")
    state["stage"] = stage
    log(state, f"stage -> {stage}")
    return save(pid, state)


def log(state, msg):
    state.setdefault("log", []).append(f"[{_now()}] {msg}")
    # keep last 200
    state["log"] = state["log"][-200:]


def delete(pid):
    import shutil

    pdir = config.project_dir(pid)
    if os.path.isdir(pdir):
        shutil.rmtree(pdir, ignore_errors=True)
        return True
    return False

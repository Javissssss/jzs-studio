# -*- coding: utf-8 -*-
"""Run OpenAI Codex CLI non-interactively (`codex exec`) as a writing / drawing
engine. Codex uses its own login (`codex login`), so no key lives here.

Config (env or .env, all optional):
  JZS_CODEX_CMD    command or path; default: `codex` on PATH.
                   e.g. "npx -y @openai/codex"  or  C:\\tools\\codex.cmd
  JZS_CODEX_MODEL  model passed via -m
"""

import os
import shlex
import shutil
import subprocess
import sys
import threading


def find_cmd():
    custom = (os.environ.get("JZS_CODEX_CMD") or "").strip().strip('"')
    if custom:
        if os.path.exists(custom):
            return [sys.executable, custom] if custom.endswith(".py") else [custom]
        parts = shlex.split(custom, posix=os.name != "nt")
        # Windows: "npx" / "codex" are .cmd shims, CreateProcess needs the full path
        exe = shutil.which(parts[0]) if parts else None
        return [exe] + parts[1:] if exe else None
    exe = shutil.which("codex")
    return [exe] if exe else None


def public_info():
    cmd = find_cmd()
    return {"available": bool(cmd), "model": os.environ.get("JZS_CODEX_MODEL") or ""}


def run(prompt, cwd, logf=None, writable=False, timeout=900):
    """Feed prompt via stdin, stream progress to logf, return Codex's final message."""
    logf = logf or (lambda m: None)
    cmd = find_cmd()
    if not cmd:
        raise RuntimeError(
            "没找到 codex 命令。先装：npm i -g @openai/codex，再执行 codex login；"
            "或在设置里把 Codex 命令填成 npx -y @openai/codex"
        )
    os.makedirs(cwd, exist_ok=True)
    last = os.path.join(cwd, "_codex_last.txt")
    if os.path.exists(last):
        os.remove(last)
    args = cmd + ["exec"]
    if os.environ.get("JZS_CODEX_MODEL"):
        args += ["-m", os.environ["JZS_CODEX_MODEL"]]
    args += [
        "--skip-git-repo-check", "--ephemeral", "--color", "never",
        "-s", "workspace-write" if writable else "read-only",
        "-C", cwd, "-o", last, "-",
    ]
    logf("启动 Codex" + (f"（{os.environ['JZS_CODEX_MODEL']}）" if os.environ.get("JZS_CODEX_MODEL") else ""))
    try:
        p = subprocess.Popen(
            args, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
        )
    except OSError as e:
        raise RuntimeError(f"Codex 启动失败：{e}") from None
    timer = threading.Timer(timeout, p.kill)
    timer.start()
    tail = []
    try:
        p.stdin.write(prompt)
        p.stdin.close()
        for line in p.stdout:
            line = line.rstrip()
            if line:
                tail = (tail + [line])[-15:]
                logf(line[:200])
        rc = p.wait()
    finally:
        timer.cancel()
        p.stdout.close()
    if rc != 0:
        hint = "\n".join(tail[-5:])
        if "login" in hint.lower() or "auth" in hint.lower():
            hint += "\n（看起来没登录：在终端执行 codex login）"
        raise RuntimeError(f"Codex 退出码 {rc}" + (f"：{hint}" if hint else "（可能超时被终止）"))
    text = ""
    if os.path.exists(last):
        with open(last, encoding="utf-8", errors="replace") as f:
            text = f.read()
        os.remove(last)
    return text

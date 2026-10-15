# -*- coding: utf-8 -*-
"""Tiny in-process background jobs, so long AI/Codex/image calls never block
or time out the HTTP request. The UI polls /api/jobs/<id> for status + log."""

import threading
import time
import uuid

_JOBS = {}
_LOCK = threading.Lock()
MAX_KEEP = 200


def start(kind, pid, fn):
    """Run fn(logf) in a thread. Returns the job dict.
    Raises RuntimeError if the same kind of job is already running for pid."""
    with _LOCK:
        for j in _JOBS.values():
            if j["pid"] == pid and j["kind"] == kind and j["status"] == "running":
                raise RuntimeError("同类任务正在进行中，请等它结束")
        jid = uuid.uuid4().hex[:12]
        job = {
            "id": jid, "kind": kind, "pid": pid, "status": "running",
            "log": [], "result": None, "error": None,
            "started": time.time(), "elapsed": 0,
        }
        _JOBS[jid] = job
        if len(_JOBS) > MAX_KEEP:  # drop oldest finished jobs
            for k in sorted(_JOBS, key=lambda k: _JOBS[k]["started"])[: len(_JOBS) - MAX_KEEP]:
                if _JOBS[k]["status"] != "running":
                    _JOBS.pop(k, None)

    def logf(msg):
        msg = str(msg).rstrip()
        if msg:
            job["log"].append(msg[:300])
            job["log"] = job["log"][-300:]

    def run():
        try:
            job["result"] = fn(logf)
            job["status"] = "done"
        except RuntimeError as e:  # expected, readable errors
            job["error"] = str(e)
            job["status"] = "error"
        except Exception as e:  # noqa: BLE001
            job["error"] = f"{type(e).__name__}: {e}"
            job["status"] = "error"
        job["elapsed"] = round(time.time() - job["started"], 1)

    threading.Thread(target=run, daemon=True).start()
    return job


def run_sync(fn):
    """Same contract as start() but inline (tests / ?wait=1)."""
    log = []
    result = fn(lambda m: log.append(str(m)))
    return result, log


def get(jid):
    return _JOBS.get(jid)


def public(job, since=0):
    out = {k: job[k] for k in ("id", "kind", "status", "result", "error")}
    out["elapsed"] = job["elapsed"] if job["status"] != "running" else round(time.time() - job["started"], 1)
    out["log"] = job["log"][since:]
    out["log_total"] = len(job["log"])
    return out

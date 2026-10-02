"""
«روند تولید این محتوا» — the step-by-step log of one content item, from planning to publishing.

One JSONL file per item in data/traces/<item_id>.jsonl. Each line is a step:
    {"ts": ISO Tehran, "stage": "plan|brief|write|qa|design|approve|publish|measure",
     "title": short Persian label, "detail": what happened, "decision": why this choice,
     "alternatives": [...], "data": {...}}

The daily planner rewrites the "plan" steps of items that are still only planned (the
schedule can legitimately change: a holiday appears, a photo gets used elsewhere). As soon
as any later stage is logged, the trace is frozen and only appended to.
"""

import json
import os

from .util import DATA, now_tehran

TDIR = os.path.join(DATA, "traces")
STAGES = {"plan": "برنامه‌ریزی", "brief": "بریف", "write": "نوشتن", "qa": "کنترل کیفیت",
          "design": "طراحی", "approve": "تأیید", "publish": "انتشار", "measure": "سنجش"}


def _path(item_id):
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in item_id)
    return os.path.join(TDIR, f"{safe}.jsonl")


def read(item_id):
    path = _path(item_id)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def step(item_id, stage, title, detail="", decision=None, alternatives=None, data=None, ts=None):
    os.makedirs(TDIR, exist_ok=True)
    row = {"ts": (ts or now_tehran()).isoformat(timespec="seconds"), "stage": stage, "title": title,
           "detail": detail, "decision": decision, "alternatives": alternatives or [], "data": data or {}}
    with open(_path(item_id), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def replan(item_id, steps):
    """Replace the planning steps of an item that has not progressed past planning."""
    existing = read(item_id)
    if any(s["stage"] != "plan" for s in existing):
        return False                                  # frozen: generation already started
    os.makedirs(TDIR, exist_ok=True)
    now = now_tehran().isoformat(timespec="seconds")
    with open(_path(item_id), "w", encoding="utf-8") as fh:
        for s in steps:
            row = {"ts": now, "stage": "plan", "alternatives": [], "data": {}, "decision": None, "detail": ""}
            row.update(s)
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return True

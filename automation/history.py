"""
Publishing history — one append-only JSONL file per network in dashboard/data/published/.

Every publisher calls record() after it posts (or fails to). The dashboard's
«تاریخچه‌ی انتشار» tab reads these files, so what went out, where, when and with
which product/photo is always answerable per network.

    from automation.history import record
    record("telegram", "post", content_type="قیمت روز", text=..., url=..., message_id=...)
"""

import json
import os
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUB_DIR = os.path.join(ROOT, "dashboard", "data", "published")
TEHRAN = timezone(timedelta(hours=3, minutes=30))

NETWORKS = {
    "site": "سایت", "telegram": "تلگرام", "bale": "بله", "eitaa": "ایتا",
    "rubika": "روبیکا", "whatsapp": "واتساپ", "instagram": "اینستاگرام",
}
KINDS = {"article": "مقاله", "post": "پست", "story": "استوری", "reel": "ریلز", "carousel": "کاروسل",
         "message": "پیام کانال", "comment": "کامنت", "like": "لایک"}
# published: live · sent-to-operator: one-tap file delivered, waiting for the tap · failed · scheduled
STATUSES = {"published", "sent-to-operator", "failed", "scheduled", "deleted"}


def record(network, kind, *, content_type=None, product=None, text=None, media=None, url=None,
           message_id=None, status="published", plan_ref=None, error=None, stats=None, when=None):
    if network not in NETWORKS:
        raise ValueError(f"unknown network {network!r}; one of {', '.join(NETWORKS)}")
    if status not in STATUSES:
        raise ValueError(f"unknown status {status!r}")
    row = {
        "ts": (when or datetime.now(TEHRAN)).isoformat(timespec="seconds"),
        "network": network, "kind": kind, "content_type": content_type, "product": product,
        "text": (text or "")[:1500], "media": media, "url": url, "message_id": message_id,
        "status": status, "plan_ref": plan_ref, "error": (error or None) and str(error)[:300], "stats": stats,
    }
    os.makedirs(PUB_DIR, exist_ok=True)
    with open(os.path.join(PUB_DIR, f"{network}.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def load(limit_per_network=1000):
    out = {}
    for net in NETWORKS:
        path = os.path.join(PUB_DIR, f"{net}.jsonl")
        rows = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        out[net] = rows[-limit_per_network:]
    return out

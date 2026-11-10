"""
The Telegram channel's face: name, description and photo, set once through the signed-in account
(it must be the channel's admin). Runs by itself right after a successful Telegram sign-in; the
result is kept in dashboard/data/channel_profile.json so it is not redone every time.

    python3 channel_profile.py        # apply now
"""

import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [HERE, os.path.dirname(HERE), os.path.join(ROOT, "dashboard")]

from sf.env import get, load_env  # noqa: E402
from sf.util import DATA, read_json, write_json  # noqa: E402

DONE = os.path.join(DATA, "channel_profile.json")
PHOTO = os.path.expanduser("~/projects/sepahanfelez-staging/pricebot/brand/avatar-640.png")
TITLE = "سپاهان فلز | مفتول، سیم و توری"


def about():
    load_env()
    phone = (get("SITE_CONTACT_PHONES", "") or "").split(",")[0].strip()
    fa = phone.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
    return ("کانال رسمی صنایع مفتولی طلوع سپاهان (سپاهان فلز)، تولیدکننده‌ی مستقیم مفتول، سیم و توری در اصفهان.\n"
            "قیمت روز، خبر بازار آهن و راهنمای خرید.\n"
            "🌐 sepahanfelez.ir/price" + (f"\n☎️ {fa}" if fa else ""))[:255]


def apply(client=None, say=print, force=False):
    from telethon.tl.functions.channels import EditPhotoRequest, EditTitleRequest
    from telethon.tl.functions.messages import EditChatAboutRequest
    from telethon.tl.types import InputChatUploadedPhoto
    load_env()
    channel = get("TELEGRAM_CHANNEL", "")
    if not channel:
        say("آدرس کانال تلگرام (TELEGRAM_CHANNEL) خالی است؛ پروفایل کانال تنظیم نشد.")
        return False
    state = read_json(DONE, {}) or {}
    if state.get("channel") == channel and state.get("ok") and not force:
        return True
    own = client is None
    if own:
        import login as L
        client = L._telegram_client()
        client.connect()
    try:
        ent = client.get_entity(channel)
        done = []
        if (getattr(ent, "title", "") or "") != TITLE:
            client(EditTitleRequest(ent, TITLE))
            done.append("نام")
        client(EditChatAboutRequest(ent, about()))
        done.append("توضیحات")
        if os.path.exists(PHOTO):
            client(EditPhotoRequest(ent, InputChatUploadedPhoto(file=client.upload_file(PHOTO))))
            done.append("عکس")
        write_json(DONE, {"channel": channel, "ok": True, "at": datetime.now().astimezone().isoformat(timespec="minutes"),
                          "title": TITLE, "about": about()})
        say(f"✓ پروفایل کانال {channel} تنظیم شد: {'، '.join(done)}.")
        return True
    except Exception as exc:                                            # noqa: BLE001
        write_json(DONE, {"channel": channel, "ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
        say(f"پروفایل کانال تنظیم نشد ({type(exc).__name__}: {str(exc)[:160]}) — این حساب باید ادمین کانال با اجازه‌ی «تغییر اطلاعات کانال» باشد.")
        return False
    finally:
        if own:
            client.disconnect()


if __name__ == "__main__":
    apply(force="--force" in sys.argv)

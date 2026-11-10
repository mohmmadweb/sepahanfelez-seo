"""
Every hour, day and night (systemd: sepahanfelez-site.timer):
  - keep the panel session alive: the site's session lasts 3 days and slides with every visit,
    so a visit every ~2 hours means it never runs out;
  - in working hours (08–21 Tehran) publish articles and news whose time has come.
Quiet when there is nothing to do.
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import articles  # noqa: E402
import news  # noqa: E402
import panel  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import alert  # noqa: E402
from sf.util import now_tehran  # noqa: E402

KEEPALIVE = timedelta(minutes=110)

if __name__ == "__main__":
    if os.path.exists(panel.state_path()):
        st = panel.status()
        last = st.get("checked")
        if not last or datetime.now().astimezone() - datetime.fromisoformat(last) > KEEPALIVE:
            ok = panel.check()
            print("panel:", "ok" if ok else "logged out / unreachable")
            st2 = panel.status()
            if not st2.get("logged_in"):
                alert.send("conn:site", "اتصال قطع: پنل مدیریت sepahanfelez.ir",
                           "داشبورد از پنل سایت بیرون افتاده؛ انتشار مقاله و خبر متوقف است.",
                           "اتصالات و تنظیمات → «پنل سایت» → موبایل مدیر → «ورود» → کد پیامکی", every_h=12)
            elif int(st2.get("fails", 0) or 0) >= 6:
                alert.send("site:down", "سایت sepahanfelez.ir جواب نمی‌دهد",
                           f"{st2.get('fails')} بار پشت‌سرهم پنل سایت باز نشد ({st2.get('detail')}).",
                           "سایت را در مرورگر باز کنید؛ اگر باز نمی‌شود هاست (cPanel) را بررسی کنید", every_h=6)
            else:
                alert.resolved("conn:site", "پنل مدیریت sepahanfelez.ir")
    try:                                                   # news sources hold ~30 items each: read them every hour
        news.collect(say=lambda *_: None)
    except Exception as exc:                               # noqa: BLE001
        print("news sources:", exc)
    if 8 <= now_tehran().hour < 22:
        # the news draft is written even while the panel is signed out, so it is ready the moment it is back
        for d in news.due(can_publish=bool(panel.status().get("logged_in"))):
            print("news published:", d.get("url"))
        if panel.status().get("logged_in"):
            for d in articles.due():
                print("published:", d.get("url"))

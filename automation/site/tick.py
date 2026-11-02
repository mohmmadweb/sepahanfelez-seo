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
from sf.util import now_tehran  # noqa: E402

KEEPALIVE = timedelta(minutes=110)

if __name__ == "__main__":
    if os.path.exists(panel.state_path()):
        st = panel.status()
        last = st.get("checked")
        if not last or datetime.now().astimezone() - datetime.fromisoformat(last) > KEEPALIVE:
            print("panel:", "ok" if panel.check() else "logged out / unreachable")
    try:                                                   # news sources hold ~30 items each: read them every hour
        news.collect(say=lambda *_: None)
    except Exception as exc:                               # noqa: BLE001
        print("news sources:", exc)
    if 8 <= now_tehran().hour < 22 and panel.status().get("logged_in"):
        for d in articles.due():
            print("published:", d.get("url"))
        for d in news.due():
            print("news published:", d.get("url"))

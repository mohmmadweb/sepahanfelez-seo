"""
Hourly in working hours (systemd: sepahanfelez-site.timer): keep the panel session alive and
publish approved drafts whose time has come. Quiet when there is nothing to do.
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import articles  # noqa: E402
import panel  # noqa: E402

if __name__ == "__main__":
    if os.path.exists(panel.state_path()):
        st = panel.status()
        last = st.get("checked")
        if not last or datetime.now().astimezone() - datetime.fromisoformat(last) > timedelta(hours=3):
            print("panel:", "ok" if panel.check() else "logged out")
    for d in articles.due():
        print("published:", d.get("url"))

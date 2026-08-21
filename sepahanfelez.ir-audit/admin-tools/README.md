# admin-tools

Scripts that drive the sepahanfelez.ir admin panel. Written because the host
gives no shell and no database access, so the panel is the only way to change
stored data — see SESSION-HANDOFF.md §3 and §6.4.

**Read §6.4 before writing anything new here.** These forms have three separate
ways to destroy data if you rebuild and POST them by hand, which is why
everything below drives the real form in a browser instead.

| Script | Does |
|---|---|
| `admin_login.py request <mobile>` | sends the SMS code |
| `admin_login.py verify <code>` | completes login, writes `cookies.json` |
| `admin.py <path>...` | dumps any admin form's fields, flagging legacy values |
| `admin_edit.py plan\|apply` | settings, sliders and category records |
| `fix_articles.py plan\|apply` | article canonical / schema / meta |
| `fix_bodies.py plan\|apply` | CKEditor bodies, via `setData()` |

Every one of them takes `plan` (or no argument) to print what it would change
and touch nothing. **Always run `plan` first and read it.**

The login code expires after **two minutes**, so have the owner at their phone
before running `request`.

```bash
python3 -m venv .venv
.venv/bin/pip install requests beautifulsoup4 playwright pillow
.venv/bin/playwright install chromium
```

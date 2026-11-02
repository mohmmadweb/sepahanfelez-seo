"""
The house signature: every piece that goes out carries the same mark of Sepahan Felez.

    site article  → a «نکته‌ی کارخانه‌ی سپاهان فلز» section (written by the writer) + the byline block below
    site news     → the news format (lead · در یک نگاه · جزئیات · برداشت سپاهان فلز) + byline with the source
    channel post / story caption / LinkedIn → the sign-off line(s) below
    cards         → the logo (render_card.py)

Wording lives in dashboard/config/signature.json so it can be changed without touching code.
Every function is idempotent: signing twice leaves one signature.
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "dashboard", "config", "signature.json")
DEFAULT = {
    "brand": "سپاهان فلز",
    "desk": "تحریریه‌ی سپاهان فلز",
    "about": "صنایع مفتولی طلوع سپاهان، تولیدکننده‌ی مستقیم مفتول، سیم و توری در اصفهان",
    "factory_tip": "نکته‌ی کارخانه‌ی سپاهان فلز",
    "news_label": "خبر و تحلیل سپاهان فلز",
    "news_take": "برداشت سپاهان فلز برای خریداران",
    "site": "sepahanfelez.ir",
    "hashtag": "#سپاهان_فلز",
}
MARK = "✍️"
NEWS_MARK = "📰"


def cfg():
    try:
        with open(CONFIG, encoding="utf-8") as fh:
            return {**DEFAULT, **json.load(fh)}
    except (OSError, ValueError):
        return dict(DEFAULT)


def _strip_block(body, mark):
    """Remove an earlier byline block (the last <blockquote> that starts with the mark)."""
    i = body.rfind("<blockquote><p><strong>" + mark)
    if i < 0:
        return body
    j = body.find("</blockquote>", i)
    return (body[:i] + body[j + len("</blockquote>"):]).rstrip() if j > 0 else body


def article_byline(body):
    c = cfg()
    body = _strip_block(body or "", MARK)
    return body + (f'<blockquote><p><strong>{MARK} {c["desk"]}</strong> — این مطلب را تیم فنی {c["about"]} نوشته است. '
                   f'<a href="/price">قیمت روز همه‌ی کالاها</a> · <a href="/contact">مشاوره با کارشناس فروش</a></p></blockquote>')


def news_byline(body, source_name, source_url):
    c = cfg()
    body = _strip_block(body or "", NEWS_MARK)
    return body + (f'<blockquote><p><strong>{NEWS_MARK} {c["news_label"]}</strong> — بازنویسی و تحلیل {c["desk"]}. '
                   f'منبع اصلی خبر: <a href="{source_url}" rel="nofollow noopener" target="_blank">{source_name}</a> · '
                   f'<a href="/price">قیمت روز</a></p></blockquote>')


def signoff():
    c = cfg()
    return f"🔩 {c['brand']} | {c['about'].split('،', 1)[-1].strip()}\n🌐 {c['site']}  {c['hashtag']}"


def caption(text):
    """Channel post, story caption or LinkedIn text + the sign-off, once."""
    text = (text or "").rstrip()
    s = signoff()
    if s.splitlines()[0] in text:
        return text
    return f"{text}\n\n{s}" if text else s

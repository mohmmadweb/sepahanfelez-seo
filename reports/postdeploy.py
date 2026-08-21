"""
Post-deploy verification against the live site.

Re-runs the same measurements as the original audit so the before/after numbers
are comparable, plus the checks specific to what this deploy changed:
the price cards, the rebuilt auth screens, the vendor bundle, the clock, and
the absence of the previous owner's logo.
"""
import asyncio, json
from playwright.async_api import async_playwright

BASE = "https://sepahanfelez.ir"
PAGES = ["/", "/price", "/blog", "/about", "/contact", "/login",
         "/category/", "/category/سیم-خاردار"]

AUDIT = r"""
() => {
  const px = s => parseFloat(s) || 0;
  const o = {};
  o.htmlFontSize = getComputedStyle(document.documentElement).fontSize;
  o.bodyFontSize = getComputedStyle(document.body).fontSize;

  const vw = document.documentElement.clientWidth;
  o.scrollWidth = document.documentElement.scrollWidth;
  window.scrollTo(600, 0); o.canScrollX = window.scrollX > 2; window.scrollTo(0, 0);

  let small = 0;
  document.querySelectorAll('p,span,li,td,th,a,label,small,div,h1,h2,h3,button').forEach(el => {
    let t=false; el.childNodes.forEach(n=>{if(n.nodeType===3&&n.textContent.trim().length>3)t=true;});
    if(!t) return;
    const cs=getComputedStyle(el); if(cs.display==='none'||cs.visibility==='hidden')return;
    if (px(cs.fontSize) < 14) small++;
  });
  o.smallText = small;

  let tt=0, tot=0, unnamed=0;
  document.querySelectorAll('a,button,input:not([type=hidden]),select,textarea').forEach(el=>{
    const cs=getComputedStyle(el); if(cs.display==='none'||cs.visibility==='hidden')return;
    const r=el.getBoundingClientRect(); if(!r.width||!r.height)return;
    tot++; if(r.width<44||r.height<44) tt++;
    const name=(el.textContent||'').trim()||el.getAttribute('aria-label')||el.getAttribute('title')||el.value;
    if(!name && el.querySelector('i,svg')) unnamed++;
  });
  o.smallTaps=tt; o.totalTaps=tot; o.unnamedIcons=unnamed;

  // price table: is the number a visitor came for actually on screen?
  const priceCell = document.querySelector('td[data-label="قیمت لحظه ای"]');
  const buyBtn = document.querySelector('.buy-cell button, td[data-label="خرید"] button');
  const inView = el => { if(!el) return null; const r=el.getBoundingClientRect();
                         return r.width>0 && r.right<=vw+2 && r.left>=-2; };
  o.priceVisible = inView(priceCell);
  o.buyVisible = inView(buyBtn);
  const table = document.querySelector('table');
  o.tableWidth = table ? Math.round(table.getBoundingClientRect().width) : null;

  o.skipLink = !!document.querySelector('.skip-to-content');
  o.thScope  = document.querySelectorAll('th[scope]').length;
  o.h1       = document.querySelectorAll('h1').length;
  o.metaDesc = !!document.querySelector('meta[name=description]')?.content;
  o.clock    = (document.getElementById('time_counter2')||{}).textContent || null;

  // the previous owner's artwork
  o.legacyLogo = [...document.images].filter(i =>
      /images\/(logo|text-logo-light)\.png/.test(i.currentSrc || i.src || '')).length;

  const scripts = [...document.querySelectorAll('script[src]')];
  o.scripts = scripts.length;
  o.renderBlocking = scripts.filter(s => !s.async && !s.defer).map(s=>s.src.split('/').pop().slice(0,32));
  o.hasVendor = scripts.some(s => s.src.includes('vendor.js'));
  o.gtagTags = scripts.filter(s => s.src.includes('gtag/js')).length;
  o.histats = document.documentElement.innerHTML.toLowerCase().includes('histats');
  o.preconnect = document.querySelectorAll('link[rel=preconnect],link[rel=preload]').length;
  o.imgNoLoading = [...document.images].filter(i => !i.getAttribute('loading')).length;
  return o;
}
"""

PERF = r"""
() => new Promise(res => {
  const r = {cls:0, lcp:0};
  try { new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) r.cls += e.value; })
        .observe({type:'layout-shift', buffered:true}); } catch(e){}
  try { new PerformanceObserver(l => { const es=l.getEntries(); r.lcp = Math.round(es[es.length-1].startTime); })
        .observe({type:'largest-contentful-paint', buffered:true}); } catch(e){}
  setTimeout(() => {
    const nav = performance.getEntriesByType('navigation')[0]||{};
    r.ttfb = Math.round(nav.responseStart||0);
    const rs = performance.getEntriesByType('resource');
    r.transferKB = Math.round(rs.reduce((a,x)=>a+(x.transferSize||0),0)/1024);
    r.jsKB = Math.round(rs.filter(x=>x.initiatorType==='script').reduce((a,x)=>a+(x.transferSize||0),0)/1024);
    r.cls = Math.round(r.cls*1000)/1000;
    res(r);
  }, 6000);
})
"""

async def main():
    out = {}
    async with async_playwright() as pw:
        b = await pw.chromium.launch(args=["--no-sandbox"])
        for dev, vp, ua in [
            ("mobile", {"width":375,"height":812},
             "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"),
            ("desktop", {"width":1440,"height":900},
             "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")]:
            ctx = await b.new_context(viewport=vp, user_agent=ua, locale="fa-IR")
            for path in PAGES:
                pg = await ctx.new_page()
                errs = []
                pg.on("pageerror", lambda e: errs.append(str(e)[:110]))
                pg.on("console", lambda m: errs.append("console:"+m.text[:90]) if m.type=="error" else None)
                try:
                    resp = await pg.goto(BASE+path, wait_until="networkidle", timeout=60000)
                except Exception:
                    try:
                        resp = await pg.goto(BASE+path, wait_until="domcontentloaded", timeout=45000)
                    except Exception as e:
                        out.setdefault(dev, {})[path] = {"error": str(e)[:140]}
                        await pg.close(); continue
                await pg.wait_for_timeout(1200)
                d = await pg.evaluate(AUDIT)
                d["perf"] = await pg.evaluate(PERF)
                d["status"] = resp.status if resp else None
                d["jsErrors"] = errs[:8]
                d["jsErrorCount"] = len(errs)
                out.setdefault(dev, {})[path] = d
                safe = path.strip("/").replace("/","_") or "home"
                await pg.screenshot(path=f"post_{dev}_{safe}.png")
                await pg.close()
                print(f"  {dev} {path} -> {d.get('status')}", flush=True)
            await ctx.close()
        await b.close()
    json.dump(out, open("post-deploy.json","w"), ensure_ascii=False, indent=1)
    print("WROTE post-deploy.json")

asyncio.run(main())

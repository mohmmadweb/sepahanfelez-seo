import json, sys, asyncio
from playwright.async_api import async_playwright

BASE = "https://sepahanfelez.ir"
PAGES = ["/", "/price", "/blog", "/about", "/contact", "/login",
         "/category/", "/category/سیم-خاردار"]

AUDIT_JS = r"""
() => {
  const out = {};
  const px = s => parseFloat(s) || 0;

  // --- root font size (rem base) ---
  out.htmlFontSize = getComputedStyle(document.documentElement).fontSize;
  out.bodyFontSize = getComputedStyle(document.body).fontSize;

  // --- horizontal overflow ---
  const vw = document.documentElement.clientWidth;
  out.scrollWidth = document.documentElement.scrollWidth;
  out.viewportWidth = vw;
  out.horizontalOverflow = document.documentElement.scrollWidth > vw + 1;
  const over = [];
  document.querySelectorAll('body *').forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width > 0 && (r.right > vw + 2 || r.left < -2)) {
      over.push({tag: el.tagName.toLowerCase(), cls: (el.className||'').toString().slice(0,60),
                 right: Math.round(r.right), left: Math.round(r.left), w: Math.round(r.width)});
    }
  });
  out.overflowingCount = over.length;
  out.overflowingSample = over.slice(0, 12);

  // --- small text ---
  const small = [];
  document.querySelectorAll('p,span,li,td,th,a,label,small,div').forEach(el => {
    if (!el.childNodes.length) return;
    let hasText = false;
    el.childNodes.forEach(n => { if (n.nodeType === 3 && n.textContent.trim().length > 3) hasText = true; });
    if (!hasText) return;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return;
    const fs = px(cs.fontSize);
    if (fs > 0 && fs < 14) small.push({tag: el.tagName.toLowerCase(), fs: Math.round(fs*10)/10,
        cls:(el.className||'').toString().slice(0,40), text: el.textContent.trim().slice(0,40)});
  });
  out.smallTextCount = small.length;
  out.smallTextSample = small.slice(0, 15);
  const buckets = {};
  small.forEach(s => { const k = s.fs.toString(); buckets[k]=(buckets[k]||0)+1; });
  out.smallTextBySize = buckets;

  // --- touch targets ---
  const tt = [];
  document.querySelectorAll('a,button,input:not([type=hidden]),select,textarea,[role=button],[onclick]').forEach(el => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return;
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return;
    if (r.width < 44 || r.height < 44) {
      tt.push({tag: el.tagName.toLowerCase(), w: Math.round(r.width), h: Math.round(r.height),
               cls:(el.className||'').toString().slice(0,40), text:(el.textContent||'').trim().slice(0,30)});
    }
  });
  out.totalInteractive = document.querySelectorAll('a,button,input:not([type=hidden]),select,textarea').length;
  out.smallTapTargets = tt.length;
  out.smallTapSample = tt.slice(0, 15);

  // --- images ---
  const imgs = [...document.querySelectorAll('img')];
  out.imgTotal = imgs.length;
  out.imgNoAlt = imgs.filter(i => !i.hasAttribute('alt')).length;
  out.imgEmptyAlt = imgs.filter(i => i.getAttribute('alt') === '').length;
  out.imgNoDims = imgs.filter(i => !(i.getAttribute('width') && i.getAttribute('height')) &&
                                    !getComputedStyle(i).aspectRatio.includes('/')).length;
  out.imgNoLazy = imgs.filter(i => i.getAttribute('loading') !== 'lazy').length;
  out.imgNoDimsSample = imgs.filter(i => !(i.getAttribute('width')&&i.getAttribute('height')))
                            .slice(0,10).map(i=>({src:(i.currentSrc||i.src||'').split('/').pop().slice(0,50),
                                                  w:Math.round(i.getBoundingClientRect().width)}));
  out.imgFormats = {};
  imgs.forEach(i => { const s=(i.currentSrc||i.src||''); const m=s.split('?')[0].split('.').pop().toLowerCase().slice(0,5);
                      out.imgFormats[m]=(out.imgFormats[m]||0)+1; });

  // --- headings ---
  const hs = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].map(h => ({
      lvl: +h.tagName[1], text: h.textContent.trim().slice(0, 60)}));
  out.headings = hs;
  out.h1Count = hs.filter(h=>h.lvl===1).length;
  let skips = [];
  for (let i=1;i<hs.length;i++) if (hs[i].lvl - hs[i-1].lvl > 1) skips.push(`h${hs[i-1].lvl}→h${hs[i].lvl}`);
  out.headingSkips = skips;

  // --- forms ---
  const fields = [...document.querySelectorAll('input:not([type=hidden]):not([type=submit]):not([type=button]),select,textarea')];
  out.formFields = fields.length;
  out.fieldsNoLabel = fields.filter(f => {
      if (f.getAttribute('aria-label') || f.getAttribute('aria-labelledby')) return false;
      if (f.id && document.querySelector(`label[for="${CSS.escape(f.id)}"]`)) return false;
      if (f.closest('label')) return false;
      return true;
  }).length;
  out.fieldsPlaceholderOnly = fields.filter(f => {
      const labelled = (f.id && document.querySelector(`label[for="${CSS.escape(f.id)}"]`)) || f.closest('label') || f.getAttribute('aria-label');
      return !labelled && f.getAttribute('placeholder');
  }).length;
  out.fieldsNoAutocomplete = fields.filter(f => !f.getAttribute('autocomplete') &&
      ['text','tel','email','password'].includes(f.type)).length;
  out.fieldTypes = fields.map(f=>({t:f.type||f.tagName.toLowerCase(), name:f.name||'', ph:f.getAttribute('placeholder')||''})).slice(0,20);

  // --- a11y misc ---
  out.langAttr = document.documentElement.getAttribute('lang');
  out.dirAttr = document.documentElement.getAttribute('dir');
  out.skipLink = !!document.querySelector('a[href^="#"][class*=skip], a[href="#main"], a[href="#content"]');
  out.landmarks = {main: document.querySelectorAll('main').length, nav: document.querySelectorAll('nav').length,
                   header: document.querySelectorAll('header').length, footer: document.querySelectorAll('footer').length,
                   aside: document.querySelectorAll('aside').length};
  const iconOnly = [...document.querySelectorAll('a,button')].filter(el=>{
      const t=(el.textContent||'').trim(); const hasIcon = el.querySelector('i,svg');
      return hasIcon && t.length===0 && !el.getAttribute('aria-label') && !el.getAttribute('title');
  });
  out.iconOnlyNoLabel = iconOnly.length;
  out.iconOnlySample = iconOnly.slice(0,10).map(e=>({tag:e.tagName.toLowerCase(), cls:(e.className||'').toString().slice(0,40)}));
  // focus visibility: check if any rule kills outline
  out.tabbable = document.querySelectorAll('[tabindex]').length;

  // --- contrast (text vs background) ---
  function lum(c){ const [r,g,b]=c.map(v=>{v/=255; return v<=0.03928? v/12.92 : Math.pow((v+0.055)/1.055,2.4);});
                   return 0.2126*r+0.7152*g+0.0722*b; }
  function parseRGB(s){ const m=s.match(/rgba?\(([^)]+)\)/); if(!m) return null;
      const p=m[1].split(',').map(x=>parseFloat(x)); return {rgb:[p[0],p[1],p[2]], a: p.length>3?p[3]:1}; }
  function bgOf(el){ let e=el; while(e && e!==document.documentElement){ const c=parseRGB(getComputedStyle(e).backgroundColor);
      if(c && c.a>0.5) return c.rgb; e=e.parentElement; } return [255,255,255]; }
  const lowc = [];
  const seen = new Set();
  document.querySelectorAll('p,span,li,td,th,a,label,small,h1,h2,h3,h4,h5,h6,button').forEach(el=>{
      let hasText=false; el.childNodes.forEach(n=>{if(n.nodeType===3&&n.textContent.trim().length>2)hasText=true;});
      if(!hasText) return;
      const cs=getComputedStyle(el); if(cs.display==='none'||cs.visibility==='hidden'||cs.opacity==='0') return;
      const fg=parseRGB(cs.color); if(!fg) return;
      const bg=bgOf(el);
      const L1=lum(fg.rgb), L2=lum(bg);
      const ratio=(Math.max(L1,L2)+0.05)/(Math.min(L1,L2)+0.05);
      const fs=px(cs.fontSize); const bold=parseInt(cs.fontWeight)>=700;
      const large = fs>=24 || (fs>=18.66 && bold);
      const need = large?3:4.5;
      if(ratio < need){
        const key=cs.color+'|'+bg.join(',')+'|'+Math.round(fs);
        if(seen.has(key)) return; seen.add(key);
        lowc.push({fg:cs.color, bg:'rgb('+bg.join(',')+')', ratio:Math.round(ratio*100)/100, need,
                   fs:Math.round(fs*10)/10, text:el.textContent.trim().slice(0,40)});
      }
  });
  out.lowContrastPairs = lowc.length;
  out.lowContrastSample = lowc.slice(0,15);

  // --- tables ---
  const tables=[...document.querySelectorAll('table')];
  out.tableCount = tables.length;
  out.tableInfo = tables.slice(0,5).map(t=>({rows:t.querySelectorAll('tr').length, cols:t.querySelectorAll('tr')[0]?.children.length||0,
      w:Math.round(t.getBoundingClientRect().width), minW:getComputedStyle(t).minWidth,
      caption: !!t.querySelector('caption'), thead: !!t.querySelector('thead'), scope: t.querySelectorAll('th[scope]').length}));

  // --- assets / weight hints ---
  out.stylesheets = [...document.querySelectorAll('link[rel=stylesheet]')].map(l=>l.href.split('/').pop().slice(0,40));
  out.scripts = [...document.querySelectorAll('script[src]')].map(s=>({src:s.src.split('/').pop().slice(0,45),
      async:s.async, defer:s.defer, third: !s.src.includes('sepahanfelez')}));
  out.inlineScripts = [...document.querySelectorAll('script:not([src])')].length;
  out.preconnect = [...document.querySelectorAll('link[rel=preconnect],link[rel=dns-prefetch],link[rel=preload]')].map(l=>l.rel+':'+l.href.slice(0,50));

  // --- SEO/meta ---
  out.title = document.title;
  out.metaDesc = document.querySelector('meta[name=description]')?.content || null;
  out.canonical = document.querySelector('link[rel=canonical]')?.href || null;
  out.robots = document.querySelector('meta[name=robots]')?.content || null;
  out.jsonLd = [...document.querySelectorAll('script[type="application/ld+json"]')].map(s=>{
      try{const j=JSON.parse(s.textContent); return j['@type']||Object.keys(j).join(',');}catch(e){return 'INVALID';}});
  out.domNodes = document.querySelectorAll('*').length;
  return out;
}
"""

PERF_JS = r"""
() => new Promise(resolve => {
  const res = {cls: 0, lcp: 0, lcpEl: '', longTasks: 0, longTaskTime: 0, shifts: []};
  try {
    new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) {
        res.cls += e.value;
        if (e.value > 0.01) res.shifts.push({v: Math.round(e.value*1000)/1000,
          src: (e.sources||[]).map(s=>s.node?(s.node.tagName||'')+'.'+((s.node.className||'').toString().split(' ')[0]):'').slice(0,3)});
    }}).observe({type:'layout-shift', buffered:true});
  } catch(e){}
  try {
    new PerformanceObserver(l => { const es=l.getEntries(); const e=es[es.length-1];
      res.lcp = Math.round(e.startTime); res.lcpEl = e.element ? (e.element.tagName+'.'+(e.element.className||'').toString().split(' ')[0]) : (e.url||'').split('/').pop();
    }).observe({type:'largest-contentful-paint', buffered:true});
  } catch(e){}
  try {
    new PerformanceObserver(l => { for(const e of l.getEntries()){res.longTasks++; res.longTaskTime+=e.duration;} })
      .observe({type:'longtask', buffered:true});
  } catch(e){}
  setTimeout(() => {
    const nav = performance.getEntriesByType('navigation')[0]||{};
    res.ttfb = Math.round(nav.responseStart||0);
    res.domContentLoaded = Math.round(nav.domContentLoadedEventEnd||0);
    res.loadEvent = Math.round(nav.loadEventEnd||0);
    const rs = performance.getEntriesByType('resource');
    res.resourceCount = rs.length;
    let byType={}; let total=0;
    rs.forEach(r=>{ const s=r.transferSize||0; total+=s;
      const t=r.initiatorType||'other'; byType[t]=(byType[t]||0)+s; });
    res.totalTransferKB = Math.round(total/1024);
    res.byTypeKB = Object.fromEntries(Object.entries(byType).map(([k,v])=>[k,Math.round(v/1024)]));
    res.heaviest = rs.map(r=>({u:r.name.split('/').pop().split('?')[0].slice(0,45), kb:Math.round((r.transferSize||0)/1024), ms:Math.round(r.duration)}))
                     .sort((a,b)=>b.kb-a.kb).slice(0,12);
    res.longTaskTime = Math.round(res.longTaskTime);
    res.cls = Math.round(res.cls*1000)/1000;
    resolve(res);
  }, 6000);
})
"""

async def run(pw, device_name, viewport, ua, out):
    browser = await pw.chromium.launch(args=["--no-sandbox"])
    ctx = await browser.new_context(viewport=viewport, user_agent=ua,
                                    locale="fa-IR", device_scale_factor=1)
    for path in PAGES:
        page = await ctx.new_page()
        errs = []
        page.on("console", lambda m: errs.append(f"{m.type}: {m.text[:120]}") if m.type in ("error","warning") else None)
        page.on("pageerror", lambda e: errs.append(f"pageerror: {str(e)[:120]}"))
        url = BASE + path
        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
        except Exception as e:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            except Exception as e2:
                out.setdefault(device_name, {})[path] = {"error": str(e2)[:200]}
                await page.close(); continue
        await page.wait_for_timeout(1500)
        try:
            data = await page.evaluate(AUDIT_JS)
        except Exception as e:
            data = {"auditError": str(e)[:200]}
        try:
            perf = await page.evaluate(PERF_JS)
        except Exception as e:
            perf = {"perfError": str(e)[:200]}
        data["perf"] = perf
        data["consoleIssues"] = errs[:15]
        data["consoleIssueCount"] = len(errs)
        out.setdefault(device_name, {})[path] = data
        safe = path.strip("/").replace("/", "_") or "home"
        try:
            await page.screenshot(path=f"shots/{device_name}_{safe}.png", full_page=False)
        except Exception: pass
        await page.close()
        print(f"  {device_name} {path} done", flush=True)
    await browser.close()

async def main():
    import os
    os.makedirs("shots", exist_ok=True)
    out = {}
    async with async_playwright() as pw:
        print("== mobile ==", flush=True)
        await run(pw, "mobile", {"width":375,"height":812},
                  "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1", out)
        print("== desktop ==", flush=True)
        await run(pw, "desktop", {"width":1440,"height":900},
                  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36", out)
    with open("audit-live.json","w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("WROTE audit-live.json")

asyncio.run(main())

"""
A/B the old and new stylesheet against real captured production HTML.

The app cannot be rendered locally (no database on this box), but the audit
folder holds the exact HTML production served for four pages. Serving those
bytes with the OLD app.css and then the NEW one isolates the stylesheet change
from everything else — same markup, same images, one variable.
"""
import asyncio, json, sys, http.server, threading, functools, pathlib, shutil, os

RAW = pathlib.Path('/home/mlops/mohammad/sepahanfelez-seo/sepahanfelez.ir-audit/raw')
SRC = pathlib.Path('/home/mlops/mohammad/ahanamn-src')
ROOT = pathlib.Path('/tmp/claude-1000/-home-mlops-mohammad/20686d25-d565-4c01-922c-94f62018aaae/scratchpad/abroot')
PAGES = ['home.html', 'cat.html', 'about.html', 'contact.html', 'price.html', 'blog.html']

MEASURE = r"""
() => {
  const px = s => parseFloat(s) || 0;
  const out = {};
  out.htmlFontSize = getComputedStyle(document.documentElement).fontSize;
  out.bodyFontSize = getComputedStyle(document.body).fontSize;

  const vw = document.documentElement.clientWidth;
  out.scrollWidth = document.documentElement.scrollWidth;
  out.horizontalOverflow = document.documentElement.scrollWidth > vw + 1;
  let over = 0;
  document.querySelectorAll('body *').forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width > 0 && (r.right > vw + 2 || r.left < -2)) over++;
  });
  out.overflowing = over;

  let small = 0, sizes = {};
  document.querySelectorAll('p,span,li,td,th,a,label,small,div,h1,h2,h3,h4,h5,h6,button').forEach(el => {
    let hasText = false;
    el.childNodes.forEach(n => { if (n.nodeType === 3 && n.textContent.trim().length > 3) hasText = true; });
    if (!hasText) return;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return;
    const fs = px(cs.fontSize);
    if (fs > 0 && fs < 14) { small++; const k = fs.toFixed(1); sizes[k]=(sizes[k]||0)+1; }
  });
  out.smallText = small; out.smallBySize = sizes;

  let tt = 0, tot = 0;
  document.querySelectorAll('a,button,input:not([type=hidden]),select,textarea').forEach(el => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return;
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return;
    tot++;
    if (r.width < 44 || r.height < 44) tt++;
  });
  out.smallTaps = tt; out.totalTaps = tot;

  // contrast
  function lum(c){const[r,g,b]=c.map(v=>{v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4);});return .2126*r+.7152*g+.0722*b;}
  function pr(s){const m=s.match(/rgba?\(([^)]+)\)/);if(!m)return null;const p=m[1].split(',').map(parseFloat);return{rgb:[p[0],p[1],p[2]],a:p.length>3?p[3]:1};}
  function bgOf(el){let e=el;while(e&&e!==document.documentElement){const c=pr(getComputedStyle(e).backgroundColor);if(c&&c.a>0.5)return c.rgb;e=e.parentElement;}return[255,255,255];}
  let low=0; const seen=new Set(); const samples=[];
  document.querySelectorAll('p,span,li,td,th,a,label,small,h1,h2,h3,h4,h5,h6,button').forEach(el=>{
    let ht=false; el.childNodes.forEach(n=>{if(n.nodeType===3&&n.textContent.trim().length>2)ht=true;});
    if(!ht)return;
    const cs=getComputedStyle(el); if(cs.display==='none'||cs.visibility==='hidden'||cs.opacity==='0')return;
    const fg=pr(cs.color); if(!fg)return; const bg=bgOf(el);
    const ratio=(Math.max(lum(fg.rgb),lum(bg))+.05)/(Math.min(lum(fg.rgb),lum(bg))+.05);
    const fs=px(cs.fontSize), bold=parseInt(cs.fontWeight)>=700;
    const need=(fs>=24||(fs>=18.66&&bold))?3:4.5;
    if(ratio<need){const k=cs.color+'|'+bg.join(',')+'|'+Math.round(fs);if(seen.has(k))return;seen.add(k);low++;
      samples.push({fg:cs.color,bg:'rgb('+bg.join(',')+')',r:Math.round(ratio*100)/100,fs:Math.round(fs*10)/10,t:el.textContent.trim().slice(0,24)});}
  });
  out.lowContrast=low; out.lowContrastSample=samples.slice(0,8);
  return out;
}
"""


def serve(directory, port):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


async def run(variant, port, results):
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        b = await pw.chromium.launch(args=['--no-sandbox'])
        for dev, vp in [('mobile', {'width': 375, 'height': 812}),
                        ('desktop', {'width': 1440, 'height': 900})]:
            ctx = await b.new_context(viewport=vp, locale='fa-IR')
            for page_name in PAGES:
                pg = await ctx.new_page()
                await pg.goto(f'http://127.0.0.1:{port}/{page_name}', wait_until='load', timeout=30000)
                await pg.wait_for_timeout(800)
                results.setdefault(variant, {}).setdefault(dev, {})[page_name] = await pg.evaluate(MEASURE)
                if page_name == 'home.html':
                    await pg.screenshot(path=f'ab_{variant}_{dev}.png')
                await pg.close()
            await ctx.close()
        await b.close()


async def main():
    if ROOT.exists():
        shutil.rmtree(ROOT)
    (ROOT / 'files' / 'css').mkdir(parents=True)
    (ROOT / 'files' / 'js').mkdir(parents=True)
    for f in PAGES:
        # The captured pages link the stylesheet absolutely
        # (https://sepahanfelez.ir/files/css/app.css), so serving them as-is
        # would load PRODUCTION css in both arms and measure nothing. Point it
        # at the local copy; leave the images pointing at the live host, which
        # keeps the layout honest.
        html = (RAW / f).read_text(encoding='utf-8', errors='replace')
        html = html.replace('https://sepahanfelez.ir/files/css/app.css', '/files/css/app.css')
        html = html.replace('http://sepahanfelez.ir/files/css/app.css', '/files/css/app.css')
        (ROOT / f).write_text(html, encoding='utf-8')
    # fonts + brand assets the stylesheet reaches for
    for sub in ('assets',):
        if (SRC / 'public_html' / sub).exists():
            shutil.copytree(SRC / 'public_html' / sub, ROOT / sub, dirs_exist_ok=True)

    results = {}
    httpd = serve(ROOT, 8731)

    # NEW css is what is currently built
    shutil.copy(SRC / 'public_html/files/css/app.css', ROOT / 'files/css/app.css')
    await run('after', 8731, results)

    # OLD css: rebuild from git HEAD
    old = pathlib.Path(sys.argv[1])
    shutil.copy(old, ROOT / 'files/css/app.css')
    await run('before', 8731, results)

    httpd.shutdown()
    json.dump(results, open('ab-results.json', 'w'), ensure_ascii=False, indent=1)

    print(f"{'':<26}{'BEFORE':>22}{'AFTER':>22}")
    for dev in ('mobile', 'desktop'):
        print(f"\n=== {dev} ===")
        for page in PAGES:
            b = results['before'][dev][page]
            a = results['after'][dev][page]
            print(f"  {page}")
            for k, label in [('bodyFontSize', 'body font-size'), ('htmlFontSize', 'root font-size'),
                             ('smallText', 'text < 14px'), ('smallTaps', 'tap targets < 44px'),
                             ('overflowing', 'elements past viewport'), ('scrollWidth', 'scrollWidth'),
                             ('lowContrast', 'low-contrast pairs')]:
                bv, av = b.get(k), a.get(k)
                flag = ''
                if isinstance(bv, (int, float)) and isinstance(av, (int, float)):
                    if av < bv: flag = '  ✓'
                    elif av > bv: flag = '  ↑'
                print(f"    {label:<24}{str(bv):>20}{str(av):>20}{flag}")

asyncio.run(main())

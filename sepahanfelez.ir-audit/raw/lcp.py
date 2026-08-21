from playwright.sync_api import sync_playwright
import json
with sync_playwright() as p:
    b=p.chromium.launch()
    ctx=b.new_context(viewport={"width":390,"height":844},is_mobile=True,has_touch=True)
    pg=ctx.new_page()
    heavy=[]
    def on_resp(r):
        try:
            cl=int(r.headers.get("content-length") or 0)
            if cl>60000: heavy.append((cl,r.url[:100],r.headers.get("content-type","")))
        except: pass
    pg.on("response",on_resp)
    pg.goto("https://sepahanfelez.ir/",wait_until="load",timeout=90000)
    pg.wait_for_timeout(3000)
    lcp=pg.evaluate("""()=>new Promise(r=>{let el=null,v=0;new PerformanceObserver(l=>{for(const e of l.getEntries()){v=e.startTime;el=e.element}}).observe({type:'largest-contentful-paint',buffered:true});setTimeout(()=>r({t:Math.round(v),tag:el?el.tagName:null,src:el?(el.currentSrc||el.src||el.className):null}),1500)})""")
    print("LCP element:",json.dumps(lcp,ensure_ascii=False))
    print("\nHEAVY RESOURCES (>60KB):")
    for cl,u,ct in sorted(heavy,reverse=True)[:15]: print(f"  {cl/1024:7.0f} KB  {ct:25s} {u}")
    print("\nRender-blocking / total scripts:")
    print(pg.evaluate("""()=>({blockingScripts:[...document.querySelectorAll('script[src]')].filter(s=>!s.async&&!s.defer).map(s=>s.src.slice(0,80)),stylesheets:[...document.querySelectorAll('link[rel=stylesheet]')].map(l=>l.href.slice(0,80))})"""))
    ctx.close(); b.close()

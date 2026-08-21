from playwright.sync_api import sync_playwright
import json
res={}
with sync_playwright() as p:
    b=p.chromium.launch()
    for name,vp,mobile in [("mobile",{"width":390,"height":844},True),("desktop",{"width":1920,"height":1080},False)]:
        ctx=b.new_context(viewport=vp,is_mobile=mobile,has_touch=mobile,
            user_agent="Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36" if mobile else None)
        pg=ctx.new_page()
        bytes_total={"n":0}
        pg.on("response", lambda r: bytes_total.__setitem__("n", bytes_total["n"]+int(r.headers.get("content-length") or 0)))
        pg.goto("https://sepahanfelez.ir/",wait_until="load",timeout=90000)
        pg.wait_for_timeout(4000)
        m=pg.evaluate("""()=>{
          const nav=performance.getEntriesByType('navigation')[0]||{};
          const paints={};performance.getEntriesByType('paint').forEach(p=>paints[p.name]=Math.round(p.startTime));
          const rs=performance.getEntriesByType('resource');
          const by={};rs.forEach(r=>{by[r.initiatorType]=(by[r.initiatorType]||0)+1});
          return {ttfb:Math.round(nav.responseStart||0),domContentLoaded:Math.round(nav.domContentLoadedEventEnd||0),
            load:Math.round(nav.loadEventEnd||0),paints,requests:rs.length,byType:by,
            transferKB:Math.round(rs.reduce((a,r)=>a+(r.transferSize||0),0)/1024),
            docScrollW:document.documentElement.scrollWidth,innerW:window.innerWidth,
            imgs:document.images.length,
            offscreen:[...document.querySelectorAll('*')].filter(e=>e.getBoundingClientRect().right>window.innerWidth+2).length};
        }""")
        # LCP
        lcp=pg.evaluate("""()=>new Promise(r=>{let v=0;new PerformanceObserver(l=>{for(const e of l.getEntries())v=e.startTime}).observe({type:'largest-contentful-paint',buffered:true});setTimeout(()=>r(Math.round(v)),1200)})""")
        m["LCP_lab_ms"]=lcp
        cls=pg.evaluate("""()=>new Promise(r=>{let v=0;new PerformanceObserver(l=>{for(const e of l.getEntries())if(!e.hadRecentInput)v+=e.value}).observe({type:'layout-shift',buffered:true});setTimeout(()=>r(Math.round(v*1000)/1000),1200)})""")
        m["CLS_lab"]=cls
        res[name]=m
        ctx.close()
    b.close()
print(json.dumps(res,indent=1,ensure_ascii=False))

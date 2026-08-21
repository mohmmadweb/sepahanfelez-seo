import requests, re, time, json, collections, sys
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, unquote

ROOT="https://sepahanfelez.ir"
H={"User-Agent":"Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"}
seen={ROOT+"/"}; queue=[ROOT+"/"]; pages={}
MAX=int(sys.argv[1]) if len(sys.argv)>1 else 120
sess=requests.Session(); sess.headers.update(H)
while queue and len(pages)<MAX:
    u=queue.pop(0)
    try:
        r=sess.get(u,timeout=20,allow_redirects=True)
    except Exception as e:
        pages[u]={"err":type(e).__name__}; continue
    ct=r.headers.get("Content-Type","")
    rec={"status":r.status_code,"final":r.url,"len":len(r.content),"ct":ct.split(";")[0],
         "ttfb":round(r.elapsed.total_seconds(),2)}
    if r.status_code==200 and "html" in ct:
        s=BeautifulSoup(r.text,"lxml")
        t=s.find("title"); rec["title"]=t.get_text(strip=True) if t else None
        md=s.find("meta",attrs={"name":"description"}); rec["desc"]=md.get("content","") if md else None
        cn=s.find("link",rel="canonical"); rec["canonical"]=cn.get("href") if cn else "MISSING"
        rb=s.find("meta",attrs={"name":"robots"}); rec["robots"]=rb.get("content") if rb else None
        rec["h1"]=[x.get_text(" ",strip=True)[:70] for x in s.find_all("h1")]
        rec["ldjson"]=len(s.find_all("script",type="application/ld+json"))
        rec["words"]=len(s.get_text(" ",strip=True).split())
        rec["imgs"]=len(s.find_all("img"))
        rec["noalt"]=len([i for i in s.find_all("img") if not (i.get("alt") or "").strip()])
        ext=set()
        for a in s.find_all("a",href=True):
            href=a["href"].strip()
            if href.startswith(("mailto:","tel:","javascript:")): continue
            l=urljoin(u,href).split("#")[0].rstrip("/")
            if not l: continue
            p=urlparse(l)
            if p.netloc.endswith("sepahanfelez.ir"):
                if re.search(r'\.(jpg|jpeg|png|pdf|webp|zip|css|js|svg|ico)$',l,re.I): continue
                if l not in seen and l+"/" not in seen:
                    seen.add(l); queue.append(l)
            elif p.scheme.startswith("http"):
                ext.add(p.netloc)
        rec["ext"]=sorted(ext)
    pages[u]=rec
    json.dump(pages,open("/home/mlops/mohammad/sepahanfelez-seo/sepahanfelez.ir-audit/raw/crawl.json","w"),ensure_ascii=False,indent=1)
    time.sleep(0.2)
print("DONE crawled",len(pages),"discovered",len(seen))

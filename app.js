/* رصد سئو سپاهان فلز — vanilla JS, no dependencies. All third-party strings go through textContent. */
(function () {
  "use strict";
  var D = window.SF || {};
  var HOST = "https://sepahanfelez.ir";

  // ------------------------------------------------------------------ helpers
  function el(tag, attrs) {
    var n = document.createElement(tag);
    if (attrs) for (var k in attrs) {
      var v = attrs[k];
      if (v == null || v === false) continue;
      if (k === "class") n.className = v;
      else if (k === "text") n.textContent = v;
      else if (k === "html") n.innerHTML = v; // only ever used with our own static markup
      else if (k.slice(0, 2) === "on") n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? "" : v);
    }
    for (var i = 2; i < arguments.length; i++) add(n, arguments[i]);
    return n;
  }
  function add(n, c) {
    if (c == null || c === false) return;
    if (Array.isArray(c)) { c.forEach(function (x) { add(n, x); }); return; }
    n.appendChild(typeof c === "object" ? c : document.createTextNode(String(c)));
  }
  var FA = "۰۱۲۳۴۵۶۷۸۹";
  function fd(s) { return String(s).replace(/[0-9]/g, function (d) { return FA[d]; }); }
  function fn(n, dec) {
    if (n == null || n === "" || isNaN(n)) return "—";
    return Number(n).toLocaleString("fa-IR", { maximumFractionDigits: dec == null ? 0 : dec });
  }
  function pct(a, b) { return b ? Math.round((100 * a) / b) : 0; }
  function short(u) {
    if (!u) return "";
    try { u = decodeURI(u); } catch (e) {}
    return u.replace(/^https?:\/\/(www\.)?sepahanfelez\.ir/, "") || "/";
  }
  function norm(s) {
    return (s || "").replace(/ي/g, "ی").replace(/ك/g, "ک").replace(/‌/g, " ").replace(/[-_]/g, " ")
      .replace(/[۰-۹]/g, function (d) { return FA.indexOf(d); }).replace(/\s+/g, " ").trim().toLowerCase();
  }
  function link(u, label) {
    var full = u && u.indexOf("http") === 0 ? u : HOST + (u || "/");
    return el("a", { href: full, target: "_blank", rel: "noopener", class: "url" }, label || short(u));
  }
  function sec(title, lead) {
    return [el("h2", { class: "sec", text: title }), lead ? el("p", { class: "lead", text: lead }) : null];
  }
  function card(title, sub, body, act) {
    return el("section", { class: "card" },
      el("div", { class: "card-h" }, el("h3", { text: title }), sub ? el("span", { class: "sub", text: sub }) : null,
        act ? el("span", { class: "act" }, act) : null), body);
  }
  function tile(label, value, foot, opts) {
    opts = opts || {};
    return el("div", { class: "card tile" + (opts.pending ? " pending" : "") },
      el("div", { class: "lbl", text: label }),
      el("div", { class: "val" }, value, opts.unit ? el("small", { text: opts.unit }) : null),
      foot ? el("div", { class: "foot" }, foot) : null);
  }
  var SEV = { critical: "بحرانی", high: "مهم", medium: "متوسط", low: "جزئی" };
  function sevChip(s) { return el("span", { class: "sev " + s, text: SEV[s] || s }); }
  var ST = { ok: "وصل", blocked: "مسدود", pending: "در انتظار", stale: "داده‌ی قدیمی", waiting: "منتظر شما",
    todo: "در صف", done: "انجام شد", ready: "آماده", partial: "نیمه‌آماده" };
  function stChip(s) { return el("span", { class: "st " + s, text: ST[s] || s }); }
  function empty(text) { return el("div", { class: "empty", text: text }); }
  var TYPE_FA = {};
  ((D.site || {}).page_types || []).forEach(function (t) { TYPE_FA[t.type] = t.label_fa; });
  TYPE_FA.other = "سایر";
  function jd(iso) { // gregorian ISO → jalali label using Intl
    if (!iso) return "—";
    try { return new Date(iso.length <= 10 ? iso + "T12:00:00" : iso).toLocaleDateString("fa-IR-u-ca-persian", { month: "long", day: "numeric" }); }
    catch (e) { return iso; }
  }

  // ------------------------------------------------------------------ data indexes
  var crawl = D.crawl || { pages: [] };
  var pages = (crawl.pages || []).filter(function (p) { return p.status === 200 && !p.redirect_to; });
  var byPath = {};
  (crawl.pages || []).forEach(function (p) { byPath[short(p.url)] = p; });
  var issues = (D.issues && D.issues.issues) || [];
  var issuesByPath = {};
  issues.forEach(function (i) { (i.urls || []).forEach(function (u) { (issuesByPath[u] = issuesByPath[u] || []).push(i); }); });
  var gsc = D.gsc || {}, gscOk = gsc.status === "ok";
  var ga4 = D.ga4 || {}, ga4Ok = ga4.status === "ok";
  var psi = D.psi || {}, psiOk = psi.status === "ok";
  var gscQ = {}, gscP = {};
  if (gscOk) {
    (gsc.queries || []).forEach(function (q) { gscQ[norm(q.query)] = q; });
    (gsc.pages || []).forEach(function (p) { gscP[short(p.page)] = p; });
  }
  var KW = D.keywords || {};
  var products = KW.products || [];
  var comp = D.competitors || {};
  var compCfg = (comp.config && comp.config.competitors) || [];
  var compWatch = {};
  ((comp.watch && comp.watch.competitors) || []).forEach(function (c) { compWatch[c.id] = c; });
  var hist = D.history || [];
  var brandTerms = ((D.site || {}).brand_terms || []).map(norm);
  function isBrand(q) { q = norm(q); return brandTerms.some(function (b) { return q.indexOf(b) >= 0; }); }

  // ------------------------------------------------------------------ table with sort + filter
  function table(cols, rows, opts) {
    opts = opts || {};
    var state = { key: opts.sortKey || null, dir: opts.sortDir || "desc", limit: opts.limit || 60 };
    var wrap = el("div");
    function render() {
      wrap.textContent = "";
      var data = rows.slice();
      if (state.key) {
        var col = cols.filter(function (c) { return c.key === state.key; })[0];
        var val = col.sort || function (r) { return r[col.key]; };
        data.sort(function (a, b) {
          var x = val(a), y = val(b);
          if (x == null) return 1; if (y == null) return -1;
          var r = typeof x === "number" ? x - y : String(x).localeCompare(String(y), "fa");
          return state.dir === "asc" ? r : -r;
        });
      }
      var tb = el("tbody");
      data.slice(0, state.limit).forEach(function (r) {
        var tr = el("tr", opts.detail ? { class: "clk", tabindex: "0" } : null);
        cols.forEach(function (c) {
          var v = c.render ? c.render(r) : r[c.key];
          tr.appendChild(el("td", { class: c.num ? "n" : null }, v == null ? "—" : v));
        });
        tb.appendChild(tr);
        if (opts.detail) {
          var open = null;
          var toggle = function () {
            if (open) { open.remove(); open = null; return; }
            open = el("tr", { class: "detail" }, el("td", { colspan: String(cols.length) }, opts.detail(r)));
            tr.after(open);
          };
          tr.addEventListener("click", toggle);
          tr.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } });
        }
      });
      var thr = el("tr");
      cols.forEach(function (c) {
        var th = el("th", { class: (c.num ? "n " : "") + (c.nosort ? "" : "sort"), text: c.label, scope: "col" });
        if (!c.nosort) {
          if (state.key === c.key) th.setAttribute("data-dir", state.dir);
          th.addEventListener("click", function () {
            state.dir = state.key === c.key && state.dir === "desc" ? "asc" : "desc";
            state.key = c.key; render();
          });
        }
        thr.appendChild(th);
      });
      wrap.appendChild(el("div", { class: "tbl-wrap" }, el("table", null, el("thead", null, thr), tb)));
      if (!data.length) wrap.appendChild(el("div", { class: "empty mt", text: opts.emptyText || "موردی نیست." }));
      if (data.length > state.limit) {
        wrap.appendChild(el("div", { class: "more" }, el("button", {
          class: "theme-btn", style: "color:var(--ink);border-color:var(--border-2)",
          onclick: function () { state.limit += 100; render(); }
        }, "نمایش " + fn(Math.min(100, data.length - state.limit)) + " ردیف دیگر از " + fn(data.length))));
      }
    }
    render();
    return wrap;
  }

  // ------------------------------------------------------------------ charts (SVG, crosshair tooltip)
  var SERIES = ["--s1", "--s2", "--s3", "--s4", "--s5", "--s6", "--s7", "--s8"];
  function cssv(v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); }
  function niceMax(v) {
    if (v <= 0) return 1;
    var p = Math.pow(10, Math.floor(Math.log10(v))), m = v / p;
    return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 5 ? 5 : 10) * p;
  }
  function lineChart(opt) {
    // opt: {x:[labels], series:[{name, values, color}], height, yfmt, minZero}
    var W = 640, H = opt.height || 220, L = 44, R = 12, T = 10, B = 28;
    var box = el("div", { class: "chart" });
    var n = opt.x.length;
    if (!n) return empty("هنوز داده‌ای نیست.");
    if (opt.series.length > 1) {
      box.appendChild(el("div", { class: "legend" }, opt.series.map(function (s, i) {
        return el("span", null, el("i", { style: "background:var(" + (s.color || SERIES[i]) + ")" }), s.name);
      })));
    }
    var all = [];
    opt.series.forEach(function (s) { s.values.forEach(function (v) { if (v != null) all.push(v); }); });
    var mx = niceMax(Math.max.apply(null, all.concat([opt.minMax || 0])) || 1);
    var mn = opt.minZero === false ? Math.min.apply(null, all) : 0;
    var invert = !!opt.invert; // for "position" (lower is better)
    function X(i) { return n === 1 ? (L + (W - R)) / 2 : W - R - (i * (W - L - R)) / (n - 1); } // RTL: first date on the right
    function Y(v) { var t = (v - mn) / (mx - mn || 1); return invert ? T + t * (H - T - B) : H - B - t * (H - T - B); }
    var ns = "http://www.w3.org/2000/svg";
    function s(tag, a) { var e = document.createElementNS(ns, tag); for (var k in a) e.setAttribute(k, a[k]); return e; }
    var svg = s("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": opt.label || "" });
    for (var g = 0; g <= 4; g++) {
      var v = mn + ((mx - mn) * g) / 4, y = Y(v);
      svg.appendChild(s("line", { x1: L, x2: W - R, y1: y, y2: y, class: g === 0 && !invert ? "axis-l" : "grid-l" }));
      var tx = s("text", { x: L - 6, y: y + 4, "text-anchor": "end" });
      tx.textContent = opt.yfmt ? opt.yfmt(v) : fn(v, v < 10 ? 1 : 0);
      svg.appendChild(tx);
    }
    var step = Math.max(1, Math.ceil(n / 6));
    for (var i = 0; i < n; i += step) {
      var t = s("text", { x: X(i), y: H - 8, "text-anchor": "middle" }); t.textContent = opt.x[i]; svg.appendChild(t);
    }
    opt.series.forEach(function (se, si) {
      var col = "var(" + (se.color || SERIES[si]) + ")", d = "", pen = false;
      se.values.forEach(function (v, i) {
        if (v == null) { pen = false; return; }
        d += (pen ? "L" : "M") + X(i).toFixed(1) + " " + Y(v).toFixed(1); pen = true;
      });
      if (opt.area && opt.series.length === 1) {
        var first = se.values.findIndex(function (v) { return v != null; });
        if (first >= 0) svg.appendChild(s("path", { d: d + "L" + X(n - 1) + " " + Y(mn) + "L" + X(first) + " " + Y(mn) + "Z", fill: col, "fill-opacity": ".10", stroke: "none" }));
      }
      svg.appendChild(s("path", { d: d, class: "line", stroke: col }));
      // end dot + selective direct label on the latest value
      var last = -1; se.values.forEach(function (v, i) { if (v != null) last = i; });
      if (last >= 0) {
        svg.appendChild(s("circle", { cx: X(last), cy: Y(se.values[last]), r: 4, fill: col, class: "dot" }));
        if (n === 1 || opt.series.length === 1) {
          var lt = s("text", { x: X(last) - 8, y: Y(se.values[last]) - 8, "text-anchor": "end", style: "fill:var(--ink);font-weight:700" });
          lt.textContent = opt.yfmt ? opt.yfmt(se.values[last]) : fn(se.values[last], 1); svg.appendChild(lt);
        }
      }
    });
    var xh = s("line", { y1: T, y2: H - B, class: "xh", style: "display:none" });
    svg.appendChild(xh);
    box.appendChild(svg);
    var tip = el("div", { class: "tip", role: "status" });
    box.appendChild(tip);
    function show(clientX) {
      var r = svg.getBoundingClientRect(), px = ((clientX - r.left) / r.width) * W, best = 0, bd = 1e9;
      for (var i = 0; i < n; i++) { var dd = Math.abs(X(i) - px); if (dd < bd) { bd = dd; best = i; } }
      xh.setAttribute("x1", X(best)); xh.setAttribute("x2", X(best)); xh.style.display = "";
      tip.textContent = "";
      tip.appendChild(el("div", { class: "muted", text: opt.x[best] }));
      opt.series.forEach(function (se, si) {
        var v = se.values[best];
        tip.appendChild(el("div", null, el("span", { class: "key", style: "background:var(" + (se.color || SERIES[si]) + ")" }),
          el("span", { class: "tv", text: v == null ? "—" : (opt.yfmt ? opt.yfmt(v) : fn(v, 1)) }), " ", el("span", { class: "muted", text: se.name })));
      });
      tip.style.display = "block";
      var left = (X(best) / W) * r.width;
      tip.style.left = Math.max(0, Math.min(r.width - tip.offsetWidth, left - tip.offsetWidth / 2)) + "px";
      tip.style.top = "0px";
    }
    svg.addEventListener("pointermove", function (e) { show(e.clientX); });
    svg.addEventListener("pointerleave", function () { tip.style.display = "none"; xh.style.display = "none"; });
    return box;
  }
  function spark(values, w, h) {
    w = w || 90; h = h || 22;
    var v = values.filter(function (x) { return x != null; });
    var svgns = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(svgns, "svg");
    svg.setAttribute("width", w); svg.setAttribute("height", h); svg.setAttribute("class", "spark");
    svg.setAttribute("aria-hidden", "true");
    if (v.length < 2) return svg;
    var mx = Math.max.apply(null, v), mn = Math.min.apply(null, v);
    var d = v.map(function (x, i) {
      var X = w - (i * (w - 4)) / (v.length - 1) - 2, Y = h - 3 - ((x - mn) / ((mx - mn) || 1)) * (h - 6);
      return (i ? "L" : "M") + X.toFixed(1) + " " + Y.toFixed(1);
    }).join("");
    var p = document.createElementNS(svgns, "path");
    p.setAttribute("d", d); p.setAttribute("fill", "none"); p.setAttribute("stroke", "var(--s1)"); p.setAttribute("stroke-width", "2");
    svg.appendChild(p);
    return svg;
  }
  function bars(items, fmt) { // [{label, value, sub}]
    var mx = Math.max.apply(null, items.map(function (i) { return i.value; }).concat([1]));
    return el("div", { class: "bars" }, items.map(function (i) {
      return el("div", { class: "b", title: i.label + ": " + (fmt ? fmt(i.value) : fn(i.value)) },
        el("span", { class: "clip", text: i.label }),
        el("span", { class: "track" }, el("i", { style: "width:" + Math.max(1, (100 * i.value) / mx) + "%" + (i.color ? ";background:var(" + i.color + ")" : "") })),
        el("span", { class: "num ink2", text: fmt ? fmt(i.value) : fn(i.value) }));
    }));
  }

  // ------------------------------------------------------------------ views
  function priorityRows() {
    var list = products.length ? products : ((D.content_plan || {}).priority || []).map(function (p) {
      return { id: p.rank, name_fa: p.name, target_url: null };
    });
    return list.map(function (p) {
      var pg = p.target_url ? byPath[short(p.target_url)] : null;
      var g = pg ? gscP[short(pg.url)] : null;
      var q = p.primary ? gscQ[norm(p.primary)] : null;
      var competitors = [];
      compCfg.forEach(function (c) { if ((c.owner_products || []).indexOf(p.id) >= 0) competitors.push(c.name_fa || c.domain); });
      var inTitle = pg && p.primary ? norm(pg.title).indexOf(norm(p.primary)) >= 0 || norm(p.primary).split(" ").every(function (w) { return norm(pg.title).indexOf(w) >= 0; }) : null;
      return { id: p.id, name: p.name_fa, url: p.target_url, page: pg, primary: p.primary, secondary: p.secondary || [],
        words: pg ? pg.words : null, inTitle: inTitle, gscPos: q ? q.position : null, gscImpr: g ? g.impressions : null,
        gscClicks: g ? g.clicks : null, competitors: competitors, ideas: p.article_ideas || [] };
    });
  }

  function viewOverview() {
    var v = [];
    var health = (D.issues || {}).health;
    var prev = hist.length > 1 ? hist[hist.length - 2].health : null;
    var sevCount = { critical: 0, high: 0, medium: 0, low: 0 };
    issues.forEach(function (i) { sevCount[i.severity]++; });
    var last = hist[hist.length - 1] || {};
    var articles = pages.filter(function (p) { return p.type === "article"; }).length;
    var prods = pages.filter(function (p) { return p.type === "product"; }).length;

    v.push(sec("نمای کلی", "وضعیت امروز سایت sepahanfelez.ir: سلامت فنی، کلمات کلیدی ۱۳ محصول اولویت‌دار، رقبا و برنامه‌ی انتشار. این صفحه هر روز صبح خودکار به‌روز می‌شود."));
    v.push(el("div", { class: "grid g2" },
      el("section", { class: "card" },
        el("div", { class: "card-h" }, el("h3", { text: "امتیاز سلامت سئو" }), el("span", { class: "sub", text: "از ۱۰۰ — بر پایه‌ی مشکلات خزش امروز" })),
        el("div", { class: "hero" },
          el("div", { class: "big" }, health == null ? "—" : fn(health), el("small", { text: " / ۱۰۰" })),
          el("div", { style: "flex:1;min-width:200px" },
            el("div", { class: "meter", role: "meter", "aria-valuenow": health || 0, "aria-valuemin": "0", "aria-valuemax": "100" },
              el("i", { style: "width:" + (health || 0) + "%" })),
            el("div", { class: "small ink2 mt" },
              prev == null ? "روند از اجرای فردا محاسبه می‌شود." :
                el("span", { class: health >= prev ? "delta-up" : "delta-down" }, (health >= prev ? "▲ " : "▼ ") + fn(Math.abs(health - prev)) + " نسبت به دیروز")),
            el("div", { class: "mt", style: "display:flex;gap:6px;flex-wrap:wrap" },
              ["critical", "high", "medium", "low"].map(function (s) { return el("span", { class: "sev " + s }, SEV[s] + " " + fn(sevCount[s])); }))))),
      el("div", { class: "grid g2 tiles2" },
        tile("صفحات زنده‌ی قابل ایندکس", fn(pages.length), "نقشه‌ی سایت: " + fn((crawl.sitemap || {}).count) + " نشانی"),
        tile("مقاله‌ها / صفحات محصول", fn(articles) + " / " + fn(prods), "۸۳ نوع کالا، فقط " + fn(prods) + " صفحه"),
        tile("عمر جدیدترین قیمت", last.price_age_days == null ? "—" : fn(last.price_age_days), "سرتیتر /price «لحظه‌ای» است", { unit: "روز" }),
        gscOk ? tile("کلیک گوگل (۲۸ روز)", fn(last.gsc && last.gsc.clicks), "ایمپرشن " + fn(last.gsc && last.gsc.impressions) + " · رتبه‌ی میانگین " + fn(last.gsc && last.gsc.position, 1))
          : tile("کلیک گوگل (۲۸ روز)", "در انتظار اتصال سرچ کنسول", el("a", { href: "#integrations", text: "راهنمای اتصال" }), { pending: true }))));

    var top = issues.filter(function (i) { return i.severity === "critical" || i.severity === "high"; }).slice(0, 6);
    v.push(el("div", { class: "grid g2 mt" },
      card("مهم‌ترین کارها", fn(issues.length) + " مشکل باز", el("div", null, top.map(issueCard)), el("a", { href: "#issues", text: "همه‌ی مشکلات ←" })),
      card("رقبا — تغییرات امروز", "صفحات تازه در نقشه‌ی سایت رقبا", competitorToday(), el("a", { href: "#competitors", text: "رصد کامل ←" }))));

    var rows = priorityRows();
    v.push(el("div", { class: "mt" }, card("۱۳ محصول اولویت‌دار (لیست دست‌نویس کارفرما)", "صفحه‌ی هدف، کلمه‌ی کلیدی اصلی و رقبای نام‌برده",
      table([
        { key: "id", label: "#", num: true },
        { key: "name", label: "محصول" },
        { key: "url", label: "صفحه‌ی هدف", render: function (r) { return r.url ? link(r.url) : el("span", { class: "no", text: "ندارد" }); }, sort: function (r) { return r.url || ""; } },
        { key: "primary", label: "کلمه‌ی کلیدی اصلی", render: function (r) { return r.primary || "—"; } },
        { key: "inTitle", label: "در عنوان؟", render: function (r) { return r.inTitle == null ? "—" : el("span", { class: r.inTitle ? "yes" : "no", text: r.inTitle ? "✓ بله" : "✗ نه" }); }, sort: function (r) { return r.inTitle ? 1 : 0; } },
        { key: "words", label: "کلمات صفحه", num: true, render: function (r) { return fn(r.words); } },
        { key: "gscPos", label: "رتبه (GSC)", num: true, render: function (r) { return gscOk ? fn(r.gscPos, 1) : "…"; } },
        { key: "competitors", label: "رقبای نام‌برده", nosort: true, render: function (r) { return r.competitors.length ? r.competitors.map(function (c) { return el("span", { class: "tag", text: c }); }) : "—"; } }
      ], rows, { sortKey: "id", sortDir: "asc", limit: 20 }))));

    v.push(el("div", { class: "mt" }, card("سه روز کاری بعد", "از صف انتشار", upcoming(3), el("a", { href: "#content", text: "تقویم کامل ←" }))));
    return v;
  }

  function issueCard(i) {
    return el("div", { class: "issue" },
      el("div", { class: "row1" }, sevChip(i.severity), el("span", { class: "t", text: fd(i.title) }),
        el("span", { class: "tag", text: i.category }), i.status === "waiting-owner" ? stChip("waiting") : null),
      i.detail ? el("div", { class: "d", text: fd(i.detail) }) : null,
      i.fix ? el("div", { class: "fix" }, el("b", { text: "راه‌حل: " }), i.fix) : null,
      i.urls && i.urls.length ? el("details", null, el("summary", { text: fn(i.urls.length) + " نشانی" }),
        el("div", { class: "urls" }, i.urls.map(function (u) { return link(u); }))) : null);
  }

  function competitorToday() {
    var list = compCfg.map(function (c) { var w = compWatch[c.id] || {}; return { c: c, w: w }; })
      .filter(function (x) { return x.w.urls_total != null; });
    if (!list.length) return empty("اولین اجرای رصد رقبا هنوز انجام نشده.");
    var firstRun = list.every(function (x) { return x.w.first_run; });
    var changed = list.filter(function (x) { return (x.w.new_today || []).length; });
    return el("div", null,
      firstRun ? el("p", { class: "small ink2", text: "امروز خط مبنای نقشه‌ی سایت " + fn(list.length) + " رقیب ثبت شد؛ از فردا هر صفحه‌ی تازه‌ای که منتشر کنند همین‌جا می‌آید." }) : null,
      changed.length ? el("ul", { class: "small", style: "margin:0;padding-inline-start:18px" }, changed.map(function (x) {
        return el("li", null, el("b", { text: x.c.name_fa || x.c.domain }), " — " + fn(x.w.new_today.length) + " صفحه‌ی جدید: ",
          x.w.new_today.slice(0, 2).map(function (u) { return el("a", { href: u, target: "_blank", rel: "noopener", class: "url", text: short(u).slice(0, 60) + " " }); }));
      })) : (!firstRun ? el("p", { class: "small muted", text: "امروز هیچ رقیبی صفحه‌ی تازه‌ای منتشر نکرد." }) : null),
      bars(list.sort(function (a, b) { return b.w.urls_total - a.w.urls_total; }).slice(0, 8).map(function (x) {
        return { label: x.c.name_fa || x.c.domain, value: x.w.urls_total };
      }), function (n) { return fn(n) + " صفحه"; }));
  }

  function upcoming(nDays) {
    var items = ((D.content_plan || {}).items || []);
    if (!items.length) return empty("صف انتشار هنوز ساخته نشده.");
    var days = [];
    items.forEach(function (it) { if (days.indexOf(it.date) < 0) days.push(it.date); });
    var cal = {};
    ((D.calendar || {}).days || []).forEach(function (d) { cal[d.date] = d; });
    return el("div", { class: "grid g3" }, days.slice(0, nDays).map(function (d) {
      var c = cal[d] || {};
      return el("div", { class: "day" },
        el("h4", null, (c.weekday_fa || "") + " " + (c.jalali_label ? fd(c.jalali_label) : jd(d)),
          c.events && c.events.length ? el("span", { class: "ev", text: c.events.slice(0, 2).join("، ") }) : null),
        items.filter(function (it) { return it.date === d; }).sort(function (a, b) { return a.time.localeCompare(b.time); }).map(slotRow));
    }));
  }
  function mediaUrl(m) {
    if (!m) return null;
    if (/\.(mp4)$/.test(m)) return null;
    if (m.indexOf("/") > 0 && !/^(banner|toloue|videos)/.test(m)) return "https://sepahanfelez.lenzit.ir/assets/products/" + m.replace("photo-", "thumb-");
    return "https://sepahanfelez.lenzit.ir/" + m;
  }
  function slotRow(it) {
    var mu = mediaUrl(it.media);
    var kindFa = { story: "استوری", telegram: "کانال", article: "مقاله" }[it.kind] || it.kind;
    return el("div", { class: "slot" },
      el("span", { class: "num ink2", text: fd(it.time) }),
      mu ? el("img", { src: mu, alt: it.product || "", loading: "lazy", width: "44", height: "44" })
        : el("span", { class: "ph", text: it.media && /mp4$/.test(it.media) ? "ویدئو" : "خبر" }),
      el("div", null, el("span", { class: "kind " + it.kind, text: kindFa }), " ", el("b", { text: it.type }),
        el("div", { class: "small ink2" }, it.title || it.product || "", it.occasion ? " — " + it.occasion : "")));
  }

  function viewIssues() {
    var v = sec("مشکلات", "هر چیزی که امروز جلوی رتبه یا فروش را می‌گیرد، به ترتیب اهمیت، با راه‌حل. مشکلاتی که از خزش خودکار پیدا نمی‌شوند (دسترسی، تصمیم‌های کارفرما) هم با برچسب «منتظر شما» آمده‌اند.");
    var state = { sev: "all", cat: "all", q: "" };
    var cats = []; issues.forEach(function (i) { if (cats.indexOf(i.category) < 0) cats.push(i.category); });
    var list = el("div");
    function render() {
      list.textContent = "";
      var f = issues.filter(function (i) {
        return (state.sev === "all" || i.severity === state.sev) && (state.cat === "all" || i.category === state.cat) &&
          (!state.q || norm(i.title + " " + i.detail + " " + (i.urls || []).join(" ")).indexOf(norm(state.q)) >= 0);
      });
      if (!f.length) list.appendChild(empty("با این فیلتر مشکلی نیست."));
      f.forEach(function (i) { list.appendChild(issueCard(i)); });
    }
    var seg = el("div", { class: "seg", role: "group", "aria-label": "شدت" }, ["all", "critical", "high", "medium", "low"].map(function (s) {
      var b = el("button", { type: "button", "aria-pressed": s === "all" ? "true" : "false", text: s === "all" ? "همه" : SEV[s] + " " + fn(issues.filter(function (i) { return i.severity === s; }).length) });
      b.addEventListener("click", function () { state.sev = s; seg.querySelectorAll("button").forEach(function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); }); render(); });
      return b;
    }));
    var sel = el("select", { "aria-label": "دسته", onchange: function (e) { state.cat = e.target.value; render(); } },
      el("option", { value: "all", text: "همه‌ی دسته‌ها" }), cats.map(function (c) { return el("option", { value: c, text: c }); }));
    var q = el("input", { type: "search", placeholder: "جستجو در مشکلات یا نشانی…", oninput: function (e) { state.q = e.target.value; render(); } });
    render();
    var log = D.issues_log || {};
    var resolved = Object.keys(log).filter(function (k) { return log[k].resolved; }).map(function (k) { return log[k]; });
    return [v, el("div", { class: "filters" }, seg, sel, q), list,
      resolved.length ? el("div", { class: "mt2" }, card("حل‌شده‌ها", fn(resolved.length) + " مورد",
        el("ul", { class: "small" }, resolved.map(function (r) { return el("li", null, fd(r.title), el("span", { class: "muted", text: " — حل شد " + jd(r.resolved) })); })))) : null];
  }

  function viewPages() {
    var v = sec("صفحات", "همه‌ی صفحاتی که خزنده امروز پیدا کرد (نقشه‌ی سایت + لینک‌های داخلی). روی هر ردیف بزنید تا جزئیات، کلمه‌ی کلیدی هدف و مشکلات همان صفحه باز شود.");
    var state = { type: "all", q: "", onlyIssues: false };
    var types = {}; (crawl.pages || []).forEach(function (p) { types[p.type] = (types[p.type] || 0) + 1; });
    var holder = el("div");
    var rows = (crawl.pages || []).map(function (p) {
      var sp = short(p.url), g = gscP[sp] || {};
      return { p: p, path: sp, type: p.type, title: p.title || "", tlen: (p.title || "").length, dlen: (p.description || "").length,
        words: p.words, inl: p.inlinks, sec: p.seconds, status: p.redirect_to ? 301 : p.status,
        issues: (issuesByPath[sp] || []).length, clicks: g.clicks, impr: g.impressions, pos: g.position, schema: (p.schema || []).length };
    });
    function render() {
      holder.textContent = "";
      var f = rows.filter(function (r) {
        return (state.type === "all" || r.type === state.type) && (!state.onlyIssues || r.issues) &&
          (!state.q || norm(r.path + " " + r.title).indexOf(norm(state.q)) >= 0);
      });
      var th = D.site.thresholds || {};
      holder.appendChild(table([
        { key: "path", label: "نشانی", render: function (r) { return el("span", { class: "url", text: r.path }); } },
        { key: "type", label: "نوع", render: function (r) { return TYPE_FA[r.type] || r.type; } },
        { key: "status", label: "وضعیت", num: true, render: function (r) { return el("span", { class: r.status === 200 ? "" : "no", text: fd(r.status || "خطا") }); } },
        { key: "title", label: "عنوان", render: function (r) { return el("span", { class: "clip", title: r.title, text: r.title || "— بدون عنوان —" }); } },
        { key: "tlen", label: "طول عنوان", num: true, render: function (r) { return el("span", { class: r.tlen > th.title_max || r.tlen < th.title_min ? "no" : "", text: fn(r.tlen) }); } },
        { key: "dlen", label: "طول توضیح", num: true, render: function (r) { return el("span", { class: !r.dlen || r.dlen > th.desc_max ? "no" : "", text: fn(r.dlen) }); } },
        { key: "words", label: "کلمات", num: true, render: function (r) { return fn(r.words); } },
        { key: "inl", label: "لینک ورودی", num: true, render: function (r) { return fn(r.inl); } },
        { key: "schema", label: "اسکیما", num: true, render: function (r) { return fn(r.schema); } },
        { key: "sec", label: "پاسخ (ث)", num: true, render: function (r) { return fn(r.sec, 2); } },
        { key: "impr", label: "ایمپرشن", num: true, render: function (r) { return gscOk ? fn(r.impr) : "…"; } },
        { key: "pos", label: "رتبه", num: true, render: function (r) { return gscOk ? fn(r.pos, 1) : "…"; } },
        { key: "issues", label: "مشکل", num: true, render: function (r) { return r.issues ? el("span", { class: "no", text: fn(r.issues) }) : el("span", { class: "yes", text: "✓" }); } }
      ], f, { sortKey: "issues", limit: 80, detail: pageDetail, emptyText: "صفحه‌ای با این فیلتر نیست." }));
    }
    var sel = el("select", { "aria-label": "نوع صفحه", onchange: function (e) { state.type = e.target.value; render(); } },
      el("option", { value: "all", text: "همه‌ی انواع (" + fn((crawl.pages || []).length) + ")" }),
      Object.keys(types).map(function (t) { return el("option", { value: t, text: (TYPE_FA[t] || t) + " (" + fn(types[t]) + ")" }); }));
    var q = el("input", { type: "search", placeholder: "جستجوی نشانی یا عنوان…", oninput: function (e) { state.q = e.target.value; render(); } });
    var cb = el("label", null, el("input", { type: "checkbox", onchange: function (e) { state.onlyIssues = e.target.checked; render(); } }), "فقط صفحات دارای مشکل");
    render();
    var typeBars = bars(Object.keys(types).map(function (t) { return { label: TYPE_FA[t] || t, value: types[t] }; }).sort(function (a, b) { return b.value - a.value; }));
    return [v, el("div", { class: "grid g3" },
      tile("صفحات خزش‌شده", fn((crawl.pages || []).length), "در " + fn(crawl.duration_s) + " ثانیه"),
      tile("ریدایرکت / خطا", fn((crawl.redirects || []).length) + " / " + fn((crawl.broken || []).length), "لینک‌های داخلی که به ۲۰۰ نمی‌رسند"),
      card("ترکیب صفحات", null, typeBars)), el("div", { class: "filters mt" }, sel, q, cb), holder];
  }

  function pageDetail(r) {
    var p = r.p, iss = issuesByPath[r.path] || [];
    var t = null;
    products.forEach(function (x) { if (x.target_url && short(x.target_url) === r.path) t = x; });
    var pairs = gscOk ? (gsc.pairs || []).filter(function (x) { return short(x.page) === r.path; }).slice(0, 15) : [];
    return el("div", { class: "grid g2" },
      el("div", { class: "stack small" },
        el("div", null, el("b", { text: "عنوان: " }), p.title || "—"),
        el("div", null, el("b", { text: "توضیح متا: " }), p.description || "—"),
        el("div", null, el("b", { text: "H1: " }), (p.h1 || []).join(" | ") || "—"),
        p.h2 && p.h2.length ? el("div", null, el("b", { text: "H2ها: " }), p.h2.join(" · ")) : null,
        el("div", null, el("b", { text: "canonical: " }), p.canonical ? el("span", { class: "url", text: short(p.canonical) }) : "—"),
        el("div", null, el("b", { text: "اسکیما: " }), (p.schema || []).map(function (s) { return el("span", { class: "tag ltr", text: s }); })),
        el("div", null, el("b", { text: "تصاویر بدون alt: " }), fn(p.images_no_alt) + " از " + fn(p.images)),
        p.redirect_to ? el("div", null, el("b", { text: "ریدایرکت به: " }), link(p.redirect_to)) : null,
        p.linked_from && p.linked_from.length ? el("div", null, el("b", { text: "لینک‌شده از: " }), p.linked_from.map(function (u) { return el("span", { class: "tag" }, short(u)); })) : null,
        el("div", null, link(p.url, "باز کردن صفحه ↗"))),
      el("div", { class: "stack small" },
        t ? el("div", { class: "note" }, el("b", { text: "هدف: " }), t.primary, " — فرعی: ", (t.secondary || []).join("، ")) : null,
        iss.length ? el("div", null, el("b", { text: "مشکلات این صفحه:" }), el("ul", { style: "margin:4px 0;padding-inline-start:18px" }, iss.map(function (i) { return el("li", null, sevChip(i.severity), " ", fd(i.title)); }))) : el("div", { class: "yes", text: "✓ مشکلی ثبت نشده" }),
        pairs.length ? el("div", null, el("b", { text: "کوئری‌های گوگل برای این صفحه (۲۸ روز):" }),
          el("ul", { style: "margin:4px 0;padding-inline-start:18px" }, pairs.map(function (x) { return el("li", null, x.query, el("span", { class: "muted", text: " — رتبه " + fn(x.position, 1) + " · " + fn(x.impressions) + " ایمپرشن · " + fn(x.clicks) + " کلیک" })); }))) :
          el("div", { class: "muted", text: gscOk ? "در ۲۸ روز گذشته ایمپرشنی نداشته." : "کوئری‌های گوگل پس از اتصال سرچ کنسول نمایش داده می‌شود." })));
  }

  function viewKeywords() {
    var v = sec("کلمات کلیدی", "کلمات کلیدی هر صفحه و کل سایت. منبع: لیست دست‌نویس اولویت‌های کارفرما + پیشنهادهای جستجوی گوگل (Autocomplete، ایران، فارسی) + سرچ کنسول. حجم جستجوی دقیق برای ایران در ابزارهای رایگان وجود ندارد؛ «رتبه در پیشنهاد گوگل» نشانه‌ی محبوبیت است.");
    var out = [v];
    if (KW.method_fa) out.push(el("details", { class: "small ink2", style: "margin:0 0 14px" }, el("summary", { style: "cursor:pointer;color:var(--s1)", text: "روش جمع‌آوری و محدودیت‌ها" }), el("p", { text: KW.method_fa })));
    if (!products.length) out.push(empty("تحقیق کلمات کلیدی در حال اجراست؛ در بیلد بعدی اینجا پر می‌شود."));
    out.push(el("div", { class: "grid g3" }, products.map(function (p) {
      var pg = p.target_url ? byPath[short(p.target_url)] : null;
      return el("section", { class: "card" },
        el("div", { class: "card-h" }, el("span", { class: "tag", text: "#" + fd(p.id) }), el("h3", { text: p.name_fa })),
        el("div", { class: "small" }, el("b", { text: "اصلی: " }), p.primary || "—"),
        el("div", { class: "small ink2" }, (p.secondary || []).map(function (s) { return el("span", { class: "tag", text: s }); })),
        el("div", { class: "small mt" }, el("b", { text: "صفحه: " }), p.target_url ? link(p.target_url) : el("span", { class: "no", text: "صفحه‌ی هدف ندارد" })),
        pg ? el("div", { class: "small muted", text: "عنوان فعلی: " + (pg.title || "—") }) : null,
        (p.article_ideas || []).length ? el("details", { class: "small mt" }, el("summary", { text: fn(p.article_ideas.length) + " ایده‌ی مقاله" }),
          el("ol", { class: "steps" }, p.article_ideas.map(function (a) { return el("li", null, a.title, " ", el("span", { class: "tag", text: a.type })); }))) : null);
    })));

    var tr = (KW.trends || {}).head_terms || {};
    var gapPages = KW.gap_pages || [];
    if (tr.status === "ok" || gapPages.length) {
      out.push(el("div", { class: "grid g2 mt2" },
        tr.status === "ok" ? card("تقاضای نسبی جستجو", "گوگل ترندز، ایران، ۱۲ ماه — عدد نسبی است نه حجم",
          el("div", null, bars(Object.keys(tr.mean_interest || {}).map(function (k) { return { label: k, value: tr.mean_interest[k] }; })
            .sort(function (a, b) { return b.value - a.value; }), function (v) { return fn(v, v < 10 ? 1 : 0); }),
            tr.note_fa ? el("p", { class: "small muted", style: "margin:10px 0 0", text: tr.note_fa }) : null)) : empty("ترندز در دسترس نبود."),
        card("صفحه‌هایی که باید ساخته شوند", "کلمات کلیدی بدون صفحه، گروه‌بندی‌شده بر اساس صفحه‌ی پیشنهادی",
          table([
            { key: "title", label: "صفحه‌ی پیشنهادی", render: function (g) { return el("span", null, el("b", { text: g.title }), el("div", { class: "small muted", text: (g.keywords || []).slice(0, 4).join("، ") })); } },
            { key: "type", label: "نوع", render: function (g) { return el("span", { class: "tag", text: { category: "دسته", "category-section": "بخش دسته", landing: "لندینگ", article: "مقاله" }[g.type] || g.type }); } },
            { key: "kw_count", label: "کلمه", num: true, render: function (g) { return fn(g.kw_count || (g.keywords || []).length); } }
          ], gapPages, { sortKey: "kw_count", limit: 8 }))));
    }

    var kws = (KW.keywords || []).map(function (k) {
      var g = gscQ[norm(k.kw)] || {};
      return Object.assign({}, k, { pos: g.position, impr: g.impressions, clicks: g.clicks });
    });
    if (kws.length) {
      var state = { cl: "all", intent: "all", gap: false, q: "" };
      var holder = el("div");
      var pname = {}; products.forEach(function (p) { pname[p.id] = p.name_fa; });
      var INT = { transactional: "خرید", commercial: "بررسی خرید", informational: "اطلاعاتی", navigational: "برند/ناوبری" };
      var render = function () {
        holder.textContent = "";
        var f = kws.filter(function (k) {
          return (state.cl === "all" || String(k.cluster) === state.cl) && (state.intent === "all" || k.intent === state.intent) &&
            (!state.gap || k.gap) && (!state.q || norm(k.kw).indexOf(norm(state.q)) >= 0);
        });
        holder.appendChild(table([
          { key: "kw", label: "کلمه‌ی کلیدی" },
          { key: "cluster", label: "خوشه", render: function (k) { return pname[k.cluster] || k.cluster; } },
          { key: "intent", label: "نیت", render: function (k) { return INT[k.intent] || k.intent; } },
          { key: "funnel", label: "قیف", render: function (k) { return el("span", { class: "ltr", text: k.funnel || "" }); } },
          { key: "target_url", label: "صفحه‌ی هدف", render: function (k) { return k.target_url ? link(k.target_url) : el("span", { class: "no", text: k.suggested_page ? "شکاف: " + (k.suggested_page.title || k.suggested_page.type || "") : "ندارد" }); }, sort: function (k) { return k.target_url || ""; } },
          { key: "suggest_rank", label: "رتبه در پیشنهاد", num: true, render: function (k) { return fn(k.suggest_rank); } },
          { key: "seen_count", label: "تکرار", num: true, render: function (k) { return fn(k.seen_count); } },
          { key: "pos", label: "رتبه‌ی ما", num: true, render: function (k) { return gscOk ? fn(k.pos, 1) : "…"; } },
          { key: "impr", label: "ایمپرشن", num: true, render: function (k) { return gscOk ? fn(k.impr) : "…"; } }
        ], f, { sortKey: "seen_count", limit: 100 }));
      };
      var cl = el("select", { "aria-label": "خوشه", onchange: function (e) { state.cl = e.target.value; render(); } },
        el("option", { value: "all", text: "همه‌ی خوشه‌ها (" + fn(kws.length) + ")" }),
        products.map(function (p) { return el("option", { value: String(p.id), text: p.name_fa }); }),
        el("option", { value: "head", text: "عمومی" }), el("option", { value: "brand", text: "برند" }));
      var it = el("select", { "aria-label": "نیت", onchange: function (e) { state.intent = e.target.value; render(); } },
        el("option", { value: "all", text: "همه‌ی نیت‌ها" }), Object.keys(INT).map(function (k) { return el("option", { value: k, text: INT[k] }); }));
      var gp = el("label", null, el("input", { type: "checkbox", onchange: function (e) { state.gap = e.target.checked; render(); } }), "فقط شکاف‌ها (بدون صفحه)");
      var q = el("input", { type: "search", placeholder: "جستجوی کلمه…", oninput: function (e) { state.q = e.target.value; render(); } });
      render();
      var gaps = kws.filter(function (k) { return k.gap; }).length;
      out.push(el("div", { class: "grid g4 mt2" },
        tile("کلمات کلیدی مرتبط", fn(kws.length)),
        tile("بدون صفحه‌ی هدف (شکاف)", fn(gaps), fn(pct(gaps, kws.length)) + "٪ کل"),
        tile("نیت خرید", fn(kws.filter(function (k) { return k.intent === "transactional"; }).length)),
        tile("اطلاعاتی (خوراک مقاله)", fn(kws.filter(function (k) { return k.intent === "informational"; }).length))));
      out.push(el("div", { class: "filters mt" }, cl, it, gp, q), holder);
    }

    if (gscOk) {
      var qs = (gsc.queries || []).map(function (q) { var w = null; (gsc.queries_7d || []).forEach(function (x) { if (x.query === q.query) w = x.position; }); return Object.assign({ brand: isBrand(q.query), pos7: w }, q); });
      out.push(el("div", { class: "mt2" }, card("کوئری‌های واقعی از سرچ کنسول", "۲۸ روز — " + fn(qs.length) + " کوئری",
        table([
          { key: "query", label: "کوئری", render: function (q) { return el("span", null, q.query, q.brand ? el("span", { class: "tag", text: "برند" }) : null); } },
          { key: "clicks", label: "کلیک", num: true, render: function (q) { return fn(q.clicks); } },
          { key: "impressions", label: "ایمپرشن", num: true, render: function (q) { return fn(q.impressions); } },
          { key: "ctr", label: "CTR ٪", num: true, render: function (q) { return fn(q.ctr, 1); } },
          { key: "position", label: "رتبه ۲۸ روز", num: true, render: function (q) { return fn(q.position, 1); } },
          { key: "pos7", label: "رتبه ۷ روز", num: true, render: function (q) { return fn(q.pos7, 1); } }
        ], qs, { sortKey: "impressions", limit: 60 }))));
    } else {
      out.push(el("div", { class: "note warn mt2", text: "رتبه، ایمپرشن و کلیک هر کلمه پس از اتصال سرچ کنسول در همین جدول‌ها پر می‌شود (ستون‌های «…»)." }));
    }
    return out;
  }

  function viewCompetitors() {
    var out = sec("رقبا", "رقبای لیست دست‌نویس کارفرما و بررسی ۱۶ مرداد، با رصد روزانه‌ی نقشه‌ی سایتشان: هر صفحه‌ای که منتشر یا حذف کنند فردا صبح اینجاست.");
    if (!compCfg.length) return [out, empty("تحقیق رقبا در حال اجراست؛ در بیلد بعدی اینجا پر می‌شود.")];
    var TH = { high: "بالا", medium: "متوسط", low: "کم" };
    var rows = compCfg.map(function (c) {
      var w = compWatch[c.id] || {}, h = ((comp.history || {})[c.id] || {}).history || [];
      var new7 = h.slice(-7).reduce(function (a, x) { return a + (x.new || 0); }, 0);
      var cover = Object.keys(c.product_pages || {}).filter(function (k) { return c.product_pages[k]; }).length;
      return { c: c, name: c.name_fa || c.domain, domain: c.domain, threat: c.threat, total: w.urls_total || c.urls_total || null,
        blog: (c.urls_by_type || {}).blog != null ? c.urls_by_type.blog : (w.by_type || {}).blog, new7: h.length > 1 ? new7 : null, cover: cover,
        price: c.has_price_table, reach: w.urls_total != null ? w.reachable : c.reachable, h: h, owner: (c.owner_products || []).length };
    });
    out = [out, table([
      { key: "name", label: "رقیب", render: function (r) { return el("span", null, el("b", { text: r.name }), el("br"), el("a", { href: "https://" + r.domain, target: "_blank", rel: "noopener", class: "ltr small", text: r.domain })); } },
      { key: "threat", label: "تهدید", render: function (r) { return r.threat ? el("span", { class: "sev " + (r.threat === "high" ? "critical" : r.threat === "medium" ? "medium" : "low"), text: TH[r.threat] || r.threat }) : "—"; }, sort: function (r) { return { high: 3, medium: 2, low: 1 }[r.threat] || 0; } },
      { key: "owner", label: "در لیست کارفرما", num: true, render: function (r) { return r.owner ? fn(r.owner) + " محصول" : "—"; } },
      { key: "total", label: "کل صفحات", num: true, render: function (r) { return fn(r.total); } },
      { key: "blog", label: "مقاله", num: true, render: function (r) { return fn(r.blog); } },
      { key: "new7", label: "جدید ۷ روز", num: true, render: function (r) { return r.new7 == null ? el("span", { class: "muted", text: "از فردا" }) : fn(r.new7); } },
      { key: "cover", label: "پوشش ۱۳ محصول", num: true, render: function (r) { return fn(r.cover) + " / ۱۳"; } },
      { key: "price", label: "جدول قیمت", render: function (r) { return r.price === "yes" ? el("span", { class: "yes", text: "✓ دارد" }) : r.price === "no" ? el("span", { class: "muted", text: "ندارد" }) : "؟"; } },
      { key: "trend", label: "روند صفحات", nosort: true, render: function (r) { return spark(r.h.map(function (x) { return x.urls; })); } },
      { key: "reach", label: "دسترسی", render: function (r) { return r.reach === false ? el("span", { class: "no", text: "باز نشد" }) : el("span", { class: "yes", text: "✓" }); } }
    ], rows, { sortKey: "owner", limit: 40, detail: function (r) {
      var c = r.c, w = compWatch[c.id] || {};
      return el("div", { class: "grid g2 small" },
        el("div", { class: "stack" },
          c.notes_fa ? el("div", { class: "note", text: c.notes_fa }) : null,
          el("div", null, el("b", { text: "عنوان صفحه‌ی اصلی: " }), w.home_title || c.home_title || "—"),
          el("div", null, el("b", { text: "تلفن: " }), el("span", { class: "ltr", text: (c.phones || []).join(" · ") || "—" })),
          el("div", null, el("b", { text: "CMS: " }), c.cms || "—"),
          c.blog_latest && c.blog_latest.url ? el("div", null, el("b", { text: "آخرین مقاله: " }), el("a", { href: c.blog_latest.url, target: "_blank", rel: "noopener", text: short(c.blog_latest.url).slice(0, 70) }), " ", c.blog_latest.date ? jd(c.blog_latest.date) : "") : null),
        el("div", null, el("b", { text: "صفحه‌ی آن‌ها برای هر محصول ما:" }),
          el("ul", { style: "margin:4px 0;padding-inline-start:18px" }, Object.keys(c.product_pages || {}).map(function (k) {
            var pp = c.product_pages[k]; if (!pp) return null;
            var pn = (products.filter(function (p) { return String(p.id) === String(k); })[0] || {}).name_fa || ("#" + k);
            return el("li", null, pn + ": ", el("a", { href: pp.url, target: "_blank", rel: "noopener", text: pp.title || short(pp.url) }));
          }))));
    } })];

    // coverage matrix
    var prodList = products.length ? products : [];
    if (prodList.length) {
      var head = el("tr", null, el("th", { text: "محصول" }), compCfg.map(function (c) { return el("th", { text: c.name_fa || c.domain, title: c.domain }); }));
      var body = el("tbody", null, prodList.map(function (p) {
        return el("tr", null, el("td", { class: "nowrap" }, fd(p.id) + ". " + p.name_fa), compCfg.map(function (c) {
          var pp = (c.product_pages || {})[String(p.id)];
          var named = (c.owner_products || []).indexOf(p.id) >= 0;
          return el("td", { style: "text-align:center" + (named ? ";background:var(--med-soft)" : ""), title: named ? "کارفرما این رقیب را برای این محصول نام برده" : "" },
            pp ? el("a", { href: pp.url, target: "_blank", rel: "noopener", class: "yes", text: "✓", "aria-label": "صفحه دارد" }) : el("span", { class: "muted", text: "·" }));
        }));
      }));
      out.push(el("div", { class: "mt2" }, card("ماتریس پوشش محصولات", "✓ = رقیب برای این محصول صفحه‌ی اختصاصی دارد · خانه‌ی زرد = رقیبی که کارفرما برای همین محصول نام برده",
        el("div", { class: "tbl-wrap" }, el("table", null, el("thead", null, head), body)))));
    }

    // feed of new pages
    var feed = [];
    Object.keys(comp.history || {}).forEach(function (id) {
      var c = compCfg.filter(function (x) { return x.id === id; })[0] || {};
      ((comp.history[id] || {}).new_log || []).forEach(function (n) { feed.push({ date: n.date, url: n.url, type: n.type, name: c.name_fa || c.domain }); });
    });
    feed.sort(function (a, b) { return b.date.localeCompare(a.date); });
    out.push(el("div", { class: "mt2" }, card("صفحات تازه‌ی رقبا", "از نقشه‌ی سایت، روزانه",
      feed.length ? table([
        { key: "date", label: "تاریخ", render: function (r) { return jd(r.date); } },
        { key: "name", label: "رقیب" },
        { key: "type", label: "نوع", render: function (r) { return { blog: "مقاله", product: "محصول", category: "دسته", other: "سایر" }[r.type] || r.type; } },
        { key: "url", label: "صفحه", render: function (r) { return el("a", { href: r.url, target: "_blank", rel: "noopener", class: "url", text: short(r.url) }); } }
      ], feed, { sortKey: "date", limit: 50 }) : empty("خط مبنا امروز ثبت شد؛ صفحات تازه از اجرای فردا ظاهر می‌شوند."))));
    return out;
  }

  function viewContent() {
    var plan = D.content_plan || {}, items = plan.items || [];
    var out = sec("تولید محتوا", "تقویم انتشار روزهای کاری (شنبه تا چهارشنبه، از تقویم رسمی time.ir): سه استوری در روز ساعت ۹، ۱۳ و ۱۶، خبر کانال، و مقاله‌ی سایت با رشد پلکانی. محصول هر روز از لیست اولویت کارفرما و عکس از پوشه‌ی همان دسته انتخاب می‌شود.");
    var stories = items.filter(function (i) { return i.kind === "story"; }).length;
    var arts = items.filter(function (i) { return i.kind === "article"; }).length;
    var articles = pages.filter(function (p) { return p.type === "article"; });
    out = [out, el("div", { class: "grid g4" },
      tile("مقاله‌های منتشرشده", fn(articles.length), "روی سایت زنده"),
      tile("استوری در ۴ هفته‌ی آینده", fn(stories), "۵ شبکه برای هر کدام"),
      tile("مقاله در ۴ هفته‌ی آینده", fn(arts), "۳ ← ۵ ← ۶ در هفته"),
      tile("عکس محصول آماده", fn(((plan.priority || []).reduce(function (a, p) { return a + (p.photos || 0); }, 0))), "تا اتصال درایو: عکس‌های پروتوتایپ"))];

    // calendar next 10 working days
    var days = []; items.forEach(function (it) { if (days.indexOf(it.date) < 0) days.push(it.date); });
    out.push(el("div", { class: "mt2" }, card("تقویم ۱۰ روز کاری آینده", "روزهای تعطیل رسمی و پنجشنبه/جمعه حذف شده‌اند", el("div", { class: "grid g2" }, days.slice(0, 10).map(function (d) {
      var c = (((D.calendar || {}).days || []).filter(function (x) { return x.date === d; })[0]) || {};
      return el("div", { class: "day" }, el("h4", null, (c.weekday_fa || "") + " " + fd(c.jalali_label || d),
        c.events && c.events.length ? el("span", { class: "ev", text: c.events.slice(0, 2).join("، ") }) : null),
        items.filter(function (it) { return it.date === d; }).sort(function (a, b) { return a.time.localeCompare(b.time); }).map(slotRow));
    })))));

    // holidays ahead
    var hol = ((D.calendar || {}).days || []).filter(function (d) { return d.holiday && d.events.length && new Date(d.date).getDay() !== 5; });
    if (hol.length) out.push(el("div", { class: "mt" }, el("div", { class: "note", text: "تعطیلات رسمی پیش رو (انتشار خودکار متوقف می‌شود): " + hol.map(function (d) { return fd(d.jalali_label) + " — " + d.events[0]; }).join(" · ") })));

    // mix
    var mix = {}; items.forEach(function (i) { mix[i.type] = (mix[i.type] || 0) + 1; });
    out.push(el("div", { class: "grid g2 mt2" },
      card("۱۱ نوع محتوا", "هدف هر نوع", el("div", { class: "stack small" }, (plan.types || []).map(function (t) {
        return el("div", null, el("b", { text: t.fa }), " — ", el("span", { class: "ink2", text: t.goal }), " ", el("span", { class: "tag", text: fn(mix[t.fa] || 0) + " در ۴ هفته" }));
      }))),
      card("سهم هر محصول در ۴ هفته", "وزن‌دهی بر اساس اولویت کارفرما", bars((plan.priority || []).map(function (p) {
        return { label: fd(p.rank) + ". " + p.name, value: items.filter(function (i) { return i.product_rank === p.rank; }).length };
      })))));

    // coverage of existing articles per priority product
    var cov = (products.length ? products : (plan.priority || []).map(function (p) { return { id: p.rank, name_fa: p.name, primary: p.name }; })).map(function (p) {
      var key = norm((p.name_fa || "").replace(/\(.*?\)/g, "")).split(" ").slice(0, 2).join(" ");
      var hits = articles.filter(function (a) { return norm(a.title + " " + (a.h1 || []).join(" ")).indexOf(key) >= 0; });
      return { id: p.id, name: p.name_fa, n: hits.length, hits: hits, ideas: (p.article_ideas || []).length };
    });
    out.push(el("div", { class: "mt2" }, card("پوشش مقاله‌ها روی محصولات اولویت‌دار", "مقاله‌هایی که نام محصول در عنوان یا H1 دارند",
      table([
        { key: "id", label: "#", num: true },
        { key: "name", label: "محصول" },
        { key: "n", label: "مقاله‌ی موجود", num: true, render: function (r) { return el("span", { class: r.n ? "" : "no", text: fn(r.n) }); } },
        { key: "hits", label: "مقاله‌ها", nosort: true, render: function (r) { return r.hits.slice(0, 3).map(function (a) { return el("div", null, link(a.url, (a.title || short(a.url)).slice(0, 60))); }); } },
        { key: "ideas", label: "ایده‌ی آماده", num: true, render: function (r) { return fn(r.ideas); } }
      ], cov, { sortKey: "id", sortDir: "asc", limit: 20 }))));

    out.push(el("div", { class: "mt2" }, card("مقاله‌های موجود سایت", fn(articles.length) + " مقاله",
      table([
        { key: "title", label: "عنوان", render: function (a) { return link(a.url, a.title || short(a.url)); } },
        { key: "cat", label: "دسته‌ی مجله", render: function (a) { return short(a.url).split("/")[2] || ""; }, sort: function (a) { return short(a.url).split("/")[2] || ""; } },
        { key: "words", label: "کلمات", num: true, render: function (a) { return fn(a.words); } },
        { key: "inlinks", label: "لینک ورودی", num: true, render: function (a) { return fn(a.inlinks); } },
        { key: "imp", label: "ایمپرشن", num: true, render: function (a) { var g = gscP[short(a.url)]; return gscOk ? fn(g && g.impressions) : "…"; }, sort: function (a) { var g = gscP[short(a.url)]; return g ? g.impressions : 0; } }
      ], articles, { sortKey: "words", limit: 50 }))));
    return out;
  }

  function viewAutomation() {
    var A = D.automation || {};
    var out = [sec("اتوماسیون محتوا", "نقشه‌ی اجرایی: چه چیزی کاملاً خودکار می‌شود، چه چیزی «یک‌لمسی»، و برای شروع چه چیزی از شما لازم است."),
      A.principle ? el("div", { class: "note", text: A.principle }) : null];
    if ((A.samples || []).length) {
      out.push(el("div", { class: "mt2" }, card("نمونه‌ی خروجی — سه استوری یک روز کاری", "ساخته‌شده خودکار از عکس واقعی محصول، با قالب برند؛ همین فایل‌ها به اینستاگرام و «یک‌لمسی» به روبیکا/ایتا/بله/واتساپ می‌روند",
        el("div", { class: "grid g3" }, A.samples.map(function (s) {
          return el("figure", { style: "margin:0" }, el("a", { href: s.src, target: "_blank", rel: "noopener" },
            el("img", { src: s.src, alt: s.caption, loading: "lazy", width: "360", height: "640", style: "width:100%;height:auto;border-radius:12px;border:1px solid var(--border)" })),
            el("figcaption", { class: "small ink2", style: "margin-top:6px", text: s.caption }));
        })))));
    }
    out.push(el("div", { class: "mt2" }, card("زنجیره‌ی تولید", null, el("div", { class: "stack" }, (A.pipeline || []).map(function (p) {
      return el("div", { style: "display:flex;gap:10px;align-items:flex-start" }, stChip(p.status), el("div", null, el("b", { text: p.step + " " }), el("span", { class: "ink2", text: p.what })));
    })))));
    var AUTO = { full: "کاملاً خودکار", partial: "نیمه‌خودکار", "one-tap": "یک‌لمسی" };
    out.push(el("div", { class: "mt2" }, card("کانال‌ها و روش انتشار", "ریسک = احتمال محدودیت یا بن اکانت", table([
      { key: "channel", label: "کانال", render: function (c) { return el("b", { text: c.channel }); } },
      { key: "auto", label: "سطح", render: function (c) { return el("span", { class: "st " + (c.auto === "full" ? "ok" : c.auto === "one-tap" ? "waiting" : "partial"), text: AUTO[c.auto] || c.auto }); } },
      { key: "method", label: "روش", render: function (c) { return el("span", { class: "small ink2", text: c.method }); } },
      { key: "risk", label: "ریسک", render: function (c) { return el("span", { class: "sev " + (c.risk === "low" ? "low" : c.risk === "medium" ? "medium" : "critical"), text: c.risk === "low" ? "کم" : c.risk === "medium" ? "متوسط" : "بالا اگر خودکار شود" }); } },
      { key: "needs", label: "لازم برای شروع", render: function (c) { return el("span", { class: "small", text: c.needs }); } }
    ], A.channels || [], { limit: 20 }))));
    out.push(el("div", { class: "grid g2 mt2" },
      card("ریتم یک روز کاری", null, el("div", { class: "stack small" }, (A.daily_rhythm || []).map(function (r) { return el("div", null, el("b", { class: "num", text: r.time + " " }), r.what); }))),
      card("رشد پلکانی مقاله‌ها", null, el("div", { class: "stack small" }, (A.article_ramp || []).map(function (r) {
        return el("div", null, el("b", { text: r.period }), " — " + fn(r.per_week) + " مقاله در هفته · ", el("span", { class: "ink2", text: r.approval }));
      }), el("p", { class: "muted", text: "کیفیت پیش از کمیت: گوگل محتوای انبوه کم‌ارزش را جریمه می‌کند؛ هر مقاله باید اطلاعات واقعی کارخانه (مشخصات، قیمت، عکس اصلی) داشته باشد." })))));
    out.push(el("div", { class: "mt2" }, card("ایده‌های بیشتر برای رشد ارگانیک و پلکانی", null, table([
      { key: "title", label: "ایده", render: function (r) { return el("b", { text: r.title }); } },
      { key: "why", label: "چرا", render: function (r) { return el("span", { class: "small ink2", text: r.why }); } },
      { key: "effort", label: "زحمت" }
    ], A.more_ideas || [], { limit: 30 }))));
    out.push(el("div", { class: "mt2" }, card("برای شروع از شما لازم است", null, el("ol", { class: "steps", style: "font-size:14.5px;color:var(--ink)" }, (A.needs_from_owner || []).map(function (n) { return el("li", { text: n }); })))));
    return out;
  }

  function viewTech() {
    var c = crawl.checks || {};
    var out = [sec("فنی و سرعت", "بررسی‌های سطح سایت، سرعت واقعی از PageSpeed/CrUX و پوشش داده‌ی ساختاریافته.")];
    var tls = c.tls || {};
    var chk = [
      { name: "robots.txt", ok: (c.robots || {}).status === 200 && (c.robots || {}).has_sitemap, v: (c.robots || {}).status === 200 ? "در دسترس، با Sitemap" : "مشکل" },
      { name: "http → https", ok: /^30[1278]$/.test(String((c.http || {}).status)) && /^https:/.test((c.http || {}).location || ""), v: fd((c.http || {}).status || "—") + " → " + ((c.http || {}).location || "") },
      { name: "www.sepahanfelez.ir", ok: true, v: (c.www || {}).status ? fd(c.www.status) + " → " + (c.www.location || "") : "رکورد DNS ندارد (مشکلی نیست؛ همه‌ی لینک‌ها بدون www)" },
      { name: "گواهی SSL", ok: tls.days_left > 21, v: tls.expires ? fd(tls.days_left) + " روز مانده (" + jd(tls.expires) + ") — " + (tls.issuer || "") : tls.error || "—" },
      { name: "نقشه‌ی سایت", ok: !(crawl.sitemap || {}).error, v: fn((crawl.sitemap || {}).count) + " نشانی" }
    ];
    (c.foreign_hosts || []).forEach(function (f) {
      chk.push({ name: "دامنه‌ی غریبه " + f.host, ok: !f.serves_our_content, v: f.serves_our_content ? "محتوای ما را نشان می‌دهد!" : "محتوای ما را نشان نمی‌دهد (" + (f.status ? fd(f.status) : "بسته") + ")" });
    });
    out.push(el("div", { class: "grid g2" },
      card("بررسی‌های سطح سایت", null, el("div", { class: "stack small" }, chk.map(function (x) {
        return el("div", { style: "display:flex;gap:8px" }, el("span", { class: x.ok ? "yes" : "no", text: x.ok ? "✓" : "✗" }), el("b", { text: x.name }), el("span", { class: "ink2", text: x.v }));
      }))),
      card("زمان پاسخ سرور به تفکیک نوع صفحه", "میانگین ثانیه، از خزش امروز (سرور در اروپا)", bars(Object.keys(TYPE_FA).map(function (t) {
        var ps = pages.filter(function (p) { return p.type === t; });
        return ps.length ? { label: TYPE_FA[t], value: ps.reduce(function (a, p) { return a + p.seconds; }, 0) / ps.length } : null;
      }).filter(Boolean).sort(function (a, b) { return b.value - a.value; }), function (v) { return fn(v, 2) + " ث"; }))));

    // PSI
    if (psiOk) {
      var res = (psi.results || []).filter(function (r) { return r.status === "ok"; });
      out.push(el("div", { class: "mt2" }, card("PageSpeed Insights", (psi.stale ? "داده‌ی قدیمی · " : "") + "امتیاز آزمایشگاهی + داده‌ی واقعی کاربران (CrUX)", table([
        { key: "url", label: "صفحه", render: function (r) { return link(r.url); } },
        { key: "strategy", label: "دستگاه", render: function (r) { return r.strategy === "mobile" ? "موبایل" : "دسکتاپ"; } },
        { key: "perf", label: "سرعت", num: true, render: function (r) { var s = r.scores.performance; return el("span", { class: s >= 90 ? "yes" : s < 50 ? "no" : "", text: fn(s) }); }, sort: function (r) { return r.scores.performance; } },
        { key: "seo", label: "سئو", num: true, render: function (r) { return fn(r.scores.seo); }, sort: function (r) { return r.scores.seo; } },
        { key: "a11y", label: "دسترس‌پذیری", num: true, render: function (r) { return fn(r.scores.accessibility); }, sort: function (r) { return r.scores.accessibility; } },
        { key: "lcp", label: "LCP (ث)", num: true, render: function (r) { return fn((r.lab["largest-contentful-paint"] || 0) / 1000, 1); }, sort: function (r) { return r.lab["largest-contentful-paint"]; } },
        { key: "cls", label: "CLS", num: true, render: function (r) { return fn(r.lab["cumulative-layout-shift"], 3); }, sort: function (r) { return r.lab["cumulative-layout-shift"]; } },
        { key: "field", label: "کاربران واقعی", render: function (r) { return r.field_overall ? el("span", { class: "tag ltr", text: r.field_overall }) : el("span", { class: "muted", text: "داده‌ی کافی نیست" }); } },
        { key: "opp", label: "بزرگ‌ترین فرصت", nosort: true, render: function (r) { var o = (r.opportunities || [])[0]; return o ? el("span", { class: "small", text: o.title + " (" + fn(o.savings_ms / 1000, 1) + " ث)" }) : "—"; } }
      ], res, { sortKey: "perf", sortDir: "asc", limit: 20 }))));
    } else {
      out.push(el("div", { class: "note warn mt2", text: "PageSpeed Insights: " + (psi.reason || "هنوز اجرا نشده") + " — اجرای روزانه در GitHub Actions این را پر می‌کند." }));
    }

    // schema coverage
    var types = ["home", "price", "category", "product", "article"];
    var schemaRows = types.map(function (t) {
      var ps = pages.filter(function (p) { return p.type === t; });
      var s = {}; ps.forEach(function (p) { (p.schema || []).forEach(function (x) { s[x] = (s[x] || 0) + 1; }); });
      return { t: TYPE_FA[t], n: ps.length, s: s };
    });
    out.push(el("div", { class: "grid g2 mt2" },
      card("پوشش داده‌ی ساختاریافته", "تعداد صفحات هر نوع که هر اسکیما را دارند", el("div", { class: "stack small" }, schemaRows.map(function (r) {
        return el("div", null, el("b", { text: r.t + " (" + fn(r.n) + "): " }), Object.keys(r.s).filter(function (k) { return ["ContactPoint", "ImageObject", "ListItem"].indexOf(k) < 0; }).map(function (k) { return el("span", { class: "tag ltr", text: k + " " + r.s[k] }); }));
      }))),
      card("ریدایرکت‌ها و خطاها", "لینک‌های داخلی که مستقیم به ۲۰۰ نمی‌رسند", (crawl.redirects || []).length + (crawl.broken || []).length ? el("div", { class: "stack small" },
        (crawl.broken || []).map(function (b) { return el("div", null, el("span", { class: "no", text: fd(b.status || "خطا") + " " }), el("span", { class: "url", text: short(b.url) }), el("span", { class: "muted", text: " ← لینک از " + (b.linked_from || []).map(short).slice(0, 2).join("، ") })); }),
        (crawl.redirects || []).map(function (b) { return el("div", null, el("span", { class: "ink2", text: fd(b.status) + " " }), el("span", { class: "url", text: short(b.url) }), " → ", el("span", { class: "url", text: short(b.to) }), el("span", { class: "muted", text: " (" + fn(b.inlinks) + " لینک ورودی)" })); })) : el("div", { class: "yes", text: "✓ همه‌ی لینک‌های داخلی سالم‌اند" }))));
    return out;
  }

  function viewTrends() {
    var out = [sec("روند روزانه", "هر اجرای روزانه یک ردیف به تاریخچه اضافه می‌کند. نمودارها با گذشت روزها معنادار می‌شوند.")];
    if (hist.length < 2) out.push(el("div", { class: "note warn", style: "margin-bottom:14px", text: "امروز اولین روز ثبت است (" + fd(hist.length ? hist[0].jalali : "") + "). از فردا خط روند کشیده می‌شود." }));
    var x = hist.map(function (h) { return fd((h.jalali || "").slice(5)); });
    function col(f) { return hist.map(f); }
    out.push(el("div", { class: "grid g2" },
      card("امتیاز سلامت", "از ۱۰۰", lineChart({ x: x, series: [{ name: "سلامت", values: col(function (h) { return h.health; }) }], minMax: 100, area: true, label: "امتیاز سلامت روزانه" })),
      card("مشکلات بر اساس شدت", null, lineChart({ x: x, series: [
        { name: "بحرانی", values: col(function (h) { return h.issues.critical; }), color: "--critical" },
        { name: "مهم", values: col(function (h) { return h.issues.high; }), color: "--serious" },
        { name: "متوسط", values: col(function (h) { return h.issues.medium; }), color: "--s4" }], label: "تعداد مشکلات" })),
      card("صفحات زنده و مقاله‌ها", null, lineChart({ x: x, series: [
        { name: "صفحات زنده", values: col(function (h) { return h.pages; }) },
        { name: "مقاله‌ها", values: col(function (h) { return h.articles; }) },
        { name: "صفحات محصول", values: col(function (h) { return h.products; }) }], label: "صفحات" })),
      card("عمر جدیدترین قیمت", "روز — هدف: صفر", lineChart({ x: x, series: [{ name: "روز", values: col(function (h) { return h.price_age_days; }), color: "--s2" }], label: "عمر قیمت" })),
      card("کلیک گوگل (۲۸ روز غلتان)", gscOk ? null : "پس از اتصال سرچ کنسول", gscOk ? lineChart({ x: x, series: [{ name: "کلیک", values: col(function (h) { return h.gsc ? h.gsc.clicks : null; }) }], area: true, label: "کلیک" }) : empty("در انتظار اتصال")),
      card("ایمپرشن گوگل (۲۸ روز غلتان)", gscOk ? null : "پس از اتصال سرچ کنسول", gscOk ? lineChart({ x: x, series: [{ name: "ایمپرشن", values: col(function (h) { return h.gsc ? h.gsc.impressions : null; }), color: "--s3" }], area: true, label: "ایمپرشن" }) : empty("در انتظار اتصال")),
      card("میانگین زمان پاسخ سرور", "ثانیه", lineChart({ x: x, series: [{ name: "ثانیه", values: col(function (h) { return h.avg_seconds; }), color: "--s7" }], label: "زمان پاسخ" })),
      card("میانگین کلمات هر صفحه", null, lineChart({ x: x, series: [{ name: "کلمه", values: col(function (h) { return h.avg_words; }) }], label: "کلمات" }))));
    if (gscOk && (gsc.daily || []).length) {
      var dd = gsc.daily;
      out.push(el("div", { class: "grid g2 mt2" },
        card("کلیک روزانه — ۹۰ روز", "سرچ کنسول", lineChart({ x: dd.map(function (d) { return jd(d.date); }), series: [{ name: "کلیک", values: dd.map(function (d) { return d.clicks; }) }], area: true })),
        card("رتبه‌ی میانگین روزانه — ۹۰ روز", "پایین‌تر = بهتر", lineChart({ x: dd.map(function (d) { return jd(d.date); }), series: [{ name: "رتبه", values: dd.map(function (d) { return d.position; }), color: "--s2" }], invert: true, minZero: false }))));
    }
    if (ga4Ok) {
      var byDate = {};
      (ga4.daily || []).forEach(function (r) { var k = r.date; byDate[k] = byDate[k] || { all: 0, org: 0 }; byDate[k].all += r.sessions; if (r.sessionDefaultChannelGroup === "Organic Search") byDate[k].org += r.sessions; });
      var ks = Object.keys(byDate).sort();
      out.push(el("div", { class: "mt2" }, card("جلسات سایت — ۹۰ روز", "GA4", lineChart({ x: ks.map(function (k) { return jd(k.slice(0, 4) + "-" + k.slice(4, 6) + "-" + k.slice(6)); }),
        series: [{ name: "همه", values: ks.map(function (k) { return byDate[k].all; }) }, { name: "ارگانیک", values: ks.map(function (k) { return byDate[k].org; }) }] }))));
    }
    // competitor small multiples
    var ch = comp.history || {};
    var ids = Object.keys(ch).filter(function (id) { return (ch[id].history || []).length; });
    if (ids.length) {
      out.push(el("div", { class: "mt2" }, card("رشد صفحات رقبا", "هر رقیب مقیاس خودش", el("div", { class: "grid g4" }, ids.map(function (id) {
        var c = compCfg.filter(function (x) { return x.id === id; })[0] || {}, h = ch[id].history;
        return el("div", { class: "card flat" }, el("div", { class: "small", text: c.name_fa || c.domain }),
          el("div", { class: "num", style: "font-weight:700" }, fn(h[h.length - 1].urls)), spark(h.map(function (x) { return x.urls; }), 120, 26));
      })))));
    }
    return out;
  }

  function viewRoadmap() {
    var R = D.roadmap || {};
    return [sec("نقشه‌ی راه", "کارها به ترتیب اثر؛ هر فاز پیش‌نیاز فاز بعد است. وضعیت‌ها همراه با پیشرفت کار به‌روز می‌شوند."),
      el("div", { class: "grid g2" }, (R.phases || []).map(function (p) {
        var done = p.tasks.filter(function (t) { return t.status === "done"; }).length;
        return el("section", { class: "card phase" },
          el("div", { class: "card-h" }, el("h3", { text: p.title }), el("span", { class: "sub", text: p.when }), el("span", { class: "act num ink2", text: fn(done) + "/" + fn(p.tasks.length) })),
          el("p", { class: "small ink2", style: "margin:0 0 8px", text: p.goal }),
          el("ul", { class: "tasks" }, p.tasks.map(function (t) { return el("li", null, stChip(t.status), el("span", { text: t.t }), el("span", { class: "who", text: t.owner })); })));
      }))];
  }

  function viewIntegrations() {
    var rows = D.integrations || [];
    return [sec("اتصالات", "وضعیت هر منبع داده و هر کانال انتشار، و قدم‌های لازم برای وصل کردنش."),
      el("div", { class: "grid g2" },
        card("وضعیت", null, el("div", { class: "stack small" }, rows.map(function (r) {
          return el("div", null, el("div", { style: "display:flex;gap:8px;align-items:center;flex-wrap:wrap" }, stChip(r.status), el("b", { text: r.name }), el("span", { class: "tag", text: r.group })),
            r.detail ? el("div", { class: "ink2", style: "margin-top:2px", text: r.detail }) : null,
            r.steps && r.steps.length && r.status !== "ok" ? el("ol", { class: "steps" }, r.steps.map(function (s) { return el("li", { text: s }); })) : null);
        }))),
        el("div", { class: "stack" },
          card("اتصال سرچ کنسول و آنالیتیکس", null, el("div", { class: "small stack" },
            el("ol", { class: "steps", style: "color:var(--ink)" },
              el("li", null, "تأیید مالکیت دامنه در Search Console با رکورد TXT در DNS هاست (راهنمای قدم‌به‌قدم در پیام جدا)."),
              el("li", null, "Search Console → Settings → Users and permissions → Add user → ایمیل سرویس‌اکانت با دسترسی ", el("b", { text: "Owner" })),
              el("li", null, "Google Analytics → Admin → Property access management → همان ایمیل با نقش ", el("b", { text: "Viewer" })),
              el("li", null, "Property ID آنالیتیکس را در .env بگذارید: ", el("code", { text: "GA4_PROPERTY_ID" }))),
            el("div", { class: "note warn", text: "همه‌ی کلیدها فقط در فایل .env روی سرور هستند و هیچ‌جا منتشر نمی‌شوند؛ این صفحه فقط نام متغیرها را نشان می‌دهد." }))),
          card("این داشبورد چطور به‌روز می‌شود", null, el("ol", { class: "steps" },
            el("li", { text: "هر روز ساعت ۰۷:۰۰ تهران: خزش کامل sepahanfelez.ir (یک درخواست در ثانیه تا هاست زیر بار نرود)" }),
            el("li", { text: "نقشه‌ی سایت همه‌ی رقبا و مقایسه با دیروز" }),
            el("li", { text: "سرچ کنسول (۹۰ روز)، آنالیتیکس، PageSpeed و بازرسی ایندکس صفحات" }),
            el("li", { text: "تقویم رسمی time.ir و ساخت صف انتشار ۴ هفته" }),
            el("li", { text: "محاسبه‌ی مشکلات، امتیاز سلامت، ثبت در تاریخچه و انتشار همین صفحه" })))))];
  }


  var NETS = [["site", "سایت"], ["telegram", "تلگرام"], ["instagram", "اینستاگرام"], ["bale", "بله"], ["eitaa", "ایتا"], ["rubika", "روبیکا"], ["whatsapp", "واتساپ"]];
  var KIND_FA = { article: "مقاله", post: "پست", story: "استوری", reel: "ریلز", carousel: "کاروسل", message: "پیام کانال", comment: "کامنت", like: "لایک" };
  var PUB_ST = { published: ["ok", "منتشر شد"], "sent-to-operator": ["waiting", "منتظر اپراتور"], failed: ["blocked", "ناموفق"], scheduled: ["pending", "زمان‌بندی‌شده"], deleted: ["pending", "حذف‌شده"] };

  function viewHistory() {
    var P = D.published || {}, S = D.social_status || {};
    var out = [sec("تاریخچه‌ی انتشار", "هر چیزی که روی سایت و شبکه‌ها منتشر می‌شود — خودکار یا یک‌لمسی — همین‌جا ثبت می‌شود: کِی، کجا، چه نوع محتوایی، برای کدام محصول، با کدام عکس، و نتیجه‌اش.")];
    var weekAgo = new Date(Date.now() - 7 * 864e5).toISOString();
    out.push(el("div", { class: "grid g4" }, NETS.map(function (n) {
      var rows = P[n[0]] || [], ok = rows.filter(function (r) { return r.status === "published"; });
      var last = rows.length ? rows[rows.length - 1] : null, st = S[n[0]];
      return el("div", { class: "card tile" },
        el("div", { class: "lbl" }, n[1], " ", n[0] !== "site" ? (st && st.logged_in ? el("span", { class: "st ok", text: "وصل" }) : el("span", { class: "st pending", text: "وارد نشده" })) : null),
        el("div", { class: "val" }, fn(ok.length), el("small", { text: "منتشرشده" })),
        el("div", { class: "foot" }, "۷ روز اخیر: " + fn(ok.filter(function (r) { return r.ts >= weekAgo; }).length) + (last ? " · آخرین: " + jd(last.ts) : "")));
    })));
    var state = { net: "all", kind: "all", q: "" };
    var all = [];
    NETS.forEach(function (n) { (P[n[0]] || []).forEach(function (r) { all.push(r); }); });
    all.sort(function (a, b) { return b.ts.localeCompare(a.ts); });
    var holder = el("div");
    function render() {
      holder.textContent = "";
      var f = all.filter(function (r) {
        return (state.net === "all" || r.network === state.net) && (state.kind === "all" || r.kind === state.kind) &&
          (!state.q || norm((r.text || "") + " " + (r.product || "") + " " + (r.content_type || "")).indexOf(norm(state.q)) >= 0);
      });
      if (!all.length) { holder.appendChild(empty("هنوز چیزی منتشر نشده. اولین انتشار پس از ورود به شبکه‌ها و تأیید شما شروع می‌شود؛ از آن لحظه هر پست، استوری و مقاله اینجا ثبت می‌شود.")); return; }
      holder.appendChild(table([
        { key: "ts", label: "زمان", render: function (r) { return el("span", { class: "nowrap" }, jd(r.ts), " ", el("span", { class: "muted", text: fd(r.ts.slice(11, 16)) })); } },
        { key: "network", label: "شبکه", render: function (r) { return (NETS.filter(function (n) { return n[0] === r.network; })[0] || [0, r.network])[1]; } },
        { key: "kind", label: "قالب", render: function (r) { return KIND_FA[r.kind] || r.kind; } },
        { key: "content_type", label: "نوع محتوا", render: function (r) { return r.content_type || "—"; } },
        { key: "product", label: "محصول", render: function (r) { return r.product || "—"; } },
        { key: "text", label: "متن", nosort: true, render: function (r) { return el("span", { class: "clip", title: r.text || "", text: r.text || "—" }); } },
        { key: "media", label: "رسانه", nosort: true, render: function (r) { var m = mediaUrl(r.media); return m ? el("img", { src: m, alt: "", width: "40", height: "40", loading: "lazy", style: "border-radius:6px;object-fit:cover" }) : "—"; } },
        { key: "url", label: "لینک", nosort: true, render: function (r) { return r.url ? el("a", { href: r.url, target: "_blank", rel: "noopener", text: "مشاهده ↗" }) : "—"; } },
        { key: "status", label: "وضعیت", render: function (r) { var s = PUB_ST[r.status] || ["pending", r.status]; return el("span", { class: "st " + s[0], title: r.error || "", text: s[1] }); } }
      ], f, { sortKey: "ts", limit: 100, emptyText: "با این فیلتر موردی نیست." }));
    }
    var seg = el("div", { class: "seg", role: "group", "aria-label": "شبکه" }, [["all", "همه"]].concat(NETS).map(function (n) {
      var b = el("button", { type: "button", "aria-pressed": n[0] === "all" ? "true" : "false", text: n[1] });
      b.addEventListener("click", function () { state.net = n[0]; seg.querySelectorAll("button").forEach(function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); }); render(); });
      return b;
    }));
    var kind = el("select", { "aria-label": "قالب", onchange: function (e) { state.kind = e.target.value; render(); } },
      el("option", { value: "all", text: "همه‌ی قالب‌ها" }), Object.keys(KIND_FA).map(function (k) { return el("option", { value: k, text: KIND_FA[k] }); }));
    var q = el("input", { type: "search", placeholder: "جستجو در متن یا محصول…", oninput: function (e) { state.q = e.target.value; render(); } });
    render();
    out.push(el("div", { class: "filters mt2" }, seg, kind, q), holder);
    return out;
  }

  // ------------------------------------------------------------------ router
  var nCrit = issues.filter(function (i) { return i.severity === "critical"; }).length;
  var TABS = [
    { id: "overview", fa: "نمای کلی", view: viewOverview },
    { id: "issues", fa: "مشکلات", view: viewIssues, badge: nCrit },
    { id: "pages", fa: "صفحات", view: viewPages },
    { id: "keywords", fa: "کلمات کلیدی", view: viewKeywords },
    { id: "competitors", fa: "رقبا", view: viewCompetitors },
    { id: "content", fa: "تولید محتوا", view: viewContent },
    { id: "automation", fa: "اتوماسیون", view: viewAutomation },
    { id: "history", fa: "تاریخچه‌ی انتشار", view: viewHistory },
    { id: "tech", fa: "فنی و سرعت", view: viewTech },
    { id: "trends", fa: "روند روزانه", view: viewTrends },
    { id: "roadmap", fa: "نقشه‌ی راه", view: viewRoadmap },
    { id: "integrations", fa: "اتصالات", view: viewIntegrations }
  ];
  var nav = document.getElementById("tabs"), view = document.getElementById("view");
  TABS.forEach(function (t) {
    nav.appendChild(el("a", { href: "#" + t.id, "data-tab": t.id }, t.fa, t.badge ? el("span", { class: "badge", text: fn(t.badge), "aria-label": fn(t.badge) + " بحرانی" }) : null));
  });
  function route() {
    var id = (location.hash || "#overview").slice(1);
    var t = TABS.filter(function (x) { return x.id === id; })[0] || TABS[0];
    nav.querySelectorAll("a").forEach(function (a) { if (a.getAttribute("data-tab") === t.id) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
    view.textContent = "";
    try { add(view, t.view()); } catch (e) { view.appendChild(empty("خطا در نمایش این بخش: " + e.message)); console.error(e); }
    var cur = nav.querySelector('[aria-current="page"]'); if (cur && cur.scrollIntoView) cur.scrollIntoView({ block: "nearest", inline: "nearest" });
  }
  window.addEventListener("hashchange", function () { route(); window.scrollTo(0, 0); });
  document.getElementById("updated").textContent = "به‌روزرسانی: " + fd(D.generated_jalali || "") + " ساعت " + fd((D.generated || "").slice(11, 16));
  document.getElementById("foot").textContent = "داده‌ها: خزش روزانه‌ی sepahanfelez.ir، نقشه‌ی سایت رقبا، پیشنهادهای جستجوی گوگل، time.ir" + (gscOk ? "، Search Console" : "") + (ga4Ok ? "، GA4" : "") + (psiOk ? "، PageSpeed" : "") + " — این صفحه noindex است.";
  var themes = ["auto", "light", "dark"], TFA = { auto: "پوسته: خودکار", light: "پوسته: روشن", dark: "پوسته: تیره" };
  var th = document.getElementById("theme");
  var cur = document.documentElement.getAttribute("data-theme") || "auto";
  th.textContent = TFA[cur];
  th.addEventListener("click", function () {
    cur = themes[(themes.indexOf(cur) + 1) % 3];
    if (cur === "auto") document.documentElement.removeAttribute("data-theme"); else document.documentElement.setAttribute("data-theme", cur);
    try { if (cur === "auto") localStorage.removeItem("sf-theme"); else localStorage.setItem("sf-theme", cur); } catch (e) {}
    th.textContent = TFA[cur]; route();
  });
  route();
})();

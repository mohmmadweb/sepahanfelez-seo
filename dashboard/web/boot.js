/* Session check → login form or live data from /api/data → app.js */
(function () {
  "use strict";
  var gate = document.getElementById("gate"), form = document.getElementById("gate-form"),
      input = document.getElementById("gate-pass"), msg = document.getElementById("gate-msg");
  // Never a blank page: say what is happening, give a stalled download a second (and third) try,
  // and if it still fails, say so with a button. On Iranian connections a Cloudflare response can
  // stall half-way (HTTP/3 over UDP); a fresh request usually goes through.
  var box = null;
  function status(text, retry) {
    if (!box) {
      box = document.createElement("div");
      box.setAttribute("role", "status");
      box.style.cssText = "max-width:520px;margin:18vh auto 0;padding:0 16px;text-align:center;line-height:2;color:var(--ink2,#555)";
      document.body.appendChild(box);
    }
    box.textContent = text;
    if (retry) {
      var b = document.createElement("button"); b.className = "btn primary"; b.type = "button"; b.textContent = "دوباره";
      b.style.marginTop = "12px"; b.onclick = function () { attempt = 0; loadApp(); };
      box.appendChild(document.createElement("br")); box.appendChild(b);
    }
  }
  function done() { if (box) { box.remove(); box = null; } }
  var attempt = 0;
  var FA = "۰۱۲۳۴۵۶۷۸۹";
  function fa(n) { return String(n).replace(/[0-9]/g, function (d) { return FA[d]; }); }
  // one small request, its own 20-second limit, up to 4 tries
  function getJSON(url, tries) {
    tries = tries || 4;
    var ctl = window.AbortController ? new AbortController() : null;
    var timer = setTimeout(function () { if (ctl) ctl.abort(); }, 20000);
    return fetch(url, { credentials: "same-origin", cache: "no-store", signal: ctl ? ctl.signal : undefined }).then(function (r) {
      clearTimeout(timer);
      if (r.status === 401) { var e = new Error("login"); e.login = true; throw e; }
      if (r.status === 409) { var s = new Error("stale"); s.stale = true; throw s; }
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).catch(function (e) {
      clearTimeout(timer);
      if (e.login || e.stale || tries <= 1) throw e;
      return getJSON(url, tries - 1);
    });
  }
  function getText(url, tries) {
    tries = tries || 4;
    var ctl = window.AbortController ? new AbortController() : null;
    var timer = setTimeout(function () { if (ctl) ctl.abort(); }, 30000);
    return fetch(url, { credentials: "same-origin", signal: ctl ? ctl.signal : undefined }).then(function (r) {
      clearTimeout(timer);
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.text();
    }).catch(function (e) {
      clearTimeout(timer);
      if (tries <= 1) throw e;
      return getText(url, tries - 1);
    });
  }
  // the data in small pieces (see /api/data/part on the server), three at a time
  function fetchData() {
    return getJSON("/api/data/index").then(function (ix) {
      var parts = new Array(ix.count), next = 0, got = 0;
      function worker() {
        if (next >= ix.count) return Promise.resolve();
        var i = next++;
        return getJSON("/api/data/part/" + i + "?stamp=" + ix.stamp).then(function (p) {
          parts[i] = p; got += 1;
          status("در حال دریافت داده‌ها… " + fa(got) + " از " + fa(ix.count));
          return worker();
        });
      }
      return Promise.all([worker(), worker(), worker()]).then(function () {
        var texts = {}, d = {};
        parts.forEach(function (p) { (texts[p.key] = texts[p.key] || [])[p.n] = p.text; });
        Object.keys(texts).forEach(function (k) { d[k] = JSON.parse(texts[k].join("")); });
        return d;
      });
    });
  }
  function loadApp() {
    attempt += 1;
    status(attempt === 1 ? "در حال دریافت داده‌ها…" : "اتصال کند بود؛ تلاش دوباره (" + fa(attempt) + " از ۳)…");
    return fetchData().then(function (d) {
      window.SF = d;
      gate.hidden = true;
      document.body.classList.remove("locked");
      var lo = document.getElementById("logout"); lo.hidden = false;
      lo.onclick = function () { window.SFAPI.post("/api/logout", {}).then(function () { location.reload(); }); };
      status("در حال آماده کردن صفحه…");
      return getText("app.js?v=" + (window.SF_V || Date.now())).then(function (code) {
        // an inline script runs synchronously on append, so this listener sees only its first run
        var failed = null;
        function onErr(ev) { failed = ev.message || "خطای نامشخص"; }
        window.addEventListener("error", onErr);
        var s = document.createElement("script"); s.text = code + "\n//# sourceURL=app.js";
        document.body.appendChild(s);
        window.removeEventListener("error", onErr);
        if (failed) status("خطا در نمایش داشبورد: " + failed + " — این پیام را برای پشتیبانی بفرستید.", true);
        else done();
      });
    }).catch(function (e) {
      if (e && e.login) { done(); showGate(); return; }
      if (attempt < 3) return loadApp();
      status("داده‌ها نرسید — اتصال به سرور قطع یا خیلی کند است. اگر Chrome است، صفحه را یک بار با Ctrl+Shift+R باز کنید.", true);
    });
  }
  function showGate() { document.body.classList.add("locked"); gate.hidden = false; input.focus(); }
  window.SFAPI = {
    get: function (u) { return fetch(u, { credentials: "same-origin" }).then(handle); },
    post: function (u, body) {
      return fetch(u, { method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-Requested-With": "sf" }, body: JSON.stringify(body || {}) }).then(handle);
    }
  };
  function handle(r) {
    return r.json().catch(function () { return {}; }).then(function (d) {
      if (r.status === 401) { location.reload(); throw new Error("login"); }
      if (!r.ok) throw new Error(d.detail || d.error || ("خطا " + r.status));
      return d;
    });
  }
  form.addEventListener("submit", function (e) {
    e.preventDefault(); msg.textContent = "…";
    fetch("/api/login", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: input.value }) }).then(function (r) {
      return r.json().then(function (d) {
        if (r.ok) { msg.textContent = ""; input.value = ""; loadApp(); } else { msg.textContent = d.error || "خطا"; input.select(); }
      });
    });
  });
  loadApp();
})();

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
  function loadApp() {
    attempt += 1;
    status(attempt === 1 ? "در حال دریافت داده‌ها…" : "اتصال کند بود؛ تلاش دوباره (" + attempt + " از ۳)…");
    var ctl = window.AbortController ? new AbortController() : null;
    var timer = setTimeout(function () { if (ctl) ctl.abort(); }, 45000);
    return fetch("/api/data", { credentials: "same-origin", cache: "no-store", signal: ctl ? ctl.signal : undefined }).then(function (r) {
      if (r.status === 401) { clearTimeout(timer); done(); showGate(); return; }
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json().then(function (d) {
        clearTimeout(timer);
        window.SF = d;
        gate.hidden = true;
        document.body.classList.remove("locked");
        var lo = document.getElementById("logout"); lo.hidden = false;
        lo.onclick = function () { window.SFAPI.post("/api/logout", {}).then(function () { location.reload(); }); };
        status("در حال آماده کردن صفحه…");
        var s = document.createElement("script"); s.src = "app.js?v=" + (window.SF_V || Date.now());
        s.onload = done;
        window.addEventListener("error", function (ev) {
          if ((ev.filename || "").indexOf("app.js") >= 0) status("خطا در نمایش داشبورد: " + (ev.message || "") + " — این پیام را برای پشتیبانی بفرستید.", true);
        });
        s.onerror = function () { status("فایل برنامه‌ی داشبورد نرسید. اتصال را بررسی کنید.", true); };
        document.body.appendChild(s);
      });
    }).catch(function () {
      clearTimeout(timer);
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

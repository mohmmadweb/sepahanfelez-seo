/* Session check → login form or live data from /api/data → app.js */
(function () {
  "use strict";
  var gate = document.getElementById("gate"), form = document.getElementById("gate-form"),
      input = document.getElementById("gate-pass"), msg = document.getElementById("gate-msg");
  function loadApp() {
    return fetch("/api/data", { credentials: "same-origin" }).then(function (r) {
      if (r.status === 401) { showGate(); return; }
      return r.json().then(function (d) {
        window.SF = d;
        gate.hidden = true;
        document.body.classList.remove("locked");
        var lo = document.getElementById("logout"); lo.hidden = false;
        lo.onclick = function () { window.SFAPI.post("/api/logout", {}).then(function () { location.reload(); }); };
        var s = document.createElement("script"); s.src = "app.js?v=" + Date.now(); document.body.appendChild(s);
      });
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

/* Password gate for the protected build: decrypts data.enc.js (AES-GCM, PBKDF2-SHA256) in the browser,
   then loads the app. Nothing readable is served without the password. */
(function () {
  "use strict";
  var E = window.SF_ENC;
  function b64(s) { var b = atob(s), u = new Uint8Array(b.length); for (var i = 0; i < b.length; i++) u[i] = b.charCodeAt(i); return u; }
  function decrypt(pass) {
    var enc = new TextEncoder();
    return crypto.subtle.importKey("raw", enc.encode(pass), "PBKDF2", false, ["deriveKey"]).then(function (base) {
      return crypto.subtle.deriveKey({ name: "PBKDF2", salt: b64(E.salt), iterations: E.iter, hash: "SHA-256" },
        base, { name: "AES-GCM", length: 256 }, false, ["decrypt"]);
    }).then(function (key) {
      return crypto.subtle.decrypt({ name: "AES-GCM", iv: b64(E.iv) }, key, b64(E.ct));
    }).then(function (buf) { return JSON.parse(new TextDecoder().decode(buf)); });
  }
  function start(data) {
    window.SF = data;
    var gate = document.getElementById("gate");
    if (gate) gate.remove();
    var s = document.createElement("script");
    s.src = "app.js?v=" + (E.v || "1");
    document.body.appendChild(s);
  }
  var saved = null;
  try { saved = localStorage.getItem("sf-pass"); } catch (e) {}
  var form = document.getElementById("gate-form"), input = document.getElementById("gate-pass"),
      msg = document.getElementById("gate-msg"), remember = document.getElementById("gate-remember");
  function attempt(pass, silent) {
    if (!silent) msg.textContent = "در حال باز کردن…";
    return decrypt(pass).then(function (d) {
      try { if (remember && remember.checked) localStorage.setItem("sf-pass", pass); } catch (e) {}
      start(d);
    }, function () {
      try { localStorage.removeItem("sf-pass"); } catch (e) {}
      if (!silent) { msg.textContent = "رمز درست نیست."; input.select(); }
    });
  }
  form.addEventListener("submit", function (e) { e.preventDefault(); if (input.value) attempt(input.value, false); });
  if (saved) attempt(saved, true); else input.focus();
})();

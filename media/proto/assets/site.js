/* رفتارهای کوچک سایت — همه «بهبود تدریجی»؛ بدون جاوااسکریپت هم صفحه سالم است.
 *
 *  ۱. تاریخ بروزرسانی: در زمان ساخت نوشته می‌شود و اینجا با تاریخ روزِ
 *     بازدید (تقویم شمسی مرورگر) جایگزین می‌شود تا «امروز» همیشه امروز باشد.
 *  ۲. جست‌وجوی سراسری صفحه‌ی قیمت: یک کادر، همه‌ی جدول‌ها.
 *  ۳. گالری صفحه‌ی محصول: کلیک روی بندانگشتی، تصویر اصلی را عوض می‌کند.
 */
(function () {
  'use strict';
  var FA = '۰۱۲۳۴۵۶۷۸۹', AR = '٠١٢٣٤٥٦٧٨٩';

  function faDigits(s) { return String(s).replace(/[0-9]/g, function (d) { return FA[+d]; }); }

  /* ---- ۱. تاریخ زنده ---- */
  function liveDate() {
    var els = document.querySelectorAll('[data-live-date],[data-live-short]');
    if (!els.length || !window.Intl || !Intl.DateTimeFormat) return;
    try {
      var now = new Date();
      var longF = new Intl.DateTimeFormat('fa-IR-u-ca-persian', { day: 'numeric', month: 'long', year: 'numeric' });
      var shortF = new Intl.DateTimeFormat('fa-IR-u-ca-persian', { day: '2-digit', month: '2-digit', year: 'numeric' });
      var iso = now.toISOString().slice(0, 10);
      for (var i = 0; i < els.length; i++) {
        var el = els[i];
        if (el.hasAttribute('data-live-short')) {
          el.textContent = shortF.format(now);
        } else {
          // همان ساختار سه‌تکه‌ای که در زمان ساخت نوشته می‌شود، وگرنه
          // چیدمان flex چیزی برای مرتب‌کردن ندارد و متن ساده دوباره
          // دست الگوریتم bidi می‌افتد.
          var parts = { day: '', month: '', year: '' };
          longF.formatToParts(now).forEach(function (p) {
            if (parts.hasOwnProperty(p.type)) parts[p.type] = p.value;
          });
          if (parts.day && parts.month && parts.year) {
            el.innerHTML = '';
            [['d-d', parts.day], ['d-m', parts.month], ['d-y', parts.year]].forEach(function (pair) {
              var sp = document.createElement('span');
              sp.className = pair[0];
              sp.textContent = pair[1];
              el.appendChild(sp);
            });
          } else {
            el.textContent = longF.format(now);
          }
        }
        el.setAttribute('datetime', iso);
      }
    } catch (e) { /* مرورگر قدیمی: تاریخِ زمان ساخت می‌ماند */ }
  }

  /* ---- ۱ب. ساعت زنده و تاریخ با روز هفته ----
   * تراشه‌ی ساعت هر ثانیه بروز می‌شود و تراشه‌ی تاریخ نام روز هفته را
   * هم دارد. هر دو با ساختار span ساخته می‌شوند، نه متن ساده، چون
   * چیدمان با flex است و الگوریتم دوجهته نباید دخالت کند. */
  function liveClock() {
    var clocks = document.querySelectorAll('[data-live-clock] b');
    var days = document.querySelectorAll('[data-live-day]');
    if (!clocks.length && !days.length) return;
    if (!window.Intl || !Intl.DateTimeFormat) return;

    var timeF, dayF;
    try {
      timeF = new Intl.DateTimeFormat('fa-IR', {
        hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
      dayF = new Intl.DateTimeFormat('fa-IR-u-ca-persian', {
        weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
    } catch (e) { return; }

    function put(el, cls, val) {
      var sp = el.querySelector('.' + cls);
      if (!sp) { sp = document.createElement('span'); sp.className = cls; el.appendChild(sp); }
      sp.textContent = val;
    }

    function tick() {
      var now = new Date();
      for (var i = 0; i < clocks.length; i++) {
        // ارقام فارسی از خود Intl می‌آید؛ جداکننده را هم فارسی نگه می‌داریم
        clocks[i].textContent = timeF.format(now).replace(/[\u200e\u200f]/g, '');
      }
      for (var j = 0; j < days.length; j++) {
        var el = days[j], parts = {};
        dayF.formatToParts(now).forEach(function (p) { parts[p.type] = p.value; });
        if (parts.weekday && parts.day && parts.month && parts.year) {
          el.innerHTML = '';
          put(el, 'd-w', parts.weekday);
          put(el, 'd-d', parts.day);
          put(el, 'd-m', parts.month);
          put(el, 'd-y', parts.year);
          el.setAttribute('datetime', now.toISOString().slice(0, 10));
        }
      }
    }
    tick();
    setInterval(tick, 1000);
  }

  /* ---- ۲. جست‌وجوی سراسری ---- */
  function normalise(s) {
    s = String(s == null ? '' : s);
    var out = '';
    for (var i = 0; i < s.length; i++) {
      var ch = s[i], k = FA.indexOf(ch);
      if (k < 0) k = AR.indexOf(ch);
      out += k >= 0 ? String(k) : ch;
    }
    return out.replace(/‌/g, ' ').replace(/[٫،]/g, '/').replace(/\./g, '/')
              .replace(/\s+/g, ' ').trim().toLowerCase();
  }

  function globalSearch() {
    var input = document.querySelector('[data-global-search]');
    if (!input) return;
    var count = document.querySelector('[data-global-count]');
    var cards = Array.prototype.slice.call(document.querySelectorAll('.pt-card:not(.ch-card)'));
    var rows = [];
    cards.forEach(function (card) {
      var trs = card.querySelectorAll('table.pt tbody tr');
      Array.prototype.forEach.call(trs, function (tr) {
        tr._hay = normalise(tr.getAttribute('data-name') + ' ' + tr.textContent);
        rows.push(tr);
      });
    });
    var total = rows.length;
    function apply() {
      var terms = normalise(input.value).split(' ').filter(Boolean);
      var shown = 0;
      cards.forEach(function (card) {
        var vis = 0;
        var trs = card.querySelectorAll('table.pt tbody tr');
        Array.prototype.forEach.call(trs, function (tr) {
          var ok = true;
          for (var i = 0; i < terms.length && ok; i++) if (tr._hay.indexOf(terms[i]) < 0) ok = false;
          tr.hidden = !ok; if (ok) vis++;
        });
        card.hidden = terms.length > 0 && vis === 0;
        shown += vis;
      });
      if (count) count.textContent = terms.length ? faDigits(shown) + ' کالا از ' + faDigits(total) : '';
      var changes = document.querySelector('.ch-card');
      if (changes) changes.hidden = terms.length > 0;
    }
    input.addEventListener('input', apply);
    // جست‌وجوی سرصفحه به اینجا می‌فرستد: /price/?q=…
    try {
      var q = new URLSearchParams(location.search).get('q');
      if (q) { input.value = q; apply(); input.scrollIntoView({ block: 'center' }); }
    } catch (e) {}
  }

  /* ---- ۴. جست‌وجوی سرصفحه → صفحه‌ی قیمت ---- */
  function headerSearch() {
    var box = document.querySelector('.masthead .search');
    if (!box) return;
    var input = box.querySelector('input'), btn = box.querySelector('button');
    function go() {
      var v = (input.value || '').trim();
      // نسخه‌ی لاراول نشانی را روی body می‌گذارد (/price)؛ پروتوتایپ ایستا /price/ است.
      var base = document.body.getAttribute('data-price-url') || '/price/';
      location.href = base + (v ? '?q=' + encodeURIComponent(v) : '');
    }
    if (btn) btn.addEventListener('click', go);
    input.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); go(); } });
  }

  /* ---- ۳. گالری محصول ---- */
  function gallery() {
    var main = document.getElementById('gmain');
    if (!main) return;
    var thumbs = document.querySelectorAll('.gallery-thumbs .thumb');
    Array.prototype.forEach.call(thumbs, function (b) {
      b.addEventListener('click', function () {
        main.src = b.getAttribute('data-src');
        Array.prototype.forEach.call(thumbs, function (x) { x.classList.remove('is-on'); });
        b.classList.add('is-on');
      });
    });
    // کلیک روی تصویر اصلی: لایت‌باکس را از همان عکسی باز کن که الان
    // دیده می‌شود، نه همیشه از اول.
    var wrap = main.closest('.gallery-main');
    if (wrap) wrap.addEventListener('click', function () {
      var srcs = [].map.call(document.querySelectorAll('.gallery .lb-src'),
        function (a) { return a.getAttribute('data-full'); });
      var cur = main.getAttribute('src');
      var at = srcs.indexOf(cur);
      if (window.__lightbox) {
        var items = [].map.call(document.querySelectorAll('.gallery .lb-src'), function (a) {
          return { full: a.getAttribute('data-full'),
                   thumb: (a.querySelector('img') || {}).src,
                   alt: a.getAttribute('aria-label') || '' };
        });
        if (items.length) window.__lightbox.open(items, at < 0 ? 0 : at);
      }
    });
  }

  function init() {
    liveDate(); liveClock(); globalSearch(); gallery(); headerSearch();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();

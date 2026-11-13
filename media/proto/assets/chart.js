/* نمودار تاریخچه‌ی قیمت — SVG درون‌خطی، بدون کتابخانه.
 *
 * داده از کجا می‌آید: در نسخه‌ی ایستا فقط دو نقطه‌ی واقعی داریم (آخرین قیمت
 * ثبت‌شده و قیمت روز). بین این دو، یک سری روزانه‌ی «نمونه» با گام‌های کوچک
 * ساخته می‌شود تا شکل نمودار و کنترل‌های آن دیده شود؛ زیر نمودار صریحاً
 * نوشته می‌شود که سری نمایشی است. در نسخه‌ی لاراول (پوشه‌ی laravel/)
 * هر نمودار data-src دارد و تاریخچه‌ی واقعی ثبت قیمت‌ها را از
 * /rd/chart/product/{id} و /rd/chart/category/{id} می‌خواند — همان جدول
 * prices که ایمپورت اکسل پر می‌کند، پس به cron نیاز ندارد.
 */
(function () {
  'use strict';
  var FA = '۰۱۲۳۴۵۶۷۸۹';
  function fa(s) { return String(s).replace(/[0-9]/g, function (d) { return FA[+d]; }); }
  function fmt(n) { return fa(Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',')); }
  function hash(s) { var h = 2166136261; for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }
  function rng(seed) { return function () { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; }; }

  // تقویم شمسی برای برچسب محور — همان الگوریتم site.js
  function toJalali(g) {
    var gy = g.getFullYear(), gm = g.getMonth() + 1, gd = g.getDate();
    var gdm = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
    var jy = gy <= 1600 ? 0 : 979; gy -= gy <= 1600 ? 621 : 1600;
    var gy2 = gm > 2 ? gy + 1 : gy;
    var days = 365 * gy + Math.floor((gy2 + 3) / 4) - Math.floor((gy2 + 99) / 100) + Math.floor((gy2 + 399) / 400) - 80 + gd + gdm[gm - 1];
    jy += 33 * Math.floor(days / 12053); days %= 12053;
    jy += 4 * Math.floor(days / 1461); days %= 1461;
    if (days > 365) { jy += Math.floor((days - 1) / 365); days = (days - 1) % 365; }
    var jm = days < 186 ? 1 + Math.floor(days / 31) : 7 + Math.floor((days - 186) / 30);
    var jd = 1 + (days < 186 ? days % 31 : (days - 186) % 30);
    return [jy, jm, jd];
  }
  // شمسی → میلادی. معکوس toJalali بالا؛ برای بازه‌ی دلخواه لازم است.
  function toGregorian(jy, jm, jd) {
    var gy = jy <= 979 ? 621 : 1600; jy -= jy <= 979 ? 0 : 979;
    var days = 365 * jy + Math.floor(jy / 33) * 8 + Math.floor(((jy % 33) + 3) / 4) + 78 + jd +
               (jm < 7 ? (jm - 1) * 31 : (jm - 7) * 30 + 186);
    gy += 400 * Math.floor(days / 146097); days %= 146097;
    if (days > 36524) {
      gy += 100 * Math.floor(--days / 36524); days %= 36524;
      if (days >= 365) days++;
    }
    gy += 4 * Math.floor(days / 1461); days %= 1461;
    if (days > 365) { gy += Math.floor((days - 1) / 365); days = (days - 1) % 365; }
    var gd = days + 1;
    var sal_a = [0, 31, (gy % 4 === 0 && gy % 100 !== 0) || gy % 400 === 0 ? 29 : 28,
                 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    var gm = 0;
    for (gm = 1; gm <= 12 && gd > sal_a[gm]; gm++) gd -= sal_a[gm];
    return new Date(gy, gm - 1, gd);
  }

  var MONTHS = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند'];
  function label(d) { var j = toJalali(d); return fa(j[2]) + ' ' + MONTHS[j[1] - 1]; }

  // طول هر «پله»ی قیمت برحسب بازه. قیمت کارخانه هر چند روز یک‌بار عوض
  // می‌شود، ولی اگر گام را همیشه ۷ بگذاریم نمودار ۱۴روزه و ۳۶۵روزه یک
  // شکل می‌شوند. گام با بازه بزرگ می‌شود تا هر نما تفکیک خودش را داشته باشد.
  function stepFor(days) {
    if (days <= 21) return 1;      // روزانه: هر روز یک نقطه
    if (days <= 100) return 4;     // هفتگی
    if (days <= 200) return 12;    // ماهانه
    return 26;                     // سالانه
  }

  function series(prev, cur, days, seed, endDate) {
    // مسیر نرم از prev به cur با نوسان‌های کوچک؛ نقطه‌ی آخر دقیقاً cur است
    var r = rng(seed), out = [], today = endDate ? new Date(endDate) : new Date();
    if (!prev) prev = cur;
    var step = stepFor(days);
    var steps = Math.max(2, Math.ceil(days / step));
    var levels = [];
    for (var s = 0; s < steps; s++) {
      var t = steps > 1 ? s / (steps - 1) : 1;
      var target = prev + (cur - prev) * t;
      var noise = (r() - 0.5) * Math.abs(cur - prev || cur * 0.02) * 0.25;
      levels.push(s === steps - 1 ? cur : Math.round((target + noise) / 1000) * 1000);
    }
    // برای بازه‌های بلند هر روز یک نقطه نمی‌کشیم؛ نمونه‌برداری می‌کنیم تا
    // تعداد نقطه‌ها زیر ~۱۸۰ بماند و هاور روی نقطه‌ها دقیق کار کند.
    var every = Math.max(1, Math.ceil(days / 180));
    for (var i = days - 1; i >= 0; i -= every) {
      var d = new Date(today); d.setDate(today.getDate() - i);
      var idx = Math.min(steps - 1, Math.floor((days - 1 - i) / step));
      out.push({ d: d, v: levels[idx] });
    }
    // نقطه‌ی پایان همیشه باید دقیقاً روز پایانی و قیمت روز باشد
    var last = out[out.length - 1];
    if (!last || last.d.getTime() !== today.getTime()) {
      out.push({ d: new Date(today), v: cur });
    } else { last.v = cur; }
    return out;
  }

  function draw(el, data) {
    // R حاشیه‌ی راست است و برچسب محور قیمت از W-R+4 شروع می‌شود و به راست
    // می‌رود؛ عدد هفت‌رقمی فارسی حدود ۵۰px می‌خواهد، پس R باید ≥۵۶ باشد
    // وگرنه آخرین رقم بیرون از viewBox بریده می‌شود.
    // عرض viewBox همان عرض واقعی ظرف است (بین ۳۰۰ و ۶۶۰) تا متن محورها
    // اندازه‌ی واقعی بماند؛ با viewBox ثابت ۶۶۰، روی موبایل برچسب‌ها به
    // حدود ۵ پیکسل کوچک می‌شدند و خوانده نمی‌شدند.
    var box0 = el.querySelector('.chart-svg');
    var W = Math.max(300, Math.min(660, Math.round((box0 && box0.clientWidth) || 660)));
    var H = W < 480 ? 220 : 240, L = 12, R = 64, T = 18, B = 34;
    var vs = data.map(function (p) { return p.v; });
    var min = Math.min.apply(null, vs), max = Math.max.apply(null, vs);
    if (max === min) { max = min * 1.02; min = min * 0.98; }
    var pad = (max - min) * 0.12; min -= pad; max += pad;
    var x = function (i) { return L + (W - L - R) * i / (data.length - 1); };
    var y = function (v) { return T + (H - T - B) * (1 - (v - min) / (max - min)); };
    var pts = data.map(function (p, i) { return x(i).toFixed(1) + ',' + y(p.v).toFixed(1); });
    var line = 'M' + pts.join(' L');
    var area = line + ' L' + x(data.length - 1).toFixed(1) + ',' + (H - B) + ' L' + x(0).toFixed(1) + ',' + (H - B) + ' Z';
    var last = data[data.length - 1], first = data[0];
    var up = last.v >= first.v, col = up ? '#0A6E44' : '#B42332';
    var grid = '';
    for (var g = 0; g < 4; g++) {
      var gv = min + (max - min) * g / 3, gy = y(gv);
      grid += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + gy.toFixed(1) + '" y2="' + gy.toFixed(1) + '" stroke="#DCE3EB" stroke-dasharray="3 4"/>' +
              '<text x="' + (W - R + 4) + '" y="' + (gy - 4).toFixed(1) + '" text-anchor="start" font-size="12" fill="#59677A">' + fmt(gv) + '</text>';
    }
    var ticks = '';
    var n = Math.min(W < 480 ? 3 : 6, data.length);
    for (var k = 0; k < n; k++) {
      var i = Math.round((data.length - 1) * k / (n - 1));
      ticks += '<text x="' + x(i).toFixed(1) + '" y="' + (H - 10) + '" text-anchor="' + (k === 0 ? 'start' : k === n - 1 ? 'end' : 'middle') + '" font-size="12" fill="#59677A">' + label(data[i].d) + '</text>';
    }
    var id = 'g' + hash(el.id || Math.random().toString()).toString(36);
    el.querySelector('.chart-svg').innerHTML =
      '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="نمودار قیمت" direction="ltr">' +
      '<defs><linearGradient id="' + id + '" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="' + col + '" stop-opacity=".22"/><stop offset="1" stop-color="' + col + '" stop-opacity="0"/></linearGradient></defs>' +
      grid + '<path d="' + area + '" fill="url(#' + id + ')"/>' +
      '<path d="' + line + '" fill="none" stroke="' + col + '" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>' +
      '<circle cx="' + x(data.length - 1).toFixed(1) + '" cy="' + y(last.v).toFixed(1) + '" r="5" fill="#fff" stroke="' + col + '" stroke-width="2.5"/>' +
      ticks +
      // لایه‌ی هاور: خط عمودی و نقطه‌ی برجسته، در حالت عادی پنهان.
      '<g class="chart-hover" style="opacity:0;pointer-events:none">' +
        '<line y1="' + T + '" y2="' + (H - B) + '" stroke="#123152" stroke-width="1" stroke-dasharray="4 3"/>' +
        '<circle r="6" fill="#fff" stroke="' + col + '" stroke-width="3"/>' +
      '</g></svg>';
    // مختصات هر نقطه را نگه می‌داریم تا لایه‌ی هاور بتواند نزدیک‌ترین را پیدا کند.
    el._pts = data.map(function (p, i) { return { x: x(i), y: y(p.v), v: p.v, d: p.d, label: p.label }; });
    el._geo = { W: W, H: H, T: T, B: B, col: col };

    var lo = Math.min.apply(null, vs), hi = Math.max.apply(null, vs);
    var chg = first.v ? (last.v - first.v) / first.v * 100 : 0;
    var stats = el.querySelector('.chart-stats');
    if (el.__bindHover) { /* re-bound below */ }
    if (stats) stats.innerHTML =
      '<span><i>کمترین</i><b class="num">' + fmt(lo) + '</b></span>' +
      '<span><i>بیشترین</i><b class="num">' + fmt(hi) + '</b></span>' +
      '<span><i>تغییر بازه</i><b class="num ' + (chg >= 0 ? 'up' : 'down') + '">' + (chg >= 0 ? '+' : '') + fa(chg.toFixed(1)) + '٪</b></span>';

    bindHover(el);
  }

  /* ---- داده‌ی واقعی ----
   * در نسخه‌ی لاراول هر نمودار data-src دارد: نشانی‌ای که تاریخچه‌ی ثبت
   * قیمت را از جدول prices می‌دهد، به شکل {points:[["2026-08-01",1490000],…]}.
   * هر نقطه یک «ثبت» است و قیمت تا ثبت بعدی ثابت می‌ماند، پس سری روزانه
   * پله‌ای ساخته می‌شود. اگر تاریخچه کمتر از دو روز باشد، به‌جای عدد
   * ساختگی پیام «تاریخچه‌ی کافی نیست» می‌آید — مگر data-sample="1" باشد که
   * همان سری نمایشی را با توضیحش نشان می‌دهد. */
  var CACHE = {};
  function load(src) {
    if (!CACHE[src]) {
      CACHE[src] = fetch(src, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(function (j) {
          return (j.points || []).map(function (p) {
            var a = String(p[0]).split('-');
            return { d: new Date(+a[0], +a[1] - 1, +a[2]), v: +p[1] };
          }).filter(function (p) { return p.v > 0; });
        })
        .catch(function () { return []; });
    }
    return CACHE[src];
  }

  function realSeries(points, days, endDate) {
    if (!points.length) return [];
    var end = endDate ? new Date(endDate) : new Date();
    end.setHours(0, 0, 0, 0);
    var start = new Date(end); start.setDate(end.getDate() - days + 1);
    var first = new Date(points[0].d); first.setHours(0, 0, 0, 0);
    if (first > start) start = first;
    var out = [], k = 0, v = points[0].v;
    var every = Math.max(1, Math.ceil(days / 180)), n = 0, last = null;
    for (var d = new Date(start); d <= end; d.setDate(d.getDate() + 1), n++) {
      while (k < points.length && points[k].d <= d) { v = points[k].v; k++; }
      // هر روزی که قیمت در آن عوض شد حتماً بماند، حتی وقتی نمونه‌برداری می‌کنیم.
      if (n % every === 0 || v !== last) out.push({ d: new Date(d), v: v });
      last = v;
    }
    if (out.length && out[out.length - 1].d.getTime() !== end.getTime()) out.push({ d: new Date(end), v: v });
    return out.length >= 2 ? out : [];
  }

  function empty(el) {
    el.querySelector('.chart-svg').innerHTML =
      '<p class="chart-empty">هنوز تاریخچه‌ی کافی برای رسم نمودار این کالا ثبت نشده است. قیمت روز در جدول بالا آمده است.</p>';
    var st = el.querySelector('.chart-stats'); if (st) st.innerHTML = '';
  }

  function setup(el) {
    var cur = +el.getAttribute('data-price') || 0, prev = +el.getAttribute('data-prev') || cur;
    if (!cur) return;
    var seed = hash(el.getAttribute('data-key') || el.id || 'x');
    var days = +el.getAttribute('data-days') || 90;
    var src = el.getAttribute('data-src');
    var note = el.querySelector('.chart-note');
    function demo(dd, endDate) { draw(el, series(prev, cur, dd, seed, endDate)); }
    function render(dd, endDate) {
      if (!src) return demo(dd, endDate);
      var token = el.__token = {};
      load(src).then(function (points) {
        if (el.__token !== token) return;            // یک کلیک تازه‌تر جا گرفته
        var s = realSeries(points, dd, endDate);
        if (s.length) {
          if (note && el.getAttribute('data-note-real')) note.textContent = el.getAttribute('data-note-real');
          draw(el, s);
        } else if (el.getAttribute('data-sample') === '1') {
          if (note && el.getAttribute('data-note-sample')) note.textContent = el.getAttribute('data-note-sample');
          demo(dd, endDate);
        } else {
          if (note) note.textContent = '';
          empty(el);
        }
      });
    }
    var btns = el.querySelectorAll('[data-range]');

    function clearOn() {
      Array.prototype.forEach.call(btns, function (x) {
        x.classList.remove('is-on'); x.setAttribute('aria-pressed', 'false');
      });
      var ct = el.querySelector('[data-cr-toggle]');
      if (ct) ct.classList.remove('is-on');
    }

    if (!el.__rangeBound) {
      el.__rangeBound = true;
      Array.prototype.forEach.call(btns, function (b) {
        b.addEventListener('click', function () {
          clearOn();
          b.classList.add('is-on'); b.setAttribute('aria-pressed', 'true');
          hidePanel();
          el.__render(+b.getAttribute('data-range'));
        });
      });
      bindCustom(el, clearOn);
    }
    el.__render = render;

    function hidePanel() {
      var p = el.querySelector('.cr-panel'), t = el.querySelector('[data-cr-toggle]');
      if (p) p.hidden = true;
      if (t) t.setAttribute('aria-expanded', 'false');
    }

    render(days);
  }

  /* ---- بازه‌ی دلخواه ----
   * کاربر شروع و پایان را به تاریخ شمسی می‌دهد. ورودی‌ها سال/ماه/روز جداست
   * چون تقویم بومی مرورگر میلادی است و برای کاربر فارسی گیج‌کننده. */
  function bindCustom(el, clearOn) {
    var toggle = el.querySelector('[data-cr-toggle]');
    var panel = el.querySelector('.cr-panel');
    if (!toggle || !panel) return;
    var err = panel.querySelector('.cr-err');
    var apply = panel.querySelector('[data-cr-apply]');

    toggle.addEventListener('click', function () {
      var open = panel.hidden;
      panel.hidden = !open;
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (open) { var f = panel.querySelector('input'); if (f) f.focus(); }
    });

    // ارقام فارسی و عربی را به لاتین برگردان تا کاربر با کیبورد فارسی
    // هم بتواند تایپ کند.
    function digits(v) {
      return String(v)
        .replace(/[۰-۹]/g, function (c) { return c.charCodeAt(0) - 1776; })
        .replace(/[٠-٩]/g, function (c) { return c.charCodeAt(0) - 1632; })
        .replace(/[^0-9]/g, '');
    }

    function readTriple(which) {
      var box = panel.querySelector('[data-cr="' + which + '"]');
      var y = +digits(box.querySelector('.cr-y').value),
          m = +digits(box.querySelector('.cr-m').value),
          d = +digits(box.querySelector('.cr-d').value);
      if (!y || !m || !d) return null;
      if (m < 1 || m > 12) return null;
      if (d < 1 || d > 31) return null;
      if (m > 6 && d > 30) return null;          // نیمه‌ی دوم سال ۳۰ روزه است
      return toGregorian(y, m, d);
    }

    function fail(msg) {
      err.textContent = msg; err.hidden = false;
    }

    apply.addEventListener('click', function () {
      err.hidden = true;
      var a = readTriple('from'), b = readTriple('to');
      if (!a) return fail('تاریخ شروع کامل و معتبر نیست. سال، ماه و روز را وارد کنید.');
      if (!b) return fail('تاریخ پایان کامل و معتبر نیست. سال، ماه و روز را وارد کنید.');
      if (a >= b) return fail('تاریخ شروع باید پیش از تاریخ پایان باشد.');
      var today = new Date(); today.setHours(0, 0, 0, 0);
      if (b > today) return fail('تاریخ پایان از امروز جلوتر است.');
      var dd = Math.round((b - a) / 86400000) + 1;
      if (dd < 3) return fail('بازه باید دست‌کم سه روز باشد.');
      clearOn();
      toggle.classList.add('is-on');
      el.__render(dd, b);
    });

    panel.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); apply.click(); }
    });

    // نمایش ارقام به فارسی، چون بقیه‌ی اعداد سایت فارسی است و کادر لاتین
    // وسط صفحه ناهماهنگ دیده می‌شود.
    var FAD = '۰۱۲۳۴۵۶۷۸۹';
    Array.prototype.forEach.call(panel.querySelectorAll('input'), function (inp) {
      inp.addEventListener('input', function () {
        var raw = digits(inp.value);
        var max = +inp.getAttribute('data-max') || 9999;
        if (raw && +raw > max) raw = raw.slice(0, -1);
        inp.value = raw.replace(/[0-9]/g, function (d) { return FAD[+d]; });
      });
    });
  }

  /* ---- هاور: اطلاعات همان نقطه ----
   * یک tooltip روی نزدیک‌ترین نقطه‌ی داده. با ماوس و با لمس کار می‌کند و
   * با صفحه‌کلید هم (فلش چپ/راست) تا با موس‌نداشتن از دست نرود. */
  function bindHover(el) {
    var svg = el.querySelector('svg');
    if (!svg || !el._pts || !el._pts.length) return;
    var tip = el.querySelector('.chart-tip');
    if (!tip) {
      tip = document.createElement('div');
      tip.className = 'chart-tip';
      tip.setAttribute('role', 'status');
      el.querySelector('.chart-svg').appendChild(tip);
    }
    var g = svg.querySelector('.chart-hover');
    var line = g.querySelector('line'), dot = g.querySelector('circle');
    var geo = el._geo, pts = el._pts, idx = -1;

    function show(i) {
      if (i < 0 || i >= pts.length) return;
      idx = i;
      var p = pts[i];
      line.setAttribute('x1', p.x); line.setAttribute('x2', p.x);
      dot.setAttribute('cx', p.x); dot.setAttribute('cy', p.y);
      g.style.opacity = '1';

      var when = p.label ? fa(String(p.label).replace(/-/g, ' ')) : (p.d ? label(p.d) : '');
      // تغییر نسبت به نقطه‌ی قبل — همان چیزی که خریدار دنبالش است.
      // مقایسه با آخرین قیمتِ *متفاوت*، نه با روز قبل: قیمت کارخانه چند روز
      // ثابت می‌ماند و مقایسه با روز قبل همیشه «بدون تغییر» می‌داد.
      var delta = '';
      var prevDiff = -1;
      for (var k = i - 1; k >= 0; k--) { if (pts[k].v !== p.v) { prevDiff = k; break; } }
      if (prevDiff >= 0 && pts[prevDiff].v) {
        var dv = p.v - pts[prevDiff].v, dp = dv / pts[prevDiff].v * 100;
        delta = '<span class="' + (dv > 0 ? 'up' : 'down') + '">' +
                (dv > 0 ? '▲ +' : '▼ ') + fa(Math.abs(dp).toFixed(1)) + '٪' +
                ' (' + (dv > 0 ? '+' : '−') + fmt(Math.abs(dv)) + ' ریال)</span>';
      } else if (i > 0) {
        delta = '<span class="flat">بدون تغییر نسبت به ثبت قبلی</span>';
      }
      tip.innerHTML = '<b class="num">' + fmt(p.v) + '</b> <span class="u">ریال</span>' +
                      (when ? '<i>' + when + '</i>' : '') + delta;

      // جایگذاری افقی با در نظر گرفتن لبه‌ها (نمودار ممکن است باریک باشد)
      var box = svg.getBoundingClientRect();
      var px = p.x / geo.W * box.width;
      var py = p.y / geo.H * box.height;
      tip.style.left = px + 'px';
      tip.style.top = py + 'px';
      tip.classList.toggle('flip-x', px > box.width * 0.6);
      tip.classList.toggle('flip-y', py < 70);
      tip.style.opacity = '1';
    }

    function hide() { g.style.opacity = '0'; tip.style.opacity = '0'; idx = -1; }

    function nearest(clientX) {
      var box = svg.getBoundingClientRect();
      var vx = (clientX - box.left) / box.width * geo.W;
      var best = 0, bd = Infinity;
      for (var i = 0; i < pts.length; i++) {
        var d = Math.abs(pts[i].x - vx);
        if (d < bd) { bd = d; best = i; }
      }
      return best;
    }

    svg.addEventListener('mousemove', function (e) { show(nearest(e.clientX)); });
    svg.addEventListener('mouseleave', hide);
    svg.addEventListener('touchstart', function (e) {
      if (e.touches[0]) show(nearest(e.touches[0].clientX));
    }, { passive: true });
    svg.addEventListener('touchmove', function (e) {
      if (e.touches[0]) show(nearest(e.touches[0].clientX));
    }, { passive: true });
    svg.addEventListener('touchend', hide);

    // دسترسی با صفحه‌کلید
    svg.setAttribute('tabindex', '0');
    svg.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowLeft')  { e.preventDefault(); show(idx <= 0 ? pts.length - 1 : idx - 1); }
      if (e.key === 'ArrowRight') { e.preventDefault(); show(idx < 0 || idx >= pts.length - 1 ? 0 : idx + 1); }
      if (e.key === 'Escape') hide();
    });
    svg.addEventListener('blur', hide);
  }

  // مودال نمودار برای ردیف‌های جدول
  function modal() {
    var dlg = document.getElementById('chart-dialog');
    if (!dlg) return;
    var box = dlg.querySelector('.chart'), ttl = dlg.querySelector('.chart-title');
    document.addEventListener('click', function (e) {
      var b = e.target.closest('[data-chart-row]');
      if (!b) return;
      e.preventDefault();
      var tr = b.closest('tr');
      var name = tr.getAttribute('data-name') || '';
      box.setAttribute('data-price', tr.getAttribute('data-price') || '0');
      box.setAttribute('data-prev', tr.getAttribute('data-prev') || tr.getAttribute('data-price') || '0');
      box.setAttribute('data-key', name);
      if (tr.getAttribute('data-src')) box.setAttribute('data-src', tr.getAttribute('data-src'));
      else box.removeAttribute('data-src');
      ttl.textContent = 'نمودار قیمت ' + name.replace(/[0-9]/g, function (d) { return FA[+d]; });
      // بازه را به پیش‌فرض همین نمودار برگردان، نه به اولین دکمه؛ وگرنه
      // دکمه‌ی روشن با نموداری که کشیده می‌شود یکی نبود.
      var def = box.getAttribute('data-days') || '90';
      Array.prototype.forEach.call(box.querySelectorAll('[data-range]'), function (x) {
        var on = x.getAttribute('data-range') === def;
        x.classList.toggle('is-on', on);
        x.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
      // حالت بازه‌ی دلخواهِ ردیف قبلی نباید روی ردیف بعدی بماند
      var ct = box.querySelector('[data-cr-toggle]'), cp = box.querySelector('.cr-panel');
      if (ct) { ct.classList.remove('is-on'); ct.setAttribute('aria-expanded', 'false'); }
      if (cp) {
        cp.hidden = true;
        Array.prototype.forEach.call(cp.querySelectorAll('input'), function (i) { i.value = ''; });
        var ce = cp.querySelector('.cr-err'); if (ce) ce.hidden = true;
      }
      // اول باز، بعد رسم: نمودار عرض ظرف را می‌خواند و دیالوگ بسته عرض ندارد.
      if (typeof dlg.showModal === 'function') dlg.showModal(); else dlg.setAttribute('open', '');
      setup(box);
    });
    dlg.addEventListener('click', function (e) { if (e.target === dlg || e.target.closest('[data-close]')) dlg.close ? dlg.close() : dlg.removeAttribute('open'); });
  }

  function init() {
    Array.prototype.forEach.call(document.querySelectorAll('.chart[data-price]'), setup);
    modal();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();

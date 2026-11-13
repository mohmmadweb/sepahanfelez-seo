/* جست‌وجوی سراسری سایت — محصول، دسته، مجله و صفحه‌ها در یک کادر.
 *
 * فهرست یک‌بار از /assets/search-index.json گرفته می‌شود (حدود ۶۰ کیلوبایت)
 * و بعد همه‌چیز سمت مرورگر انجام می‌شود، پس تایپ‌کردن هیچ رفت‌وبرگشتی به
 * سرور ندارد. بارگیری تنبل است: تا کاربر کادر را لمس نکند دانلود نمی‌شود.
 *
 * بعد از اتصال به بک‌اند: همین فایل را یک اندپوینت لاراول با همان ساختار
 * برمی‌گرداند و این کد دست‌نخورده می‌ماند. اگر بخواهید جست‌وجو سمت سرور
 * باشد، فقط search() را با یک fetch عوض کنید.
 */
(function () {
  'use strict';

  var FA = '۰۱۲۳۴۵۶۷۸۹', AR = '٠١٢٣٤٥٦٧٨٩';
  var INDEX = null, LOADING = null;

  /* ---- یکسان‌سازی متن فارسی ----
   * کاربر «ي» عربی، «ك» عربی، ارقام فارسی، نیم‌فاصله و «/» یا «.» به‌جای
   * ممیز می‌نویسد. بدون این، «چشمه ۵/۵» با «چشمه 5.5» تطبیق نمی‌خورد. */
  function norm(s) {
    s = String(s == null ? '' : s);
    var out = '';
    for (var i = 0; i < s.length; i++) {
      var ch = s[i], k = FA.indexOf(ch);
      if (k < 0) k = AR.indexOf(ch);
      if (k >= 0) { out += k; continue; }
      if (ch === 'ي') ch = 'ی';
      else if (ch === 'ك') ch = 'ک';
      else if (ch === 'ۀ' || ch === 'ة') ch = 'ه';
      else if (ch === 'أ' || ch === 'إ' || ch === 'آ') ch = 'ا';
      else if (ch === '‌') ch = ' ';          // نیم‌فاصله
      else if ('.،٫-_'.indexOf(ch) >= 0) ch = '/';
      out += ch;
    }
    return out.replace(/[ً-ٰٟ]/g, '')   // اعراب
              .replace(/\s+/g, ' ').trim().toLowerCase();
  }

  function load() {
    if (INDEX) return Promise.resolve(INDEX);
    if (LOADING) return LOADING;
    LOADING = fetch('/assets/search-index.json', { credentials: 'same-origin' })
      .then(function (r) {
        if (!r.ok) throw new Error('index ' + r.status);
        return r.json();
      })
      .then(function (rows) {
        INDEX = rows.map(function (r) {
          r._t = norm(r.t);
          r._all = norm(r.t + ' ' + (r.s || '') + ' ' + (r.x || ''));
          return r;
        });
        return INDEX;
      });
    return LOADING;
  }

  /* ---- امتیازدهی ----
   * چند سیگنال، به ترتیب اهمیت: تطبیق کامل عنوان، شروع عنوان، همه‌ی
   * کلمه‌ها در عنوان، همه‌ی کلمه‌ها در متن. وزن نوع (محصول > دسته > مقاله)
   * فقط تفاوت‌های نزدیک را می‌شکند، نه اینکه یک مقاله‌ی بی‌ربط را بالا ببرد. */
  function score(rec, q, words) {
    var t = rec._t, all = rec._all, sc = 0, i;
    if (t === q) sc += 1000;
    else if (t.indexOf(q) === 0) sc += 600;
    else if (t.indexOf(q) >= 0) sc += 400;

    var inTitle = 0, inAll = 0, inSub = 0;
    var sub = norm(rec.s || '');
    for (i = 0; i < words.length; i++) {
      if (t.indexOf(words[i]) >= 0) inTitle++;
      if (sub.indexOf(words[i]) >= 0) inSub++;
      if (all.indexOf(words[i]) >= 0) inAll++;
    }
    if (inAll < words.length) return 0;            // همه‌ی کلمه‌ها باید باشند

    // تطبیق در عنوان بسیار مهم‌تر از تطبیق در متن است. قبلاً هر تطبیقِ
    // متنی ۳۰ امتیاز می‌گرفت و چند کلمه‌ی پراکنده در بدنه‌ی یک مقاله،
    // صفحه‌ای را که همان کلمه در عنوانش بود عقب می‌انداخت.
    sc += inTitle * 260 + inSub * 60 + inAll * 8;
    if (!inTitle && !inSub) sc -= 150;             // فقط در متن پیدا شده

    // صفحه‌ی مقصد بر آیتم مقدم است: کسی که «حصاری» می‌زند اول صفحه‌ی
    // دسته را می‌خواهد نه یکی از سیزده کالای داخلش؛ «قیمت» هم یعنی
    // صفحه‌ی قیمت، نه مقاله‌ای که کلمه در عنوانش آمده.
    if ((rec.k === 'cat' || rec.k === 'page') && inTitle === words.length) sc += 320;
    sc += (rec.w || 0) / 10;
    sc -= Math.min(t.length, 60) / 20;             // عنوان کوتاه‌تر، دقیق‌تر
    return sc;
  }

  function search(q, limit) {
    var nq = norm(q);
    if (nq.length < 2 || !INDEX) return [];
    var words = nq.split(' ').filter(Boolean);
    var hits = [];
    for (var i = 0; i < INDEX.length; i++) {
      var s = score(INDEX[i], nq, words);
      if (s > 0) { hits.push({ r: INDEX[i], s: s }); }
    }
    hits.sort(function (a, b) { return b.s - a.s; });
    hits = hits.slice(0, limit || 12);
    // بهترین امتیاز هر نوع را نگه می‌داریم تا نمایش، گروه‌ها را به همان
    // ترتیب بچیند؛ وگرنه ترتیب ثابتِ «کالا اول» باعث می‌شد جست‌وجوی
    // «حصاری» سیزده کالا را جلوی صفحه‌ی خود دسته بگذارد.
    var best = {};
    hits.forEach(function (h) {
      if (best[h.r.k] == null || h.s > best[h.r.k]) best[h.r.k] = h.s;
    });
    var rows = hits.map(function (h) { return h.r; });
    rows._best = best;
    return rows;
  }

  /* ---- نمایش ---- */
  var KIND = {
    prod: { label: 'کالا', cls: 'k-prod' },
    cat: { label: 'دسته', cls: 'k-cat' },
    art: { label: 'مقاله', cls: 'k-art' },
    blogcat: { label: 'مجله', cls: 'k-art' },
    page: { label: 'صفحه', cls: 'k-page' }
  };
  var ORDER = ['prod', 'cat', 'art', 'blogcat', 'page'];
  var GROUP = { prod: 'کالاها', cat: 'دسته‌ها', art: 'مجله', blogcat: 'مجله', page: 'صفحه‌ها' };

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }
  function fa(s) { return String(s).replace(/[0-9]/g, function (d) { return FA[+d]; }); }
  function money(n) { return fa(String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',')); }

  // برجسته‌کردن بخش تطبیق‌یافته. روی متن اصلی کار می‌کنیم ولی جای تطبیق را
  // از نسخه‌ی نرمال‌شده می‌گیریم، چون طول این دو با هم فرق می‌کند؛ پس فقط
  // وقتی برجسته می‌کنیم که طول‌ها یکی باشد.
  function mark(text, q) {
    var n = norm(text);
    if (n.length !== text.length) return esc(text);
    var i = n.indexOf(q);
    if (i < 0) return esc(text);
    return esc(text.slice(0, i)) + '<mark>' + esc(text.slice(i, i + q.length)) +
           '</mark>' + esc(text.slice(i + q.length));
  }

  function render(box, rows, q) {
    if (!rows.length) {
      box.innerHTML = '<div class="gs-empty">چیزی پیدا نشد.' +
        ' می‌توانید نام کالا، چشمه یا مفتول را بنویسید،' +
        ' یا <a href="/price">همه‌ی قیمت‌ها</a> را ببینید.</div>';
      return;
    }
    var nq = norm(q), html = '', shown = {}, idx = 0;
    var best = rows._best || {};
    var order = ORDER.slice().sort(function (a, b) {
      return (best[b] == null ? -1e9 : best[b]) - (best[a] == null ? -1e9 : best[a]);
    });
    order.forEach(function (kind) {
      var group = rows.filter(function (r) { return r.k === kind; });
      if (!group.length) return;
      var title = GROUP[kind];
      if (shown[title]) title = null; else shown[title] = 1;
      if (title) html += '<div class="gs-group">' + title + '</div>';
      group.forEach(function (r) {
        var meta = r.k === 'prod' && r.p
          ? '<span class="gs-price"><b>' + money(r.p) + '</b> ریال / ' + esc(r.unit || '') + '</span>'
          : '<span class="gs-sub">' + esc(r.s || '') + '</span>';
        html += '<a class="gs-item" href="' + esc(r.u) + '" role="option" id="gs-o' + idx + '" data-i="' + idx + '">' +
                '<span class="gs-k ' + KIND[r.k].cls + '">' + KIND[r.k].label + '</span>' +
                '<span class="gs-t">' + mark(r.t, nq) + '</span>' + meta + '</a>';
        idx++;
      });
    });
    box.innerHTML = html;
  }

  function bind(input) {
    var wrap = input.closest('.search') || input.parentNode;
    wrap.classList.add('gs-wrap');
    var box = document.createElement('div');
    box.className = 'gs-results';
    box.setAttribute('role', 'listbox');
    box.hidden = true;
    wrap.appendChild(box);

    input.setAttribute('role', 'combobox');
    input.setAttribute('aria-expanded', 'false');
    input.setAttribute('aria-autocomplete', 'list');
    input.setAttribute('autocomplete', 'off');

    var active = -1, timer = null, lastQ = '';

    function close() {
      box.hidden = true; active = -1;
      input.setAttribute('aria-expanded', 'false');
      input.removeAttribute('aria-activedescendant');
    }
    function open() {
      box.hidden = false;
      input.setAttribute('aria-expanded', 'true');
    }
    function items() { return box.querySelectorAll('.gs-item'); }
    function highlight(n) {
      var list = items();
      if (!list.length) return;
      if (active >= 0 && list[active]) list[active].classList.remove('is-on');
      active = (n + list.length) % list.length;
      list[active].classList.add('is-on');
      input.setAttribute('aria-activedescendant', list[active].id);
      list[active].scrollIntoView({ block: 'nearest' });
    }

    function run() {
      var q = input.value.trim();
      if (norm(q).length < 2) { close(); lastQ = ''; return; }
      if (q === lastQ) { open(); return; }
      lastQ = q;
      load().then(function () {
        if (input.value.trim() !== q) return;      // کاربر ادامه داده
        render(box, search(q, 12), q);
        active = -1;
        open();
      }).catch(function () {
        box.innerHTML = '<div class="gs-empty">جست‌وجو در دسترس نیست. ' +
          '<a href="/price">همه‌ی قیمت‌ها</a></div>';
        open();
      });
    }

    // «ایجکسی» یعنی بدون رفرش صفحه و با تأخیر کوتاه تا هر حرف یک اجرا نشود
    input.addEventListener('input', function () {
      clearTimeout(timer);
      timer = setTimeout(run, 110);
    });
    input.addEventListener('focus', function () {
      load();                                      // پیش‌بارگیری در اولین تمرکز
      if (norm(input.value).length >= 2) run();
    });

    input.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown') { e.preventDefault(); if (box.hidden) run(); else highlight(active + 1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); highlight(active - 1); }
      else if (e.key === 'Enter') {
        var list = items();
        if (!box.hidden && active >= 0 && list[active]) { e.preventDefault(); list[active].click(); }
        else if (input.value.trim()) { e.preventDefault(); window.location.href = '/price?q=' + encodeURIComponent(input.value.trim()); }
      } else if (e.key === 'Escape') { close(); input.blur(); }
    });

    box.addEventListener('mousemove', function (e) {
      var it = e.target.closest ? e.target.closest('.gs-item') : null;
      if (it) highlight(+it.getAttribute('data-i'));
    });

    document.addEventListener('click', function (e) {
      if (!wrap.contains(e.target)) close();
    });

    // دکمه‌ی ذره‌بین کنار کادر
    var btn = wrap.querySelector('button');
    if (btn) btn.addEventListener('click', function () {
      if (input.value.trim()) window.location.href = '/price?q=' + encodeURIComponent(input.value.trim());
      else input.focus();
    });
  }

  function init() {
    var inputs = document.querySelectorAll('#q,[data-site-search]');
    Array.prototype.forEach.call(inputs, bind);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();

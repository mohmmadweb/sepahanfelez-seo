/* لایت‌باکس تصویر — مثل وقتی در تلگرام روی عکس می‌زنید.
 *
 * چرا: تا امروز کلیک روی عکس، کاربر را از صفحه بیرون می‌برد (target=_blank)
 * و برگشتنش یعنی از دست دادن جای خواندن. حالا عکس در همان صفحه بزرگ
 * می‌شود، با فلش بین عکس‌ها می‌چرخد و با ضربدر یا Escape بسته می‌شود.
 *
 * چیزی که عمداً ساده نگه داشته شده: بدون کتابخانه. کل رفتار حدود ۲۰۰ خط
 * است و وابستگی تازه‌ای به صفحه اضافه نمی‌کند — سرعت مهم‌ترین مزیت ماست.
 */
(function () {
  'use strict';
  var FA = '۰۱۲۳۴۵۶۷۸۹';
  function fa(s) { return String(s).replace(/[0-9]/g, function (d) { return FA[+d]; }); }

  var box = null, items = [], idx = 0, lastFocus = null;

  function build() {
    if (box) return box;
    box = document.createElement('div');
    box.className = 'lb';
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-modal', 'true');
    box.setAttribute('aria-label', 'نمایش تصویر');
    box.hidden = true;
    box.innerHTML =
      '<button type="button" class="lb-x" aria-label="بستن">&times;</button>' +
      '<button type="button" class="lb-nav lb-prev" aria-label="تصویر قبلی">' +
        '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5l-7 7 7 7" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg></button>' +
      '<button type="button" class="lb-nav lb-next" aria-label="تصویر بعدی">' +
        '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 5l7 7-7 7" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg></button>' +
      '<figure class="lb-stage"><img class="lb-img" alt=""><figcaption class="lb-cap"></figcaption></figure>' +
      '<div class="lb-count" aria-live="polite"></div>' +
      '<div class="lb-strip" role="tablist" aria-label="تصاویر"></div>';
    document.body.appendChild(box);

    box.querySelector('.lb-x').addEventListener('click', close);
    box.querySelector('.lb-prev').addEventListener('click', function () { go(idx - 1); });
    box.querySelector('.lb-next').addEventListener('click', function () { go(idx + 1); });
    // کلیک روی زمینه می‌بندد، ولی کلیک روی خود عکس نه
    box.addEventListener('click', function (e) {
      if (e.target === box || e.target.classList.contains('lb-stage')) close();
    });
    return box;
  }

  function render() {
    var it = items[idx];
    if (!it) return;
    var img = box.querySelector('.lb-img');
    img.src = it.full;
    img.alt = it.alt || '';
    box.querySelector('.lb-cap').textContent = it.alt || '';
    box.querySelector('.lb-count').textContent =
      items.length > 1 ? fa(idx + 1) + ' از ' + fa(items.length) : '';
    var multi = items.length > 1;
    box.querySelector('.lb-prev').hidden = !multi;
    box.querySelector('.lb-next').hidden = !multi;
    var strip = box.querySelector('.lb-strip');
    strip.hidden = !multi;
    if (multi && strip.childElementCount !== items.length) {
      strip.innerHTML = '';
      items.forEach(function (x, i) {
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'lb-th';
        b.setAttribute('aria-label', 'تصویر ' + fa(i + 1));
        b.innerHTML = '<img src="' + (x.thumb || x.full) + '" alt="" loading="lazy">';
        b.addEventListener('click', function () { go(i); });
        strip.appendChild(b);
      });
    }
    Array.prototype.forEach.call(strip.children, function (b, i) {
      b.classList.toggle('is-on', i === idx);
      if (i === idx && b.scrollIntoView) b.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    });
    // پیش‌بارگیری همسایه‌ها تا چرخش بدون مکث باشد
    [idx - 1, idx + 1].forEach(function (j) {
      var n = items[(j + items.length) % items.length];
      if (n) { var p = new Image(); p.src = n.full; }
    });
  }

  function go(n) {
    if (!items.length) return;
    idx = (n + items.length) % items.length;
    render();
  }

  function open(list, start) {
    build();
    items = list; idx = start || 0;
    lastFocus = document.activeElement;
    box.hidden = false;
    document.documentElement.classList.add('lb-open');
    render();
    box.querySelector('.lb-x').focus();
  }

  function close() {
    if (!box || box.hidden) return;
    box.hidden = true;
    document.documentElement.classList.remove('lb-open');
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  document.addEventListener('keydown', function (e) {
    if (!box || box.hidden) return;
    if (e.key === 'Escape') { e.preventDefault(); close(); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); go(idx + 1); }   // RTL: چپ یعنی بعدی
    else if (e.key === 'ArrowRight') { e.preventDefault(); go(idx - 1); }
    else if (e.key === 'Tab') {
      // تمرکز داخل لایت‌باکس بماند
      var f = box.querySelectorAll('button');
      if (!f.length) return;
      var first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });

  // کشیدن انگشت روی موبایل
  var sx = 0, sy = 0, moved = false;
  document.addEventListener('touchstart', function (e) {
    if (!box || box.hidden) return;
    sx = e.touches[0].clientX; sy = e.touches[0].clientY; moved = false;
  }, { passive: true });
  document.addEventListener('touchmove', function () { moved = true; }, { passive: true });
  document.addEventListener('touchend', function (e) {
    if (!box || box.hidden || !moved) return;
    var dx = e.changedTouches[0].clientX - sx, dy = e.changedTouches[0].clientY - sy;
    if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.5) go(dx > 0 ? idx - 1 : idx + 1);
    else if (dy > 90 && Math.abs(dy) > Math.abs(dx)) close();     // کشیدن به پایین = بستن
  }, { passive: true });

  /* ---- جمع‌آوری گروه‌های تصویر ----
   * هر عنصری با data-lb یک گروه است. عکس‌های داخلش با هم می‌چرخند.
   * لینک‌های تکیِ تصویر هم گروه یک‌نفره می‌شوند. */
  function collect(root) {
    var out = [];
    root.querySelectorAll('[data-lb-item]').forEach(function (el) {
      var full = el.getAttribute('data-full') || el.getAttribute('href') ||
                 (el.querySelector('img') || {}).src;
      if (!full) return;
      var im = el.querySelector('img');
      out.push({ full: full, thumb: im ? im.src : full,
                 alt: (im && im.alt) || el.getAttribute('aria-label') || '' });
    });
    return out;
  }

  function init() {
    document.querySelectorAll('[data-lb]').forEach(function (group) {
      var list = collect(group);
      if (!list.length) return;
      group.querySelectorAll('[data-lb-item]').forEach(function (el, i) {
        el.addEventListener('click', function (e) {
          e.preventDefault();
          open(list, i);
        });
      });
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  window.__lightbox = { open: open, close: close };
})();

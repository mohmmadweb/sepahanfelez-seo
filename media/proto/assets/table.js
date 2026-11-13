/* جست‌وجوی پیشرفته‌ی جدول قیمت.
 *
 * بهبود تدریجی: جدول کامل در HTML رندر شده و نوار فیلتر با `hidden`
 * می‌آید. این فایل که اجرا شد، نوار را باز می‌کند. اگر جاوااسکریپت
 * نیامد یا خطا خورد، کاربر جدول کامل را دارد — نه فرمی که کار نمی‌کند.
 *
 * ارقام فارسی و عربی به لاتین نرمال می‌شوند، و «/» که در این صنعت
 * جداکننده‌ی اعشار است هم پشتیبانی می‌شود، تا جست‌وجوی «۵/۵» و «5.5»
 * و «5/5» هر سه یک نتیجه بدهند.
 */
(function () {
  'use strict';

  var FA = '۰۱۲۳۴۵۶۷۸۹', AR = '٠١٢٣٤٥٦٧٨٩';

  function normalise(s) {
    s = String(s == null ? '' : s);
    var out = '';
    for (var i = 0; i < s.length; i++) {
      var ch = s[i], k = FA.indexOf(ch);
      if (k < 0) k = AR.indexOf(ch);
      out += k >= 0 ? String(k) : ch;
    }
    return out
      .replace(/‌/g, ' ')      // نیم‌فاصله = فاصله، تا «ریزبافت» هم پیدا شود
      .replace(/[٫،]/g, '/')
      .replace(/\./g, '/')
      .replace(/\s+/g, ' ')
      .trim()
      .toLowerCase();
  }

  // شمارنده باید فارسی باشد؛ بقیه‌ی صفحه فارسی است و «13» وسط متن می‌زند توی ذوق
  function faDigits(n) {
    return String(n).replace(/[0-9]/g, function (d) { return FA[+d]; });
  }

  function setup(form) {
    var table = document.getElementById(form.getAttribute('data-for'));
    if (!table) return;
    var tbody = table.tBodies[0];
    if (!tbody) return;

    var rows = Array.prototype.slice.call(tbody.rows);
    var original = rows.slice();
    var q = form.querySelector('[data-q]');
    var sortSel = form.querySelector('[data-sort]');
    var specSels = Array.prototype.slice.call(form.querySelectorAll('[data-spec]'));
    var count = form.querySelector('[data-count]');
    var reset = form.querySelector('[data-reset]');

    // متن قابل جست‌وجوی هر ردیف یک‌بار ساخته می‌شود، نه در هر کلید
    rows.forEach(function (tr) {
      tr._hay = normalise(tr.getAttribute('data-name') + ' ' + tr.textContent);
      tr._price = parseInt(tr.getAttribute('data-price') || '0', 10);
    });

    function apply() {
      var needle = normalise(q ? q.value : '');
      var terms = needle ? needle.split(' ').filter(Boolean) : [];
      var shown = 0;

      rows.forEach(function (tr) {
        var ok = true;
        for (var i = 0; i < terms.length && ok; i++) {
          if (tr._hay.indexOf(terms[i]) < 0) ok = false;
        }
        for (var j = 0; j < specSels.length && ok; j++) {
          var sel = specSels[j], want = sel.value;
          if (!want) continue;
          var got = tr.getAttribute('data-s' + sel.getAttribute('data-spec')) || '';
          if (normalise(got) !== normalise(want)) ok = false;
        }
        tr.hidden = !ok;
        if (ok) shown++;
      });

      var order = sortSel ? sortSel.value : '';
      var seq = original;
      if (order) {
        seq = original.slice().sort(function (a, b) {
          return order === 'asc' ? a._price - b._price : b._price - a._price;
        });
      }
      seq.forEach(function (tr) { tbody.appendChild(tr); });

      if (count) {
        count.textContent = shown === rows.length
          ? 'نمایش هر ' + faDigits(rows.length) + ' کد'
          : faDigits(shown) + ' کد از ' + faDigits(rows.length) + ' کد';
      }
      table.setAttribute('data-empty', shown === 0 ? 'yes' : 'no');
    }

    if (q) q.addEventListener('input', apply);
    if (sortSel) sortSel.addEventListener('change', apply);
    specSels.forEach(function (s) { s.addEventListener('change', apply); });
    if (reset) reset.addEventListener('click', function () {
      if (q) q.value = '';
      if (sortSel) sortSel.value = '';
      specSels.forEach(function (s) { s.value = ''; });
      apply();
    });

    form.hidden = false;   // فقط حالا که واقعاً کار می‌کند
    apply();
  }

  function init() {
    Array.prototype.forEach.call(
      document.querySelectorAll('.tfilter[data-for]'), setup);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

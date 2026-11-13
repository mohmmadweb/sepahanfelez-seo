/* ماشین‌حساب وزن و هزینه + امتیاز ستاره‌ای فرم دیدگاه.
 * بدون جاوااسکریپت: ماشین‌حساب با hidden پنهان می‌ماند و اعداد پایه (قیمت
 * هر مترمربع/کیلو) در متن صفحه هست؛ فرم دیدگاه هم رادیوهای معمولی دارد. */
(function () {
  'use strict';
  var FA = '۰۱۲۳۴۵۶۷۸۹';
  function fa(s) { return String(s).replace(/[0-9]/g, function (d) { return FA[+d]; }); }
  function fmt(n) { return fa(Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',')); }
  function norm(s) { return String(s || '').replace(/[۰-۹]/g, function (d) { return FA.indexOf(d); }).replace(/[٫،]/g, '.').replace('/', '.'); }

  function calc(form) {
    var price = +form.getAttribute('data-price') || 0;          // ریال به واحد فروش
    var unit = form.getAttribute('data-unit') || '';
    var kgPerUnit = +form.getAttribute('data-kg-per-unit') || 0; // وزن هر واحد فروش (kg)
    var m2PerUnit = +form.getAttribute('data-m2-per-unit') || 0; // مساحت هر واحد فروش (m²)
    var freight = JSON.parse(form.getAttribute('data-freight') || '[]');
    var minTon = +form.getAttribute('data-freight-min') || 1;
    var qty = form.querySelector('[name=qty]'), mode = form.querySelector('[name=mode]'), dest = form.querySelector('[name=dest]');
    var pick = form.querySelector('[data-pick]');
    var out = form.querySelector('.calc-out'), basis = form.querySelector('.calc-basis');
    var baseTxt = basis ? basis.innerHTML : '';
    if (pick) pick.addEventListener('change', function () {
      var v = pick.value.split('|');
      price = +v[0] || price; kgPerUnit = +v[1] || 0; m2PerUnit = +v[2] || 0;
      if (basis) basis.innerHTML = baseTxt.replace(/<b>[^<]*<\/b>/, '<b>' + pick.options[pick.selectedIndex].text + '</b>')
        .replace(/<span class="num">[^<]*<\/span>/, '<span class="num">' + fmt(price) + '</span>');
      apply();
    });
    function apply() {
      var q = parseFloat(norm(qty.value)) || 0;
      var m = mode.value;                       // unit | m2 | kg
      var units = 0;
      if (m === 'unit') units = q;
      else if (m === 'm2' && m2PerUnit) units = q / m2PerUnit;
      else if (m === 'kg' && kgPerUnit) units = q / kgPerUnit;
      var cost = units * price;
      var kg = kgPerUnit ? units * kgPerUnit : 0;
      var m2 = m2PerUnit ? units * m2PerUnit : 0;
      var tons = kg / 1000;
      var rate = dest ? (+dest.value || 0) : 0;
      var fr = rate ? Math.max(tons, minTon) * rate : 0;
      if (!q) { out.hidden = true; return; }
      out.hidden = false;
      out.innerHTML =
        '<div class="calc-row"><span>مقدار سفارش</span><b class="num">' + fa(units >= 100 ? Math.round(units) : +units.toFixed(1)) + ' ' + unit + '</b></div>' +
        (kg ? '<div class="calc-row"><span>وزن تقریبی بار</span><b class="num">' + fmt(kg) + ' کیلوگرم</b></div>' : '') +
        (m2 ? '<div class="calc-row"><span>سطح پوشش</span><b class="num">' + fa(+m2.toFixed(1)) + ' متر مربع</b></div>' : '') +
        '<div class="calc-row"><span>مبلغ کالا (مبنای روز)</span><b class="num">' + fmt(cost) + ' ریال</b></div>' +
        (!dest ? '' : rate ? '<div class="calc-row"><span>برآورد کرایه‌ی حمل' + (tons < minTon ? ' (کف ' + fa(minTon) + ' تن)' : '') + '</span><b class="num">' + fmt(fr) + ' ریال</b></div>' : '<div class="calc-row"><span>کرایه‌ی حمل</span><b>تحویل درب کارخانه / انبار</b></div>') +
        '<div class="calc-row total"><span>جمع برآورد</span><b class="num">' + fmt(cost + fr) + ' ریال</b></div>';
    }
    [qty, mode, dest].filter(Boolean).forEach(function (el) { el.addEventListener('input', apply); el.addEventListener('change', apply); });
    form.addEventListener('submit', function (e) { e.preventDefault(); apply(); });
    form.hidden = false; apply();
  }

  function stars() {
    Array.prototype.forEach.call(document.querySelectorAll('.star-input'), function (box) {
      var radios = box.querySelectorAll('input[type=radio]');
      function paint() {
        var v = 0; Array.prototype.forEach.call(radios, function (r) { if (r.checked) v = +r.value; });
        Array.prototype.forEach.call(box.querySelectorAll('label'), function (l, i) { l.classList.toggle('is-on', i < v); });
      }
      Array.prototype.forEach.call(radios, function (r) { r.addEventListener('change', paint); });
      paint();
    });
  }

  function init() {
    Array.prototype.forEach.call(document.querySelectorAll('form.calc[data-price]'), calc);
    stars();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();

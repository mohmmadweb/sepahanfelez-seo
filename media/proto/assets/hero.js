/* اسلایدر بنر صفحه‌ی اصلی — چرخش خودکار.
 *
 * الگو از ahanonline: بنر تمام‌عرض که خودِ عکس محتواست و اسلایدها
 * خودبه‌خود جلو می‌روند.
 *
 * بدون جاوااسکریپت هم سالم است: اسلایدها با scroll-snap دستی می‌لغزند و
 * نقطه‌ها لنگرند. این فایل فقط چرخش خودکار را اضافه می‌کند.
 *
 * سه محافظ که چرخش خودکار را از آزاردهنده‌بودن درمی‌آورد:
 *   • با نگه‌داشتن ماوس یا رسیدن فوکوس صفحه‌کلید، می‌ایستد
 *   • با لمس یا اسکرول دستی کاربر، می‌ایستد
 *   • اگر کاربر «کاهش حرکت» را در سیستم‌عاملش روشن کرده باشد، اصلاً
 *     شروع نمی‌شود
 * مخاطب این سایت بالای ۴۰ سال است؛ بنری که وسط خواندن جابه‌جا شود
 * بیشتر از آنکه کمک کند، آزار می‌دهد.
 */
(function () {
  'use strict';

  var DELAY = 6000;      // شش ثانیه: فرصت خواندن یک تیتر و یک خط توضیح

  function init() {
    var hero = document.querySelector('.hero');
    if (!hero) return;
    var track = hero.querySelector('.hero-track');
    var slides = track ? track.querySelectorAll('.slide') : [];
    if (!track || slides.length < 2) return;

    var dots = hero.querySelectorAll('.hero-dots a');
    var timer = null;
    var stopped = false;
    var index = 0;

    var reduce = window.matchMedia &&
                 window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    function current() {
      // RTL: scrollLeft منفی است، پس قدرمطلق می‌گیریم
      var w = track.clientWidth || 1;
      return Math.round(Math.abs(track.scrollLeft) / w);
    }

    function mark(i) {
      for (var k = 0; k < dots.length; k++) {
        if (k === i) dots[k].setAttribute('aria-current', 'true');
        else dots[k].removeAttribute('aria-current');
      }
    }

    function go(i) {
      index = (i + slides.length) % slides.length;
      var dir = getComputedStyle(track).direction === 'rtl' ? -1 : 1;
      track.scrollTo({ left: dir * index * track.clientWidth, behavior: 'smooth' });
      mark(index);
    }

    function start() {
      if (stopped || reduce || timer) return;
      timer = setInterval(function () { go(index + 1); }, DELAY);
    }

    function pause() {
      if (timer) { clearInterval(timer); timer = null; }
    }

    function stopForGood() {      // کاربر خودش دست به اسلایدر زد
      stopped = true;
      pause();
    }

    hero.addEventListener('mouseenter', pause);
    hero.addEventListener('mouseleave', start);
    hero.addEventListener('focusin', pause);
    hero.addEventListener('focusout', start);
    track.addEventListener('touchstart', stopForGood, { passive: true });
    track.addEventListener('wheel', stopForGood, { passive: true });

    for (var d = 0; d < dots.length; d++) {
      (function (n) {
        dots[n].addEventListener('click', function (e) {
          e.preventDefault();
          stopForGood();
          go(n);
        });
      })(d);
    }

    // اسکرول دستی هم نشانگر را به‌روز کند
    var settle;
    track.addEventListener('scroll', function () {
      clearTimeout(settle);
      settle = setTimeout(function () {
        index = current();
        mark(index);
      }, 120);
    }, { passive: true });

    // صفحه که پنهان شد، تایمر بی‌خود نچرخد
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) pause(); else start();
    });

    mark(0);
    start();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

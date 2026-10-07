/* Small behaviours that Wix provided with its own scripts. */
(function () {
  // Slider galleries: prev/next arrows shift the strip by one item.
  document.querySelectorAll('.sgal').forEach(function (gal) {
    var strip = gal.querySelector('.sgal-items');
    var vis = gal.querySelector('.sgal-vis');
    if (!strip || !vis) return;
    var pos = 0;
    function step(dir) {
      var item = strip.querySelector('.sgal-item');
      if (!item) return;
      var w = item.getBoundingClientRect().width + parseFloat(getComputedStyle(item).marginRight || 0);
      var max = Math.max(0, strip.scrollWidth - vis.clientWidth);
      pos = Math.min(max, Math.max(0, pos + dir * w));
      strip.style.transform = 'translateX(' + (-pos) + 'px)';
    }
    var prev = gal.querySelector('.sgal-prev'), next = gal.querySelector('.sgal-next');
    if (prev) prev.addEventListener('click', function () { step(-1); });
    if (next) next.addEventListener('click', function () { step(1); });
  });
})();

/* Product galleries: "Load More" reveals the next page of items. */
(function () {
  document.querySelectorAll('.pgal-load').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var gal = btn.closest('.pgal');
      var step = parseInt(btn.getAttribute('data-step'), 10) || 15;
      var hidden = gal.querySelectorAll('.pgal-item.is-hidden');
      for (var i = 0; i < hidden.length && i < step; i++) hidden[i].classList.remove('is-hidden');
      if (hidden.length <= step) btn.parentNode.removeChild(btn);
    });
  });
})();

/* Product page: quantity stepper and thumbnail switching. */
(function () {
  document.querySelectorAll('.pp-qty').forEach(function (box) {
    var input = box.querySelector('input'), btns = box.querySelectorAll('button');
    btns[0].addEventListener('click', function () { input.value = Math.max(1, (parseInt(input.value, 10) || 1) - 1); });
    btns[1].addEventListener('click', function () { input.value = (parseInt(input.value, 10) || 1) + 1; });
  });
  document.querySelectorAll('.pp-thumbs button').forEach(function (b) {
    b.addEventListener('click', function () {
      var main = b.closest('.pp-media').querySelector('.pp-imgbox img');
      if (main) { main.src = b.getAttribute('data-full'); main.removeAttribute('srcset'); }
    });
  });
})();

/* Mobile menu: toggle panel, close on overlay tap, expand sub-menus. */
(function () {
  var body = document.body;
  document.querySelectorAll('.wixui-mobile-menu__icon').forEach(function (t) {
    function toggle() { body.classList.toggle('menu-open'); t.setAttribute('aria-expanded', body.classList.contains('menu-open')); }
    t.addEventListener('click', toggle);
    t.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); } });
  });
  var overlay = document.getElementById('overlay-MENU_AS_CONTAINER');
  document.querySelectorAll('[id="overlay-MENU_AS_CONTAINER"]').forEach(function (o) {
    o.addEventListener('click', function () { body.classList.remove('menu-open'); });
  });
  document.querySelectorAll('.t-expandablemenu-toggle').forEach(function (b) {
    b.addEventListener('click', function (e) {
      e.preventDefault();
      var li = b.closest('.wixui-vertical-menu__item');
      li.classList.toggle('is-open');
      b.setAttribute('aria-expanded', li.classList.contains('is-open'));
    });
  });
})();

/* Back-to-top button appears after scrolling. */
(function () {
  function onScroll() { document.body.classList.toggle('scrolled', window.scrollY > 300); }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
  document.querySelectorAll('[id="BACK_TO_TOP_BUTTON"]').forEach(function (b) {
    b.addEventListener('click', function (e) { e.preventDefault(); window.scrollTo({ top: 0, behavior: 'smooth' }); });
  });
})();

/* FAQ: tabs and question search. */
(function () {
  document.querySelectorAll('.faqw').forEach(function (w) {
    var tabs = w.querySelectorAll('.faqw-tab'), lists = w.querySelectorAll('.faqw-list'), none = w.querySelector('.faqw-none');
    tabs.forEach(function (t) {
      t.addEventListener('click', function () {
        tabs.forEach(function (x) { x.classList.toggle('is-active', x === t); x.setAttribute('aria-selected', x === t); });
        lists.forEach(function (l) { l.hidden = l.getAttribute('data-tab') !== t.getAttribute('data-tab'); });
      });
    });
    var input = w.querySelector('.faqw-search input');
    if (input) input.addEventListener('input', function () {
      var q = input.value.trim().toLowerCase(), shown = 0;
      w.querySelectorAll('.faqw-item').forEach(function (it) {
        var hit = !q || it.textContent.toLowerCase().indexOf(q) >= 0;
        it.hidden = !hit;
        if (hit && !it.closest('.faqw-list').hidden) shown++;
      });
      if (none) none.hidden = shown > 0;
    });
  });
})();

/* ==========================================================================
   Home page — hero plate rotation + section scroll-reveal.
   Both no-op under prefers-reduced-motion; rotation pauses in hidden tabs.
   ========================================================================== */

(function () {
    'use strict';

    var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // ── Scroll reveal ──────────────────────────────────────────────────
    if (!reducedMotion && 'IntersectionObserver' in window) {
        document.documentElement.classList.add('js-reveal');
        var observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    entry.target.classList.add('revealed');
                    observer.unobserve(entry.target);
                }
            });
        }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });

        document.querySelectorAll('.section').forEach(function (section) {
            // Anything already in the viewport shows immediately.
            if (section.getBoundingClientRect().top < window.innerHeight) {
                section.classList.add('revealed');
            } else {
                observer.observe(section);
            }
        });
    }

    // ── Hero plate rotation ────────────────────────────────────────────
    var dataEl = document.getElementById('heroRotationImages');
    var plateFood = document.querySelector('.plate-food');
    var plateImg = plateFood ? plateFood.querySelector('img') : null;
    if (reducedMotion || !dataEl || !plateImg) return;

    var images;
    try {
        images = JSON.parse(dataEl.textContent);
    } catch (e) {
        return;
    }
    if (!Array.isArray(images) || images.length < 2) return;

    // Preload so swaps never flash empty.
    images.forEach(function (src) { (new Image()).src = src; });

    var index = Math.max(0, images.indexOf(plateImg.getAttribute('src')));
    var ROTATE_MS = 5000;
    var FADE_MS = 450;

    setInterval(function () {
        if (document.hidden) return;
        index = (index + 1) % images.length;
        plateFood.classList.add('is-fading');
        setTimeout(function () {
            plateImg.setAttribute('src', images[index]);
            plateFood.classList.remove('is-fading');
        }, FADE_MS);
    }, ROTATE_MS);
})();

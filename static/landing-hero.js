  (function () {
    var hero = document.querySelector('.hero');
    var nav = document.querySelector('nav');
    if (!hero) return;

    function fitHero() {
      hero.style.transform = 'none';
      hero.style.transformOrigin = 'top center';

      // Phones: page scrolls normally, so don't shrink the hero to fit one screen
      if (window.innerWidth <= 700) { hero.style.marginBottom = '0px'; return; }

      var navHeight = nav ? nav.getBoundingClientRect().height : 0;
      var available = window.innerHeight - navHeight;
      var contentHeight = hero.scrollHeight;

      var scale = available / contentHeight;
      if (scale > 1) scale = 1;
      if (scale < 0.82) scale = 0.82;

      hero.style.transform = 'scale(' + scale + ')';
      hero.style.marginBottom = (contentHeight * (scale - 1)) + 'px';
      // Scale changed, so re-place the playhead / markers against it.
      try {
        if (typeof updatePlayheadPosition === 'function') updatePlayheadPosition();
        if (typeof renderAllStemMarkers === 'function') renderAllStemMarkers();
        if (typeof renderAllStemSampleRegions === 'function') renderAllStemSampleRegions();
      } catch (e) {}
    }

    window.addEventListener('load', fitHero);
    window.addEventListener('resize', fitHero);
    setTimeout(fitHero, 300);
  })();

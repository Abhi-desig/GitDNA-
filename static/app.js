// Hover tooltips + timeline scrubbing. No framework, no build step.
(function () {
  const svg = document.querySelector('#organism svg');
  const tip = document.getElementById('tip');
  const slider = document.getElementById('time');
  const readout = document.getElementById('readout');
  if (!svg) return;

  const labels = JSON.parse(document.getElementById('events').textContent);
  const range = JSON.parse(document.getElementById('range').textContent);

  // ---- hover -------------------------------------------------------------
  svg.addEventListener('mouseover', function (event) {
    const el = event.target.closest('[data-e]');
    if (!el) return;
    tip.textContent = labels[el.dataset.e] || el.dataset.e;
    tip.hidden = false;
  });

  svg.addEventListener('mousemove', function (event) {
    if (tip.hidden) return;
    // Flip to the left of the cursor near the right edge so it stays on screen.
    const width = tip.offsetWidth;
    const x = event.clientX + 14 + width > window.innerWidth
      ? event.clientX - width - 14
      : event.clientX + 14;
    tip.style.left = x + 'px';
    tip.style.top = (event.clientY + 16) + 'px';
  });

  svg.addEventListener('mouseout', function (event) {
    if (!event.relatedTarget || !svg.contains(event.relatedTarget)) tip.hidden = true;
  });

  // ---- timeline ----------------------------------------------------------
  // Sorted once by birth time, so scrubbing only touches elements that
  // actually changed state instead of walking all ~1000 nodes every frame.
  const nodes = Array.prototype.map
    .call(svg.querySelectorAll('[data-t]'), function (el) {
      return { el: el, t: parseFloat(el.dataset.t) };
    })
    .sort(function (a, b) { return a.t - b.t; });

  let shown = nodes.length;

  const first = new Date(range.first + 'T00:00:00Z');
  const last = new Date(range.last + 'T00:00:00Z');
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

  function dateAt(t) {
    const d = new Date(first.getTime() + (last.getTime() - first.getTime()) * t);
    return months[d.getUTCMonth()] + ' ' + d.getUTCFullYear();
  }

  function apply(t) {
    let target = 0;
    while (target < nodes.length && nodes[target].t <= t) target++;
    if (target > shown) {
      for (let i = shown; i < target; i++) nodes[i].el.style.display = '';
    } else if (target < shown) {
      for (let i = target; i < shown; i++) nodes[i].el.style.display = 'none';
    }
    shown = target;
    readout.textContent = dateAt(t) + ' · ' + target;
  }

  slider.addEventListener('input', function () {
    apply(parseInt(slider.value, 10) / 1000);
  });

  apply(1);
})();

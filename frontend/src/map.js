// The choropleth: loads us-atlas once, then renders fills / hover / selection /
// labels / tooltip / legend from state. Path shapes are projected once and
// cached in `shapes` (also stored on the app state so the panel can zoom).
import { GEO_URL, PROPS } from './config.js';
import { esc } from './format.js';

const VIEW_W = 975, VIEW_H = 610;

export async function loadShapes(F) {
  const us = await (await fetch(GEO_URL)).json();
  const feats = topojson.feature(us, us.objects.states).features.filter(f => F.byFips[f.id]);
  const path = d3.geoPath(d3.geoAlbersUsa().scale(1300).translate([VIEW_W / 2, 305]));
  return feats.map(f => { const [x, y] = path.centroid(f); return { fips: f.id, d: path(f), cx: x, cy: y, b: path.bounds(f) }; });
}

export function createMap({ F, model, store }) {
  const el = {
    map: document.getElementById('map'),
    loading: document.getElementById('map-loading'),
    g: document.getElementById('map-g'),
    paths: d3.select('#map-paths'),
    sel: document.getElementById('map-sel'),
    labels: d3.select('#map-labels'),
    hatch: document.getElementById('hatch'),
    tip: document.getElementById('tooltip'),
    tipName: document.getElementById('tip-name'),
    tipRows: document.getElementById('tip-rows'),
    title: document.getElementById('map-title'),
    subtitle: document.getElementById('map-subtitle'),
    legendLo: document.getElementById('legend-lo'),
    legendHi: document.getElementById('legend-hi'),
    legendBar: document.getElementById('legend-bar'),
    legendHatch: document.getElementById('legend-hatch'),
    legendNote: document.getElementById('legend-note'),
  };
  document.documentElement.style.setProperty('--transition-ms', PROPS.transitionMs + 'ms');

  el.map.addEventListener('mouseleave', () => store.set({ hover: null }));
  el.map.addEventListener('mousemove', e => {
    const r = el.map.getBoundingClientRect();
    store.set({ hx: e.clientX - r.left, hy: e.clientY - r.top });
  });

  const toggleSelect = fips => { const { selected } = store.get(); store.set({ selected: selected === fips ? null : fips }); };

  /** Zoom factor + translate for the selected state (identity when none). */
  function zoom(state) {
    const sh = state.shapes.find(s => s.fips === state.selected);
    if (!sh) return { k: 1, tx: 0, ty: 0, sh: null };
    const [[x0, y0], [x1, y1]] = sh.b;
    const k = Math.max(1, Math.min(2.6, 0.55 / Math.max((x1 - x0) / VIEW_W, (y1 - y0) / VIEW_H)));
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    return { k, tx: VIEW_W / 2 - k * cx, ty: 305 - k * cy, sh };
  }

  function renderShapes(state) {
    el.loading.toggleAttribute('hidden', !state.loading);
    el.paths.selectAll('path').data(state.shapes, d => d.fips).join(enter => enter.append('path')
      .attr('d', d => d.d).attr('tabindex', 0).attr('aria-label', d => F.byFips[d.fips].name)
      .on('mouseenter', (e, d) => store.set({ hover: d.fips }))
      .on('focus', (e, d) => store.set({ hover: d.fips }))
      .on('click', (e, d) => { e.preventDefault(); toggleSelect(d.fips); })
      .on('contextmenu', (e, d) => { e.preventDefault(); toggleSelect(d.fips); })
      .on('keydown', (e, d) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); store.set({ selected: d.fips }); } }));
  }

  function renderFills(state) {
    el.paths.selectAll('path').attr('fill', d => model.fillFor(F.byFips[d.fips], state));
  }

  function renderStrokes(state) {
    const { k } = zoom(state);
    el.paths.selectAll('path')
      .attr('stroke', d => (state.hover === d.fips ? 'var(--color-text)' : 'var(--color-bg)'))
      .attr('stroke-width', d => (state.hover === d.fips ? 1.4 : 0.7) / k)
      // Raise the hovered path so its dark stroke isn't hidden by neighbours.
      .filter(d => state.hover === d.fips).raise();
  }

  function renderZoom(state) {
    const { k, tx, ty, sh } = zoom(state);
    el.g.style.transform = `translate(${tx}px,${ty}px) scale(${k})`;
    el.hatch.setAttribute('patternTransform', `rotate(45) scale(${(1 / k).toFixed(3)})`);
    el.sel.toggleAttribute('hidden', !sh);
    if (sh) { el.sel.setAttribute('d', sh.d); el.sel.setAttribute('stroke-width', 1.8 / k); }
    return k;
  }

  function renderLabels(state, k) {
    if (!PROPS.showLabels) { el.labels.selectAll('text').remove(); return; }
    const visible = state.shapes.filter(sh => { const [[x0, y0], [x1, y1]] = sh.b; return (x1 - x0) * k > 34 && (y1 - y0) * k > 24; });
    el.labels.selectAll('text').data(visible, d => d.fips).join('text')
      .attr('x', d => d.cx).attr('y', d => d.cy).attr('text-anchor', 'middle').attr('dominant-baseline', 'middle')
      .attr('font-size', 11 / k)
      .attr('fill', d => (model.labelIsLight(F.byFips[d.fips], state) ? 'rgba(255,255,255,.92)' : 'var(--color-text)'))
      .text(d => F.byFips[d.fips].abbr);
  }

  function renderTooltip(state) {
    const st = state.hover ? F.byFips[state.hover] : null;
    el.tip.hidden = !st;
    if (!st) return;
    el.tipName.textContent = st.name;
    el.tipRows.innerHTML = model.tooltipRows(st, state).map(r =>
      `<div class="tip-row"><span>${esc(r.k)}</span><span style="${r.color ? `color:${r.color};` : ''}${r.bold ? 'font-weight:500' : ''}">${esc(r.v)}</span></div>`).join('');
    const w = el.map.clientWidth || 800;
    const left = state.hx + 16 + 200 > w ? state.hx - 216 : state.hx + 16;
    el.tip.style.left = left + 'px';
    el.tip.style.top = Math.max(0, state.hy - 20) + 'px';
  }

  function renderChrome(state) {
    const selSt = state.selected ? F.byFips[state.selected] : null;
    el.title.textContent = model.mapTitle(state);
    el.subtitle.textContent = selSt ? `${selSt.name} · Esc to reset` : 'Hover for detail · click to analyse · right-click also selects';
    const L = model.legend(state);
    el.legendLo.textContent = L.lo; el.legendHi.textContent = L.hi;
    el.legendBar.style.background = L.bar; el.legendHatch.hidden = !L.hatch; el.legendNote.textContent = L.note;
  }

  const FULL = ['shapes', 'loading', 'office', 'year', 'metric', 'selected'];
  return {
    render(state, changed) {
      const full = !changed || FULL.some(k => changed.has(k));
      if (full) {
        if (!changed || changed.has('shapes') || changed.has('loading')) renderShapes(state);
        renderFills(state);
        const k = renderZoom(state);
        renderLabels(state, k);
        renderChrome(state);
      }
      if (full || changed.has('hover')) renderStrokes(state);
      if (full || changed.has('hover') || changed.has('hx') || changed.has('hy')) renderTooltip(state);
    },
  };
}

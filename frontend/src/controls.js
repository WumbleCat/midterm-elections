// Header + toolbar + footer controls: office / metric segments, the year
// readout, state search (⌘K), the as-of date, the timeline and transport
// buttons, autoplay and the global keyboard shortcuts.
import { AUTOPLAY_MS } from './config.js';
import { OFFICES, METRICS, esc } from './format.js';

export function createControls({ F, model, store }) {
  const el = {
    office: document.getElementById('office-seg'),
    metric: document.getElementById('metric-seg'),
    year: document.getElementById('year'),
    label: document.getElementById('election-label'),
    search: document.getElementById('search'),
    results: document.getElementById('search-results'),
    sourceTag: document.getElementById('source-tag'),
    asOf: document.getElementById('asof'),
    timeline: document.getElementById('timeline'),
    prev: document.getElementById('prev'),
    next: document.getElementById('next'),
    play: document.getElementById('play'),
  };
  let timer = null;

  // — navigation between valid years —
  function step(dir) {
    const { office, year, playing } = store.get();
    const ys = model.validYears(office);
    const i = ys.indexOf(year) + dir;
    if (i < 0 || i >= ys.length) { if (playing) stopPlay(); return; }
    store.set({ year: ys[i] });
  }
  function setOffice(office) {
    const { year } = store.get();
    const ys = model.validYears(office);
    const nearest = ys.includes(year) ? year : ys.reduce((a, b) => (Math.abs(b - year) < Math.abs(a - year) ? b : a));
    store.set({ office, year: nearest });
  }
  function stopPlay() { clearInterval(timer); timer = null; store.set({ playing: false }); }
  function togglePlay() {
    if (store.get().playing) return stopPlay();
    const { office, year } = store.get();
    const ys = model.validYears(office);
    const patch = { playing: true };
    if (year === ys[ys.length - 1]) patch.year = ys[0];
    store.set(patch);
    timer = setInterval(() => step(1), AUTOPLAY_MS);
  }

  // — segmented controls (native radios under the DS .seg classes) —
  const seg = (root, name, opts, current, onSelect) => {
    root.innerHTML = opts.map(([k, label]) => `<label class="seg-opt"><input type="radio" name="${name}" value="${k}"${k === current ? ' checked' : ''}>${esc(label)}</label>`).join('');
    root.addEventListener('change', e => { if (e.target.name === name) onSelect(e.target.value); });
  };
  const { office: office0, metric: metric0 } = store.get();
  seg(el.office, 'office', OFFICES, office0, setOffice);
  seg(el.metric, 'metric', METRICS, metric0, metric => store.set({ metric }));

  // — search —
  el.sourceTag.textContent = F.source.label;
  el.sourceTag.title = F.source.note;
  el.search.addEventListener('input', e => store.set({ query: e.target.value }));
  el.search.addEventListener('keydown', e => {
    if (e.key === 'Enter') { const first = el.results.querySelector('button'); if (first) first.click(); }
    if (e.key === 'Escape') { store.set({ query: '' }); el.search.blur(); }
  });
  el.results.addEventListener('mousedown', e => e.preventDefault()); // keep input focus while clicking a result
  el.results.addEventListener('click', e => {
    const b = e.target.closest('button[data-fips]');
    if (b) { store.set({ selected: b.dataset.fips, query: '' }); el.search.blur(); }
  });
  const searchResults = q => (q ? F.states.filter(s => s.name.toLowerCase().startsWith(q) || s.abbr.toLowerCase() === q).slice(0, 6) : []);

  // — as-of date, transport, timeline —
  el.asOf.addEventListener('change', e => store.set({ asOf: e.target.value }));
  el.prev.addEventListener('click', () => step(-1));
  el.next.addEventListener('click', () => step(1));
  el.play.addEventListener('click', togglePlay);
  el.timeline.addEventListener('click', e => {
    const b = e.target.closest('button[data-year]');
    if (b && !b.classList.contains('is-off')) store.set({ year: Number(b.dataset.year) });
  });

  // — keyboard —
  window.addEventListener('keydown', e => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); el.search.focus(); el.search.select(); return; }
    if (e.target && /INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;
    if (e.key === 'ArrowLeft') step(-1);
    else if (e.key === 'ArrowRight') step(1);
    else if (e.key === 'Escape') store.set({ selected: null });
  });

  function renderTimeline(state) {
    const valid = model.validYears(state.office);
    el.timeline.innerHTML = F.years.map(y => {
      const ok = valid.includes(y), act = y === state.year, pres = F.isPres(y);
      return `<button data-year="${y}" class="tl-year${act ? ' is-active' : ''}${ok ? '' : ' is-off'}" aria-pressed="${act}"${ok ? '' : ' tabindex="-1"'}><span class="tl-dot${pres ? ' pres' : ''}"></span><span>${String(y).slice(2)}</span></button>`;
    }).join('');
  }

  return {
    render(state, changed) {
      const any = ks => !changed || ks.some(k => changed.has(k));
      if (any(['office', 'year'])) {
        el.year.textContent = state.year;
        el.label.textContent = model.electionLabel(state);
        renderTimeline(state);
        const r = el.office.querySelector(`input[value="${state.office}"]`); if (r) r.checked = true;
      }
      if (any(['metric'])) { const r = el.metric.querySelector(`input[value="${state.metric}"]`); if (r) r.checked = true; }
      if (any(['query'])) {
        if (el.search.value !== state.query) el.search.value = state.query;
        const res = searchResults(state.query.trim().toLowerCase());
        el.results.hidden = !res.length;
        el.results.innerHTML = res.map(s => `<button class="search-result" data-fips="${s.fips}"><span>${esc(s.name)}</span><span class="is-muted">${s.abbr}</span></button>`).join('');
      }
      if (any(['playing'])) {
        el.play.classList.toggle('is-on', state.playing);
        el.play.setAttribute('aria-pressed', String(state.playing));
        el.play.querySelector('.icon-pause').toggleAttribute('hidden', !state.playing);
        el.play.querySelector('.icon-play').toggleAttribute('hidden', state.playing);
      }
      if (any(['asOf']) && el.asOf.value !== state.asOf) el.asOf.value = state.asOf;
    },
  };
}

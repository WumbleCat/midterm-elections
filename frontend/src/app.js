// Election Explorer — entry point. Loads the data provider, wires the store
// to the three renderers and kicks off the geography fetch.
import { loadProvider } from '../data/provider.js';
import { createStore } from './store.js';
import { createModel } from './model.js';
import { createMap, loadShapes } from './map.js';
import { createPanel } from './panel.js';
import { createControls } from './controls.js';
import { OFFICES, METRICS } from './format.js';

/** Initial office / year / metric / selected state from the URL, validated against the data. */
function stateFromUrl(F, model) {
  const p = new URLSearchParams(location.search);
  const office = OFFICES.some(o => o[0] === p.get('office')) ? p.get('office') : 'president';
  const metric = METRICS.some(m => m[0] === p.get('metric')) ? p.get('metric') : 'margin';
  const valid = model.validYears(office);
  const y = Number(p.get('year'));
  const year = valid.includes(y) ? y : valid[valid.length - 1];
  const s = (p.get('state') || '').toUpperCase();
  const selected = F.byAbbr[s]?.fips ?? (F.byFips[s] ? s : null);
  return { office, year, metric, selected };
}

function syncUrl(F, state) {
  const p = new URLSearchParams(location.search);
  p.set('office', state.office); p.set('year', state.year); p.set('metric', state.metric);
  if (state.selected) p.set('state', F.byFips[state.selected].abbr); else p.delete('state');
  history.replaceState(null, '', `${location.pathname}?${p}`);
}

async function main() {
  const F = await loadProvider();
  const model = createModel(F);
  const store = createStore({
    ...stateFromUrl(F, model),
    hover: null, hx: 0, hy: 0,
    playing: false, asOf: '', query: '',
    shapes: [], loading: true,
  });

  const views = [createControls({ F, model, store }), createMap({ F, model, store }), createPanel({ F, model, store })];
  const URL_KEYS = ['office', 'year', 'metric', 'selected'];
  store.subscribe((state, changed) => {
    views.forEach(v => v.render(state, changed));
    if (URL_KEYS.some(k => changed.has(k))) syncUrl(F, state);
  });
  views.forEach(v => v.render(store.get(), null));

  try {
    store.set({ shapes: await loadShapes(F), loading: false });
  } catch (e) {
    console.error('geo load failed', e);
    store.set({ loading: false });
  }
}

main();

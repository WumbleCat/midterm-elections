// Page props (the design exposed these as editor props). Overridable from the
// URL: ?labels=0 hides state abbreviations, ?transition=250 sets the fill
// transition in milliseconds.
const params = new URLSearchParams(location.search);
const num = (k, d) => { const v = Number(params.get(k)); return params.has(k) && Number.isFinite(v) ? v : d; };

export const PROPS = {
  showLabels: params.has('labels') ? !/^(0|false|no)$/i.test(params.get('labels')) : true,
  transitionMs: Math.max(0, Math.min(1500, num('transition', 500))),
};

export const GEO_URL = 'https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json';
export const AUTOPLAY_MS = 1100;

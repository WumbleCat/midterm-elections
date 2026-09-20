// Formatting helpers and the party colour encodings shared by every module.
export const DEM = '#1d4e89';
export const REP = '#b3282d';
export const NEU = '#e3e4e7';

export const pct = v => (v * 100).toFixed(1) + '%';
/** Margin text: "D +3.2", "R +0.4" or "Even". `m` is Dem share minus 0.5. */
export const mtxt = m => (Math.abs(m) < 0.0005 ? 'Even' : (m > 0 ? 'D +' : 'R +') + (Math.abs(m) * 100).toFixed(1));
export const mcolor = m => (m > 0 ? DEM : REP);
export const fmtN = n => (n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e3 ? (n / 1e3).toFixed(0) + 'K' : String(n));
export const fmtUSD = n => '$' + (n / 1000).toFixed(0) + 'K';

/** Escape text for insertion into an HTML template. */
export const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export const OFFICES = [['president', 'President'], ['senate', 'Senate'], ['house', 'House'], ['midterm', 'Midterm']];
export const METRICS = [['margin', 'Winner / margin'], ['swing', 'Swing'], ['dem', 'Dem share'], ['turnout', 'Turnout'], ['income', 'Income'], ['bachelors', 'Degree']];
export const officeLabel = k => OFFICES.find(o => o[0] === k)[1];
export const metricLabel = k => METRICS.find(m => m[0] === k)[1];

// The right-hand panel: national summary when nothing is selected, the state
// analysis when a state is. Rendered as an HTML template from model output.
import { pct, esc } from './format.js';

const bar = (fD, fR, cls = '') => `<div class="bar ${cls}"><div class="d" style="flex:0 0 ${(fD * 100).toFixed(1)}%"></div><div class="r" style="flex:0 0 ${(fR * 100).toFixed(1)}%"></div></div>`;
const rows = list => list.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join('');
const asOfNote = state => (state.asOf ? `As of ${esc(state.asOf)} (point-in-time filter not yet applied).` : '');

function chamber(label, need, c, cls) {
  return `
    <div class="chamber-head"><span class="kicker">${label} · ${need} to control</span><span class="prev">${esc(c.prev)} → now</span></div>
    <div class="chamber-row"><span class="dem">${c.d}</span><span class="control">${esc(c.control)}</span><span class="rep">${c.r}</span></div>
    <div class="chamber-bar ${cls}">${bar(c.d / c.total, c.r / c.total)}</div>`;
}

export function nationalHTML(nat, state) {
  return `
    <h6 class="muted-h6 mb-3">National summary</h6>
    <h3>${esc(nat.title)}</h3>
    ${nat.showEV ? `
      <div class="stat-pair mb-4">
        <div><div class="stat-label dem">Democratic EV</div><div class="stat-value xl">${nat.evD}</div></div>
        <div><div class="stat-label rep">Republican EV</div><div class="stat-value xl">${nat.evR}</div></div>
      </div>
      <div class="mb-4">${bar(nat.evD / 538, nat.evR / 538, 'tall')}</div>` : ''}
    ${nat.showHouse ? chamber('House', 218, { ...nat.house, total: 435 }) : ''}
    ${nat.showSenate ? chamber('Senate', 51, { ...nat.senate, total: 100 }, 'tight') + `<div class="sen-races">${esc(nat.senate.races)}</div>` : ''}
    <div class="chamber-head"><span class="kicker">${esc(nat.popLabel)}</span></div>
    <div class="pop-row"><span class="dem">DEM ${pct(nat.popD)}</span><span class="rep">${pct(1 - nat.popD)} REP</span></div>
    <div class="mb-4">${bar(nat.popD, 1 - nat.popD)}</div>
    <table class="table"><tbody>${rows([
      ['National margin', nat.margin], ['Swing vs previous', nat.swing], ['Turnout (VAP)', nat.turnout], ['Ballots cast', nat.ballots], ['States flipped', nat.flips],
    ])}</tbody></table>
    <div class="sources">Sources (target): FEC · MIT MEDSL · Census ACS · EAC EAVS via <code>electiondata</code> API. Currently synthetic fixtures. ${asOfNote(state)}</div>`;
}

export function stateHTML(sel, state) {
  const race = sel.hasRace ? `
    <div class="stat-pair race-stats">
      <div><div class="stat-label dem">Democratic</div><div class="stat-value lg">${pct(sel.ls)}</div></div>
      <div><div class="stat-label rep">Republican</div><div class="stat-value lg">${pct(1 - sel.ls)}</div></div>
    </div>
    <div class="mb-3">${bar(sel.ls, 1 - sel.ls)}</div>`
    : `<div class="no-race">No Senate race in ${state.year}. Showing seat history and the most recent contest.</div>`;
  return `
    <div class="panel-head">
      <div><h6>${esc(sel.kicker)}</h6><h2>${esc(sel.name)}</h2></div>
      <button id="deselect" class="btn btn-icon close-btn" aria-label="Close"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M18 6 6 18M6 6l12 12"></path></svg></button>
    </div>
    ${race}
    <table class="table"><tbody>
      <tr><td>Margin</td><td style="color:${sel.marginColor}">${esc(sel.margin)}</td></tr>
      ${rows([['Swing vs previous', sel.swing], ['Turnout rate', sel.turnout], ['Ballots cast', sel.ballots], [sel.seatLabel, sel.seatVal], ['Partisan lean', sel.lean]])}
    </tbody></table>

    <h6 class="section">Political history</h6>
    <div class="strip">${sel.strip.map(b => `<button data-year="${b.year}" title="${esc(b.title)}" class="${b.active ? 'is-active' : ''}" style="background:${b.color}"></button>`).join('')}</div>
    <div class="strip-axis"><span>${sel.stripFirst}</span><span>${sel.stripLast}</span></div>

    <h6 class="section">Two-party Democratic share</h6>
    <svg class="share-chart" viewBox="0 0 312 120">
      <line class="grid-edge" x1="28" x2="304" y1="8" y2="8"></line>
      <line class="grid-mid" x1="28" x2="304" y1="31.5" y2="31.5"></line>
      <line class="grid-50" x1="28" x2="304" y1="55" y2="55"></line>
      <line class="grid-mid" x1="28" x2="304" y1="78.5" y2="78.5"></line>
      <line class="grid-edge" x1="28" x2="304" y1="102" y2="102"></line>
      <text class="axis" x="24" y="11" text-anchor="end">70</text>
      <text class="axis" x="24" y="58" text-anchor="end">50</text>
      <text class="axis" x="24" y="105" text-anchor="end">30</text>
      <text class="lbl" x="30" y="20" fill="var(--color-dem)">DEM</text>
      <text class="lbl" x="30" y="99" fill="var(--color-rep)">REP</text>
      <path class="line" d="${sel.chartPath}"></path>
      ${sel.chartPts.map(p => `<circle data-year="${p.year}" cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="${p.r}" fill="${p.fill}"></circle>`).join('')}
      ${sel.ticks.map(t => `<text class="axis" x="${t.x.toFixed(1)}" y="116" text-anchor="middle">${t.year}</text>`).join('')}
    </svg>

    <h6 class="section">Turnout rate</h6>
    <div class="turnout-bars">${sel.turnBars.map(b => `<div title="${esc(b.title)}" class="${b.active ? 'is-active' : ''}" style="height:${b.h}px"></div>`).join('')}</div>

    <h6 class="section">Demographics · ACS</h6>
    <table class="table"><tbody>${rows(sel.demo)}</tbody></table>

    <h6 class="section">Economy · BLS / BEA</h6>
    <table class="table"><tbody>${rows(sel.econ)}</tbody></table>
    <div class="sources">/states/${esc(sel.slug)} · synthetic fixture · ${asOfNote(state)}</div>`;
}

export function createPanel({ F, model, store }) {
  const body = document.getElementById('panel-body');
  const panel = document.getElementById('panel');

  // One delegated listener: close button, history strip and chart points all set state.
  panel.addEventListener('click', e => {
    if (e.target.closest('#deselect')) { store.set({ selected: null }); return; }
    const yearEl = e.target.closest('[data-year]');
    if (yearEl) store.set({ year: Number(yearEl.dataset.year) });
  });

  const KEYS = ['office', 'year', 'metric', 'selected', 'asOf'];
  return {
    render(state, changed) {
      if (changed && !KEYS.some(k => changed.has(k))) return;
      const selSt = state.selected ? F.byFips[state.selected] : null;
      const wasSelected = body.dataset.selected;
      body.innerHTML = selSt ? stateHTML(model.statePanel(selSt, state), state) : nationalHTML(model.national(state), state);
      body.dataset.selected = state.selected ?? '';
      if (wasSelected !== body.dataset.selected) panel.scrollTop = 0;
    },
  };
}

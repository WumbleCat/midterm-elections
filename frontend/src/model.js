// Derived election numbers. Pure functions over the data provider `F` and the
// current UI state — no DOM here, so every renderer reads from one place.
import { DEM, REP, NEU, pct, mtxt, mcolor, fmtN, fmtUSD, officeLabel, metricLabel } from './format.js';

export function createModel(F) {
  const validYears = office => F.years.filter(y => (office === 'president' ? F.isPres(y) : office === 'midterm' ? !F.isPres(y) : true));

  /** Two-party Dem share for the office in play; Senate returns null when no seat is up. */
  const share = (st, year, office) => (office === 'senate' ? F.senateRace(st, year) : F.demShare(st, year, office === 'midterm' ? 'house' : office));
  const prevYear = (year, office) => (office === 'president' || office === 'midterm' ? year - 4 : office === 'senate' ? year - 6 : year - 2);
  const swing = (st, year, office) => {
    const a = share(st, year, office), py = prevYear(year, office);
    if (a == null || py < 1980) return null;
    const b = share(st, py, office);
    return b == null ? null : a - b;
  };

  const colorMargin = m => {
    if (m == null) return 'url(#hatch)';
    const t = Math.min(1, Math.abs(m) / 0.30);
    return d3.interpolateLab(NEU, m > 0 ? DEM : REP)(0.1 + 0.9 * t);
  };
  const seq = t => d3.interpolateLab('#eef6ff', '#1d2d3d')(Math.max(0, Math.min(1, t)));

  const fillFor = (st, { metric, year, office }) => {
    const s = share(st, year, office);
    if (metric === 'margin') return s == null ? 'url(#hatch)' : colorMargin(s - 0.5);
    if (metric === 'swing') {
      const sw = swing(st, year, office);
      return sw == null ? 'url(#hatch)' : d3.interpolateLab(NEU, sw > 0 ? DEM : REP)(0.1 + 0.9 * Math.min(1, Math.abs(sw) / 0.08));
    }
    if (metric === 'dem') return s == null ? 'url(#hatch)' : d3.interpolateLab('#eef2f8', DEM)((s - 0.3) / 0.4);
    if (metric === 'turnout') return seq((F.turnoutRate(st, year) - 0.35) / 0.45);
    if (metric === 'income') return seq((F.demographics(st).median_income - 36000) / 52000);
    if (metric === 'bachelors') return seq((F.demographics(st).pct_bachelors - 0.18) / 0.44);
    return NEU;
  };

  /** Whether a label over this state should be light (dark fill) or dark. */
  const labelIsLight = (st, { metric, year, office }) => {
    const s = share(st, year, office);
    return (metric === 'margin' && s != null && Math.abs(s - 0.5) > 0.1) || (metric !== 'margin' && metric !== 'swing');
  };

  const electionLabel = ({ office, year }) => {
    const isPres = F.isPres(year);
    return office === 'president' ? 'Presidential election'
      : office === 'midterm' ? 'Midterm elections'
      : (isPres ? 'Presidential-year ' : 'Midterm ') + (office === 'senate' ? 'Senate races' : 'House elections');
  };
  const title = ({ office, year }) => (office === 'president' ? `${year} Presidential` : office === 'midterm' ? `${year} Midterms` : office === 'senate' ? `${year} Senate` : `${year} House`);
  const mapTitle = ({ office, year, metric }) => `${metricLabel(metric)} · ${officeLabel(office)} ${year}`;

  const legend = ({ office, year, metric }) => {
    const grad = (a, b) => `linear-gradient(90deg,${a},${NEU} 50%,${b})`;
    const seqBar = 'linear-gradient(90deg,#eef6ff,#1d2d3d)';
    return {
      margin: { lo: 'R +30', hi: 'D +30', bar: grad(REP, DEM), hatch: office === 'senate', note: 'Two-party margin' },
      swing: { lo: 'R +8', hi: 'D +8', bar: grad(REP, DEM), hatch: true, note: `Swing vs ${prevYear(year, office)} (same office)` },
      dem: { lo: '30%', hi: '70%', bar: `linear-gradient(90deg,#eef2f8,${DEM})`, hatch: office === 'senate', note: 'Two-party Democratic share' },
      turnout: { lo: '35%', hi: '80%', bar: seqBar, hatch: false, note: 'Ballots / voting-age population' },
      income: { lo: '$36K', hi: '$88K', bar: seqBar, hatch: false, note: 'Median household income · ACS' },
      bachelors: { lo: '18%', hi: '62%', bar: seqBar, hatch: false, note: "Bachelor's degree or higher · ACS" },
    }[metric];
  };

  const tooltipRows = (st, { year, office, metric }) => {
    const s = share(st, year, office), sw = swing(st, year, office);
    const rows = s == null ? [{ k: 'Senate race', v: 'None this cycle' }] : [
      { k: 'DEM', v: pct(s), color: DEM, bold: true }, { k: 'REP', v: pct(1 - s), color: REP, bold: true },
      { k: 'Margin', v: mtxt(s - 0.5), color: mcolor(s - 0.5), bold: true },
      { k: 'Turnout', v: fmtN(F.ballots(st, year)) + ' · ' + pct(F.turnoutRate(st, year)) },
      { k: 'Swing', v: sw == null ? '—' : mtxt(sw), color: sw == null ? null : mcolor(sw) },
    ];
    if (metric === 'income') rows.push({ k: 'Median income', v: fmtUSD(F.demographics(st).median_income) });
    if (metric === 'bachelors') rows.push({ k: "Bachelor's+", v: pct(F.demographics(st).pct_bachelors) });
    return rows;
  };

  /** National totals for the current office/year. */
  const national = state => {
    const { office, year } = state;
    let evD = 0, evR = 0, vD = 0, vR = 0, ball = 0, pop = 0, pvD = 0, pvT = 0, flips = 0;
    const py = prevYear(year, office);
    for (const st of F.states) {
      const s = share(st, year, office);
      const b = F.ballots(st, year);
      pop += F.population(st, year);
      if (s != null) {
        ball += b; vD += b * s; vR += b * (1 - s);
        if (office === 'president') { if (s > 0.5) evD += st.ev; else evR += st.ev; }
        const ps = py >= 1980 ? share(st, py, office) : null;
        if (ps != null && (ps > 0.5) !== (s > 0.5)) flips++;
      }
      if (py >= 1980) {
        const ps = share(st, py, office);
        if (ps != null) { const pb = F.ballots(st, py); pvD += pb * ps; pvT += pb; }
      }
    }
    const popD = vD / (vD + vR);
    const natSw = pvT ? popD - pvD / pvT : null;
    const nat = {
      title: title(state),
      showEV: office === 'president', evD, evR,
      showHouse: office === 'house' || office === 'midterm',
      showSenate: office === 'senate' || office === 'midterm',
      popLabel: office === 'president' ? 'Popular vote (two-party)' : office === 'senate' ? 'Aggregate vote in contested races' : 'House popular vote (two-party)',
      popD, margin: mtxt(popD - 0.5), swing: natSw == null ? '—' : mtxt(natSw),
      turnout: pct(ball / (pop * 0.74)), ballots: fmtN(ball),
      flips: office === 'senate' ? `${flips} seats` : `${flips} states`,
    };
    if (nat.showHouse) {
      const h = F.houseComposition(year), hp = F.houseComposition(year - 2);
      nat.house = { d: h.d, r: h.r, prev: `${hp.d}–${hp.r}`, control: (h.d >= 218 ? 'DEM' : 'REP') + ((hp.d >= 218) !== (h.d >= 218) ? ' · flipped' : ' · held') };
    }
    if (nat.showSenate) {
      const c = F.senateComposition(year), cp = F.senateComposition(year - 2);
      let sr = 0, sd = 0;
      for (const st of F.states) { const s = F.senateRace(st, year); if (s != null) { sr++; if (s > 0.5) sd++; } }
      nat.senate = { d: c.d, r: c.r, prev: `${cp.d}–${cp.r}`, control: (c.d >= 51 ? 'DEM' : c.d === 50 ? '50–50' : 'REP') + ((cp.d >= 51) !== (c.d >= 51) ? ' · flipped' : ' · held'), races: `${sr} seats contested · DEM ${sd} · REP ${sr - sd}` };
    }
    return nat;
  };

  /** Everything the state panel shows for the selected state. */
  const statePanel = (selSt, state) => {
    const { office, year } = state;
    const valid = validYears(office);
    const s = share(selSt, year, office);
    const hist = valid.filter(y => share(selSt, y, office) != null);
    const lastY = s != null ? year : ([...hist].reverse().find(y => y <= year) ?? hist[hist.length - 1]);
    const ls = share(selSt, lastY, office), sw = swing(selSt, lastY, office);
    const demo = F.demographics(selSt), ec = F.economics(selSt, year);
    const yr0 = hist[0], yr1 = hist[hist.length - 1];
    const X = y => 28 + (y - yr0) / Math.max(1, yr1 - yr0) * 276;
    const Y = v => 8 + (0.7 - Math.max(0.3, Math.min(0.7, v))) / 0.4 * 94;
    const pts = hist.map(y => { const v = share(selSt, y, office); return { year: y, x: X(y), y: Y(v), r: y === lastY ? 4 : 2.6, fill: v > 0.5 ? DEM : REP }; });
    const seat = office === 'senate'
      ? (() => { const d = F.senateClasses(selSt).filter(c => F.demShare(selSt, F.lastSenateYear(c, year), 'senate') > 0.5).length; return ['Senate delegation', selSt.abbr === 'DC' ? '—' : `${d} D · ${2 - d} R`]; })()
      : office === 'president' ? ['Electoral votes', String(selSt.ev)]
      : (() => { const h = F.houseSeats(selSt, year); return ['House seats', `${h.d} D · ${h.r} R of ${h.d + h.r}`]; })();
    // Partisan lean: the state's presidential Dem share relative to the national presidential Dem share.
    let nd = 0, nt = 0;
    for (const st of F.states) { const b = F.ballots(st, year); nd += b * F.demShare(st, year, 'president'); nt += b; }
    const leanV = F.demShare(selSt, year, 'president') - nd / nt;
    return {
      kicker: `${title(state)} · ${selSt.abbr}`, name: selSt.name, slug: selSt.name.toLowerCase().replace(/\s+/g, '-'),
      hasRace: s != null, ls, margin: mtxt(ls - 0.5), marginColor: mcolor(ls - 0.5), swing: sw == null ? '—' : mtxt(sw),
      turnout: pct(F.turnoutRate(selSt, year)), ballots: fmtN(F.ballots(selSt, year)), seatLabel: seat[0], seatVal: seat[1], lean: mtxt(leanV) + ' vs nation',
      strip: hist.map(y => { const v = share(selSt, y, office); return { year: y, title: `${y} · ${mtxt(v - 0.5)}`, color: colorMargin(v - 0.5), active: y === year }; }),
      stripFirst: yr0, stripLast: yr1,
      chartPath: pts.length ? 'M' + pts.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join('L') : '', chartPts: pts,
      ticks: hist.filter((y, i) => hist.length <= 8 || i % Math.ceil(hist.length / 6) === 0 || i === hist.length - 1).map(y => ({ year: y, x: X(y) })),
      turnBars: valid.map(y => { const t = F.turnoutRate(selSt, y); return { year: y, title: `${y} · ${pct(t)}`, h: ((t - 0.3) / 0.5 * 56).toFixed(0), active: y === year }; }),
      demo: [['Median age', demo.median_age.toFixed(1)], ["Bachelor's or higher", pct(demo.pct_bachelors)], ['Median household income', fmtUSD(demo.median_income)], ['Poverty rate', pct(demo.poverty_rate)], ['Urban share', pct(demo.pct_urban)], ['Density / sq mi', String(demo.density)], ['White, non-Hispanic', pct(demo.pct_white)], ['Foreign-born', pct(demo.pct_foreign_born)]],
      econ: [['Unemployment', ec.unemployment.toFixed(1) + '%'], ['Unemployment Δ 12m', (ec.unemployment_change_12m > 0 ? '+' : '') + ec.unemployment_change_12m.toFixed(1) + ' pts'], ['Real GDP growth', ec.real_gdp_growth.toFixed(1) + '%'], ['Personal income growth', ec.personal_income_growth.toFixed(1) + '%'], ['Wage growth', ec.wage_growth.toFixed(1) + '%']],
    };
  };

  return { validYears, share, prevYear, swing, colorMargin, fillFor, labelIsLight, electionLabel, title, mapTitle, legend, tooltipRows, national, statePanel };
}

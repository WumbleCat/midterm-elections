// SYNTHETIC FIXTURE DATA — deterministic, election-shaped, NOT real results.
// Ported from the Election Explorer design project (data/fixtures.js).
// Replace with the electiondata API responses (GET /elections?year=&office=, GET /states/:id/…)
// by implementing the same surface in ./provider.js.
export const STATES = [
  ['AL','Alabama','01',9,-.19,-.005],['AK','Alaska','02',3,-.10,.004],['AZ','Arizona','04',11,-.06,.012],['AR','Arkansas','05',6,-.16,-.015],
  ['CA','California','06',54,.15,.002],['CO','Colorado','08',10,.03,.012],['CT','Connecticut','09',7,.10,0],['DE','Delaware','10',3,.11,0],
  ['DC','District of Columbia','11',3,.42,0],['FL','Florida','12',30,-.01,-.010],['GA','Georgia','13',16,-.07,.014],['HI','Hawaii','15',4,.22,-.004],
  ['ID','Idaho','16',4,-.22,-.004],['IL','Illinois','17',19,.10,0],['IN','Indiana','18',11,-.10,-.004],['IA','Iowa','19',6,.02,-.018],
  ['KS','Kansas','20',6,-.13,.004],['KY','Kentucky','21',8,-.15,-.010],['LA','Louisiana','22',8,-.13,-.005],['ME','Maine','23',4,.07,-.006],
  ['MD','Maryland','24',10,.15,.003],['MA','Massachusetts','25',11,.15,.003],['MI','Michigan','26',15,.04,-.008],['MN','Minnesota','27',10,.05,-.004],
  ['MS','Mississippi','28',6,-.10,-.003],['MO','Missouri','29',10,-.06,-.014],['MT','Montana','30',4,-.09,-.004],['NE','Nebraska','31',5,-.14,.002],
  ['NV','Nevada','32',6,.03,-.006],['NH','New Hampshire','33',4,.03,.002],['NJ','New Jersey','34',14,.09,-.002],['NM','New Mexico','35',5,.06,0],
  ['NY','New York','36',28,.14,-.006],['NC','North Carolina','37',16,-.02,.002],['ND','North Dakota','38',3,-.16,-.010],['OH','Ohio','39',17,.01,-.018],
  ['OK','Oklahoma','40',7,-.20,-.005],['OR','Oregon','41',8,.07,.002],['PA','Pennsylvania','42',19,.03,-.008],['RI','Rhode Island','44',4,.14,-.004],
  ['SC','South Carolina','45',9,-.09,.002],['SD','South Dakota','46',3,-.14,-.008],['TN','Tennessee','47',11,-.14,-.014],['TX','Texas','48',40,-.10,.012],
  ['UT','Utah','49',6,-.22,.010],['VT','Vermont','50',3,.18,.004],['VA','Virginia','51',13,.01,.012],['WA','Washington','53',12,.09,.004],
  ['WV','West Virginia','54',4,-.06,-.030],['WI','Wisconsin','55',10,.03,-.006],['WY','Wyoming','56',3,-.25,-.004],
].map(([abbr,name,fips,ev,lean,trend],i)=>({abbr,name,fips,ev,lean,trend,idx:i,houseSeats:Math.max(1,ev-2)}));
export const BY_FIPS = Object.fromEntries(STATES.map(s=>[s.fips,s]));
export const BY_ABBR = Object.fromEntries(STATES.map(s=>[s.abbr,s]));

export const YEARS = []; for (let y=1980;y<=2024;y+=2) YEARS.push(y);
export const isPres = y => y%4===0;
// National two-party environment (fixture; Dem minus 50%)
const PRES_ENV = {1980:-.05,1984:-.09,1988:-.04,1992:.03,1996:.045,2000:.003,2004:-.012,2008:.037,2012:.02,2016:.011,2020:.023,2024:-.008};
const HOUSE_ENV = {1982:.03,1986:.05,1990:.03,1994:-.035,1998:-.005,2002:-.025,2006:.04,2010:-.035,2014:-.03,2018:.045,2022:-.015};

const hash = s => { let h=2166136261; for (const c of String(s)) { h^=c.charCodeAt(0); h=Math.imul(h,16777619); } return ((h>>>0)%10000)/10000-0.5; };
const clamp = (v,a,b)=>Math.min(b,Math.max(a,v));
const env = (year,office)=> office==='president' ? (PRES_ENV[year]??0) : (isPres(year) ? (PRES_ENV[year]??0)*0.8 : (HOUSE_ENV[year]??0));

export function demShare(st, year, office) {
  const base = 0.5 + st.lean + st.trend*((year-2012)/4);
  const noise = hash(st.abbr+year+office) * (office==='senate' ? .07 : .03);
  return clamp(base + env(year,office) + noise, .18, .92);
}
export const senateClasses = st => [st.idx%3, (st.idx+1)%3];
export const cycleOf = y => (((y-1980)/2)%3+3)%3;
export function senateRace(st, year) { return senateClasses(st).includes(cycleOf(year)) ? demShare(st,year,'senate') : null; }
export function lastSenateYear(cls, year) { let y=year; while (cycleOf(y)!==cls) y-=2; return y; }
export function senateComposition(year) {
  let d=0,r=0; for (const st of STATES) { if (st.abbr==='DC') continue; for (const c of senateClasses(st)) { (demShare(st,lastSenateYear(c,year),'senate')>0.5? d++ : r++); } } return {d,r};
}
export function houseSeats(st, year) { if (st.abbr==='DC') return {d:0,r:0}; const s=demShare(st,year,'house'); const d=Math.round(st.houseSeats*clamp(0.5+(s-0.5)*2.2,0,1)); return {d,r:st.houseSeats-d}; }
export function houseComposition(year) { let d=0,r=0; for (const st of STATES) { const h=houseSeats(st,year); d+=h.d; r+=h.r; } return {d,r}; }
export function population(st, year) { const base=(st.ev-2)*0.75e6+0.55e6; return Math.round(base*Math.pow(1+0.006+st.trend*0.3, year-2012)); }
export function turnoutRate(st, year) { return clamp(0.5 + (isPres(year)?.1:-.04) + hash(st.abbr+'to')*.12 + (year-1980)*.001, .3, .8); }
export function ballots(st, year) { return Math.round(population(st,year)*0.74*turnoutRate(st,year)); }
export function demographics(st) {
  const h=k=>hash(st.abbr+k);
  return {
    median_age: 36+h('age')*8, pct_bachelors: clamp(.30+h('ba')*.14+st.lean*.25,.18,.62), median_income: Math.round(62000+h('inc')*26000+st.lean*40000),
    poverty_rate: clamp(.12+h('pov')*.06-st.lean*.1,.06,.22), pct_urban: clamp(.68+h('urb')*.3+st.lean*.3,.3,.99),
    density: Math.round(Math.exp(4+h('den')*4+st.lean*3)), pct_white: clamp(.65+h('wh')*.4,.2,.95), pct_foreign_born: clamp(.08+h('fb')*.1+st.lean*.15,.01,.3),
  };
}
export function economics(st, year) {
  const h=k=>hash(st.abbr+k+year);
  return { unemployment: clamp(4.2+h('u')*2.5,2,10), unemployment_change_12m: h('du')*1.6, real_gdp_growth: 2.1+h('g')*3, personal_income_growth: 3.4+h('pi')*3, wage_growth: 3.0+h('w')*2.5 };
}

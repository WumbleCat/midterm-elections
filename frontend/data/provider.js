// Data provider — the one seam between the UI and its data.
//
// The UI only ever calls `loadProvider()` and uses the returned object. Today
// it is backed by the synthetic fixtures; wiring the real `electiondata` API
// means returning an object with the same surface from a different module
// (e.g. fetch GET /elections?year=&office= and GET /states/:id/… up front and
// memoise the lookups) and flipping `SOURCE`.
import * as F from './fixtures.js';

export const SOURCE = { kind: 'fixture', label: 'Fixture data', note: 'Synthetic election-shaped fixtures. Wire to electiondata FastAPI to replace.' };

/** Years the explorer can step through, ascending. */
export const YEARS = F.YEARS;
export const isPresidentialYear = F.isPres;

/**
 * Build the provider. Every accessor is synchronous so render code stays
 * simple; an API-backed provider should prefetch inside `loadProvider`.
 */
export async function loadProvider() {
  return {
    source: SOURCE,
    states: F.STATES,
    byFips: F.BY_FIPS,
    byAbbr: F.BY_ABBR,
    years: F.YEARS,
    isPres: F.isPres,
    /** Two-party Democratic share for an office ('president' | 'house' | 'senate'). */
    demShare: F.demShare,
    /** Two-party Dem share of this year's Senate race in the state, or null when no seat is up. */
    senateRace: F.senateRace,
    senateClasses: F.senateClasses,
    lastSenateYear: F.lastSenateYear,
    senateComposition: F.senateComposition,
    houseSeats: F.houseSeats,
    houseComposition: F.houseComposition,
    population: F.population,
    turnoutRate: F.turnoutRate,
    ballots: F.ballots,
    demographics: F.demographics,
    economics: F.economics,
  };
}

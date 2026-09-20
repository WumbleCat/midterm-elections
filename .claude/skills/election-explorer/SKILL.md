---
name: election-explorer
description: Work on the Election Explorer frontend (frontend/) — the buildless d3 choropleth UI implemented from the Claude Design project. Use when adding or changing map metrics, panel sections, controls, styling, or when re-syncing the vendored Industry design system or wiring the electiondata API in place of fixtures.
---

# Election Explorer frontend

The screen lives in `frontend/` and is a faithful, buildless implementation of
`Election Explorer.dc.html` from Claude Design project
`b005845c-c592-4a23-89f3-d40b670da986`. Read `frontend/README.md` for the
file map before editing.

## Run and verify

```
uv run python frontend/serve.py --port 8000
```

There is no Node on this machine — never add a bundler, npm packages or JSX.
Libraries come from jsdelivr `<script>` tags in `index.html` (d3@7,
topojson-client@3) and geometry from `us-atlas@3`.

To check a change visually without a browser session, screenshot with
headless Chrome, using URL state to reach the view you touched:

```
"/c/Program Files/Google/Chrome/Application/chrome.exe" --headless=new --disable-gpu --hide-scrollbars \
  --window-size=1400,1000 --virtual-time-budget=8000 --screenshot=<scratchpad>/shot.png \
  "http://127.0.0.1:8000/index.html?office=senate&year=2022&metric=swing&state=GA"
```

Then Read the PNG. Check at least: default view, a selected state (zoom +
panel), the `midterm` office (House + Senate composition), and one sequential
metric (`turnout` / `income` / `bachelors`).

## Architecture rules

- **One store, keyed change sets.** `src/store.js` notifies subscribers with
  the `Set` of changed keys. Every view's `render(state, changed)` must early-
  return when none of its keys changed (`changed === null` means first paint).
  Hover (`hover`, `hx`, `hy`) fires on every mouse move — never re-render the
  panel or rebuild map paths on it.
- **Derived numbers live in `src/model.js`, never in a renderer.** Model
  functions are pure over the provider `F` and `state`; add a new metric or
  panel figure there and consume it from `map.js` / `panel.js`.
- **The data seam is `data/provider.js`.** The UI only uses the object
  `loadProvider()` returns. To wire the real `electiondata` API, implement the
  same accessor surface (prefetch inside `loadProvider`, keep accessors
  synchronous), set `SOURCE.kind = 'api'`, and update the "Fixture data" tag and
  the "synthetic fixture" footnotes in `panel.js`. Do not call `fetch` from
  renderers.
- **Adding a map metric:** append to `METRICS` in `format.js`, add its fill in
  `model.fillFor`, its legend entry in `model.legend`, and (if it needs one) a
  tooltip row in `model.tooltipRows`. Nothing else should change.
- **Adding an office:** `OFFICES` in `format.js`, `validYears` / `share` /
  `prevYear` in `model.js`, `electionLabel` / `title`, and the national and
  state-panel branches.
- **URL state** (`office`, `year`, `metric`, `state`) is parsed and validated in
  `app.js`; keep new shareable state there too.
- Templates use `esc()` from `format.js` for any text from data.
- SVG elements have no `.hidden` property — toggle visibility with
  `el.toggleAttribute('hidden', bool)` (the `[hidden]` rule in `app.css` hides
  it).

## Design system

`frontend/ds/industry.css` is the Industry design system, vendored verbatim
from the design project (`_ds/industry-1045886b-…/styles.css`). Rules that
matter when styling:

- Take every colour, font, spacing, radius and shadow from its variables
  (`--color-*`, `--font-*`, `--space-*`, `--radius-*`, `--shadow-*`). The only
  hard-coded colours allowed in `app.css` are the party encodings
  `--color-dem` / `--color-rep` / `--color-neutral-map` and the chart ramps in
  `model.js` (they are data, not brand).
- Build with the DS classes — `.blueprint` + four `<i class="corner tl/tr/bl/br">`,
  `.btn`/`.btn-icon`, `.seg` + `.seg-opt` (native radios), `.input`, `.table`,
  `.tag`, `.nav`. Square corners everywhere; cards are transparent hairline
  frames with registration marks, never filled or rounded.
- Barlow Condensed for headings and big numbers, Barlow for body; `h6` is the
  uppercase tracked kicker. Icons are Lucide-style inline SVG at
  stroke-width 1.5.
- Keep `:focus-visible` on the accent ring; don't restyle hover/pressed states
  per element.
- Never hand-edit `ds/industry.css`. To re-sync it, read the file from the
  design project with the DesignSync tool (`get_file`, path
  `_ds/industry-1045886b-26bf-4e70-b3bf-5b448f3e1630/styles.css`) and overwrite
  the vendored copy in one commit.

## Syncing with the design

When the design project changes, `get_file` `Election Explorer.dc.html` and
diff its template (`<x-dc>` markup) and `renderVals()` logic against
`index.html` / `panel.js` / `model.js`. The design's `data-props`
(`showLabels`, `transitionMs`) map to `PROPS` in `src/config.js`.

## Commits

One commit per feature or fix, scoped `feat(frontend): …` / `fix(frontend): …`
/ `docs(frontend): …`. Screenshot-verify before committing UI changes.

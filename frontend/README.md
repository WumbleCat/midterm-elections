# Election Explorer (frontend)

A buildless static implementation of the **Election Explorer** screen from the
Claude Design project (`Election Explorer.dc.html`): a choropleth of the United
States that steps through every federal election since 1980, with a national
summary and a per-state analysis panel.

```
uv run python frontend/serve.py        # http://127.0.0.1:8000/
```

No Node toolchain: plain HTML, CSS and ES modules. `d3` and `topojson-client`
load from jsdelivr, and the state geometry (`us-atlas` 10m) is fetched at
runtime.

## Layout

| Path | Role |
| --- | --- |
| `index.html` | Page skeleton — header, toolbar, map card, side panel, timeline footer. Dynamic regions are empty containers with ids. |
| `app.css` | Page styles. Values come from the design-system tokens; only the two party colours are added. |
| `ds/industry.css` | The Industry design system, vendored verbatim. Do not hand-edit (see `ds/README.md`). |
| `data/fixtures.js` | Synthetic, deterministic, election-shaped fixture data (ported from the design). Not real results. |
| `data/provider.js` | The data seam. `loadProvider()` returns the accessor object the UI uses; swap its implementation to wire the `electiondata` API. |
| `src/app.js` | Entry: builds the store, model and views; reads/writes URL state. |
| `src/store.js` | Tiny observable state (`get` / `set(patch)` / `subscribe`), notifies with the set of changed keys. |
| `src/model.js` | Pure derived numbers: shares, swings, fills, legend, national totals, state-panel data. |
| `src/map.js` | Geography load + choropleth rendering, hover/selection, zoom-to-state, labels, tooltip, legend. |
| `src/panel.js` | Side panel templates (national summary / state analysis). |
| `src/controls.js` | Office & metric segments, search (⌘K), as-of date, timeline, transport, autoplay, keyboard. |
| `src/format.js` | Formatters, party colours, office/metric option lists. |
| `src/config.js` | Page props (`?labels=0`, `?transition=250`), CDN URL, autoplay interval. |

## URL state

`?office=president|senate|house|midterm&year=YYYY&metric=margin|swing|dem|turnout|income|bachelors&state=GA`
— the app keeps the query string in sync as you navigate, so any view is
linkable.

## Interaction

- Hover a state for the tooltip; click (or right-click, or Enter/Space when
  focused) to select and zoom; Esc or the ✕ button clears.
- ← / → step through elections valid for the current office; ▶ autoplays.
- ⌘K / Ctrl+K focuses the state search; Enter picks the first match.
- Clicking a year in the political-history strip, the share chart or the
  timeline jumps to it.

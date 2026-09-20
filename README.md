# midterm-elections

## Election Explorer (frontend)

An interactive choropleth explorer of U.S. federal elections since 1980, implemented
from the Claude Design screen `Election Explorer.dc.html`. It is a buildless static app
(ES modules + d3) served by Python:

    uv run python frontend/serve.py        # http://127.0.0.1:8000/

It currently runs on synthetic fixture data; `frontend/data/provider.js` is the seam
where the `electiondata` API replaces the fixtures. See `frontend/README.md`.

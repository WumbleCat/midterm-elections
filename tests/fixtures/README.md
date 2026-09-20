# Test fixtures

Files named `*_sample.*` are **excerpts of real upstream files** downloaded on 2026-09-20
(rows for a few states only) and exercise the real source formats.

Files named `*_format_fixture.*`, `*_layout_fixture.*` and `*_template.csv` reproduce the
**structure** of sources that could not be fetched live (Census ACS and BEA need API keys,
MEDSL House is guestbook-gated, polls/Pew are manual). Their values are illustrative and
must never be ingested into the data store; they only test parsers and normalizers.

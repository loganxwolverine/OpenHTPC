# RC8 Media Enrichment — Development Limitation

Interactive single-item enrichment currently runs synchronously through Flex
`:applyback`.

While TMDb movie details are fetched, poster artwork is downloaded and cached,
and the Flex configuration is regenerated, the Flex event loop is blocked and
the UI is unresponsive. Repeated input from the same Flex process is therefore
serialized rather than launching concurrent enrichment commands.

A future `RC8 UX — ASYNC ENRICHMENT / ACTIVITY FEEDBACK` tranche is required to
make enrichment asynchronous and support animated busy feedback. The current
functional patch intentionally does not change the Flex execution model.

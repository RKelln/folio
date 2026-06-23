"""Offline converter comparison/benchmark harness.

Runs every available document converter over the committed synthetic corpus
(``benchmark/corpus/``, produced by ``folio corpus``) and scores each output
against its golden Markdown reference. Modules:

* :mod:`folio.core.bench.spec`    — standalone benchmark spec (YAML config).
* :mod:`folio.core.bench.corpus`  — discover golden/rendered case pairs.
* :mod:`folio.core.bench.scorer`  — deterministic, offline scoring metrics.
* :mod:`folio.core.bench.runner`  — run converters, time them, aggregate scores.
* :mod:`folio.core.bench.report`  — scorecard table + Markdown comparison report.

Consumers import directly from the submodules (mirroring
``folio.core.corpus``); this package ``__init__`` deliberately re-exports
nothing to keep import order simple.
"""

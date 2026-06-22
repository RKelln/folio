"""Seeded, length-matched synthetic content helpers for the corpus builder.

These helpers produce PII-free, *realistic-looking* filler — names, emails,
phone numbers, addresses, organisation names, money amounts, dates and prose —
for the synthetic grant corpus (bead folio-4v7). The generated text never
contains real personal data; every value comes from `Faker`.

Determinism contract
---------------------
The corpus pipeline treats authored Markdown as a deterministic golden
reference, so identical input must produce byte-identical output. To guarantee
that:

* :func:`seed_all` seeds **three** sources of randomness — Python's global
  ``random`` module, Faker's shared class-level generator (``Faker.seed``) and
  the returned instance's private generator (``Faker.seed_instance``).
* Every helper draws *only* from a :class:`~faker.Faker` instance's own
  generator (``fake.random_int``, ``fake.sentence`` …). No helper reads the
  wall clock, the environment, process state, or any unseeded global. As a
  result, ``fake_date`` is reproducible regardless of the day it runs.
* Helpers accept an explicit ``Faker`` instance **or** fall back to a
  module-level default that :func:`seed_all` configures. Passing the instance
  returned by :func:`seed_all` is the recommended, thread-safe pattern; the
  module-level default exists for convenience in single-threaded call sites and
  its assignment is guarded by a lock.

Given the same seed and the same *ordered* sequence of helper calls, the output
is identical across processes — **provided the same Faker version and the
``en_CA`` locale are installed**. Different Faker releases or a missing locale
can change generated values for the same seed; pin Faker for fully
machine-independent reproducibility.
"""
from __future__ import annotations

import datetime
import logging
import random
import re
import threading

from faker import Faker

logger = logging.getLogger(__name__)

_PREFERRED_LOCALE = "en_CA"

_DEFAULT_FAKE: Faker | None = None
#: Guards assignment/lazy-init of the module-level default Faker (AGENTS.md
#: Rule 10 — shared mutable state touched from multiple threads needs a lock).
_DEFAULT_LOCK = threading.Lock()


def _make_faker() -> Faker:
    """Build a Faker configured with the preferred locale, falling back safely.

    Returns:
        A :class:`~faker.Faker` instance using the ``en_CA`` locale when the
        installed Faker ships it, otherwise the default locale.
    """
    try:
        return Faker(_PREFERRED_LOCALE)
    except (AttributeError, ValueError, KeyError) as exc:
        logger.warning(
            "Faker locale %r unavailable (%s); using default locale.",
            _PREFERRED_LOCALE,
            exc,
        )
        return Faker()


def _seed(seed: int) -> Faker:
    """Seed all randomness sources and return a fresh seeded Faker.

    Mutates global ``random`` state and Faker's class-level seed; does **not**
    touch the module default (so it is safe to call inside the default lock).
    """
    random.seed(seed)
    Faker.seed(seed)
    fake = _make_faker()
    fake.seed_instance(seed)
    return fake


def seed_all(seed: int) -> Faker:
    """Seed every randomness source and return a configured Faker instance.

    Seeds Python's global ``random`` module, Faker's shared class-level
    generator and a fresh instance's private generator, then stores that
    instance as the module-level default used by helpers when no explicit
    instance is supplied.

    Args:
        seed: Integer seed. The same seed reproduces identical output for an
            identical, ordered sequence of helper calls.

    Returns:
        A seeded :class:`~faker.Faker` instance. Pass this back into the other
        helpers (recommended) or rely on the module-level default.

    Side effects:
        Mutates global ``random`` state, Faker's class-level seed and this
        module's default Faker instance (the latter under ``_DEFAULT_LOCK``).
    """
    fake = _seed(seed)
    global _DEFAULT_FAKE
    with _DEFAULT_LOCK:
        _DEFAULT_FAKE = fake
    return fake


def _resolve(fake: Faker | None) -> Faker:
    """Return the supplied Faker, or the seeded module default, seeding lazily.

    Args:
        fake: An explicit Faker instance, or ``None`` to use the default.

    Returns:
        A usable Faker instance. If no default has been configured yet, one is
        created and seeded with ``0`` (with a warning) so calls never fail;
        callers wanting reproducible output should always call :func:`seed_all`
        first.
    """
    if fake is not None:
        return fake
    global _DEFAULT_FAKE
    with _DEFAULT_LOCK:
        if _DEFAULT_FAKE is None:
            logger.warning(
                "content default Faker used before seed_all(); seeding with 0. "
                "Call seed_all(seed) first for intended reproducibility."
            )
            _DEFAULT_FAKE = _seed(0)
        return _DEFAULT_FAKE


def fake_name(fake: Faker | None = None) -> str:
    """Return a synthetic personal name.

    Args:
        fake: Optional seeded Faker instance; falls back to the module default.

    Returns:
        A full personal name such as ``"Shannon Farrell"``.
    """
    return _resolve(fake).name()


def _slugify_name(name: str) -> str:
    """Convert a personal name into an email-friendly dotted local part.

    Args:
        name: A human name, possibly containing initials and punctuation.

    Returns:
        A lowercase, dot-separated token (e.g. ``"john.smith"``), or an empty
        string if nothing usable remains.
    """
    tokens = re.findall(r"[A-Za-z0-9]+", name.lower())
    return ".".join(tokens)


def fake_email(fake: Faker | None = None, name: str | None = None) -> str:
    """Return a synthetic email address.

    Args:
        fake: Optional seeded Faker instance; falls back to the module default.
        name: When provided, the local part is derived from it so the address
            reads as belonging to that person (e.g. ``"john.smith@..."``).

    Returns:
        An email address containing exactly one ``@``.
    """
    resolved = _resolve(fake)
    if name:
        local = _slugify_name(name)
        if local:
            return f"{local}@{resolved.domain_name()}"
    return resolved.email()


def fake_phone(fake: Faker | None = None) -> str:
    """Return a synthetic North American phone number.

    The number is built from seeded integers (not Faker's locale-dependent
    ``phone_number`` provider) so the format and digit count are stable.

    Args:
        fake: Optional seeded Faker instance; falls back to the module default.

    Returns:
        A string formatted ``"(NPA) NXX-XXXX"`` with at least ten digits.
    """
    resolved = _resolve(fake)
    area = resolved.random_int(200, 999)
    prefix = resolved.random_int(200, 999)
    line = resolved.random_int(0, 9999)
    return f"({area}) {prefix}-{line:04d}"


def fake_address(fake: Faker | None = None) -> str:
    """Return a synthetic single-line street address.

    Faker addresses are multi-line; newlines are collapsed to ``", "`` so the
    value drops cleanly into a form field or table cell.

    Args:
        fake: Optional seeded Faker instance; falls back to the module default.

    Returns:
        A single-line address with no embedded newlines.
    """
    raw = _resolve(fake).address()
    return ", ".join(part.strip() for part in raw.splitlines() if part.strip())


def fake_org_name(fake: Faker | None = None) -> str:
    """Return a synthetic organisation name.

    Args:
        fake: Optional seeded Faker instance; falls back to the module default.

    Returns:
        A company-style organisation name (e.g. ``"Perez-Smith"``).
    """
    return _resolve(fake).company()


def fake_money(fake: Faker | None = None, low: int = 500, high: int = 50000) -> str:
    """Return a synthetic, thousands-separated currency amount.

    Args:
        fake: Optional seeded Faker instance; falls back to the module default.
        low: Inclusive lower bound for the amount.
        high: Inclusive upper bound for the amount.

    Returns:
        A string formatted like ``"$12,500"`` matching ``\\$\\d{1,3}(,\\d{3})*``.
    """
    amount = _resolve(fake).random_int(low, high)
    return f"${amount:,}"


def fake_date(
    fake: Faker | None = None, start_year: int = 2018, end_year: int = 2024
) -> str:
    """Return a synthetic ISO date within an inclusive year range.

    The range is anchored to explicit ``date`` objects (Jan 1 of ``start_year``
    through Dec 31 of ``end_year``) rather than "today", so the result does not
    depend on when the helper runs.

    Args:
        fake: Optional seeded Faker instance; falls back to the module default.
        start_year: First eligible calendar year (inclusive).
        end_year: Last eligible calendar year (inclusive).

    Returns:
        An ISO-8601 date string ``"YYYY-MM-DD"``.
    """
    start = datetime.date(start_year, 1, 1)
    end = datetime.date(end_year, 12, 31)
    return _resolve(fake).date_between_dates(start, end).isoformat()


def _trim_to_word_boundary(text: str, target_chars: int, tolerance: float) -> str:
    """Trim ``text`` down to the word boundary closest to the target length.

    Used as the precise fallback when whole-sentence accumulation overshoots
    the requested length by more than the tolerance.

    Args:
        text: Source text (assumed at least ``target_chars`` long).
        target_chars: Desired character count.
        tolerance: Maximum allowed absolute deviation from ``target_chars``.

    Returns:
        A prefix of ``text`` ending on a word boundary whose length is within
        ``tolerance`` of ``target_chars`` when achievable.
    """
    words = text.split(" ")
    out = ""
    for word in words:
        candidate = word if not out else f"{out} {word}"
        if len(candidate) > target_chars + tolerance:
            break
        out = candidate
        if abs(len(out) - target_chars) <= tolerance:
            break
    return out or text[: target_chars + int(tolerance)]


def lorem_matching(fake: Faker | None = None, target_chars: int = 0) -> str:
    """Generate sentence-based filler whose length matches ``target_chars``.

    Sentences are appended until the running text reaches the target band, then
    the result is trimmed to a sentence boundary near the target (falling back
    to a word boundary when a single sentence would overshoot the 10% band).
    The text is genuine varied Faker prose, never a fixed "Lorem ipsum" string,
    so wrapping and pagination behave like a real document.

    Args:
        fake: Optional seeded Faker instance; falls back to the module default.
        target_chars: Desired character count. Non-positive values yield ``""``.

    Returns:
        Filler text whose length is within ~10% of ``target_chars``.
    """
    if target_chars <= 0:
        return ""
    resolved = _resolve(fake)
    tolerance = target_chars * 0.1

    sentences: list[str] = []
    text = ""
    # Accumulate sentences until we have at least enough material to trim from.
    while len(text) < target_chars + tolerance:
        sentences.append(resolved.sentence(nb_words=resolved.random_int(8, 16)))
        text = " ".join(sentences)

    # Prefer trimming on a sentence boundary: keep the longest prefix of whole
    # sentences that stays within the upper tolerance bound.
    best = ""
    running = ""
    for sentence in sentences:
        candidate = sentence if not running else f"{running} {sentence}"
        if len(candidate) > target_chars + tolerance:
            break
        running = candidate
        best = candidate

    if best and abs(len(best) - target_chars) <= tolerance:
        return best

    # A single sentence overshot the band (or the prefix fell short); fall back
    # to a precise word-boundary trim of the full accumulated text.
    return _trim_to_word_boundary(text, target_chars, tolerance)


def fake_paragraphs(
    fake: Faker | None = None, target_chars: int = 0, min_paras: int = 1
) -> list[str]:
    """Generate length-matched filler split across one or more paragraphs.

    The character budget is divided roughly evenly across the paragraphs, and
    each paragraph is produced with :func:`lorem_matching`, so the combined
    length stays within ~10% of ``target_chars``.

    Args:
        fake: Optional seeded Faker instance; falls back to the module default.
        target_chars: Total desired character count across all paragraphs.
        min_paras: Minimum number of paragraphs to emit.

    Returns:
        A list of paragraph strings. Returns ``[]`` for a non-positive target.
    """
    if target_chars <= 0:
        return []
    resolved = _resolve(fake)
    para_count = max(min_paras, round(target_chars / 500) or 1)

    base = target_chars // para_count
    remainder = target_chars - base * para_count
    paragraphs: list[str] = []
    for index in range(para_count):
        share = base + (1 if index < remainder else 0)
        paragraphs.append(lorem_matching(resolved, share))
    return paragraphs

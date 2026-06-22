"""Golden Markdown generator for the synthetic, PII-free grant corpus.

PURPOSE
    Author deterministic, PII-free grant documents whose *structure* (frontmatter,
    headings, labelled form fields, pipe tables, letters) mirrors a real grant
    archive, but whose *content* is entirely synthetic. The Markdown produced
    here is THE golden reference for bead folio-4v7: every derived render
    (PDF/DOCX/XLSX) is generated from this source, so it must be reproducible to
    the byte.

DESIGN
    * Section headings are **config-driven**: canonical heading names are read
      from the bundled profile YAML (``templates/profiles/<profile>.yaml``) via
      :func:`load_profile_headings`, never hardcoded.
    * Content comes exclusively from the seeded helpers in
      ``folio.core.corpus.content`` (Faker-backed, length-matched). The whole
      corpus is seeded **once** per :func:`generate_corpus` call, then every
      document is authored in a fixed order so the ordered sequence of Faker
      draws — and therefore the output — is identical for a given spec.
    * Budget totals are computed arithmetically from their rows (never faked),
      so the XLSX/structured renderers can rely on them.

PUBLIC API (imported by the ``folio corpus`` CLI in Round C):
    GoldenDoc (dataclass)
    load_profile_headings(profile, funder) -> list[str]
    generate_corpus(spec)                  -> list[GoldenDoc]
    write_golden(doc, out_dir)             -> Path

PII SAFETY
    Application/budget/activity documents legitimately contain emails, phones,
    addresses and ``$`` amounts in their form fields, so the conservative
    :mod:`folio.core.corpus.pii_scan` gate will flag those structurally — that
    is expected. The generator never emits a real personal name: all names are
    Faker-generated and the corpus is validated against the denylist in tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import yaml
from faker import Faker

from .content import (
    fake_address,
    fake_date,
    fake_email,
    fake_money,
    fake_name,
    fake_org_name,
    fake_paragraphs,
    fake_phone,
    lorem_matching,
    seed_all,
)
from .spec import CorpusSpec

#: Default language tag stamped into every document's frontmatter. English-only
#: keeps the golden corpus clean for the PII gate; multilingual variants would
#: live in profile config, not here.
_DEFAULT_LANGUAGE = "en"

#: Revenue line-item labels for budget documents. Generic financial categories
#: (not org-specific), so they live here as authoring vocabulary rather than in
#: the profile. ``{funder}`` is interpolated into the first row.
_REVENUE_LABELS: tuple[str, ...] = (
    "Grant — {funder} Project",
    "Earned revenue",
    "Memberships and donations",
)

#: Expense line-item labels for budget documents (see note on revenue labels).
_EXPENSE_LABELS: tuple[str, ...] = (
    "Artist fees",
    "Programming and production",
    "Administration",
    "Marketing and outreach",
)

#: Staff/board roles for staff_board documents — a mix of paid staff and
#: volunteer board positions, ~8 rows.
_STAFF_BOARD_ROLES: tuple[str, ...] = (
    "Executive Director",
    "Artistic Director",
    "Program Coordinator",
    "Technical Director",
    "Board Chair",
    "Board Treasurer",
    "Board Secretary",
    "Board Member",
)


@dataclass
class GoldenDoc:
    """One authored golden document.

    Attributes:
        kind: The document kind (one of ``spec.ALLOWED_KINDS``).
        funder: The funder abbreviation the document targets (e.g. ``"OAC"``).
        frontmatter: The canonical frontmatter fields as a dict (funder, type,
            written, period, optionally grant_amount, language).
        markdown: The full golden source, INCLUDING the ``---`` frontmatter
            block at the very top.
        slug: The filename stem, e.g. ``"oac-application-01"``.
    """

    kind: str
    funder: str
    frontmatter: dict
    markdown: str
    slug: str


# --------------------------------------------------------------------------- #
# Profile headings (config-driven)
# --------------------------------------------------------------------------- #
def _profile_path(profile: str) -> Path:
    """Resolve a bundled profile YAML by name.

    Tries ``importlib.resources`` first (installed packages) and falls back to a
    path relative to this module (editable/source tree), mirroring
    ``spec._default_spec_path``.

    Args:
        profile: Profile name without extension (e.g. ``"canadian-artist-run-centre"``).

    Returns:
        The resolved :class:`~pathlib.Path` (which may not exist; callers check).
    """
    filename = f"{profile}.yaml"
    try:
        traversable = resources.files("folio.templates") / "profiles" / filename
        candidate = Path(str(traversable))
        if candidate.exists():
            return candidate
    except (ModuleNotFoundError, FileNotFoundError):
        pass
    # parents[2] == folio package root (corpus -> core -> folio).
    return Path(__file__).resolve().parents[2] / "templates" / "profiles" / filename


def load_profile_headings(profile: str, funder: str) -> list[str]:
    """Return the ordered canonical heading names for a funder from a profile.

    The bundled profile YAML stores headings under ``headings: <FUNDER>:
    headings:`` as a mapping of *canonical name* -> *variant list*. Only the
    canonical names (the mapping keys) are returned, in their declared order
    (YAML mappings preserve insertion order, so this is deterministic).

    Args:
        profile: Profile name (file stem under ``templates/profiles/``).
        funder: Funder abbreviation present in the profile's ``headings`` block.

    Returns:
        The ordered list of canonical heading names.

    Raises:
        ValueError: The profile file is missing/invalid, has no ``headings``
            block, or does not define the requested funder.
    """
    path = _profile_path(profile)
    if not path.exists():
        raise ValueError(f"profile not found: {profile!r} (looked at {path})")

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"profile {profile!r} is not valid YAML: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"profile {profile!r} must be a YAML mapping")

    headings_block = data.get("headings")
    if not isinstance(headings_block, dict):
        raise ValueError(f"profile {profile!r} has no 'headings' mapping")

    funder_block = headings_block.get(funder)
    if not isinstance(funder_block, dict):
        raise ValueError(
            f"profile {profile!r} defines no headings for funder {funder!r}; "
            f"known funders: {', '.join(sorted(headings_block))}"
        )

    funder_headings = funder_block.get("headings")
    if not isinstance(funder_headings, dict) or not funder_headings:
        raise ValueError(
            f"profile {profile!r} funder {funder!r} has an empty 'headings' map"
        )

    return [str(name) for name in funder_headings]


# --------------------------------------------------------------------------- #
# Frontmatter helpers
# --------------------------------------------------------------------------- #
#: Maps a corpus document ``kind`` to its canonical frontmatter ``type`` value.
_KIND_TO_TYPE: dict[str, str] = {
    "application": "application",
    "narrative": "report",
    "budget": "budget",
    "activity_list": "activity_list",
    "staff_board": "staff_board",
    "support_letter": "support_material",
}


def _build_frontmatter(
    fake: Faker, kind: str, funder: str, grant_amount: str | None
) -> dict:
    """Build the canonical frontmatter dict for a document.

    Draws a ``written`` year and ``period`` from the seeded Faker so the values
    are reproducible. ``grant_amount`` is included only when supplied (budget /
    application), keeping currency out of documents that must scan clean.

    Args:
        fake: The seeded Faker instance (draw order matters for determinism).
        kind: The document kind.
        funder: The funder abbreviation.
        grant_amount: Optional ``"$..."`` string to record, or ``None`` to omit.

    Returns:
        An ordered dict of canonical frontmatter fields.
    """
    written = fake.random_int(2018, 2024)
    fm: dict = {
        "funder": funder,
        "type": _KIND_TO_TYPE[kind],
        "written": written,
    }
    if kind in ("application", "budget"):
        fm["period"] = f"{written}\u2013{written + 2}"
    else:
        fm["period"] = str(written)
    if grant_amount is not None:
        fm["grant_amount"] = grant_amount
    fm["language"] = _DEFAULT_LANGUAGE
    return fm


def _frontmatter_block(fm: dict) -> str:
    """Render a frontmatter dict to the ``---`` YAML block (no trailing newline).

    Delegates to :func:`folio.core.frontmatter.dict_to_frontmatter` (the single
    canonical frontmatter serializer) so quoting rules stay consistent across
    folio. Imported lazily to avoid a hard import-time dependency.
    """
    from ..frontmatter import dict_to_frontmatter

    return dict_to_frontmatter(**fm)


# --------------------------------------------------------------------------- #
# Per-kind body authors
# --------------------------------------------------------------------------- #
def _money_to_int(amount: str) -> int:
    """Parse the integer value out of a ``fake_money`` string like ``"$12,500"``."""
    digits = amount.replace("$", "").replace(",", "").strip()
    return int(digits)


def _author_application(
    fake: Faker, funder: str, headings: list[str], grant_amount: str
) -> str:
    """Author an application body: labelled form fields then heading sections.

    ``grant_amount`` is the single per-document grant figure drawn once in
    :func:`generate_corpus` and shared with the frontmatter, so the
    ``**Request Amount:**`` line can never contradict ``grant_amount`` in the
    frontmatter (golden-corpus internal consistency).
    """
    name = fake_name(fake)
    lines = [
        f"# {funder} Operating Grant Application",
        "",
        f"**Applicant:** {name}",
        f"**Email:** {fake_email(fake, name=name)}",
        f"**Phone:** {fake_phone(fake)}",
        f"**Organization:** {fake_org_name(fake)}",
        f"**Address:** {fake_address(fake)}",
        f"**Request Amount:** {grant_amount}",
        f"**Project Title:** {lorem_matching(fake, 45)}",
        f"**Submission Date:** {fake_date(fake)}",
        "",
    ]
    for heading in headings:
        lines.append(f"## {heading}")
        lines.append("")
        for _ in range(fake.random_int(1, 2)):
            lines.append(lorem_matching(fake, fake.random_int(220, 360)))
            lines.append("")
    return "\n".join(lines).rstrip()


def _author_narrative(fake: Faker, funder: str, headings: list[str]) -> str:
    """Author a narrative report body: heading sections of multi-paragraph prose.

    Contains no form fields and no currency, so a narrative scans completely
    clean — it is the document the PII test asserts on.
    """
    lines = [f"# {funder} Program Narrative", ""]
    for heading in headings:
        lines.append(f"## {heading}")
        lines.append("")
        target = fake.random_int(600, 1200)
        for paragraph in fake_paragraphs(fake, target, min_paras=2):
            lines.append(paragraph)
            lines.append("")
    return "\n".join(lines).rstrip()


def _budget_table(
    fake: Faker,
    title: str,
    label_column: str,
    labels: tuple[str, ...],
    funder: str,
    *,
    override_first: str | None = None,
) -> tuple[list[str], int]:
    """Build one revenue/expense pipe table; return its lines and computed total.

    Amounts come from :func:`fake_money`; the total row is the arithmetic sum of
    the line amounts (computed here, never faked).

    ``override_first`` pins the amount of the FIRST row to a pre-drawn value
    (used for the funder grant line so it matches the frontmatter
    ``grant_amount``). When set, the first row does NOT draw its own
    ``fake_money`` value, keeping the remaining draw order stable.
    """
    rows: list[tuple[str, str]] = []
    total = 0
    for idx, label in enumerate(labels):
        if idx == 0 and override_first is not None:
            amount = override_first
        else:
            amount = fake_money(fake, 2000, 30000)
        total += _money_to_int(amount)
        rows.append((label.format(funder=funder), amount))

    lines = [
        f"### {title}",
        f"| {label_column} | Amount |",
        "| --- | --- |",
    ]
    lines.extend(f"| {label} | {amount} |" for label, amount in rows)
    lines.append(f"| **Total {title.lower()}** | ${total:,} |")
    return lines, total


def _author_budget(fake: Faker, funder: str, grant_amount: str) -> str:
    """Author a budget body: a ``## Budget`` with Revenue + Expenses tables.

    ``grant_amount`` (drawn once per document in :func:`generate_corpus`) is
    pinned to the ``Grant — <funder> Project`` Revenue row so it matches the
    frontmatter ``grant_amount`` exactly.
    """
    lines = ["# Project Budget", "", "## Budget", ""]
    revenue_lines, _ = _budget_table(
        fake, "Revenue", "Source", _REVENUE_LABELS, funder, override_first=grant_amount
    )
    lines.extend(revenue_lines)
    lines.append("")
    expense_lines, _ = _budget_table(
        fake, "Expenses", "Category", _EXPENSE_LABELS, funder
    )
    lines.extend(expense_lines)
    return "\n".join(lines).rstrip()


def _author_activity_list(fake: Faker, funder: str) -> str:
    """Author an activity-list body: a 6–12 row Date/Activity/Location table."""
    lines = [
        f"# {funder} Activity List",
        "",
        "| Date | Activity | Location |",
        "| --- | --- | --- |",
    ]
    for _ in range(fake.random_int(6, 12)):
        date = fake_date(fake)
        activity = lorem_matching(fake, fake.random_int(28, 48))
        location = fake_address(fake)
        lines.append(f"| {date} | {activity} | {location} |")
    return "\n".join(lines).rstrip()


def _author_staff_board(fake: Faker, funder: str) -> str:
    """Author a staff/board body: a Name/Role table of ~8 mixed roles."""
    lines = [
        f"# {funder} Staff and Board",
        "",
        "| Name | Role |",
        "| --- | --- |",
    ]
    for role in _STAFF_BOARD_ROLES:
        lines.append(f"| {fake_name(fake)} | {role} |")
    return "\n".join(lines).rstrip()


def _author_support_letter(fake: Faker, funder: str) -> str:
    """Author a support letter: date, salutation, body paragraphs, signature."""
    signatory = fake_name(fake)
    lines = [
        fake_date(fake),
        "",
        "Dear Grants Committee,",
        "",
    ]
    for _ in range(fake.random_int(2, 3)):
        lines.append(lorem_matching(fake, fake.random_int(280, 420)))
        lines.append("")
    lines.extend(
        [
            "Sincerely,",
            "",
            signatory,
            fake_org_name(fake),
        ]
    )
    return "\n".join(lines).rstrip()


def _author_body(
    fake: Faker,
    kind: str,
    funder: str,
    headings: list[str],
    grant_amount: str | None,
) -> str:
    """Dispatch to the author for ``kind`` and return the document body Markdown.

    ``grant_amount`` is the per-document grant figure (non-None for application
    and budget, which is enforced by :func:`_grant_amount_for`) propagated so
    the body and frontmatter agree.
    """
    if kind == "application":
        assert grant_amount is not None  # invariant: see _grant_amount_for
        return _author_application(fake, funder, headings, grant_amount)
    if kind == "narrative":
        return _author_narrative(fake, funder, headings)
    if kind == "budget":
        assert grant_amount is not None  # invariant: see _grant_amount_for
        return _author_budget(fake, funder, grant_amount)
    if kind == "activity_list":
        return _author_activity_list(fake, funder)
    if kind == "staff_board":
        return _author_staff_board(fake, funder)
    if kind == "support_letter":
        return _author_support_letter(fake, funder)
    raise ValueError(f"unknown document kind: {kind!r}")


# --------------------------------------------------------------------------- #
# Public generation API
# --------------------------------------------------------------------------- #
def _grant_amount_for(kind: str, fake: Faker) -> str | None:
    """Return a frontmatter ``grant_amount`` for kinds that carry one, else None.

    Drawn for application/budget only; doing it here (before body authoring)
    keeps the Faker draw order stable and deterministic.
    """
    if kind in ("application", "budget"):
        return fake_money(fake, 10000, 80000)
    return None


def generate_corpus(spec: CorpusSpec) -> list[GoldenDoc]:
    """Generate every document described by ``spec`` as golden Markdown.

    The corpus is seeded **once** via :func:`folio.core.corpus.content.seed_all`,
    then documents are authored in a stable order — spec order, and within each
    spec entry indices ``1..count`` — so the ordered sequence of Faker draws (and
    therefore the produced Markdown) is identical for an identical spec.

    Args:
        spec: The validated corpus specification.

    Returns:
        A list of :class:`GoldenDoc`, one per (document spec x index), in
        generation order.
    """
    fake = seed_all(spec.seed)
    headings = load_profile_headings(spec.profile, spec.funder)

    docs: list[GoldenDoc] = []
    for doc_spec in spec.documents:
        for index in range(1, doc_spec.count + 1):
            kind = doc_spec.kind
            grant_amount = _grant_amount_for(kind, fake)
            frontmatter = _build_frontmatter(fake, kind, spec.funder, grant_amount)
            body = _author_body(fake, kind, spec.funder, headings, grant_amount)
            block = _frontmatter_block(frontmatter)
            markdown = f"{block}\n\n{body}\n"
            slug = f"{spec.funder.lower()}-{kind}-{index:02d}"
            docs.append(
                GoldenDoc(
                    kind=kind,
                    funder=spec.funder,
                    frontmatter=frontmatter,
                    markdown=markdown,
                    slug=slug,
                )
            )
    return docs


def write_golden(doc: GoldenDoc, out_dir: str | Path) -> Path:
    """Write a golden document's Markdown to ``<out_dir>/golden/<slug>.md``.

    Args:
        doc: The document to write.
        out_dir: Base output directory; a ``golden/`` subdirectory is created
            beneath it (along with any missing parents).

    Returns:
        The path the Markdown was written to.

    Side effects:
        Creates directories and writes a UTF-8 file (overwriting any existing
        file at the target path).
    """
    golden_dir = Path(out_dir) / "golden"
    golden_dir.mkdir(parents=True, exist_ok=True)
    target = golden_dir / f"{doc.slug}.md"
    target.write_text(doc.markdown, encoding="utf-8")
    return target

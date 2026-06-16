"""File quality classification and tier assignment.

Replaces Python ``eval()`` with a safe condition DSL for rule evaluation.
Scores files by content quality (form chrome, corruption, draft markers,
content density) and assigns a :class:`FileStatus` and :class:`ProcessingTier`
based on configurable skip/tier rules.

Usage::

    from folio.core.classifier import classify_file, classify_directory

    config = load_my_config()  # dict with funders, doc_types, skip_rules, etc.
    result = classify_file(Path("clean_md/my_doc.md"), config)
    manifest = classify_directory(Path("clean_md"), config)
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from pathlib import Path

logger = logging.getLogger(__name__)

from folio.core.errors import FileStatus, ProcessingTier
from folio.core.frontmatter import extract_year, parse_frontmatter

_FRENCH_WORDS = frozenset({"le", "la", "les", "de", "du", "des", "et", "est", "que", "qui", "dans", "pour", "sur", "une", "avec", "sont", "par", "plus", "faire", "peut", "ces", "leur", "pas", "nous", "vous", "ils", "elle", "ses", "aux"})
_ENGLISH_WORDS = frozenset({"the", "and", "for", "with", "that", "this", "have", "from", "are", "was", "not", "but", "all", "can", "had", "been", "one", "has", "were", "its", "also", "than", "them", "some", "may", "who", "which", "will"})


def detect_language(text: str) -> str:
    """Detect document language as 'en', 'fr', or 'mixed'.

    Uses frequency analysis of common French vs English words.
    No external dependencies required.
    """
    words = set(text.lower().split())
    fr_count = len(words & _FRENCH_WORDS)
    en_count = len(words & _ENGLISH_WORDS)
    if fr_count == 0 and en_count == 0:
        return "en"
    ratio = fr_count / max(en_count, 1)
    if ratio > 2.0:
        return "fr"
    elif ratio > 0.5:
        return "mixed"
    return "en"

# ── Default configuration ─────────────────────────────────────────────────────

DEFAULT_CLASSIFY_CONFIG: dict = {
    "funders": {},
    "doc_types": {},
    "form_chrome": [],
    "draft_markers": [],
    "corruption": {
        "single_char_alpha": True,
        "bare_digits": True,
    },
    "thresholds": {
        "min_content_lines": 15,
        "max_corruption_score": 0.5,
        "full_rewrite": {
            "form_chrome_count": 5,
            "draft_marker_count": 5,
            "duplicate_heading_count": 5,
            "word_count_annotation_count": 5,
        },
        "full_rewrite_app_report": {
            "form_chrome_count": 2,
            "draft_marker_count": 2,
        },
        "light_cleanup": {
            "form_chrome_count": 2,
            "draft_marker_count": 2,
            "duplicate_heading_count": 2,
            "word_count_annotation_count": 2,
        },
        "raw_financial": {
            "max_avg_line_length": 50,
            "min_content_lines": 50,
        },
    },
    "skip_rules": [],
    "tier_rules": [],
}

def build_classify_config(project_config) -> dict:
    """Merge project configuration into a classify-ready config dict.

    Starts from :data:`DEFAULT_CLASSIFY_CONFIG` and overlays funders,
    classification rules, and document types from a project config object
    (or a YAML-loaded dict).  Returns a flat dict ready to pass to
    :func:`classify_file` / :func:`classify_directory`.

    If *project_config* is ``None`` the defaults are returned unchanged.
    """
    classify_config = dict(DEFAULT_CLASSIFY_CONFIG)
    if project_config is None:
        return classify_config
    classify_config["funders"] = project_config.funders
    if project_config.classification:
        for key in ("doc_types", "form_chrome", "draft_markers", "corruption",
                     "thresholds", "skip_rules", "tier_rules", "word_count_pattern"):
            if key in project_config.classification:
                classify_config[key] = project_config.classification[key]
    if project_config.doc_types and "doc_types" not in classify_config:
        classify_config["doc_types"] = {dt: [r'(?i)\b' + dt + r'\b'] for dt in project_config.doc_types}
    return classify_config


# ── Safe Condition DSL ────────────────────────────────────────────────────────


def evaluate_condition(condition: dict, context: dict) -> bool:
    """Evaluate a single condition against a file context.

    Supported condition types:

    * ``has_doc_type`` — check if a document type label is present.
    * ``has_any_type`` — check if any of several type labels is present.
    * ``field_gt`` / ``field_lt`` / ``field_gte`` / ``field_lte`` — numeric
      field comparisons against the context.
    * ``path_contains`` — check if any substring appears in the file path.
    * ``filename_starts_with`` — prefix match against the filename.
    * ``has_headings`` / ``has_tables`` — boolean flags.
    * ``not_`` — negate another condition.
    * ``true`` — always true.
    """
    cond_type = condition["type"]
    if cond_type == "has_doc_type":
        return condition["value"] in context.get("doc_types", [])
    if cond_type == "has_any_type":
        return any(t in context.get("doc_types", []) for t in condition["values"])
    if cond_type == "field_gt":
        return context.get(condition["field"], 0) > condition["value"]
    if cond_type == "field_lt":
        return context.get(condition["field"], 0) < condition["value"]
    if cond_type == "field_gte":
        return context.get(condition["field"], 0) >= condition["value"]
    if cond_type == "field_lte":
        return context.get(condition["field"], 0) <= condition["value"]
    if cond_type == "path_contains":
        return any(s in context.get("filepath", "") for s in condition["values"])
    if cond_type == "filename_starts_with":
        return context.get("filename", "").startswith(condition["value"])
    if cond_type == "has_headings":
        return context.get("has_headings", False)
    if cond_type == "has_tables":
        return context.get("has_tables", False)
    if cond_type == "not_":
        return not evaluate_condition(condition["condition"], context)
    if cond_type == "true":
        return True
    raise ValueError(f"Unknown condition type: {cond_type}")


def evaluate_rule(rule: dict, context: dict) -> bool:
    """Evaluate a rule (set of conditions) against a file context.

    A rule has ``conditions`` (list of condition dicts) and ``match``
    (``"all"`` or ``"any"``).  Returns ``True`` when the match strategy
    is satisfied.

    Sub-conditions that themselves have a ``conditions`` key (nested
    compound rules from parenthesized expressions) are evaluated
    recursively instead of being passed to :func:`evaluate_condition`.
    """
    conditions = rule.get("conditions", [])
    match_type = rule.get("match", "all")
    if not conditions:
        return True

    def _eval_one(c: dict) -> bool:
        if "conditions" in c:
            return evaluate_rule(c, context)
        return evaluate_condition(c, context)

    if match_type == "all":
        return all(_eval_one(c) for c in conditions)
    return any(_eval_one(c) for c in conditions)


# ── Legacy eval-string parser ─────────────────────────────────────────────────

# Maps old function/expression patterns to new DSL condition dicts.
#
# The parser handles the subset of Python expressions used in
# ``classify_config.yaml`` skip/tier rules:
#
#   has_type('X')                → has_doc_type
#   has_any_type('X', 'Y')       → has_any_type
#   path_contains('X', 'Y')      → path_contains
#   filename.startswith('X')     → filename_starts_with
#   has_headings                 → has_headings
#   has_tables                   → has_tables
#   not <expr>                   → not_
#   > < >= <= comparisons        → field_gt / field_lt / field_gte / field_lte
#   and / or                     → multiple conditions + match
#   true / True / false / False  → true / not_ true

_TOKEN_RE = re.compile(
    r"""(?P<LPAREN>\()|(?P<RPAREN>\))|(?P<COMMA>,)|(?P<DOT>\.)|
        (?P<OP>>=?|<=?)|
        (?P<STRING>'[^']*'|\"[^\"]*\")|
        (?P<NUMBER>\d+\.?\d*)|
        (?P<NAME>~?\$?[a-zA-Z_][\w$]*)|(?P<UNKNOWN>\S+)""",
    re.VERBOSE,
)

_KEYWORDS = frozenset({"not", "and", "or", "true", "false"})


def _tokenize(expr: str) -> list[tuple[str, str | int | float]]:
    """Tokenize a legacy condition expression string."""
    tokens: list[tuple[str, str | int | float]] = []
    for m in _TOKEN_RE.finditer(expr):
        kind = m.lastgroup
        value: str | int | float = m.group(kind)
        if kind == "STRING":
            value = value[1:-1]
        elif kind == "NUMBER":
            value = float(value) if "." in str(value) else int(value)
        elif kind == "NAME":
            kind = "KEYWORD" if value.lower() in _KEYWORDS else "NAME"
            value = value if value.lower() in ("true", "false") else value
            if isinstance(value, str) and value.lower() in ("true", "false"):
                value = value.lower()
        elif kind == "UNKNOWN":
            continue
        tokens.append((kind, value))
    return tokens


class _ParseError(ValueError):
    """Raised when a legacy condition expression cannot be parsed."""


def parse_legacy_eval_condition(condition_str: str) -> dict:
    """Convert an old eval-style condition string to the safe DSL format.

    Returns a single condition dict (for simple expressions) or a rule-like
    dict with ``conditions`` and ``match`` keys (for ``and``/``or`` compounds).

    Examples::

        >>> parse_legacy_eval_condition("has_type('guidelines')")
        {'type': 'has_doc_type', 'value': 'guidelines'}

        >>> parse_legacy_eval_condition(
        ...     "has_type('guidelines') and corruption_score > 0.5"
        ... )
        {'conditions': [
            {'type': 'has_doc_type', 'value': 'guidelines'},
            {'type': 'field_gt', 'field': 'corruption_score', 'value': 0.5}
        ], 'match': 'all'}
    """
    if not condition_str or not condition_str.strip():
        return {"type": "true"}
    tokens = _tokenize(condition_str)
    parser = _LegacyParser(tokens)
    result = parser.parse_expression()
    if parser.pos < len(parser.tokens):
        raise _ParseError(
            f"Unexpected token at position {parser.pos}: "
            f"{parser.tokens[parser.pos]}"
        )
    return result


class _LegacyParser:
    """Recursive-descent parser for legacy eval condition strings."""

    def __init__(self, tokens: list[tuple[str, str | int | float]]) -> None:
        self.tokens = tokens
        self.pos = 0

    # -- helpers ---------------------------------------------------------------

    def _peek(self) -> tuple[str, str | int | float] | None:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def _consume(self, expected_kind: str | None = None) -> tuple[str, str | int | float]:
        if self.pos >= len(self.tokens):
            raise _ParseError("Unexpected end of expression")
        tok = self.tokens[self.pos]
        if expected_kind is not None and tok[0] != expected_kind:
            raise _ParseError(f"Expected {expected_kind}, got {tok}")
        self.pos += 1
        return tok

    # -- grammar ---------------------------------------------------------------

    def parse_expression(self) -> dict:
        """expression := or_expr"""
        return self._parse_or()

    def _parse_or(self) -> dict:
        """or_expr := and_expr ("or" and_expr)*"""
        left = self._parse_and()
        parts: list[dict] = []
        while self._peek() and self._peek()[0] == "KEYWORD" and self._peek()[1] == "or":
            if not parts:
                parts.append(left)
            self._consume("KEYWORD")
            parts.append(self._parse_and())
        if not parts:
            return left
        return {"conditions": parts, "match": "any"}

    def _parse_and(self) -> dict:
        """and_expr := not_expr ("and" not_expr)*"""
        left = self._parse_not()
        parts: list[dict] = []
        while self._peek() and self._peek()[0] == "KEYWORD" and self._peek()[1] == "and":
            if not parts:
                parts.append(left)
            self._consume("KEYWORD")
            parts.append(self._parse_not())
        if not parts:
            return left
        return {"conditions": parts, "match": "all"}

    def _parse_not(self) -> dict:
        """not_expr := "not" not_expr | atom"""
        if self._peek() and self._peek()[0] == "KEYWORD" and self._peek()[1] == "not":
            self._consume("KEYWORD")
            inner = self._parse_not()
            return {"type": "not_", "condition": inner}
        return self._parse_atom()

    def _parse_atom(self) -> dict:
        """atom := "(" expression ")" | call_or_comparison | bare_name"""
        tok = self._peek()
        if tok is None:
            raise _ParseError("Unexpected end of expression")
        if tok[0] == "LPAREN":
            self._consume("LPAREN")
            result = self.parse_expression()
            self._consume("RPAREN")
            return result
        if tok[0] == "NAME" or tok[0] == "KEYWORD":
            return self._parse_name_or_keyword()
        raise _ParseError(f"Unexpected token: {tok}")

    def _parse_name_or_keyword(self) -> dict:
        """Parse a name token — may be func call, method call, comparison, or bare."""
        first = self._consume()
        name = first[1]

        # Handle bare true/false
        if first[0] == "KEYWORD" and name in ("true", "false"):
            if name == "true":
                return {"type": "true"}
            return {"type": "not_", "condition": {"type": "true"}}

        # Look ahead for .method( or ( or OP
        nxt = self._peek()

        if nxt and nxt[0] == "DOT":
            # Method call: name.method(args)
            self._consume("DOT")
            method_tok = self._consume("NAME")
            method = method_tok[1]
            args = self._parse_arg_list()
            return self._build_method_call(name, method, args)

        if nxt and nxt[0] == "LPAREN":
            # Function call: name(args)
            args = self._parse_arg_list()
            return self._build_func_call(name, args)

        if nxt and nxt[0] == "OP":
            # Comparison: name OP value
            op = self._consume("OP")[1]
            val = self._consume("NUMBER")[1]
            return self._build_comparison(name, op, val)

        # Bare name (boolean)
        if name == "has_headings":
            return {"type": "has_headings"}
        if name == "has_tables":
            return {"type": "has_tables"}
        raise _ParseError(f"Unknown bare name: {name}")

    def _parse_arg_list(self) -> list[str]:
        """Parse (arg, arg, ...) — already consumed LPAREN by caller if needed."""
        tok = self._peek()
        if tok and tok[0] == "LPAREN":
            self._consume("LPAREN")
        else:
            # Caller already consumed LPAREN or there's no arg list
            return []
        args: list[str] = []
        while self._peek() and self._peek()[0] != "RPAREN":
            tok = self._consume("STRING")
            args.append(str(tok[1]))
            if self._peek() and self._peek()[0] == "COMMA":
                self._consume("COMMA")
        self._consume("RPAREN")
        return args

    # -- builders --------------------------------------------------------------

    @staticmethod
    def _build_func_call(name: str, args: list[str]) -> dict:
        if name == "has_type":
            if len(args) != 1:
                raise _ParseError(f"has_type expects 1 argument, got {len(args)}")
            return {"type": "has_doc_type", "value": args[0]}
        if name == "has_any_type":
            if len(args) < 1:
                raise _ParseError(f"has_any_type expects at least 1 argument")
            return {"type": "has_any_type", "values": args}
        if name == "path_contains":
            if len(args) < 1:
                raise _ParseError(f"path_contains expects at least 1 argument")
            return {"type": "path_contains", "values": args}
        raise _ParseError(f"Unknown function: {name}")

    @staticmethod
    def _build_method_call(obj: str, method: str, args: list[str]) -> dict:
        if obj == "filename" and method == "startswith":
            if len(args) != 1:
                raise _ParseError(f"filename.startswith expects 1 argument")
            return {"type": "filename_starts_with", "value": args[0]}
        raise _ParseError(f"Unknown method call: {obj}.{method}")

    @staticmethod
    def _build_comparison(name: str, op: str, value: int | float) -> dict:
        if op == ">":
            return {"type": "field_gt", "field": name, "value": value}
        if op == "<":
            return {"type": "field_lt", "field": name, "value": value}
        if op == ">=":
            return {"type": "field_gte", "field": name, "value": value}
        if op == "<=":
            return {"type": "field_lte", "field": name, "value": value}
        raise _ParseError(f"Unknown operator: {op}")


# ── Content analysis ──────────────────────────────────────────────────────────

_WORD_COUNT_RE = re.compile(r"\d+\s*words?")

_SINGLE_CHAR_RE = re.compile(r"^[\w]$")

_BARE_DIGITS_RE = re.compile(r"^[\d\s]+$")


def _compile_patterns(config: dict) -> dict:
    """Compile all regex patterns from config strings into a cache dict."""
    compiled: dict = {}

    compiled["doc_types"] = {}
    for tname, patterns in config.get("doc_types", {}).items():
        compiled["doc_types"][tname] = [re.compile(p) for p in patterns]

    compiled["form_chrome"] = [
        re.compile(p) for p in config.get("form_chrome", [])
    ]

    compiled["draft_markers"] = [
        re.compile(p) for p in config.get("draft_markers", [])
    ]

    return compiled


def _detect_funder(
    path_str: str,
    funders: dict[str, str],
) -> str | None:
    """Match path against configured funder abbreviations (longest first)."""
    lower = path_str.lower()
    for key in sorted(funders.keys(), key=len, reverse=True):
        if key.lower() in lower:
            return key
    return None


def _detect_doc_types(
    path_str: str,
    compiled: dict,
) -> list[str]:
    """Detect document types from the file path using regex patterns.

    Underscores in the path are normalised to spaces so that
    ``staff_board`` segments match ``staff board`` patterns.
    """
    normalized = path_str.replace("_", " ")
    types: list[str] = []
    for tname, patterns in compiled.get("doc_types", {}).items():
        for pattern in patterns:
            if pattern.search(normalized):
                types.append(tname)
                break
    return types if types else ["unknown"]


def _analyze_content(
    text: str,
    compiled: dict,
    corruption_config: dict | None = None,
) -> dict:
    """Score content quality from raw file text.

    Returns a flat dict with all quality metrics.
    """
    lines = text.split("\n")
    total_lines = len(lines)

    if total_lines == 0:
        return {
            "total_lines": 0,
            "content_lines": 0,
            "empty_lines": 0,
            "corruption_score": 1.0,
            "image_marker_count": 0,
            "form_chrome_count": 0,
            "draft_marker_count": 0,
            "has_headings": False,
            "has_tables": False,
            "avg_content_line_length": 0.0,
            "duplicate_heading_count": 0,
            "word_count_annotation_count": 0,
        }

    corruption_cfg = corruption_config or {}

    # Single-character lines (corruption indicator)
    single_char: int = 0
    if corruption_cfg.get("single_char_alpha", True):
        single_char += sum(
            1 for l in lines if _SINGLE_CHAR_RE.match(l.strip())
        )
    if corruption_cfg.get("bare_digits", True):
        single_char += sum(
            1 for l in lines
            if _BARE_DIGITS_RE.match(l.strip())
            and len(l.strip()) <= 4
        )

    # Image markers
    image_markers = sum(1 for l in lines if "<!-- image -->" in l)

    # Form chrome patterns
    form_chrome = 0
    for pattern in compiled.get("form_chrome", []):
        form_chrome += sum(1 for l in lines if pattern.search(l))

    # Draft markers
    draft_markers = 0
    for pattern in compiled.get("draft_markers", []):
        draft_markers += sum(1 for l in lines if pattern.search(l))

    # Word count annotations
    word_count_annotations = sum(1 for l in lines if _WORD_COUNT_RE.search(l))

    # Content lines (not blank, not corruption, not image markers)
    def _is_content_line(l: str) -> bool:
        s = l.strip()
        if not s:
            return False
        if _SINGLE_CHAR_RE.match(s):
            return False
        if s in ("<!-- image -->", "[IMAGE]"):
            return False
        return True

    content_lines_list = [l for l in lines if _is_content_line(l)]
    content_count = len(content_lines_list)

    has_headings = any(l.strip().startswith("#") for l in lines)
    has_tables = any("|" in l for l in lines if l.strip())
    avg_len = sum(len(l) for l in content_lines_list) / max(content_count, 1)

    headings = [l.strip() for l in lines if l.strip().startswith("#")]
    dup_headings = sum(
        c - 1 for c in Counter(headings).values() if c > 1
    )

    corruption_score = single_char / max(total_lines, 1)

    return {
        "total_lines": total_lines,
        "content_lines": content_count,
        "empty_lines": total_lines - content_count,
        "corruption_score": corruption_score,
        "image_marker_count": image_markers,
        "form_chrome_count": form_chrome,
        "draft_marker_count": draft_markers,
        "has_headings": has_headings,
        "has_tables": has_tables,
        "avg_content_line_length": avg_len,
        "duplicate_heading_count": dup_headings,
        "word_count_annotation_count": word_count_annotations,
    }


# ── Rule normalisation (legacy → DSL) ─────────────────────────────────────────


def _normalize_rules(
    rules: list[dict],
    condition_key: str = "condition",
    result_key: str = "tier",
) -> list[dict]:
    """Convert legacy eval-string rules to the safe DSL format.

    If a rule already has ``conditions`` (new DSL), leave it untouched.
    Otherwise, parse the legacy ``condition`` string via
    :func:`parse_legacy_eval_condition` and embed the result.
    """
    normalized: list[dict] = []
    for rule in rules:
        if "conditions" in rule:
            normalized.append(rule)
            continue
        legacy = rule.get(condition_key, "")
        if not legacy or legacy.strip() == "":
            normalized.append({"conditions": [], "match": "all", result_key: rule.get(result_key, "")})
            continue
        parsed = parse_legacy_eval_condition(legacy)
        if "conditions" in parsed:
            # Already a compound — merge in the result/reason
            normalized_rule: dict = dict(parsed)
            if result_key in rule:
                normalized_rule[result_key] = rule[result_key]
            if "reason" in rule:
                normalized_rule["reason"] = rule["reason"]
            normalized.append(normalized_rule)
        else:
            # Single condition — wrap in a rule
            wrapped: dict = {
                "conditions": [parsed],
                "match": "all",
            }
            if result_key in rule:
                wrapped[result_key] = rule[result_key]
            if "reason" in rule:
                wrapped["reason"] = rule["reason"]
            normalized.append(wrapped)
    return normalized


# ── Classification ────────────────────────────────────────────────────────────


def _make_context(result: dict) -> dict:
    """Build the evaluation context dict for rule conditions."""
    return {
        "corruption_score": result["corruption_score"],
        "content_lines": result["content_lines"],
        "form_chrome_count": result["form_chrome_count"],
        "draft_marker_count": result["draft_marker_count"],
        "duplicate_heading_count": result["duplicate_heading_count"],
        "word_count_annotation_count": result["word_count_annotation_count"],
        "avg_content_line_length": result["avg_content_line_length"],
        "has_headings": result["has_headings"],
        "has_tables": result["has_tables"],
        "doc_types": result["doc_types"],
        "filename": result["filename"],
        "filepath": result["filepath"],
        "funder": result["funder"],
    }


def _evaluate_skip_rules(
    skip_rules: list[dict],
    ctx: dict,
) -> dict | None:
    """Evaluate skip rules in order.  First match wins.

    Returns ``{"reason": str, "status": FileStatus}`` or ``None``.
    """
    for rule in skip_rules:
        try:
            if evaluate_rule(rule, ctx):
                reason = rule.get("reason", "Unknown reason")
                try:
                    reason = reason.format(**ctx)
                except (KeyError, ValueError):
                    pass
                return {"reason": reason}
        except Exception as e:
            logger.warning("Skip rule evaluation failed for %s: %s", ctx.get("filename", "?"), e)
            continue
    return None


def _evaluate_tier_rules(
    tier_rules: list[dict],
    ctx: dict,
) -> str:
    """Evaluate tier rules in order.  First match wins.

    Returns a tier name string (``"full"``, ``"light"``, ``"minimal"``,
    ``"skip"``).
    """
    for rule in tier_rules:
        try:
            if evaluate_rule(rule, ctx):
                return rule.get("tier", "minimal")
        except Exception as e:
            logger.warning("Tier rule evaluation failed for %s: %s", ctx.get("filename", "?"), e)
            continue
    return "minimal"


def _tier_reason(result: dict) -> str:
    """Generate a human-readable reason for the assigned tier."""
    reasons: list[str] = []
    if result.get("form_chrome_count", 0) > 0:
        reasons.append(f'{result["form_chrome_count"]} form chrome lines')
    if result.get("draft_marker_count", 0) > 0:
        reasons.append(f'{result["draft_marker_count"]} draft markers')
    if result.get("duplicate_heading_count", 0) > 0:
        reasons.append(
            f'{result["duplicate_heading_count"]} duplicate headings'
        )
    if result.get("word_count_annotation_count", 0) > 0:
        reasons.append(
            f'{result["word_count_annotation_count"]} word count annotations'
        )
    if reasons:
        return "; ".join(reasons)
    if result.get("tier") == "minimal":
        return "Clean prose, minimal issues"
    if result.get("tier") == "full":
        return "Application/report — heading normalization needed"
    return "Default classification"


_TIER_MAP: dict[str, ProcessingTier] = {
    "full_rewrite": ProcessingTier.FULL,
    "full": ProcessingTier.FULL,
    "light_cleanup": ProcessingTier.LIGHT,
    "light": ProcessingTier.LIGHT,
    "minimal": ProcessingTier.MINIMAL,
    "skip": ProcessingTier.SKIP,
}


def classify_file(filepath: Path, config: dict) -> dict:
    """Score a single file and assign a processing tier.

    Args:
        filepath: Path to the ``.md`` file to classify.
        config: Classification configuration dict.  Expected keys include
            ``funders``, ``doc_types``, ``form_chrome``, ``draft_markers``,
            ``corruption``, ``thresholds``, ``skip_rules``, ``tier_rules``.

    Returns:
        A dict with keys: ``filepath``, ``filename``, ``status``, ``tier``,
        ``funder``, ``doc_types``, ``content_lines``, ``corruption_score``,
        ``form_chrome_count``, ``draft_marker_count``, ``has_headings``,
        ``has_tables``, ``reason``, and all content-quality metrics.
    """
    path_str = str(filepath)

    funder = _detect_funder(path_str, config.get("funders", {}))
    compiled = _compile_patterns(config)
    doc_types = _detect_doc_types(path_str, compiled)

    try:
        text = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        text = ""

    # Parse frontmatter if present
    fm, body = parse_frontmatter(text)
    analysis_text = body if body else text

    quality = _analyze_content(
        analysis_text,
        compiled,
        config.get("corruption", {}),
    )

    file_size_kb = len(text.encode("utf-8")) / 1024

    result = {
        "filepath": path_str,
        "filename": filepath.name,
        "status": FileStatus.PENDING,
        "tier": ProcessingTier.MINIMAL,
        "funder": funder,
        "doc_types": doc_types,
        "size_kb": round(file_size_kb, 1),
        "reason": "",
        **quality,
    }

    # Extract years from frontmatter if available
    if fm:
        result["year_written"] = extract_year(fm.get("written"))
        result["year_intended_start"] = extract_year(fm.get("period_start"))
        result["year_intended_end"] = extract_year(fm.get("period_end"))

    ctx = _make_context(result)

    # Evaluate skip rules first
    skip_rules = _normalize_rules(
        config.get("skip_rules", []),
        condition_key="condition",
        result_key="reason",
    )
    skip = _evaluate_skip_rules(skip_rules, ctx)
    if skip:
        result["status"] = FileStatus.SKIPPED_DRAFT
        result["tier"] = ProcessingTier.SKIP
        result["reason"] = skip["reason"]
        return result

    # Evaluate tier rules
    tier_rules = _normalize_rules(
        config.get("tier_rules", []),
        condition_key="condition",
        result_key="tier",
    )
    tier_name = _evaluate_tier_rules(tier_rules, ctx)
    result["tier"] = _TIER_MAP.get(tier_name, ProcessingTier.MINIMAL)
    result["status"] = FileStatus.OK
    result["reason"] = _tier_reason(result)
    return result


def classify_directory(
    directory: Path,
    config: dict,
) -> dict:
    """Classify all ``.md`` files in a directory and return a manifest dict.

    Args:
        directory: Path to a directory containing ``.md`` files.
        config: Classification configuration dict (same shape as
            :func:`classify_file`).

    Returns:
        A manifest dict with ``files`` (filename → result) and ``summary``
        sections.
    """
    from datetime import datetime, timezone

    md_files = sorted(directory.glob("*.md"))

    files: dict[str, dict] = {}
    by_tier: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_funder: dict[str, int] = {}

    for fpath in md_files:
        result = classify_file(fpath, config)
        fname = fpath.name
        files[fname] = result

        tier_val = (
            result["tier"].value
            if isinstance(result["tier"], ProcessingTier)
            else str(result["tier"])
        )
        by_tier[tier_val] = by_tier.get(tier_val, 0) + 1

        status_val = (
            result["status"].value
            if isinstance(result["status"], FileStatus)
            else str(result["status"])
        )
        by_status[status_val] = by_status.get(status_val, 0) + 1

        funder_val = result.get("funder") or "unknown"
        by_funder[funder_val] = by_funder.get(funder_val, 0) + 1

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "project": "folio",
        "stage": "classify",
        "generated": now,
        "updated": now,
        "files": files,
        "summary": {
            "total_files": len(files),
            "by_tier": by_tier,
            "by_status": by_status,
            "by_funder": by_funder,
            "total_cost_usd": 0.0,
        },
    }


# ── Smoke tests ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # -- Test DSL evaluation --
    ctx = {
        "doc_types": ["application", "draft"],
        "corruption_score": 0.6,
        "content_lines": 20,
    }
    cond = {"type": "has_doc_type", "value": "application"}
    assert evaluate_condition(cond, ctx) is True
    cond2 = {"type": "field_gt", "field": "corruption_score", "value": 0.5}
    assert evaluate_condition(cond2, ctx) is True

    rule = {
        "conditions": [cond, cond2],
        "match": "all",
    }
    assert evaluate_rule(rule, ctx) is True

    # -- Test legacy parser --
    r1 = parse_legacy_eval_condition("has_type('guidelines')")
    assert r1 == {"type": "has_doc_type", "value": "guidelines"}, f"got {r1}"

    r2 = parse_legacy_eval_condition(
        "has_type('guidelines') and corruption_score > 0.5"
    )
    assert r2 == {
        "conditions": [
            {"type": "has_doc_type", "value": "guidelines"},
            {"type": "field_gt", "field": "corruption_score", "value": 0.5},
        ],
        "match": "all",
    }, f"got {r2}"

    r3 = parse_legacy_eval_condition(
        "has_type('email') and not has_any_type('notification', 'budget')"
    )
    assert r3 == {
        "conditions": [
            {"type": "has_doc_type", "value": "email"},
            {
                "type": "not_",
                "condition": {
                    "type": "has_any_type",
                    "values": ["notification", "budget"],
                },
            },
        ],
        "match": "all",
    }, f"got {r3}"

    r4 = parse_legacy_eval_condition("content_lines < 15")
    assert r4 == {"type": "field_lt", "field": "content_lines", "value": 15}, (
        f"got {r4}"
    )

    r5 = parse_legacy_eval_condition(
        "not has_headings and has_tables and avg_content_line_length < 50 and content_lines > 50"
    )
    assert r5 == {
        "conditions": [
            {"type": "not_", "condition": {"type": "has_headings"}},
            {"type": "has_tables"},
            {
                "type": "field_lt",
                "field": "avg_content_line_length",
                "value": 50,
            },
            {"type": "field_gt", "field": "content_lines", "value": 50},
        ],
        "match": "all",
    }, f"got {r5}"

    r6 = parse_legacy_eval_condition(
        "form_chrome_count > 5 or draft_marker_count > 5"
    )
    assert r6 == {
        "conditions": [
            {"type": "field_gt", "field": "form_chrome_count", "value": 5},
            {"type": "field_gt", "field": "draft_marker_count", "value": 5},
        ],
        "match": "any",
    }, f"got {r6}"

    r7 = parse_legacy_eval_condition("filename.startswith('~$')")
    assert r7 == {"type": "filename_starts_with", "value": "~$"}, f"got {r7}"

    r8 = parse_legacy_eval_condition("true")
    assert r8 == {"type": "true"}, f"got {r8}"

    r9 = parse_legacy_eval_condition(
        "path_contains('prep', 'todo', 'ToDo', 'PREP') and not has_type('meeting_notes')"
    )
    assert r9 == {
        "conditions": [
            {
                "type": "path_contains",
                "values": ["prep", "todo", "ToDo", "PREP"],
            },
            {
                "type": "not_",
                "condition": {"type": "has_doc_type", "value": "meeting_notes"},
            },
        ],
        "match": "all",
    }, f"got {r9}"

    print("OK")

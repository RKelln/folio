"""Tests for the synthetic-corpus spec loader (folio.core.corpus.spec).

Covers loading the bundled default spec, round-tripping a custom YAML spec,
validation error reporting, the ValueError contract on invalid spec files,
and the ``to_dict`` / ``total_outputs`` helpers.
"""

from __future__ import annotations

import textwrap

import pytest
import yaml

from folio.core.corpus.spec import (
    ALLOWED_FORMATS,
    ALLOWED_KINDS,
    CorpusSpec,
    DocSpec,
    load_corpus_spec,
    validate_spec,
)


def _write_spec(tmp_path, data: dict):
    spec_file = tmp_path / "corpus-spec.yaml"
    spec_file.write_text(yaml.safe_dump(data), encoding="utf-8")
    return spec_file


class TestLoadBundledDefault:
    def test_load_default_returns_valid_spec(self):
        spec = load_corpus_spec()
        assert isinstance(spec, CorpusSpec)
        assert spec.documents, "bundled default must define at least one document"
        assert validate_spec(spec) == []

    def test_default_seed_is_deterministic_int(self):
        spec = load_corpus_spec()
        assert isinstance(spec.seed, int)
        assert not isinstance(spec.seed, bool)

    def test_default_covers_all_doc_kinds(self):
        spec = load_corpus_spec()
        kinds = {doc.kind for doc in spec.documents}
        assert kinds == ALLOWED_KINDS

    def test_default_output_dir_is_benchmark_corpus(self):
        spec = load_corpus_spec()
        assert spec.output_dir == "benchmark/corpus"

    def test_default_only_uses_allowed_formats(self):
        spec = load_corpus_spec()
        for doc in spec.documents:
            assert set(doc.formats) <= ALLOWED_FORMATS


class TestDocSpecDefaults:
    def test_docspec_defaults(self):
        doc = DocSpec(kind="application")
        assert doc.count == 1
        assert doc.formats == ["md"]

    def test_docspec_formats_independent_instances(self):
        a = DocSpec(kind="application")
        b = DocSpec(kind="narrative")
        a.formats.append("pdf")
        assert b.formats == ["md"]


class TestCorpusSpecDefaults:
    def test_corpusspec_defaults(self):
        spec = CorpusSpec()
        assert spec.seed == 1234
        assert spec.profile == "canadian-artist-run-centre"
        assert spec.funder == "OAC"
        assert spec.output_dir == "benchmark/corpus"
        assert spec.documents == []


class TestRoundTrip:
    def test_custom_yaml_round_trips(self, tmp_path):
        data = {
            "seed": 99,
            "profile": "my-profile",
            "funder": "CCA",
            "output_dir": "out/corpus",
            "documents": [
                {"kind": "application", "count": 2, "formats": ["md", "pdf", "docx"]},
                {"kind": "budget", "count": 3, "formats": ["xlsx"]},
            ],
        }
        spec_file = _write_spec(tmp_path, data)
        spec = load_corpus_spec(spec_file)

        assert spec.seed == 99
        assert spec.profile == "my-profile"
        assert spec.funder == "CCA"
        assert spec.output_dir == "out/corpus"
        assert len(spec.documents) == 2

        app = spec.documents[0]
        assert app.kind == "application"
        assert app.count == 2
        assert app.formats == ["md", "pdf", "docx"]

        budget = spec.documents[1]
        assert budget.kind == "budget"
        assert budget.count == 3
        assert budget.formats == ["xlsx"]

    def test_doc_defaults_applied_from_partial_yaml(self, tmp_path):
        data = {"documents": [{"kind": "narrative"}]}
        spec_file = _write_spec(tmp_path, data)
        spec = load_corpus_spec(spec_file)
        assert spec.documents[0].kind == "narrative"
        assert spec.documents[0].count == 1
        assert spec.documents[0].formats == ["md"]

    def test_load_accepts_string_path(self, tmp_path):
        data = {"documents": [{"kind": "application", "formats": ["md"]}]}
        spec_file = _write_spec(tmp_path, data)
        spec = load_corpus_spec(str(spec_file))
        assert spec.documents[0].kind == "application"


class TestValidation:
    def test_valid_spec_has_no_errors(self):
        spec = CorpusSpec(documents=[DocSpec(kind="application", count=1, formats=["md"])])
        assert validate_spec(spec) == []

    def test_empty_documents_flagged(self):
        spec = CorpusSpec(documents=[])
        errors = validate_spec(spec)
        assert errors
        assert any("document" in e.lower() for e in errors)

    @pytest.mark.parametrize("bad_kind", ["", "essay", "report", "invoice"])
    def test_bad_kind_flagged(self, bad_kind):
        spec = CorpusSpec(documents=[DocSpec(kind=bad_kind, formats=["md"])])
        errors = validate_spec(spec)
        assert any("kind" in e.lower() for e in errors)

    @pytest.mark.parametrize("bad_format", ["", "txt", "html", "doc"])
    def test_bad_format_flagged(self, bad_format):
        spec = CorpusSpec(documents=[DocSpec(kind="application", formats=[bad_format])])
        errors = validate_spec(spec)
        assert any("format" in e.lower() for e in errors)

    @pytest.mark.parametrize("bad_count", [0, -1, -5])
    def test_count_less_than_one_flagged(self, bad_count):
        spec = CorpusSpec(documents=[DocSpec(kind="application", count=bad_count, formats=["md"])])
        errors = validate_spec(spec)
        assert any("count" in e.lower() for e in errors)

    @pytest.mark.parametrize("bad_seed", ["abc", 1.5, None, True])
    def test_non_int_seed_flagged(self, bad_seed):
        spec = CorpusSpec(
            seed=bad_seed,
            documents=[DocSpec(kind="application", formats=["md"])],
        )
        errors = validate_spec(spec)
        assert any("seed" in e.lower() for e in errors)

    @pytest.mark.parametrize("bad_funder", ["", "   ", None])
    def test_empty_funder_flagged(self, bad_funder):
        spec = CorpusSpec(
            funder=bad_funder,
            documents=[DocSpec(kind="application", formats=["md"])],
        )
        errors = validate_spec(spec)
        assert any("funder" in e.lower() for e in errors)


class TestLoadRaisesOnInvalid:
    def test_invalid_spec_file_raises_value_error(self, tmp_path):
        data = {"documents": [{"kind": "not_a_kind", "formats": ["md"]}]}
        spec_file = _write_spec(tmp_path, data)
        with pytest.raises(ValueError, match="kind"):
            load_corpus_spec(spec_file)

    def test_empty_documents_file_raises_value_error(self, tmp_path):
        spec_file = _write_spec(tmp_path, {"documents": []})
        with pytest.raises(ValueError, match="document"):
            load_corpus_spec(spec_file)

    def test_missing_file_raises_file_not_found(self, tmp_path):
        missing = tmp_path / "nope.yaml"
        with pytest.raises(FileNotFoundError):
            load_corpus_spec(missing)

    def test_yaml_must_be_mapping(self, tmp_path):
        spec_file = tmp_path / "corpus-spec.yaml"
        spec_file.write_text("- just\n- a\n- list\n", encoding="utf-8")
        with pytest.raises(ValueError):
            load_corpus_spec(spec_file)


class TestToDict:
    def test_to_dict_round_trips_through_load(self, tmp_path):
        spec = CorpusSpec(
            seed=7,
            profile="p",
            funder="TAC",
            output_dir="o/c",
            documents=[
                DocSpec(kind="application", count=2, formats=["md", "pdf"]),
                DocSpec(kind="budget", count=1, formats=["xlsx"]),
            ],
        )
        d = spec.to_dict()
        assert d["seed"] == 7
        assert d["profile"] == "p"
        assert d["funder"] == "TAC"
        assert d["output_dir"] == "o/c"
        assert d["documents"] == [
            {"kind": "application", "count": 2, "formats": ["md", "pdf"]},
            {"kind": "budget", "count": 1, "formats": ["xlsx"]},
        ]

        spec_file = tmp_path / "corpus-spec.yaml"
        spec_file.write_text(yaml.safe_dump(d), encoding="utf-8")
        reloaded = load_corpus_spec(spec_file)
        assert reloaded.to_dict() == d

    def test_to_dict_is_json_serializable(self):
        import json

        spec = load_corpus_spec()
        json.dumps(spec.to_dict())


class TestTotalOutputs:
    def test_total_outputs_sums_count_times_formats(self):
        spec = CorpusSpec(
            documents=[
                DocSpec(kind="application", count=2, formats=["md", "pdf", "docx"]),
                DocSpec(kind="budget", count=3, formats=["xlsx"]),
            ]
        )
        assert spec.total_outputs() == (2 * 3) + (3 * 1)

    def test_total_outputs_empty_is_zero(self):
        assert CorpusSpec(documents=[]).total_outputs() == 0

    def test_total_outputs_single_default_doc(self):
        spec = CorpusSpec(documents=[DocSpec(kind="application")])
        assert spec.total_outputs() == 1


class TestParametrizedAllowedSets:
    @pytest.mark.parametrize("kind", sorted(ALLOWED_KINDS))
    def test_each_allowed_kind_validates(self, kind):
        spec = CorpusSpec(documents=[DocSpec(kind=kind, formats=["md"])])
        assert validate_spec(spec) == []

    @pytest.mark.parametrize("fmt", sorted(ALLOWED_FORMATS))
    def test_each_allowed_format_validates(self, fmt):
        spec = CorpusSpec(documents=[DocSpec(kind="application", formats=[fmt])])
        assert validate_spec(spec) == []

    def test_allowed_sets_match_spec(self):
        assert ALLOWED_KINDS == {
            "application",
            "narrative",
            "budget",
            "activity_list",
            "staff_board",
            "support_letter",
        }
        assert ALLOWED_FORMATS == {"md", "docx", "xlsx", "pdf", "pdf_scanned"}


_INLINE_SPEC = textwrap.dedent(
    """\
    seed: 2024
    profile: canadian-artist-run-centre
    funder: OAC
    output_dir: benchmark/corpus
    documents:
      - kind: application
        count: 1
        formats: [md, pdf, docx]
    """
)


class TestInlineSpec:
    def test_inline_spec_loads(self, tmp_path):
        spec_file = tmp_path / "corpus-spec.yaml"
        spec_file.write_text(_INLINE_SPEC, encoding="utf-8")
        spec = load_corpus_spec(spec_file)
        assert spec.seed == 2024
        assert spec.documents[0].formats == ["md", "pdf", "docx"]
        assert spec.total_outputs() == 3

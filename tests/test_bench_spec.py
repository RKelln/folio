"""Tests for the offline-benchmark spec loader (folio.core.bench.spec).

Covers loading the bundled default spec, round-tripping a custom YAML spec,
every validation error path, ``CategoryWeights`` normalization, the
``enabled_converters`` helper, and the FileNotFoundError / ValueError contracts
of ``load_bench_spec``.
"""

from __future__ import annotations

import json
import textwrap

import pytest
import yaml

from folio.core.bench.spec import (
    DEFAULT_CONVERTERS,
    BenchSpec,
    CategoryWeights,
    ConverterSpec,
    load_bench_spec,
    validate_spec,
)


def _write_spec(tmp_path, data: dict):
    spec_file = tmp_path / "bench-spec.yaml"
    spec_file.write_text(yaml.safe_dump(data), encoding="utf-8")
    return spec_file


class TestLoadBundledDefault:
    def test_load_default_returns_valid_spec(self):
        spec = load_bench_spec()
        assert isinstance(spec, BenchSpec)
        assert spec.converters, "bundled default must define at least one converter"
        assert validate_spec(spec) == []

    def test_default_paths(self):
        spec = load_bench_spec()
        assert spec.corpus_dir == "benchmark/corpus"
        assert spec.golden_subdir == "golden"
        assert spec.rendered_subdir == "rendered"

    def test_default_pass_threshold(self):
        spec = load_bench_spec()
        assert spec.pass_threshold == 0.7

    def test_default_converter_names(self):
        spec = load_bench_spec()
        names = {c.name for c in spec.converters}
        assert {"liteparse", "docling", "pandoc", "datalab", "marker"} <= names

    def test_default_datalab_is_paid_online(self):
        spec = load_bench_spec()
        datalab = next(c for c in spec.converters if c.name == "datalab")
        assert datalab.enabled is False
        assert datalab.offline is False
        assert datalab.cost_per_page > 0

    def test_default_marker_disabled_offline(self):
        spec = load_bench_spec()
        marker = next(c for c in spec.converters if c.name == "marker")
        assert marker.enabled is False
        assert marker.offline is True

    def test_default_offline_converters_enabled(self):
        spec = load_bench_spec()
        for name in ("liteparse", "docling", "pandoc"):
            c = next(conv for conv in spec.converters if conv.name == name)
            assert c.enabled is True
            assert c.offline is True
            assert c.cost_per_page == 0.0


class TestConverterSpecDefaults:
    def test_converterspec_defaults(self):
        c = ConverterSpec(name="x")
        assert c.enabled is True
        assert c.offline is True
        assert c.cost_per_page == 0.0


class TestDefaultConverters:
    def test_default_converters_constant_independent_per_spec(self):
        a = BenchSpec()
        b = BenchSpec()
        a.converters[0].enabled = False
        assert b.converters[0].enabled is True

    def test_default_converters_constant_matches_spec_default(self):
        spec = BenchSpec()
        assert [c.name for c in spec.converters] == [c.name for c in DEFAULT_CONVERTERS]


class TestCategoryWeights:
    def test_weights_defaults(self):
        w = CategoryWeights()
        assert w.text == 0.4
        assert w.tables == 0.25
        assert w.structure == 0.25
        assert w.links_images == 0.10

    def test_normalized_sums_to_one(self):
        w = CategoryWeights(text=1, tables=1, structure=1, links_images=1)
        n = w.normalized()
        total = n.text + n.tables + n.structure + n.links_images
        assert total == pytest.approx(1.0)
        assert n.text == pytest.approx(0.25)

    def test_normalized_preserves_ratios(self):
        w = CategoryWeights(text=2, tables=1, structure=1, links_images=0)
        n = w.normalized()
        assert n.text == pytest.approx(0.5)
        assert n.tables == pytest.approx(0.25)
        assert n.links_images == pytest.approx(0.0)

    def test_normalized_zero_sum_raises(self):
        w = CategoryWeights(text=0, tables=0, structure=0, links_images=0)
        with pytest.raises(ValueError):
            w.normalized()

    def test_to_dict(self):
        w = CategoryWeights()
        assert w.to_dict() == {
            "text": 0.4,
            "tables": 0.25,
            "structure": 0.25,
            "links_images": 0.10,
        }


class TestBenchSpecDefaults:
    def test_benchspec_defaults(self):
        spec = BenchSpec()
        assert spec.corpus_dir == "benchmark/corpus"
        assert spec.golden_subdir == "golden"
        assert spec.rendered_subdir == "rendered"
        assert spec.pass_threshold == 0.7
        assert isinstance(spec.weights, CategoryWeights)
        assert [c.name for c in spec.converters] == [c.name for c in DEFAULT_CONVERTERS]

    def test_enabled_converters_filters(self):
        spec = BenchSpec(
            converters=[
                ConverterSpec(name="a", enabled=True),
                ConverterSpec(name="b", enabled=False),
                ConverterSpec(name="c", enabled=True),
            ]
        )
        assert [c.name for c in spec.enabled_converters()] == ["a", "c"]

    def test_to_dict_is_json_serializable(self):
        spec = load_bench_spec()
        json.dumps(spec.to_dict())

    def test_to_dict_shape(self):
        spec = BenchSpec(
            converters=[ConverterSpec(name="a", enabled=False, offline=False, cost_per_page=0.5)]
        )
        d = spec.to_dict()
        assert d["corpus_dir"] == "benchmark/corpus"
        assert d["pass_threshold"] == 0.7
        assert d["weights"] == CategoryWeights().to_dict()
        assert d["converters"] == [
            {"name": "a", "enabled": False, "offline": False, "cost_per_page": 0.5}
        ]


class TestRoundTrip:
    def test_custom_yaml_round_trips(self, tmp_path):
        data = {
            "corpus_dir": "out/corpus",
            "golden_subdir": "gold",
            "rendered_subdir": "render",
            "pass_threshold": 0.8,
            "weights": {
                "text": 0.5,
                "tables": 0.2,
                "structure": 0.2,
                "links_images": 0.1,
            },
            "converters": [
                {"name": "liteparse", "enabled": True, "offline": True, "cost_per_page": 0.0},
                {"name": "datalab", "enabled": False, "offline": False, "cost_per_page": 0.01},
            ],
        }
        spec_file = _write_spec(tmp_path, data)
        spec = load_bench_spec(spec_file)

        assert spec.corpus_dir == "out/corpus"
        assert spec.golden_subdir == "gold"
        assert spec.rendered_subdir == "render"
        assert spec.pass_threshold == 0.8
        assert spec.weights.text == 0.5
        assert len(spec.converters) == 2
        assert spec.converters[1].name == "datalab"
        assert spec.converters[1].cost_per_page == 0.01

    def test_partial_yaml_keeps_defaults(self, tmp_path):
        spec_file = _write_spec(tmp_path, {"pass_threshold": 0.9})
        spec = load_bench_spec(spec_file)
        assert spec.pass_threshold == 0.9
        assert spec.corpus_dir == "benchmark/corpus"
        assert [c.name for c in spec.converters] == [c.name for c in DEFAULT_CONVERTERS]

    def test_load_accepts_string_path(self, tmp_path):
        spec_file = _write_spec(tmp_path, {"pass_threshold": 0.6})
        spec = load_bench_spec(str(spec_file))
        assert spec.pass_threshold == 0.6


class TestValidation:
    def test_valid_spec_has_no_errors(self):
        assert validate_spec(BenchSpec()) == []

    def test_empty_converters_flagged(self):
        spec = BenchSpec(converters=[])
        errors = validate_spec(spec)
        assert any("converter" in e.lower() for e in errors)

    def test_empty_converter_name_flagged(self):
        spec = BenchSpec(converters=[ConverterSpec(name="")])
        errors = validate_spec(spec)
        assert any("name" in e.lower() for e in errors)

    def test_negative_cost_flagged(self):
        spec = BenchSpec(converters=[ConverterSpec(name="x", cost_per_page=-1.0)])
        errors = validate_spec(spec)
        assert any("cost" in e.lower() for e in errors)

    @pytest.mark.parametrize("bad", [-0.1, 1.1, 2.0])
    def test_pass_threshold_out_of_range_flagged(self, bad):
        spec = BenchSpec(pass_threshold=bad)
        errors = validate_spec(spec)
        assert any("threshold" in e.lower() for e in errors)

    @pytest.mark.parametrize("good", [0.0, 0.5, 1.0])
    def test_pass_threshold_in_range_ok(self, good):
        spec = BenchSpec(pass_threshold=good)
        assert validate_spec(spec) == []

    @pytest.mark.parametrize("attr", ["corpus_dir", "golden_subdir", "rendered_subdir"])
    def test_empty_path_field_flagged(self, attr):
        spec = BenchSpec(**{attr: "  "})
        errors = validate_spec(spec)
        assert any(attr in e for e in errors)

    def test_negative_weight_flagged(self):
        spec = BenchSpec(weights=CategoryWeights(text=-0.1))
        errors = validate_spec(spec)
        assert any("weight" in e.lower() for e in errors)

    def test_zero_sum_weights_flagged(self):
        spec = BenchSpec(
            weights=CategoryWeights(text=0, tables=0, structure=0, links_images=0)
        )
        errors = validate_spec(spec)
        assert any("weight" in e.lower() for e in errors)

    def test_non_numeric_weight_flagged(self):
        spec = BenchSpec(weights=CategoryWeights(text="lots"))  # type: ignore[arg-type]
        errors = validate_spec(spec)
        assert any("weight" in e.lower() for e in errors)


class TestLoadRaisesOnInvalid:
    def test_invalid_spec_file_raises_value_error(self, tmp_path):
        spec_file = _write_spec(tmp_path, {"converters": []})
        with pytest.raises(ValueError, match="converter"):
            load_bench_spec(spec_file)

    def test_bad_threshold_file_raises_value_error(self, tmp_path):
        spec_file = _write_spec(tmp_path, {"pass_threshold": 5})
        with pytest.raises(ValueError, match="threshold"):
            load_bench_spec(spec_file)

    def test_missing_file_raises_file_not_found(self, tmp_path):
        missing = tmp_path / "nope.yaml"
        with pytest.raises(FileNotFoundError):
            load_bench_spec(missing)

    def test_yaml_must_be_mapping(self, tmp_path):
        spec_file = tmp_path / "bench-spec.yaml"
        spec_file.write_text("- just\n- a\n- list\n", encoding="utf-8")
        with pytest.raises(ValueError):
            load_bench_spec(spec_file)

    def test_converters_must_be_list(self, tmp_path):
        spec_file = _write_spec(tmp_path, {"converters": {"name": "x"}})
        with pytest.raises(ValueError):
            load_bench_spec(spec_file)


_INLINE_SPEC = textwrap.dedent(
    """\
    corpus_dir: benchmark/corpus
    golden_subdir: golden
    rendered_subdir: rendered
    pass_threshold: 0.75
    weights:
      text: 0.4
      tables: 0.25
      structure: 0.25
      links_images: 0.10
    converters:
      - name: liteparse
        enabled: true
        offline: true
        cost_per_page: 0.0
    """
)


class TestInlineSpec:
    def test_inline_spec_loads(self, tmp_path):
        spec_file = tmp_path / "bench-spec.yaml"
        spec_file.write_text(_INLINE_SPEC, encoding="utf-8")
        spec = load_bench_spec(spec_file)
        assert spec.pass_threshold == 0.75
        assert spec.converters[0].name == "liteparse"
        assert spec.enabled_converters()[0].name == "liteparse"

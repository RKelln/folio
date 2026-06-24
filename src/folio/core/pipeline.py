"""Pipeline orchestrator.

Runs the full folio document processing pipeline:
    scan → convert → clean → canonicalize → classify → rewrite → prioritize → wiki

Supports checkpoint/resume via a manifest file, dry-run estimation,
and per-stage cost/timing tracking.
"""

from __future__ import annotations

import logging
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

from folio.config.loader import load_project_config
from folio.config.schema import ProjectConfig
from folio.core.manifest import load_manifest, save_manifest, update_file

logger = logging.getLogger(__name__)

AVAILABLE_STAGES = [
    "scan", "convert", "clean", "canonicalize", "classify",
    "rewrite", "prioritize", "wiki",
]


def run_pipeline(
    config_path: str | Path = "folio.yaml",
    stages: list[str] | None = None,
    dry_run: bool = False,
    resume: bool = True,
    files: list[str] | None = None,
) -> dict:
    """Run the full folio pipeline.

    Stages (in order): scan, convert, clean, canonicalize, classify,
    rewrite, prioritize, wiki.

    Args:
        config_path: Path to folio.yaml.
        stages: List of stages to run (default: all enabled stages).
        dry_run: Preview without making changes or API calls.
        resume: Skip already-completed stages (from manifest).
            Ignored when ``files`` is specified.
        files: Limit processing to specific filenames (not paths).
            When set, resume is ignored and each stage processes only
            matching files in its respective directory.

    Returns:
        Pipeline report dict with per-stage results and aggregate stats.
    """
    config = load_project_config(config_path)

    for path_attr in ["raw_md", "clean_md", "rewrite_md", "wiki_project"]:
        p = Path(getattr(config.paths, path_attr))
        p.mkdir(parents=True, exist_ok=True)

    manifest_path = Path(config.paths.rewrite_md) / "manifest.json"
    manifest = load_manifest(manifest_path)

    if stages is None:
        enabled = list(AVAILABLE_STAGES)
    else:
        enabled = [s for s in AVAILABLE_STAGES if s in stages]

    report: dict = {
        "project": config.org.name,
        "started": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stages": {},
        "total_cost_usd": 0.0,
        "total_time_seconds": 0.0,
    }

    if "stages" not in manifest:
        manifest["stages"] = {}

    print(f"folio pipeline \u2014 {config.org.name} Grant Archive")
    print("=" * 50)
    print()

    total_stages = len(AVAILABLE_STAGES)
    total_cost = 0.0
    total_time = 0.0

    stage_index = {name: i for i, name in enumerate(AVAILABLE_STAGES)}

    for stage_name in enabled:
        stage_num = stage_index.get(stage_name, len(AVAILABLE_STAGES)) + 1

        if resume and not files and manifest["stages"].get(stage_name, {}).get("status") in ("ok", "warning"):
            stage_data = manifest["stages"][stage_name]
            print(
                f"Stage {stage_num}/{total_stages}: {stage_name} \u2014 skipped"
                f" (already complete)"
            )
            report["stages"][stage_name] = stage_data
            total_cost += stage_data.get("cost_usd", 0.0)
            total_time += stage_data.get("time_seconds", 0.0)
            continue

        print(f"Stage {stage_num}/{total_stages}: {stage_name}")

        start = time.time()
        result = _run_stage(stage_name, config, dry_run, resume=resume, manifest=manifest, files=files)
        elapsed = time.time() - start

        result["time_seconds"] = round(elapsed, 1)
        result.setdefault("cost_usd", 0.0)

        total_cost += result.get("cost_usd", 0.0)
        total_time += elapsed

        report["stages"][stage_name] = result

        manifest["stages"][stage_name] = result
        save_manifest(manifest, manifest_path)

        _print_stage_summary(stage_name, result)

    report["completed"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report["total_cost_usd"] = round(total_cost, 2)
    report["total_time_seconds"] = round(total_time, 1)

    print()
    print("=" * 50)
    print("Pipeline complete!")

    total_files = sum(
        s.get("files", 0) or s.get("converted", 0) or 0
        for s in report["stages"].values()
        if s.get("status") == "ok"
        and s.get("stage") not in ("scan", "convert", "rewrite", "prioritize")
    )
    if total_files == 0 and "classify" in report["stages"]:
        total_files = report["stages"]["classify"].get("files", 0)

    total_files_est = 0
    if "scan" in report["stages"]:
        total_files_est = report["stages"]["scan"].get("files", 0)
    if total_files == 0:
        total_files = total_files_est

    print(f"  Files processed: {total_files}")
    print(f"  Total cost: ${report['total_cost_usd']:.2f}")
    print(f"  Total time: {_format_time(report['total_time_seconds'])}")

    return report


def _estimate_pipeline(config: ProjectConfig) -> dict:
    """Estimate costs for all pipeline stages (for dry-run).

    Returns a report dict with estimated per-stage costs and timings,
    without executing any stage.
    """
    from folio.core.scanner import scan_archive

    try:
        scan = scan_archive(config.paths.raw_archive, config)
    except Exception:
        scan = {"total_files": 0, "estimated_costs": {"total_usd": 0.0}}

    enabled = list(AVAILABLE_STAGES)
    report: dict = {
        "project": config.org.name,
        "started": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stages": {},
        "total_cost_usd": 0.0,
        "total_time_seconds": 0.0,
    }

    total_cost = 0.0
    total_time = 0.0

    for stage_name in enabled:
        result = _estimate_stage(stage_name, config, scan)
        report["stages"][stage_name] = result
        total_cost += result.get("cost_usd", 0.0)
        total_time += result.get("time_seconds", 0.0)

    report["completed"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report["total_cost_usd"] = round(total_cost, 2)
    report["total_time_seconds"] = round(total_time, 1)
    return report


def _format_pipeline_report(report: dict) -> str:
    """Format a pipeline report as human-readable text."""
    lines: list[str] = []
    project = report.get("project", "folio")
    lines.append(f"folio pipeline \u2014 {project} Grant Archive")
    lines.append("=" * 50)

    stages = report.get("stages", {})
    stage_order = [s for s in AVAILABLE_STAGES if s in stages]

    for i, stage_name in enumerate(stage_order):
        stage_data = stages[stage_name]
        num = i + 1
        total = len(stage_order)
        status = stage_data.get("status", "?")

        if status == "ok":
            lines.append(f"Stage {num}/{total}: {stage_name}")
            elapsed = stage_data.get("time_seconds", 0)
            lines.append(f"  Complete ({_format_time(elapsed)})")
            files = stage_data.get("files", stage_data.get("converted"))
            if files is not None:
                lines.append(f"  \u2192 {files} files")
            cost = stage_data.get("cost_usd", 0)
            if cost > 0:
                lines.append(f"  \u2192 Cost: ${cost:.2f}")
        elif status == "skipped":
            lines.append(
                f"Stage {num}/{total}: {stage_name} \u2014 skipped"
            )
        elif status == "warning":
            lines.append(f"Stage {num}/{total}: {stage_name}")
            lines.append(f"  Warning: {stage_data.get('warning', '')}")
        else:
            lines.append(f"Stage {num}/{total}: {stage_name}")
            lines.append(f"  Error: {stage_data.get('error', 'Unknown error')}")

        lines.append("")

    lines.append("=" * 50)
    lines.append("Pipeline complete!")
    lines.append(f"  Total cost: ${report.get('total_cost_usd', 0):.2f}")
    lines.append(f"  Total time: {_format_time(report.get('total_time_seconds', 0))}")

    return "\n".join(lines)


# ── Stage dispatch ──────────────────────────────────────────────────────────


def _run_stage(
    stage_name: str,
    config: ProjectConfig,
    dry_run: bool,
    resume: bool = True,
    manifest: dict | None = None,
    files: list[str] | None = None,
) -> dict:
    if dry_run:
        return _estimate_stage(stage_name, config)

    try:
        if stage_name == "scan":
            return _run_scan(config)
        elif stage_name == "convert":
            return _run_convert(config, manifest=manifest, resume=resume, files=files)
        elif stage_name == "clean":
            return _run_clean(config, files=files)
        elif stage_name == "canonicalize":
            return _run_canonicalize(config, files=files)
        elif stage_name == "classify":
            return _run_classify(config, files=files)
        elif stage_name == "rewrite":
            return _run_rewrite(config, files=files)
        elif stage_name == "prioritize":
            return _run_prioritize(config, files=files)
        elif stage_name == "wiki":
            return _run_wiki(config, files=files)
        else:
            return {"status": "error", "error": f"Unknown stage: {stage_name}"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def _estimate_stage(stage_name: str, config: ProjectConfig, scan: dict | None = None) -> dict:
    """Produce a dry-run estimate for a single stage based on config."""
    if scan is None:
        from folio.core.scanner import scan_archive

        try:
            scan = scan_archive(config.paths.raw_archive, config)
        except Exception:
            scan = {"total_files": 0, "estimated_costs": {"total_usd": 0.0}}

    total_files = scan.get("total_files", 0)
    est_cost = scan.get("estimated_costs", {})
    est_time = scan.get("estimated_time_minutes", 0) * 60

    if stage_name == "scan":
        return {
            "status": "ok",
            "files": total_files,
            "cost_usd": 0.0,
            "time_seconds": 1.0,
            "note": "scan is local; no LLM or conversion cost",
        }
    elif stage_name == "convert":
        conv_cost = est_cost.get("conversion_usd", 0)
        return {
            "status": "ok",
            "files": total_files,
            "cost_usd": conv_cost,
            "time_seconds": est_time * 0.6,
            "note": "estimate based on file count and Datalab pricing",
        }
    elif stage_name == "clean":
        return {
            "status": "ok",
            "files": total_files,
            "cost_usd": 0.0,
            "time_seconds": max(total_files * 0.01, 0.1),
            "note": "deterministic cleanup; no API calls",
        }
    elif stage_name == "canonicalize":
        return {
            "status": "ok",
            "files": total_files,
            "cost_usd": est_cost.get("llm_rewrite_usd", 0) * 0.05,
            "time_seconds": max(total_files * 0.02, 0.1),
            "note": "filename scoring + content similarity; optional LLM pass",
        }
    elif stage_name == "classify":
        return {
            "status": "ok",
            "files": total_files,
            "cost_usd": 0.0,
            "time_seconds": max(total_files * 0.005, 0.1),
            "note": "deterministic rule evaluation; no API calls",
        }
    elif stage_name == "rewrite":
        return {
            "status": "ok",
            "files": total_files,
            "cost_usd": est_cost.get("llm_rewrite_usd", 0),
            "time_seconds": est_time * 0.3,
            "note": "LLM re-authoring; largest cost driver",
        }
    elif stage_name == "prioritize":
        return {
            "status": "ok",
            "files": total_files,
            "cost_usd": est_cost.get("llm_prioritize_usd", 0),
            "time_seconds": est_time * 0.05,
            "note": "LLM priority scoring; batched by year",
        }
    elif stage_name == "wiki":
        return {
            "status": "ok",
            "files": total_files,
            "cost_usd": est_cost.get("wiki_compile_usd", 0),
            "time_seconds": est_time * 0.05,
            "note": "wiki compilation (sage-wiki)",
        }
    return {"status": "error", "error": f"Unknown stage: {stage_name}"}


# ── Stage implementations ───────────────────────────────────────────────────


def _run_scan(config: ProjectConfig) -> dict:
    from folio.core.scanner import scan_archive

    raw_path = config.paths.raw_archive
    print(f"  Scanning {raw_path}...", end=" ", flush=True)
    report = scan_archive(raw_path, config)
    total = report.get("total_files", 0)
    funders = report.get("by_funder", {})
    est = report.get("estimated_costs", {})

    print(f"{total} files found")
    if funders:
        funder_list = ", ".join(
            f"{abbrev} ({info['count']})"
            for abbrev, info in sorted(funders.items())
        )
        print(f"  Funders: {funder_list}")

    return {
        "stage": "scan",
        "status": "ok",
        "files": total,
        "funders_detected": len(funders),
        "by_extension": report.get("by_extension", {}),
        "by_funder": {k: {"count": v["count"], "years": v["years"]} for k, v in funders.items()},
        "estimated_cost_usd": est.get("total_usd", 0),
        "estimated_time_minutes": report.get("estimated_time_minutes", 0),
        "cost_usd": 0.0,
    }


def _run_convert(config: ProjectConfig, manifest: dict | None = None, resume: bool = True, files: list[str] | None = None) -> dict:
    from folio.adapters.converters import get_converter
    from folio.adapters.sources import get_source

    converter = get_converter(config)
    source = get_source(config.paths.raw_archive)
    out_dir = Path(config.paths.raw_md)
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_root = Path(config.paths.raw_archive).resolve()

    source_files = source.list_files()
    convertible_exts = {ext.lower() for ext in converter.supported_extensions}
    convertible = [
        ref
        for ref in source_files
        if Path(ref.name).suffix.lower() in convertible_exts
    ]

    if not convertible:
        print(f"  No convertible files found in {config.paths.raw_archive}")
        return {
            "stage": "convert",
            "status": "warning",
            "warning": "No convertible files found",
            "files": 0,
            "converted": 0,
            "failed": 0,
            "cost_usd": 0.0,
        }

    print(f"  Converting {len(convertible)} files via {converter.name}...")

    converted = 0
    skipped = 0
    failed = 0
    total_cost = 0.0
    failed_files: list[str] = []
    failures: list[dict] = []

    if resume:
        for ref in convertible:
            dest_path = out_dir / (Path(ref.name).stem + ".md")
            if dest_path.exists() and dest_path.stat().st_size > 0:
                skipped += 1
        if skipped:
            print(f"  Found {skipped} already-converted files — skipping")

    for ref in tqdm(convertible, desc="  Converting", unit="file"):
        dest_path = out_dir / (Path(ref.name).stem + ".md")
        if resume and dest_path.exists() and dest_path.stat().st_size > 0:
            converted += 1
            continue

        try:
            src_path = raw_root / ref.path
            if not src_path.exists():
                src_path = raw_root / ref.name
            conv = converter.convert_traced(src_path)
            total_cost += conv.cost_usd
            md = conv.markdown
            if md:
                out_path = out_dir / (src_path.stem + ".md")
                out_path.write_text(md, encoding="utf-8")
                converted += 1
                if manifest is not None:
                    update_file(
                        manifest,
                        out_path.name,
                        converter_tier=conv.tier,
                        conversion_cost_usd=conv.cost_usd,
                    )
            else:
                failed += 1
                failed_files.append(ref.name)
                failures.append({"file": ref.name, "error": "converter returned empty result"})
                logger.error("Conversion returned empty result for %s", ref.name)
        except Exception as exc:
            failed += 1
            error_str = str(exc)[:300]
            failed_files.append(f"{ref.name}: {error_str}")
            failures.append({"file": ref.name, "error": error_str})
            logger.error("Conversion failed for %s: %s", ref.name, error_str)

    result: dict = {
        "stage": "convert",
        "status": "ok" if failed == 0 else "warning",
        "files": len(convertible),
        "converted": converted,
        "skipped": skipped,
        "failed": failed,
        "cost_usd": total_cost,
    }
    if failed_files:
        result["failed_files"] = failed_files[:20]
        result["failure_details"] = failures[:20]
        result["warning"] = f"{failed} conversion failures"

    _check_common_conversion_failures(converted, failures)

    return result


def _check_common_conversion_failures(converted: int, failures: list[dict]) -> None:
    if not failures or converted > 0:
        return

    error_texts = [f["error"] for f in failures]
    unique_errors = set(error_texts)
    if len(unique_errors) == 1:
        error = error_texts[0]
        logger.error("All %d conversions failed with the same error: %s", len(failures), error)
        if "ModuleNotFoundError" in error or "No module named" in error:
            logger.error(
                "All conversions failed — install a converter:\n"
                "  pip install docling\n"
                "Or configure converter in folio.yaml:\n"
                "  converters:\n"
                "    engine: docling"
            )
        elif "datalab" in error.lower():
            logger.error(
                "Datalab conversion failed — try switching to docling in folio.yaml:\n"
                "  converters:\n"
                "    engine: docling"
            )
    else:
        logger.error(
            "All %d conversions failed with different errors. "
            "First 3:\n  %s",
            len(failures),
            "\n  ".join(f"{f['file']}: {f['error'][:120]}" for f in failures[:3]),
        )


def _run_clean(config: ProjectConfig, files: list[str] | None = None) -> dict:
    from folio.core.cleaner import clean_file, clean_markdown

    raw_md_dir = Path(config.paths.raw_md)
    clean_md_dir = Path(config.paths.clean_md)

    if not raw_md_dir.is_dir():
        return {
            "stage": "clean",
            "status": "warning",
            "warning": f"raw_md directory not found: {raw_md_dir}",
            "files": 0,
            "cost_usd": 0.0,
        }

    if files:
        classification = config.classification if hasattr(config, "classification") else {}
        if not isinstance(classification, dict):
            classification = {}
        clean_md_dir.mkdir(parents=True, exist_ok=True)
        processed = 0
        for filename in files:
            src = raw_md_dir / filename
            dest = clean_md_dir / filename
            if not src.exists():
                continue
            content = src.read_text(encoding="utf-8", errors="replace")
            cleaned = clean_markdown(content, classification)
            dest.write_text(cleaned, encoding="utf-8")
            processed += 1
        print(f"  Cleaned {processed}/{len(files)} files")
        return {
            "stage": "clean",
            "status": "ok",
            "files": processed,
            "cost_usd": 0.0,
        }

    md_files = list(raw_md_dir.glob("*.md"))
    if not md_files:
        return {
            "stage": "clean",
            "status": "warning",
            "warning": f"No .md files in {raw_md_dir}",
            "files": 0,
            "cost_usd": 0.0,
        }

    print(f"  Cleaning {len(md_files)} files...")
    clean_file(raw_md_dir, clean_md_dir)

    cleaned = len(list(clean_md_dir.glob("*.md")))
    return {
        "stage": "clean",
        "status": "ok",
        "files": cleaned,
        "cost_usd": 0.0,
    }


def _run_canonicalize(config: ProjectConfig, files: list[str] | None = None) -> dict:
    from folio.core.canonicalizer import DEFAULT_CANONICALIZE_CONFIG, canonicalize_directory

    clean_dir = Path(config.paths.clean_md)
    archive_dir = Path(config.paths.rewrite_md) / ".non_canonical"

    if not clean_dir.is_dir():
        return {
            "stage": "canonicalize",
            "status": "warning",
            "warning": f"clean_md directory not found: {clean_dir}",
            "files": 0,
            "cost_usd": 0.0,
        }

    md_files = list(clean_dir.glob("*.md"))
    if not md_files:
        return {
            "stage": "canonicalize",
            "status": "warning",
            "warning": f"No .md files in {clean_dir}",
            "files": 0,
            "cost_usd": 0.0,
        }

    print(f"  Analyzing {len(md_files)} files for canonical versions...")

    canonicalize_config = dict(DEFAULT_CANONICALIZE_CONFIG)

    result = canonicalize_directory(
        directory=clean_dir,
        config=canonicalize_config,
        archive_dir=archive_dir,
        dry_run=False,
        use_llm=False,
    )

    canonical = sum(1 for v in result.values() if v["status"] == "canonical")
    non_canonical = sum(1 for v in result.values() if v["status"] == "non_canonical")

    return {
        "stage": "canonicalize",
        "status": "ok",
        "files": len(result),
        "canonical": canonical,
        "non_canonical": non_canonical,
        "cost_usd": 0.0,
    }


def _run_classify(config: ProjectConfig, files: list[str] | None = None) -> dict:
    from folio.core.classifier import build_classify_config, classify_directory, classify_file

    clean_dir = Path(config.paths.clean_md)

    if not clean_dir.is_dir():
        return {
            "stage": "classify",
            "status": "warning",
            "warning": f"clean_md directory not found: {clean_dir}",
            "files": 0,
            "cost_usd": 0.0,
        }

    classify_config = build_classify_config(config)

    if files:
        existing = [f for f in files if (clean_dir / f).exists()]
        results = {f: classify_file(clean_dir / f, classify_config) for f in existing}
        summary = _build_classify_summary(results)
        print(f"  Classified {len(results)}/{len(files)} files")
        return {
            "stage": "classify",
            "status": "ok",
            "files": len(results),
            "by_tier": summary.get("by_tier", {}),
            "by_status": summary.get("by_status", {}),
            "by_funder": summary.get("by_funder", {}),
            "cost_usd": 0.0,
        }

    md_files = list(clean_dir.glob("*.md"))
    if not md_files:
        return {
            "stage": "classify",
            "status": "warning",
            "warning": f"No .md files in {clean_dir}",
            "files": 0,
            "cost_usd": 0.0,
        }

    print(f"  Classifying {len(md_files)} files...")

    manifest = classify_directory(clean_dir, classify_config)
    summary = manifest.get("summary", {})

    return {
        "stage": "classify",
        "status": "ok",
        "files": summary.get("total_files", len(md_files)),
        "by_tier": summary.get("by_tier", {}),
        "by_status": summary.get("by_status", {}),
        "by_funder": summary.get("by_funder", {}),
        "cost_usd": 0.0,
    }


def _build_classify_summary(results: dict) -> dict:
    tiers: dict[str, int] = {}
    statuses: dict[str, int] = {}
    funders: dict[str, int] = {}
    for result in results.values():
        tier = result.get("tier", "unknown")
        tiers[tier] = tiers.get(tier, 0) + 1
        status = result.get("status", "unknown")
        statuses[status] = statuses.get(status, 0) + 1
        funder = result.get("funder")
        if funder:
            funders[funder] = funders.get(funder, 0) + 1
    return {
        "total_files": len(results),
        "by_tier": tiers,
        "by_status": statuses,
        "by_funder": funders,
    }


def _run_rewrite(config: ProjectConfig, files: list[str] | None = None) -> dict:
    try:
        from folio.core.rewriter import rewrite_directory, rewrite_file
    except ImportError:
        return {
            "stage": "rewrite",
            "status": "skipped",
            "warning": "rewrite stage not yet implemented",
            "files": 0,
            "cost_usd": 0.0,
        }

    clean_dir = Path(config.paths.clean_md)
    rewrite_dir = Path(config.paths.rewrite_md)

    try:
        if files:
            existing = [f for f in files if (clean_dir / f).exists()]
            total_cost = 0.0
            ok_count = 0
            for filename in existing:
                src = clean_dir / filename
                try:
                    result = rewrite_file(src, config)
                    if isinstance(result, dict) and result.get("status") == "ok":
                        total_cost += result.get("cost_usd", 0.0)
                        ok_count += 1
                    else:
                        logger.warning("Rewrite returned non-ok for %s: %s", filename, result)
                except Exception as exc:
                    logger.warning("Rewrite failed for %s: %s", filename, exc)
            print(f"  Rewrote {ok_count}/{len(existing)} files" if existing else "  No files to rewrite")
            return {
                "stage": "rewrite",
                "status": "ok" if ok_count > 0 or not existing else "warning",
                "files": ok_count,
                "cost_usd": total_cost,
            }

        manifest_path = Path(config.paths.rewrite_md) / "manifest.json"
        result = rewrite_directory(clean_dir, config, manifest_path=manifest_path, dest=rewrite_dir)
        files_count = len(list(rewrite_dir.glob("*.md"))) if rewrite_dir.is_dir() else 0
        return {
            "stage": "rewrite",
            "status": "ok",
            "files": files_count,
            "cost_usd": result.get("total_cost_usd", 0.0) if isinstance(result, dict) else 0.0,
        }
    except Exception as exc:
        return {
            "stage": "rewrite",
            "status": "error",
            "error": str(exc),
            "files": 0,
            "cost_usd": 0.0,
        }


def _run_prioritize(config: ProjectConfig, files: list[str] | None = None) -> dict:
    try:
        from folio.core.prioritizer import prioritize_directory, prioritize_file
    except ImportError:
        return {
            "stage": "prioritize",
            "status": "skipped",
            "warning": "prioritize stage not yet implemented",
            "files": 0,
            "cost_usd": 0.0,
        }

    rewrite_dir = Path(config.paths.rewrite_md)

    try:
        if files:
            existing = [f for f in files if (rewrite_dir / f).exists()]
            total_cost = 0.0
            ok_count = 0
            for filename in existing:
                src = rewrite_dir / filename
                try:
                    result = prioritize_file(src, config)
                    if isinstance(result, dict) and result.get("priority") is not None:
                        total_cost += result.get("cost_usd", 0.0)
                        ok_count += 1
                    else:
                        logger.warning("Prioritize returned no priority for %s: %s", filename, result)
                except Exception as exc:
                    logger.warning("Prioritize failed for %s: %s", filename, exc)
            print(f"  Prioritized {ok_count}/{len(existing)} files" if existing else "  No files to prioritize")
            return {
                "stage": "prioritize",
                "status": "ok" if ok_count > 0 or not existing else "warning",
                "files": ok_count,
                "cost_usd": total_cost,
            }

        result = prioritize_directory(rewrite_dir, config)
        return {
            "stage": "prioritize",
            "status": "ok",
            "files": len(list(rewrite_dir.glob("*.md"))) if rewrite_dir.is_dir() else 0,
            "cost_usd": result.get("total_cost_usd", 0.0) if isinstance(result, dict) else 0.0,
        }
    except Exception as exc:
        return {
            "stage": "prioritize",
            "status": "error",
            "error": str(exc),
            "files": 0,
            "cost_usd": 0.0,
        }


def _run_wiki(config: ProjectConfig, files: list[str] | None = None) -> dict:
    import os

    from folio.adapters.wiki import get_wiki_backend

    wiki_type = config.wiki.type if hasattr(config.wiki, "type") else "null"

    if wiki_type == "null":
        return {
            "stage": "wiki",
            "status": "skipped",
            "warning": "Wiki backend is 'null'; markdown-only mode",
            "files": 0,
            "cost_usd": 0.0,
        }

    try:
        backend = get_wiki_backend(config)
    except Exception as exc:
        return {
            "stage": "wiki",
            "status": "error",
            "error": f"Failed to initialize wiki backend: {exc}",
            "files": 0,
            "cost_usd": 0.0,
        }

    wiki_dir = Path(config.paths.wiki_project)
    rewrite_dir = Path(config.paths.rewrite_md)

    pack_name = config.wiki.sage_wiki_pack if hasattr(config.wiki, "sage_wiki_pack") else "arts-org"

    print(f"  Initializing wiki project at {wiki_dir}...")
    try:
        wiki_config = {
            "version": 1,
            "project": config.org.name,
            "pack": pack_name,
            "sources": [{"path": "raw", "type": "auto", "watch": False}],
            "output": "wiki",
        }
        llm = config.llm
        if llm and hasattr(llm, "provider"):
            fetch_model = getattr(llm, "fast_model", None)
            write_model = getattr(llm, "quality_model", None)
            # Ensure the API key env var is set in the current process so
            # the sage-wiki subprocess inherits it for ${ENV_VAR} expansion.
            api_key = os.environ.get(llm.api_key_env, "")
            if api_key:
                os.environ.setdefault(llm.api_key_env, api_key)
            wiki_config["api"] = {
                "provider": "openai-compatible" if "deepseek" in str(llm.base_url) else llm.provider,
                "base_url": llm.base_url,
                "api_key": f"${{{llm.api_key_env}}}",
            }
            wiki_config["models"] = {
                "summarize": fetch_model or write_model or "deepseek-chat",
                "extract": fetch_model or write_model or "deepseek-chat",
                "write": write_model or fetch_model or "deepseek-chat",
                "lint": fetch_model or write_model or "deepseek-chat",
                "query": write_model or fetch_model or "deepseek-chat",
            }
            wiki_config["embed"] = {"provider": "auto"}
        backend.init(wiki_dir, wiki_config, source_dir=rewrite_dir)

        # Install and apply the pack from folio's templates
        pack_dir = Path(__file__).resolve().parent.parent / "templates" / "packs" / pack_name
        if pack_dir.is_dir():
            try:
                result = subprocess.run(
                    ["sage-wiki", "pack", "install", str(pack_dir)],
                    cwd=str(wiki_dir),
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=300,
                )
                logger.debug("sage-wiki pack install stdout:\n%s", result.stdout.strip())
                result = subprocess.run(
                    ["sage-wiki", "pack", "apply", pack_name, "--mode", "merge"],
                    cwd=str(wiki_dir),
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=300,
                )
                logger.debug("sage-wiki pack apply stdout:\n%s", result.stdout.strip())
                logger.info("Pack %s v1.1 installed and applied", pack_name)
            except FileNotFoundError:
                logger.warning("sage-wiki binary not found — pack install/apply skipped")
            except subprocess.CalledProcessError as e:
                logger.warning("Failed to install/apply pack %s: %s", pack_name, e.stderr.strip() if e.stderr else str(e))
    except Exception as exc:
        return {
            "stage": "wiki",
            "status": "error",
            "error": f"Failed to init wiki project: {exc}",
            "files": 0,
            "cost_usd": 0.0,
        }

    if rewrite_dir.is_dir():
        md_files = list(rewrite_dir.glob("*.md"))
        if md_files:
            print(f"  Wiki linked to {len(md_files)} documents in {rewrite_dir}")
            backend.add_documents(md_files)

    print("  Compiling wiki...")
    try:
        backend.compile()
        print("  Wiki compiled successfully")

        # Create root wiki/ symlink pointing to the compiled output
        compiled_wiki = wiki_dir / "wiki"
        if compiled_wiki.is_dir():
            public_link = Path("wiki")
            if public_link.is_symlink() or public_link.exists():
                public_link.unlink()
            public_link.symlink_to(compiled_wiki, target_is_directory=True)
            print(f"  Wiki output → {public_link}")

    except Exception as exc:
        return {
            "stage": "wiki",
            "status": "error",
            "error": f"Wiki compilation failed: {exc}",
            "files": len(list(rewrite_dir.glob("*.md"))) if rewrite_dir.is_dir() else 0,
            "cost_usd": 0.0,
        }

    return {
        "stage": "wiki",
        "status": "ok",
        "files": len(list(rewrite_dir.glob("*.md"))) if rewrite_dir.is_dir() else 0,
        "cost_usd": 0.0,
    }


# ── Formatting helpers ──────────────────────────────────────────────────────


def _format_time(seconds: float) -> str:
    if seconds < 0.5:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"{hours}h {minutes}m"


def _print_stage_summary(stage_name: str, result: dict) -> None:
    status = result.get("status", "?")
    elapsed = result.get("time_seconds", 0)

    if status == "ok":
        print(f"  Complete ({_format_time(elapsed)})")
        files = result.get("files", result.get("converted"))
        if files is not None:
            extras = []
            if stage_name == "scan":
                funders = result.get("funders_detected", 0)
                extras.append(f"{funders} funders detected")
                est = result.get("estimated_cost_usd", 0)
                if est:
                    extras.append(f"estimated LLM cost: ${est:.2f}")
            elif stage_name == "convert":
                failed = result.get("failed", 0)
                if failed:
                    extras.append(f"{failed} failed")
                    details = result.get("failure_details", [])
                    if details:
                        show = min(3, len(details))
                        for d in details[:show]:
                            err = d["error"][:120]
                            print(f"      {d['file']}: {err}")
                        if len(details) > 3:
                            remaining = len(details) - 3
                            print(f"      ... and {remaining} more. "
                                  f"Run with --verbose for full details.")
            elif stage_name == "canonicalize":
                extras.append(f"{result.get('canonical', 0)} canonical")
                extras.append(f"{result.get('non_canonical', 0)} non-canonical")
            elif stage_name == "classify":
                by_tier = result.get("by_tier", {})
                if by_tier:
                    tier_str = ", ".join(f"{t}={c}" for t, c in sorted(by_tier.items()))
                    extras.append(f"tiers: {tier_str}")
            if extras:
                print(f"  \u2192 {', '.join(extras)}")
            else:
                print(f"  \u2192 {files} files")
    elif status == "skipped":
        print(f"  Skipped — {result.get('warning', 'not implemented')}")
    elif status == "warning":
        print(f"  Warning — {result.get('warning', '')}")
    else:
        print(f"  Error — {result.get('error', 'Unknown error')}")

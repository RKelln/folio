"""PDF renderers — golden Markdown → PDF (text) and → image-only PDF (scanned).

PdfRenderer converts Markdown to a real, text-bearing PDF using pandoc + typst.
ScannedPdfRenderer builds on it: it rasterizes each page to PNG and recombines
the images into an image-only PDF (no embedded text), producing an OCR-test
fixture that mimics a scanned document.

Both shell out to external tools and capture output; on any failure they raise
RuntimeError rather than leaving a partial/empty file behind.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from folio.adapters.renderers.base import Renderer

logger = logging.getLogger(__name__)

_PDF_MAGIC = b"%PDF"


def _on_path(tool: str) -> bool:
    """True when ``tool`` resolves on PATH."""
    return shutil.which(tool) is not None


def _run(cmd: list[str]) -> subprocess.CompletedProcess[bytes]:
    """Run a command, capturing output and raising on non-zero exit."""
    return subprocess.run(cmd, capture_output=True, check=True)


def _is_pdf(path: Path) -> bool:
    """True when ``path`` exists and begins with the ``%PDF`` magic bytes."""
    try:
        with path.open("rb") as handle:
            return handle.read(4) == _PDF_MAGIC
    except OSError:
        return False


class PdfRenderer(Renderer):
    """Render Markdown to a text PDF via pandoc + the typst PDF engine."""

    name = "pandoc+typst"
    output_format = "pdf"

    def available(self) -> bool:
        ok = _on_path("pandoc") and _on_path("typst")
        if not ok:
            logger.warning(
                "PdfRenderer unavailable: requires both pandoc and typst on PATH "
                "(pandoc=%s, typst=%s)",
                shutil.which("pandoc"),
                shutil.which("typst"),
            )
        return ok

    def render(self, markdown: str, meta: dict, out_path: Path) -> Path:
        if not self.available():
            raise RuntimeError(
                "PdfRenderer requires pandoc and typst on PATH; cannot render PDF."
            )
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="folio-pdf-") as tmp:
            tmp_dir = Path(tmp)
            src_md = tmp_dir / "source.md"
            src_md.write_text(markdown, encoding="utf-8")

            # Preferred: let pandoc drive typst directly.
            try:
                _run(
                    [
                        "pandoc",
                        str(src_md),
                        "-o",
                        str(out_path),
                        "--pdf-engine=typst",
                    ]
                )
                if _is_pdf(out_path):
                    return out_path
                logger.warning(
                    "pandoc --pdf-engine=typst produced no valid PDF for %s; "
                    "falling back to a two-step typst compile",
                    out_path,
                )
            except (subprocess.CalledProcessError, OSError) as exc:
                detail = getattr(exc, "stderr", b"") or b""
                logger.warning(
                    "pandoc --pdf-engine=typst failed (%s); falling back to "
                    "two-step typst compile",
                    detail.decode("utf-8", "replace").strip()[:300] or exc,
                )

            # Clear any partial output before the fallback attempt.
            out_path.unlink(missing_ok=True)

            # Fallback: pandoc -> .typ, then typst compile -> .pdf.
            typ = tmp_dir / "source.typ"
            try:
                _run(["pandoc", str(src_md), "-t", "typst", "-o", str(typ)])
                _run(["typst", "compile", str(typ), str(out_path)])
            except (subprocess.CalledProcessError, OSError) as exc:
                out_path.unlink(missing_ok=True)
                detail = getattr(exc, "stderr", b"") or b""
                raise RuntimeError(
                    f"PDF render failed (pandoc/typst): "
                    f"{detail.decode('utf-8', 'replace').strip()[:500] or exc}"
                ) from exc

        if not _is_pdf(out_path):
            out_path.unlink(missing_ok=True)
            raise RuntimeError(f"PDF render produced no valid PDF at {out_path}")
        return out_path


class ScannedPdfRenderer(Renderer):
    """Render Markdown to an image-only ("scanned") PDF for OCR fixtures.

    Renders a normal text PDF first, rasterizes each page to PNG via
    ``pdftoppm``, then recombines the PNGs into a single image-only PDF with
    Pillow. The result contains no extractable text.
    """

    name = "pandoc+typst+poppler+pillow"
    output_format = "pdf_scanned"

    def __init__(self) -> None:
        self._pdf = PdfRenderer()

    def available(self) -> bool:
        if not self._pdf.available():
            return False
        if not _on_path("pdftoppm"):
            logger.warning("ScannedPdfRenderer unavailable: pdftoppm (poppler) not on PATH")
            return False
        try:
            import PIL  # type: ignore[import-not-found]  # noqa: F401
        except ImportError as exc:
            logger.warning("ScannedPdfRenderer unavailable: Pillow not importable (%s)", exc)
            return False
        return True

    def render(self, markdown: str, meta: dict, out_path: Path) -> Path:
        if not self.available():
            raise RuntimeError(
                "ScannedPdfRenderer requires pandoc, typst, pdftoppm and Pillow."
            )
        try:
            from PIL import Image  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("Pillow not installed; cannot render scanned PDF.") from exc

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="folio-scan-") as tmp:
            tmp_dir = Path(tmp)
            text_pdf = tmp_dir / "text.pdf"
            self._pdf.render(markdown, meta, text_pdf)

            prefix = tmp_dir / "page"
            try:
                _run(["pdftoppm", "-r", "100", "-png", str(text_pdf), str(prefix)])
            except (subprocess.CalledProcessError, OSError) as exc:
                detail = getattr(exc, "stderr", b"") or b""
                raise RuntimeError(
                    f"pdftoppm rasterization failed: "
                    f"{detail.decode('utf-8', 'replace').strip()[:300] or exc}"
                ) from exc

            pages = sorted(tmp_dir.glob("page*.png"))
            if not pages:
                raise RuntimeError("pdftoppm produced no page images; cannot build scanned PDF")

            images = [Image.open(p).convert("RGB") for p in pages]
            try:
                images[0].save(
                    str(out_path),
                    "PDF",
                    save_all=True,
                    append_images=images[1:],
                )
            finally:
                for img in images:
                    img.close()

        if not _is_pdf(out_path):
            out_path.unlink(missing_ok=True)
            raise RuntimeError(f"Scanned PDF render produced no valid PDF at {out_path}")
        return out_path

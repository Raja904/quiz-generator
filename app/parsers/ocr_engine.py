"""
app/parsers/ocr_engine.py

Modular OCR interface for scanned PDF pages.

Design:
  - Defines an abstract base class (OCREngine) so any OCR backend can be
    swapped in by implementing a single method: `run(image_bytes) -> str`.
  - Ships with one concrete implementation: EasyOCREngine.
  - EasyOCR is preferred over Tesseract for Azure App Service deployment
    because it ships as a pure-Python/PyTorch package with no system-level
    binary dependencies.

Usage (from pdf_parser.py):
    from app.parsers.ocr_engine import EasyOCREngine

    engine = EasyOCREngine()                  # lazily loads model on first call
    text   = engine.run(png_bytes_of_a_page)  # returns str
"""

from __future__ import annotations

import abc
import logging

logger = logging.getLogger(__name__)


# ── Abstract base class ───────────────────────────────────────────────────────

class OCREngine(abc.ABC):
    """
    Swap any OCR backend by subclassing this and implementing `run`.

    The contract:
      - Accept raw image bytes (PNG/JPEG/BMP).
      - Return the extracted text as a single string.
      - Raise RuntimeError on unrecoverable failure.
    """

    @abc.abstractmethod
    def run(self, image_bytes: bytes) -> str:
        """Run OCR on *image_bytes* and return the extracted text."""


# ── EasyOCR implementation ────────────────────────────────────────────────────

class EasyOCREngine(OCREngine):
    """
    OCR backend powered by EasyOCR.

    The EasyOCR Reader object is expensive to construct (it loads a neural
    network model) so it is lazily instantiated on the first call and
    cached for the lifetime of the process.

    Args:
        languages: List of ISO 639-1 language codes to recognise.
                   Defaults to English only. Add more as needed,
                   e.g. ["en", "hi"] for Hindi support.
        gpu:       Enable GPU inference. Defaults to False because Azure
                   App Service (Basic/Standard) does not have GPUs.
    """

    def __init__(self, languages: list[str] | None = None, *, gpu: bool = False):
        self._languages: list[str] = languages or ["en"]
        self._gpu: bool = gpu
        self._reader = None  # lazy-init; None until first call

    # -- private --

    def _get_reader(self):
        if self._reader is None:
            try:
                import easyocr  # noqa: PLC0415
            except ImportError as exc:
                raise RuntimeError(
                    "easyocr is not installed. "
                    "Add 'easyocr>=1.7.0' to your dependencies."
                ) from exc

            logger.info(
                "Initialising EasyOCR reader | languages=%s gpu=%s",
                self._languages,
                self._gpu,
            )
            self._reader = easyocr.Reader(self._languages, gpu=self._gpu)
            logger.info("EasyOCR reader ready.")
        return self._reader

    # -- public --

    @staticmethod
    def preprocess(image_bytes: bytes) -> bytes:
        """
        Apply image preprocessing to improve OCR accuracy.

        Pipeline:
          1. Decode PNG/JPEG bytes → Pillow Image
          2. Convert to grayscale (eliminates colour noise)
          3. Enhance contrast (makes text edges sharper)
          4. Re-encode as PNG bytes for EasyOCR

        Args:
            image_bytes: Raw image bytes (PNG or JPEG).

        Returns:
            Preprocessed PNG bytes.

        Note:
            Pillow is a transitive dependency of EasyOCR so it will always
            be present when this module is active.
        """
        try:
            import io
            from PIL import Image, ImageEnhance, ImageOps  # noqa: PLC0415

            img = Image.open(io.BytesIO(image_bytes))

            # Step 1 — Grayscale
            # Removes colour channels that confuse OCR models trained on text.
            img = ImageOps.grayscale(img)

            # Step 2 — Contrast enhancement
            # Factor >1.0 increases contrast. 1.5 is a reliable middle ground:
            # strong enough to sharpen faint text, mild enough not to blow out
            # high-contrast pages (e.g. black text on white background).
            img = ImageEnhance.Contrast(img).enhance(1.5)

            # Re-encode as PNG
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()

        except ImportError:
            # Pillow not available — return original bytes unchanged.
            logger.warning("Pillow not available; skipping image preprocessing.")
            return image_bytes
        except Exception as exc:
            # Preprocessing failure is non-fatal — fall back to raw bytes.
            logger.warning("Image preprocessing failed (%s); using raw image.", exc)
            return image_bytes

    def run(self, image_bytes: bytes) -> str:
        """
        Preprocess *image_bytes* then run EasyOCR.

        Full pipeline:
          raw PNG → grayscale → contrast enhance → EasyOCR inference → str

        Returns:
            Extracted text joined into a single string (one line per item).
        Raises:
            RuntimeError: If EasyOCR is not installed or inference fails.
        """
        reader = self._get_reader()
        preprocessed = self.preprocess(image_bytes)
        try:
            results = reader.readtext(preprocessed, detail=0, paragraph=True)
            return "\n".join(str(r) for r in results)
        except Exception as exc:
            raise RuntimeError(f"EasyOCR inference failed: {exc}") from exc

"""
app/parsers/ocr_engine.py

Modular OCR interface for scanned PDF pages.

Design:
  - Defines an abstract base class (OCREngine) so any OCR backend can be
    swapped in by implementing a single method: `run(image_bytes) -> str`.
  - Ships with one concrete implementation: RapidOCREngine.
  - RapidOCR (ONNX runtime) is preferred for Azure/Render App Service 
    deployment because it is extremely lightweight and avoids PyTorch/CUDA 
    OOM crashes on free tiers (512MB RAM).

Usage (from pdf_parser.py):
    from app.parsers.ocr_engine import RapidOCREngine

    engine = RapidOCREngine()                 # lazily loads model on first call
    text   = engine.run(png_bytes_of_a_page)  # returns str
"""

from __future__ import annotations

import abc
import logging
import os

# Limit threading for OCR to prevent out-of-memory (OOM) and CPU spikes on Render's free tier (512MB RAM).
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

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


# ── RapidOCR (ONNX) implementation ────────────────────────────────────────────

class RapidOCREngine(OCREngine):
    """
    OCR backend powered by rapidocr-onnxruntime.

    It is extremely lightweight and uses CPU ONNX runtime. The model is lazily 
    instantiated on the first call and cached.
    """

    def __init__(self):
        self._engine = None  # lazy-init; None until first call

    # -- private --

    def _get_engine(self):
        if self._engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR  # noqa: PLC0415
            except ImportError as exc:
                raise RuntimeError(
                    "rapidocr-onnxruntime is not installed. "
                    "Add 'rapidocr-onnxruntime>=1.3.0' to your dependencies."
                ) from exc

            logger.info("Initialising RapidOCR (ONNX) engine...")
            self._engine = RapidOCR()
            logger.info("RapidOCR engine ready.")
        return self._engine

    # -- public --

    @staticmethod
    def preprocess(image_bytes: bytes) -> bytes:
        """
        Apply image preprocessing to improve OCR accuracy.

        Pipeline:
          1. Decode PNG/JPEG bytes → Pillow Image
          2. Convert to grayscale (eliminates colour noise)
          3. Enhance contrast (makes text edges sharper)
          4. Re-encode as PNG bytes for OCR

        Args:
            image_bytes: Raw image bytes (PNG or JPEG).

        Returns:
            Preprocessed PNG bytes.
        """
        try:
            import io
            from PIL import Image, ImageEnhance, ImageOps  # noqa: PLC0415

            img = Image.open(io.BytesIO(image_bytes))

            # Step 1 — Grayscale
            img = ImageOps.grayscale(img)

            # Step 2 — Contrast enhancement
            img = ImageEnhance.Contrast(img).enhance(1.5)

            # Re-encode as PNG
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()

        except ImportError:
            logger.warning("Pillow not available; skipping image preprocessing.")
            return image_bytes
        except Exception as exc:
            logger.warning("Image preprocessing failed (%s); using raw image.", exc)
            return image_bytes

    def run(self, image_bytes: bytes) -> str:
        """
        Preprocess *image_bytes* then run RapidOCR.

        Full pipeline:
          raw PNG → grayscale → contrast enhance → RapidOCR inference → str

        Returns:
            Extracted text joined into a single string (one line per item).
        Raises:
            RuntimeError: If RapidOCR is not installed or inference fails.
        """
        engine = self._get_engine()
        preprocessed = self.preprocess(image_bytes)
        try:
            # rapidocr returns (result, elapse_time)
            # result is a list of [box, text, confidence]
            result, _ = engine(preprocessed)
            if result:
                return "\n".join(str(r[1]) for r in result if r)
            return ""
        except Exception as exc:
            raise RuntimeError(f"RapidOCR inference failed: {exc}") from exc


# ── Native Subprocess OCR (Ocrad) implementation ──────────────────────────────

class OcradEngine(OCREngine):
    """
    OCR backend using the highly optimized C utility 'ocrad'.
    
    This runs entirely outside the Python memory space, consuming almost zero
    RAM (~15 MB). It is ideal for extremely resource-constrained environments
    like Render's free tier.
    
    Requires `ocrad` to be installed on the host system:
        Linux: sudo apt-get install ocrad
        Windows: Download ocrad.exe and add to PATH
    """

    def run(self, image_bytes: bytes) -> str:
        import io
        import tempfile
        import subprocess
        try:
            from PIL import Image, ImageEnhance  # noqa: PLC0415
        except ImportError as exc:
            raise RuntimeError("Pillow is required for Ocrad preprocessing.") from exc

        # 1. Decode and preprocess the image (grayscale + contrast)
        img = Image.open(io.BytesIO(image_bytes))
        img = img.convert("L")  # Convert to grayscale
        img = ImageEnhance.Contrast(img).enhance(1.5)

        # 2. Save as PGM (Portable GrayMap) to a temporary file
        # ocrad natively understands PGM format.
        with tempfile.NamedTemporaryFile(suffix=".pgm", delete=False) as tmp:
            tmp_name = tmp.name
            img.save(tmp_name, format="PPM")  # Pillow writes PGM if mode is 'L'

        # 3. Execute the native ocrad binary
        # Check if we have the compiled binary from build.sh (Render), otherwise fallback to global PATH
        import shutil
        ocrad_cmd = "./ocrad_bin" if os.path.exists("ocrad_bin") else "ocrad"
        
        try:
            result = subprocess.run(
                [ocrad_cmd, tmp_name],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"'{ocrad_cmd}' binary not found. Please compile it using build.sh "
                "or install it globally."
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"ocrad execution failed: {exc.stderr}") from exc
        finally:
            # 4. Clean up the temporary file
            try:
                os.remove(tmp_name)
            except OSError:
                pass

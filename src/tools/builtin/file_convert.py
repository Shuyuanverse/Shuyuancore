from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from src.tools.interfaces import ITool, ToolParameter, ToolResult, ToolSpec


class FileConvertTool(ITool):
    """File conversion tool supporting PDF-to-text extraction and OCR.

    PDF text extraction attempts to use PyMuPDF (fitz) first, falling
    back to the pdftotext command-line tool. OCR uses pytesseract for
    image-to-text conversion. All operations are read-only and do not
    modify input files.
    """

    def get_spec(self) -> ToolSpec:
        """Return the tool specification.

        Returns:
            ToolSpec describing this tool's metadata and parameters.
        """

        return ToolSpec(
            name="file_convert",
            description="File conversion tool. Supports PDF-to-text extraction and OCR.",
            category="office",
            dangerous=False,
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    description="Operation: pdf_to_text or ocr_image",
                    required=True,
                ),
                ToolParameter(
                    name="input_path",
                    type="string",
                    description="Path to the input file",
                    required=True,
                ),
                ToolParameter(
                    name="output_path",
                    type="string",
                    description="Optional path to save the extracted text",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="language",
                    type="string",
                    description="OCR language (used for ocr_image action)",
                    required=False,
                    default="eng",
                ),
                ToolParameter(
                    name="timeout",
                    type="integer",
                    description="Operation timeout in seconds",
                    required=False,
                    default=60,
                ),
            ],
        )

    async def validate(self, params: dict[str, Any]) -> list[str]:
        """Validate parameters before execution.

        Args:
            params: Dictionary of tool parameters.

        Returns:
            List of validation error messages. Empty list means valid.
        """

        errors: list[str] = []
        action = params.get("action", "")
        valid_actions = {"pdf_to_text", "ocr_image"}
        if action not in valid_actions:
            errors.append(f"action must be one of: {', '.join(sorted(valid_actions))}")
            return errors

        input_path = params.get("input_path")
        if not input_path or not isinstance(input_path, str) or not input_path.strip():
            errors.append("input_path is required and must be a non-empty string")
            return errors

        if not Path(input_path).exists():
            errors.append(f"input_path does not exist: {input_path}")

        return errors

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str = "default",
    ) -> ToolResult:
        """Execute the file conversion operation.

        Args:
            params: Dictionary of tool parameters.
            user_id: Identifier of the user making the request.

        Returns:
            ToolResult with extracted text content.
        """

        action: str = params["action"]
        input_path: str = params["input_path"]
        output_path: str | None = params.get("output_path")
        language: str = params.get("language", "eng")
        timeout_val: int = int(params.get("timeout", 60))
        start = time.time()

        try:
            if action == "pdf_to_text":
                return await self._extract_pdf_text(input_path, output_path, timeout_val, start)
            else:
                return await self._ocr_image(input_path, output_path, language, timeout_val, start)
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"File conversion failed: {e}",
                duration_ms=(time.time() - start) * 1000,
            )

    async def _extract_pdf_text(
        self,
        input_path: str,
        output_path: str | None,
        timeout_val: int,
        start: float,
    ) -> ToolResult:
        """Extract text from a PDF file.

        Attempts to use PyMuPDF (fitz) first. Falls back to the
        pdftotext command-line tool if fitz is not available.

        Args:
            input_path: Path to the PDF file.
            output_path: Optional path to write extracted text.
            timeout_val: Operation timeout in seconds.
            start: Start timestamp for duration calculation.

        Returns:
            ToolResult with the extracted text content.
        """

        text: str = ""

        try:
            import fitz

            doc = fitz.open(input_path)
            pages: list[str] = []
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                pages.append(page.get_text())
            doc.close()
            text = "\n\n".join(pages)
        except ImportError:
            try:
                result = subprocess.run(
                    ["pdftotext", input_path, "-"],
                    capture_output=True,
                    text=True,
                    timeout=timeout_val,
                )
                if result.returncode == 0:
                    text = result.stdout
                else:
                    return ToolResult(
                        success=False,
                        error=(
                            f"pdftotext failed (exit {result.returncode}): {result.stderr.strip()}"
                        ),
                        duration_ms=(time.time() - start) * 1000,
                    )
            except FileNotFoundError:
                return ToolResult(
                    success=False,
                    error=(
                        "Neither PyMuPDF (fitz) nor pdftotext is available. "
                        "Install PyMuPDF with 'pip install pymupdf' or "
                        "install poppler-utils for pdftotext."
                    ),
                    duration_ms=(time.time() - start) * 1000,
                )
            except subprocess.TimeoutExpired:
                return ToolResult(
                    success=False,
                    error=f"pdftotext timed out after {timeout_val}s",
                    duration_ms=(time.time() - start) * 1000,
                )

        if output_path:
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")

        return ToolResult(
            success=True,
            data={
                "text": text,
                "length": len(text),
                "output_path": output_path,
            },
            duration_ms=(time.time() - start) * 1000,
        )

    async def _ocr_image(
        self,
        input_path: str,
        output_path: str | None,
        language: str,
        timeout_val: int,
        start: float,
    ) -> ToolResult:
        """Perform OCR on an image file using pytesseract.

        Falls back with an error message if pytesseract is not installed.

        Args:
            input_path: Path to the image file.
            output_path: Optional path to save the OCR text.
            language: OCR language code (e.g. 'eng', 'chi_sim').
            timeout_val: Operation timeout in seconds.
            start: Start timestamp for duration calculation.

        Returns:
            ToolResult with the OCR-extracted text.
        """

        try:
            import pytesseract
            from PIL import Image
        except ImportError:
            return ToolResult(
                success=False,
                error=(
                    "pytesseract or Pillow is not installed. Install with "
                    "'pip install pytesseract Pillow'."
                ),
                duration_ms=(time.time() - start) * 1000,
            )

        try:
            image = Image.open(input_path)
            text: str = pytesseract.image_to_string(image, lang=language, timeout=timeout_val)
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"OCR failed: {e}",
                duration_ms=(time.time() - start) * 1000,
            )

        if output_path:
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")

        return ToolResult(
            success=True,
            data={
                "text": text,
                "length": len(text),
                "output_path": output_path,
            },
            duration_ms=(time.time() - start) * 1000,
        )

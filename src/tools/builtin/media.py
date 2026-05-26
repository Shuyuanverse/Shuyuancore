from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any

from src.security.audit import get_audit_logger
from src.tools.interfaces import ITool, ToolParameter, ToolResult, ToolSpec

_ACTION_REQUIRED_PARAMS: dict[str, set[str]] = {
    "image_to_text": {"input_path"},
    "tts": {"text"},
    "stt": {"input_path"},
    "resize_image": {"input_path", "width", "height"},
    "convert_format": {"input_path", "output_format"},
}

_VALID_ACTIONS: frozenset[str] = frozenset({
    "image_to_text", "tts", "stt", "resize_image", "convert_format",
})


class MediaTool(ITool):

    def __init__(self) -> None:
        self._spec = ToolSpec(
            name="media",
            description=(
                "媒体处理工具，支持图片文字识别（OCR）、"
                "文本转语音（TTS）、语音转文字（STT）、"
                "图片尺寸调整和格式转换。"
            ),
            category="extension",
            dangerous=False,
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    description=(
                        "操作类型：image_to_text（OCR）/ tts（文本转语音）"
                        "/ stt（语音转文字）/ resize_image（调整尺寸）"
                        "/ convert_format（格式转换）"
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="input_path",
                    type="string",
                    description=(
                        "输入文件路径，image_to_text / stt / "
                        "resize_image / convert_format 操作必填"
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="text",
                    type="string",
                    description="待转换文本，tts 操作必填",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="language",
                    type="string",
                    description="语言代码，默认为 zh",
                    required=False,
                    default="zh",
                ),
                ToolParameter(
                    name="output_format",
                    type="string",
                    description="输出格式，convert_format 操作必填；默认 wav",
                    required=False,
                    default="wav",
                ),
                ToolParameter(
                    name="width",
                    type="integer",
                    description="目标宽度（像素），resize_image 操作必填",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="height",
                    type="integer",
                    description="目标高度（像素），resize_image 操作必填",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="timeout",
                    type="integer",
                    description="操作超时时间（秒），默认为 60",
                    required=False,
                    default=60,
                ),
            ],
        )

    def get_spec(self) -> ToolSpec:
        return self._spec

    async def validate(self, params: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        action: str = params.get("action", "").strip()

        if not action:
            errors.append("action is required and must not be empty")
            return errors

        if action not in _VALID_ACTIONS:
            valid = ", ".join(sorted(_VALID_ACTIONS))
            errors.append(
                f"Invalid action: {action}. Must be one of: {valid}"
            )
            return errors

        required = _ACTION_REQUIRED_PARAMS.get(action, set())
        for param in required:
            value = params.get(param)
            if value is None:
                errors.append(
                    f"'{param}' is required for action '{action}'"
                )
            elif isinstance(value, str) and not value.strip():
                errors.append(
                    f"'{param}' must not be empty for action '{action}'"
                )

        return errors

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str = "default",
    ) -> ToolResult:
        action: str = params["action"]
        start = time.time()
        audit = get_audit_logger()

        try:
            if action == "image_to_text":
                return await self._image_to_text(
                    params, user_id, start, audit
                )
            elif action == "tts":
                return await self._tts(
                    params, user_id, start, audit
                )
            elif action == "stt":
                return await self._stt(
                    params, user_id, start, audit
                )
            elif action == "resize_image":
                return await self._resize_image(
                    params, user_id, start, audit
                )
            elif action == "convert_format":
                return await self._convert_format(
                    params, user_id, start, audit
                )
            else:
                return ToolResult(
                    success=False,
                    error=f"Unknown action: {action}",
                    duration_ms=(time.time() - start) * 1000,
                )
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action=f"media.{action}",
                resource="media",
                params=params,
                result="error",
                error=str(e),
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=f"Media action '{action}' failed: {e}",
                duration_ms=duration_ms,
            )

    async def _image_to_text(
        self,
        params: dict[str, Any],
        user_id: str,
        start: float,
        audit: Any,
    ) -> ToolResult:
        input_path: str = params["input_path"]
        path = Path(input_path)

        if not path.exists():
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="media.image_to_text",
                resource=str(path),
                params=params,
                result="error",
                error="File not found",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=f"File not found: {input_path}",
                duration_ms=duration_ms,
            )

        try:
            import pytesseract
            from PIL import Image

            image = Image.open(str(path))
            language: str = params.get("language", "zh")
            text: str = pytesseract.image_to_string(image, lang=language)
            text = text.strip()

            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="media.image_to_text",
                resource=str(path),
                params={"input_path": input_path},
                result="success",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=True,
                data={"text": text, "length": len(text)},
                duration_ms=duration_ms,
            )
        except ImportError:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="media.image_to_text",
                resource=str(path),
                params=params,
                result="error",
                error="pytesseract or PIL not installed",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=(
                    "pytesseract or Pillow is not installed. "
                    "Install with: pip install pytesseract Pillow"
                ),
                duration_ms=duration_ms,
            )

    async def _tts(
        self,
        params: dict[str, Any],
        user_id: str,
        start: float,
        audit: Any,
    ) -> ToolResult:
        text: str = params["text"]
        language: str = params.get("language", "zh")

        try:
            import edge_tts

            communicate = edge_tts.Communicate(text, language)
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]

            encoded = base64.b64encode(audio_data).decode("utf-8")

            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="media.tts",
                resource="edge_tts",
                params={"text_length": len(text), "language": language},
                result="success",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=True,
                data={
                    "audio_base64": encoded,
                    "format": "mp3",
                    "text_length": len(text),
                },
                duration_ms=duration_ms,
            )
        except ImportError:
            pass

        try:
            import io

            from gtts import gTTS
            tts = gTTS(text=text, lang=language[:2])
            audio_bytes = io.BytesIO()
            tts.write_to_fp(audio_bytes)
            audio_data = audio_bytes.getvalue()
            encoded = base64.b64encode(audio_data).decode("utf-8")

            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="media.tts",
                resource="gtts",
                params={"text_length": len(text), "language": language},
                result="success",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=True,
                data={
                    "audio_base64": encoded,
                    "format": "mp3",
                    "text_length": len(text),
                },
                duration_ms=duration_ms,
            )
        except ImportError:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="media.tts",
                resource="tts",
                params=params,
                result="error",
                error="edge-tts or gTTS not installed",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=(
                    "Neither edge-tts nor gTTS is installed. "
                    "Install one with: pip install edge-tts "
                    "or pip install gtts"
                ),
                duration_ms=duration_ms,
            )

    async def _stt(
        self,
        params: dict[str, Any],
        user_id: str,
        start: float,
        audit: Any,
    ) -> ToolResult:
        input_path: str = params["input_path"]
        path = Path(input_path)

        if not path.exists():
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="media.stt",
                resource=str(path),
                params=params,
                result="error",
                error="File not found",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=f"File not found: {input_path}",
                duration_ms=duration_ms,
            )

        try:
            import speech_recognition as sr

            recognizer = sr.Recognizer()
            with sr.AudioFile(str(path)) as source:
                audio = recognizer.record(source)

            language: str = params.get("language", "zh")
            text: str = recognizer.recognize_google(audio, language=language)

            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="media.stt",
                resource=str(path),
                params={"input_path": input_path},
                result="success",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=True,
                data={"text": text, "length": len(text)},
                duration_ms=duration_ms,
            )
        except ImportError:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="media.stt",
                resource=str(path),
                params=params,
                result="error",
                error="speech_recognition not installed",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=(
                    "speech_recognition is not installed. "
                    "Install with: pip install SpeechRecognition"
                ),
                duration_ms=duration_ms,
            )

    async def _resize_image(
        self,
        params: dict[str, Any],
        user_id: str,
        start: float,
        audit: Any,
    ) -> ToolResult:
        input_path: str = params["input_path"]
        width: int = params["width"]
        height: int = params["height"]
        path = Path(input_path)

        if not path.exists():
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="media.resize_image",
                resource=str(path),
                params=params,
                result="error",
                error="File not found",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=f"File not found: {input_path}",
                duration_ms=duration_ms,
            )

        try:
            from PIL import Image

            image = Image.open(str(path))
            resized = image.resize((width, height), Image.LANCZOS)

            output_path = path.parent / f"{path.stem}_resized{path.suffix}"
            resized.save(str(output_path))

            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="media.resize_image",
                resource=str(path),
                params={
                    "input_path": input_path,
                    "width": width,
                    "height": height,
                },
                result="success",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=True,
                data={
                    "output_path": str(output_path),
                    "original_size": image.size,
                    "new_size": (width, height),
                },
                duration_ms=duration_ms,
            )
        except ImportError:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="media.resize_image",
                resource=str(path),
                params=params,
                result="error",
                error="Pillow not installed",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=(
                    "Pillow is not installed. "
                    "Install with: pip install Pillow"
                ),
                duration_ms=duration_ms,
            )

    async def _convert_format(
        self,
        params: dict[str, Any],
        user_id: str,
        start: float,
        audit: Any,
    ) -> ToolResult:
        input_path: str = params["input_path"]
        output_format: str = params.get("output_format", "wav")
        path = Path(input_path)

        if not path.exists():
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="media.convert_format",
                resource=str(path),
                params=params,
                result="error",
                error="File not found",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=f"File not found: {input_path}",
                duration_ms=duration_ms,
            )

        try:
            from PIL import Image

            image = Image.open(str(path))
            output_path = path.parent / f"{path.stem}.{output_format}"
            image.save(str(output_path), format=output_format.upper())

            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="media.convert_format",
                resource=str(path),
                params={
                    "input_path": input_path,
                    "output_format": output_format,
                },
                result="success",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=True,
                data={
                    "output_path": str(output_path),
                    "format": output_format,
                },
                duration_ms=duration_ms,
            )
        except ImportError:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="media.convert_format",
                resource=str(path),
                params=params,
                result="error",
                error="Pillow not installed",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=(
                    "Pillow is not installed. "
                    "Install with: pip install Pillow"
                ),
                duration_ms=duration_ms,
            )

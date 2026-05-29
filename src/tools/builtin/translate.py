from __future__ import annotations

import os
from typing import Any

import httpx

from src.tools.interfaces import ITool, ToolParameter, ToolResult, ToolSpec

GOOGLE_TRANSLATE_URL = (
    "https://translate.googleapis.com/translate_a/single"
    "?client=gtx&sl={source}&tl={target}&dt=t&q={text}"
)

DEEPL_API_URL = "https://api-free.deepl.com/v2/translate"


class TranslateTool(ITool):
    """Translation tool supporting Google Translate and DeepL providers.

    Uses the free Google Translate API by default. For DeepL, the
    DEEPL_API_KEY environment variable must be set.
    """

    def __init__(self) -> None:
        self._spec = ToolSpec(
            name="translate",
            description=(
                "Translate text between languages using Google Translate "
                "or DeepL. Supports auto-detection of source language."
            ),
            category="office",
            dangerous=False,
            parameters=[
                ToolParameter(
                    name="text",
                    type="string",
                    description="Text to translate",
                    required=True,
                ),
                ToolParameter(
                    name="source_lang",
                    type="string",
                    description=(
                        "Source language code (e.g. 'en', 'zh', 'ja'). "
                        "Use 'auto' for automatic detection."
                    ),
                    required=False,
                    default="auto",
                ),
                ToolParameter(
                    name="target_lang",
                    type="string",
                    description=("Target language code (e.g. 'zh', 'en', 'ja')"),
                    required=False,
                    default="zh",
                ),
                ToolParameter(
                    name="provider",
                    type="string",
                    description="Translation provider: 'google' or 'deepl'",
                    required=False,
                    default="google",
                ),
                ToolParameter(
                    name="timeout",
                    type="integer",
                    description="Request timeout in seconds",
                    required=False,
                    default=30,
                ),
            ],
        )

    def get_spec(self) -> ToolSpec:
        """Return the tool specification.

        Returns:
            ToolSpec instance describing this tool's interface.
        """

        return self._spec

    async def validate(self, params: dict[str, Any]) -> list[str]:
        """Validate parameters before execution.

        Args:
            params: Dictionary of tool parameters.

        Returns:
            List of validation error messages. Empty list means valid.
        """

        errors: list[str] = []
        text = params.get("text", "")
        if not text:
            errors.append("text is required and must not be empty")

        provider = params.get("provider", "google")
        if provider not in ("google", "deepl"):
            errors.append(f"Invalid provider: {provider}. Must be 'google' or 'deepl'.")

        if provider == "deepl":
            api_key = os.environ.get("DEEPL_API_KEY")
            if not api_key:
                errors.append(
                    "DEEPL_API_KEY environment variable is required when using the deepl provider"
                )

        return errors

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str = "default",
    ) -> ToolResult:
        """Execute the translation request.

        Args:
            params: Dictionary of tool parameters.
            user_id: Identifier of the user making the request.

        Returns:
            ToolResult with translated text in data.
        """

        text = params.get("text", "")
        source = params.get("source_lang", "auto")
        target = params.get("target_lang", "zh")
        provider = params.get("provider", "google")
        timeout = params.get("timeout", 30)

        try:
            if provider == "google":
                return await self._translate_google(text, source, target, timeout)
            else:
                return await self._translate_deepl(text, source, target, timeout)
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Translation failed: {e}",
            )

    async def _translate_google(
        self,
        text: str,
        source: str,
        target: str,
        timeout: int,
    ) -> ToolResult:
        """Translate text using the Google Translate free API.

        Args:
            text: Text to translate.
            source: Source language code or 'auto'.
            target: Target language code.
            timeout: Request timeout in seconds.

        Returns:
            ToolResult with translated text.
        """

        import urllib.parse

        encoded_text = urllib.parse.quote(text, safe="")
        url = GOOGLE_TRANSLATE_URL.format(source=source, target=target, text=encoded_text)

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            result = response.json()

        translated = ""
        if result and isinstance(result, list) and result[0]:
            for segment in result[0]:
                if segment and isinstance(segment, list) and segment[0]:
                    translated += segment[0]

        if not translated:
            return ToolResult(
                success=False,
                error="Google Translate returned an empty result",
            )

        return ToolResult(
            success=True,
            data={
                "translated_text": translated,
                "source_lang": source,
                "target_lang": target,
                "provider": "google",
            },
        )

    async def _translate_deepl(
        self,
        text: str,
        source: str,
        target: str,
        timeout: int,
    ) -> ToolResult:
        """Translate text using the DeepL API.

        Requires the DEEPL_API_KEY environment variable to be set.

        Args:
            text: Text to translate.
            source: Source language code or 'auto'.
            target: Target language code.
            timeout: Request timeout in seconds.

        Returns:
            ToolResult with translated text.
        """

        api_key = os.environ.get("DEEPL_API_KEY", "")
        payload: dict[str, Any] = {
            "text": [text],
            "target_lang": target.upper(),
        }
        if source and source != "auto":
            payload["source_lang"] = source.upper()

        headers = {
            "Authorization": f"DeepL-Auth-Key {api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(DEEPL_API_URL, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()

        translations = result.get("translations", [])
        if not translations:
            return ToolResult(
                success=False,
                error="DeepL returned an empty translation result",
            )

        translated = translations[0].get("text", "")
        detected = translations[0].get("detected_source_language", source)

        return ToolResult(
            success=True,
            data={
                "translated_text": translated,
                "source_lang": detected.lower(),
                "target_lang": target,
                "provider": "deepl",
            },
        )

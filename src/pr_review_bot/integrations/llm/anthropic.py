"""Anthropic Claude LLM provider — uses requests directly (no anthropic SDK)."""
import json
import logging
import requests
from typing import Dict
from .base import LLMProvider

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"


class AnthropicProvider(LLMProvider):
    """Anthropic Claude LLM provider."""

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.headers = {
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_API_VERSION,
            "content-type": "application/json",
        }
        logger.info(f"🤖 Initializing Anthropic provider: {model}")

    def _call(self, prompt: str, max_tokens: int = 4096) -> str:
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": 0.3,
            "messages": [{"role": "user", "content": prompt}],
        }
        response = requests.post(
            ANTHROPIC_API_URL, headers=self.headers, json=payload, timeout=120
        )
        response.raise_for_status()
        return response.json()["content"][0]["text"]

    def health_check(self) -> bool:
        try:
            self._call("test", max_tokens=10)
            return True
        except Exception as e:
            logger.warning(f"  ⚠ Anthropic health check failed: {e}")
            return False

    def review(self, guide: str, diff: str, pr_context: Dict) -> Dict:
        logger.info(f"🧠 Generating review with Claude ({self.model})")
        prompt = self._build_prompt(guide, diff, pr_context)
        try:
            response_text = self._call(prompt)
            logger.info(f"  ✓ Received response: {len(response_text)} chars")
            return self._parse_response(response_text)
        except Exception as e:
            logger.error(f"  ❌ Claude API error: {e}")
            return self._error_review(f"Error: {str(e)}")

    def _build_prompt(self, guide: str, diff: str, pr_context: Dict) -> str:
        title = pr_context.get("title", "")
        author = pr_context.get("author", "")
        current_file = pr_context.get("current_file")

        if current_file:
            context_desc = f"File: {current_file}"
        else:
            files_changed = pr_context.get("files_changed", 0)
            context_desc = f"PR: {title} by {author} ({files_changed} files)"

        return f"""Review this Django/Python code and find issues.

{context_desc}

GUIDELINES:
{guide}

CODE CHANGES:
{diff}

Return JSON with this structure:
{{
  "comments": [
    {{"path": "full/file/path.py", "line": 15, "body": "Issue description"}}
  ]
}}

RULES:
- "path": Full path from diff
- "line": Line number from NEW file (+ lines)
- Look for: soft-delete violations, multi-tenancy issues, migration problems, security issues
- Max 3 comments per file on critical issues only
- Empty array [] if no issues
"""

    def _parse_response(self, text: str) -> Dict:
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start == -1 or end == 0:
                logger.warning("  ⚠ No JSON found in response")
                return self._error_review("No valid JSON in LLM response")
            data = json.loads(text[start:end])
            if "comments" not in data:
                return {"event": "COMMENT", "summary": "", "comments": []}
            data.setdefault("event", "COMMENT")
            data.setdefault("summary", "")
            logger.info(f"  ✓ Parsed: {len(data.get('comments', []))} comments")
            return data
        except json.JSONDecodeError as e:
            logger.error(f"  ❌ JSON parse error: {e}")
            return {
                "event": "COMMENT",
                "summary": f"Review generated but JSON parsing failed: {text[:200]}...",
                "comments": [],
            }

    def _error_review(self, error_msg: str) -> Dict:
        return {
            "event": "COMMENT",
            "summary": f"⚠️ Review generation failed: {error_msg}",
            "comments": [],
        }

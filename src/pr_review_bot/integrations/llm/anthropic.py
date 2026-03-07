"""Anthropic Claude LLM provider."""
import anthropic
import json
import logging
from typing import Dict
from .base import LLMProvider

logger = logging.getLogger(__name__)


class AnthropicProvider(LLMProvider):
    """Anthropic Claude LLM provider."""
    
    def __init__(self, api_key: str, model: str):
        """Initialize Anthropic provider.
        
        Args:
            api_key: Anthropic API key
            model: Model name (e.g., claude-3-5-sonnet-20241022)
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        logger.info(f"🤖 Initializing Anthropic provider: {model}")
    
    def health_check(self) -> bool:
        """Check if Anthropic API is available."""
        try:
            # Try a minimal API call
            self.client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "test"}]
            )
            return True
        except Exception as e:
            logger.warning(f"  ⚠ Anthropic health check failed: {e}")
            return False
    
    def review(self, guide: str, diff: str, pr_context: Dict) -> Dict:
        """Generate code review using Claude.
        
        Args:
            guide: Review guidelines
            diff: PR diff
            pr_context: PR metadata
            
        Returns:
            Review dictionary
        """
        logger.info(f"🧠 Generating review with Claude ({self.model})")
        
        # Build prompt
        prompt = self._build_prompt(guide, diff, pr_context)
        
        try:
            # Call Claude API
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                temperature=0.3,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            response_text = response.content[0].text
            logger.info(f"  ✓ Received response: {len(response_text)} chars")
            
            # Parse JSON from response
            review_data = self._parse_response(response_text)
            return review_data
            
        except anthropic.APIError as e:
            logger.error(f"  ❌ Claude API error: {e}")
            return self._error_review(f"API Error: {str(e)}")
        except Exception as e:
            logger.error(f"  ❌ Unexpected error: {e}")
            return self._error_review(f"Error: {str(e)}")
    
    def _build_prompt(self, guide: str, diff: str, pr_context: Dict) -> str:
        """Build the review prompt with focus on critical rules."""
        title = pr_context.get("title", "")
        author = pr_context.get("author", "")
        current_file = pr_context.get("current_file")
        
        # Build context description
        if current_file:
            context_desc = f"File: {current_file}"
        else:
            files_changed = pr_context.get("files_changed", 0)
            context_desc = f"PR: {title} by {author} ({files_changed} files)"
        
        prompt = f"""Review this Django/Python code and find issues.

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
        return prompt
    
    def _parse_response(self, text: str) -> Dict:
        """Parse JSON from LLM response."""
        try:
            # Find JSON in response
            start = text.find("{")
            end = text.rfind("}") + 1
            
            if start == -1 or end == 0:
                logger.warning("  ⚠ No JSON found in response")
                return self._error_review("No valid JSON in LLM response")
            
            json_str = text[start:end]
            data = json.loads(json_str)
            
            # Handle both full review and file-level review formats
            if "comments" not in data:
                logger.warning("  ⚠ No comments field in response")
                return {"event": "COMMENT", "summary": "", "comments": []}
            
            # Ensure event and summary exist (for backward compatibility)
            if "event" not in data:
                data["event"] = "COMMENT"
            if "summary" not in data:
                data["summary"] = ""
            
            logger.info(f"  ✓ Parsed: {len(data.get('comments', []))} comments")
            return data
            
        except json.JSONDecodeError as e:
            logger.error(f"  ❌ JSON parse error: {e}")
            return {
                "event": "COMMENT",
                "summary": f"Review generated but JSON parsing failed: {text[:200]}...",
                "comments": []
            }
    
    def _error_review(self, error_msg: str) -> Dict:
        """Return an error review."""
        return {
            "event": "COMMENT",
            "summary": f"⚠️ Review generation failed: {error_msg}",
            "comments": []
        }

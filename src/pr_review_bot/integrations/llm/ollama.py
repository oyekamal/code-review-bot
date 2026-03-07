"""Ollama LLM provider."""
import requests
import json
import logging
from typing import Dict
from .base import LLMProvider

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """Ollama local LLM provider."""
    
    def __init__(self, base_url: str, model: str):
        """Initialize Ollama provider.
        
        Args:
            base_url: Ollama API base URL (e.g., http://localhost:11434)
            model: Model name (e.g., llama3.2)
        """
        self.base_url = base_url.rstrip('/')
        self.model = model
        logger.info(f"🤖 Initializing Ollama provider: {model} at {base_url}")
    
    def health_check(self) -> bool:
        """Check if Ollama is available."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"  ⚠ Ollama health check failed: {e}")
            return False
    
    def review(self, guide: str, diff: str, pr_context: Dict) -> Dict:
        """Generate code review using Ollama.
        
        Args:
            guide: Review guidelines
            diff: PR diff
            pr_context: PR metadata
            
        Returns:
            Review dictionary
        """
        logger.info(f"🧠 Generating review with Ollama ({self.model})")
        
        # Build prompt
        prompt = self._build_prompt(guide, diff, pr_context)
        
        try:
            # Call Ollama API with JSON format enforcement
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",  # Force valid JSON output
                    "options": {
                        "temperature": 0.3,  # Lower temperature for more consistent output
                        "num_predict": 2048,  # Max tokens
                    }
                },
                timeout=180  # 3 minutes max
            )
            response.raise_for_status()
            
            result = response.json()
            response_text = result.get("response", "")
            
            logger.info(f"  ✓ Received response: {len(response_text)} chars")
            
            # Parse JSON from response
            review_data = self._parse_response(response_text)
            return review_data
            
        except requests.exceptions.Timeout:
            logger.error("  ❌ Ollama request timed out")
            return self._error_review("Request timed out after 3 minutes")
        except Exception as e:
            logger.error(f"  ❌ Ollama error: {e}")
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
            # Try to extract any useful text
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

"""Base LLM provider interface."""
from abc import ABC, abstractmethod
from typing import Dict


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    def review(self, guide: str, diff: str, pr_context: Dict) -> Dict:
        """Generate a code review.
        
        Args:
            guide: Review guidelines/prompts
            diff: PR diff content
            pr_context: PR metadata (title, description, files, etc.)
            
        Returns:
            Review dictionary with 'event', 'summary', 'comments'
        """
        pass
    
    @abstractmethod
    def health_check(self) -> bool:
        """Check if the LLM provider is available.
        
        Returns:
            True if available, False otherwise
        """
        pass

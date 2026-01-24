"""
Bank detection module - dynamically detect bank from document content.

Following prompt requirement: absolute avoidance of hardcoding,
dynamic adaptation to document variations.
"""
from typing import Any, Dict, Optional
import re

from src.config import config


class BankDetector:
    """Detect bank from document content."""
    
    def __init__(self):
        """Initialize bank detector."""
        self.bank_profiles = config.get('bank_profiles', {})
        self.default_profile = config.get('default_bank_profile', 'bbva_mexico')
    
    def detect_bank(
        self,
        ocr_data: Dict[str, Any],
        structured_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Detect bank from document content.
        
        Args:
            ocr_data: OCR data from document
            structured_data: Optional structured data
            
        Returns:
            Bank profile key (e.g., 'bbva_mexico')
        """
        # Extract document text
        document_text = self._extract_document_text(ocr_data)
        
        # Score each bank profile
        scores = {}
        for profile_key, profile_config in self.bank_profiles.items():
            score = self._calculate_match_score(document_text, profile_config)
            scores[profile_key] = score
        
        # Return highest scoring profile, or default if no clear match
        if scores:
            best_match = max(scores, key=scores.get)
            if scores[best_match] > 3:  # Threshold
                return best_match
        
        return self.default_profile
    
    def _extract_document_text(self, ocr_data: Dict[str, Any]) -> str:
        """Extract all text from OCR data."""
        text_parts = []
        for page_data in ocr_data.get("pages", []):
            for block in page_data.get("text_blocks", []):
                text = block.get("text", "")
                if text:
                    text_parts.append(text)
        return " ".join(text_parts).lower()
    
    def _calculate_match_score(self, document_text: str, profile_config: Dict[str, Any]) -> int:
        """Calculate match score for a bank profile."""
        score = 0
        
        # Check for bank name
        bank_name = profile_config.get('name', '').lower()
        if bank_name in document_text:
            score += 10
        
        # Check for language-specific keywords
        skip_keywords = profile_config.get('skip_keywords', [])
        for keyword in skip_keywords[:5]:  # Check first 5
            if keyword.lower() in document_text:
                score += 1
        
        # Check for header keywords
        header_keywords = profile_config.get('header_keywords', [])
        for keyword in header_keywords:
            if keyword.lower() in document_text:
                score += 2
        
        # Check for transaction keywords
        transaction_keywords = profile_config.get('transaction_keywords', {})
        for category, keywords in transaction_keywords.items():
            for keyword in keywords[:3]:  # Check first 3
                if keyword.lower() in document_text:
                    score += 1
        
        return score
    
    def get_bank_config(self, bank_profile: Optional[str] = None) -> Dict[str, Any]:
        """
        Get bank configuration.
        
        Args:
            bank_profile: Bank profile key. If None, use default.
            
        Returns:
            Bank configuration dictionary
        """
        if bank_profile is None:
            bank_profile = self.default_profile
        
        return self.bank_profiles.get(bank_profile, self.bank_profiles.get(self.default_profile, {}))


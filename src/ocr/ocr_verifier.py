"""OCR verification with dual verification and LLM validation."""
from typing import Any, Dict, List, Optional

from src.config import config


class OCRVerifier:
    """Verify OCR results using dual verification and LLM."""
    
    def __init__(self):
        """Initialize OCR verifier."""
        self.enable_dual_verification = config.get(
            'ocr.dual_verification_enabled', True
        )
        self.confidence_threshold = config.ocr_confidence_threshold
    
    def validate_critical_fields(
        self, 
        critical_fields: Dict[str, Any],
        llm_client: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Validate critical fields using LLM.
        
        Args:
            critical_fields: Dictionary of critical fields to validate
            llm_client: Optional LLM client for semantic validation
            
        Returns:
            Validated fields with confidence scores
        """
        validated_fields = {
            "account_numbers": [],
            "amounts": [],
            "dates": [],
            "balances": []
        }
        
        # Basic validation (without LLM)
        for field_type, fields in critical_fields.items():
            for field in fields:
                validated = self._validate_field(field, field_type)
                if validated:
                    validated_fields[field_type].append(validated)
        
        # LLM validation if available
        if llm_client:
            validated_fields = self._llm_validate(
                validated_fields, 
                llm_client
            )
        
        return validated_fields
    
    def _validate_field(
        self, 
        field: Dict[str, Any], 
        field_type: str
    ) -> Optional[Dict[str, Any]]:
        """Basic field validation."""
        value = field.get("value", "")
        
        if field_type == "account_numbers":
            # Validate account number format (from config, not hardcoded)
            import re
            # Get account pattern from bank config
            bank_profile = config.get('default_bank_profile', 'bbva_mexico')
            bank_profiles = config.get('bank_profiles', {})
            bank_config = bank_profiles.get(bank_profile, {})
            pattern = bank_config.get('account_number_pattern', r'^[0-9]{10,18}$')
            
            # Fallback pattern if not found in bank_profiles
            if not pattern:
                pattern = r'^[0-9]{10,18}$'  # Generic account number pattern
            if re.match(pattern, value.replace("-", "").replace(" ", "")):
                return {
                    **field,
                    "validated": True,
                    "confidence": 0.9
                }
        
        elif field_type == "amounts":
            # Validate amount format (using config, not hardcoded)
            # Get currency format from config
            bank_profile = config.get('default_bank_profile', 'bbva_mexico')
            bank_profiles = config.get('bank_profiles', {})
            bank_config = bank_profiles.get(bank_profile, {})
            
            currency_format = bank_config.get('currency_format', {})
            currency_symbol = bank_config.get('currency_symbol', '$')
            
            # Build flexible amount pattern
            currency_symbols = [currency_symbol, '$', '€', '£', '¥', '₹']
            currency_symbols_str = ''.join(set(currency_symbols))
            amount_pattern = f'^[{currency_symbols_str}]?\\s*[\\d,]+\.?\\d*$'
            
            import re
            if re.match(amount_pattern, value):
                return {
                    **field,
                    "validated": True,
                    "confidence": 0.85
                }
        
        elif field_type == "dates":
            # Validate date format
            from datetime import datetime
            date_formats = ["%d/%m/%Y", "%d/%m/%y", "%d/%m"]
            for fmt in date_formats:
                try:
                    datetime.strptime(value, fmt)
                    return {
                        **field,
                        "validated": True,
                        "confidence": 0.9
                    }
                except ValueError:
                    continue
        
        return None
    
    def _llm_validate(
        self, 
        fields: Dict[str, Any], 
        llm_client: Any
    ) -> Dict[str, Any]:
        """
        Use LLM to validate and correct fields.
        
        Args:
            fields: Fields to validate
            llm_client: LLM client instance
            
        Returns:
            LLM-validated fields
        """
        # Build prompt for LLM
        prompt = self._build_validation_prompt(fields)
        
        try:
            response = llm_client.validate_fields(prompt, fields)
            # Process LLM response and update fields
            # This is a placeholder - actual implementation depends on
            # your LLM client interface
            return response
        except Exception as e:
            print(f"LLM validation failed: {e}. Using basic validation.")
            return fields
    
    def _build_validation_prompt(
        self, 
        fields: Dict[str, Any]
    ) -> str:
        """Build prompt for LLM validation."""
        prompt = """你是一名银行文档专家，请校正以下银行文档中的关键数据。

请验证并校正以下字段：
"""
        for field_type, field_list in fields.items():
            prompt += f"\n{field_type}:\n"
            for field in field_list[:5]:  # Limit for prompt size
                prompt += f"  - {field.get('value')} (位置: {field.get('bbox')})\n"
        
        prompt += """
请：
1. 验证每个字段是否符合银行文档格式
2. 校正任何明显的OCR错误
3. 提供置信度评分（0-1）
4. 如果字段不确定，标记为需要人工复核

返回JSON格式的验证结果。
"""
        return prompt
    
    def compare_ocr_results(
        self, 
        primary_result: Dict[str, Any],
        secondary_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compare results from two OCR engines.
        
        Args:
            primary_result: Primary OCR result (MinerU)
            secondary_result: Secondary OCR result (fallback)
            
        Returns:
            Comparison report
        """
        discrepancies = []
        matches = 0
        total = 0
        
        # Compare text blocks (simplified comparison)
        primary_blocks = self._extract_text_blocks(primary_result)
        secondary_blocks = self._extract_text_blocks(secondary_result)
        
        # Simple text comparison
        primary_text = " ".join(primary_blocks)
        secondary_text = " ".join(secondary_blocks)
        
        # Calculate similarity
        similarity = self._text_similarity(primary_text, secondary_text)
        
        return {
            "similarity": similarity,
            "discrepancies": discrepancies,
            "matches": matches,
            "total": total,
            "recommendation": "use_primary" if similarity > 0.9 else "review"
        }
    
    def _extract_text_blocks(self, ocr_result: Dict[str, Any]) -> List[str]:
        """Extract all text blocks from OCR result."""
        texts = []
        for page in ocr_result.get("pages", []):
            for block in page.get("text_blocks", []):
                texts.append(block.get("text", ""))
        return texts
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calculate simple text similarity."""
        from difflib import SequenceMatcher
        return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()


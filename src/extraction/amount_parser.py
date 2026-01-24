"""
Currency amount parsing utility - generic and configurable.

Following prompt requirement: absolute avoidance of hardcoding,
use bank configuration for currency formatting.
"""
import re
from decimal import Decimal
from typing import Any, Dict, Optional


def parse_amount(
    amount_text: str,
    bank_config: Optional[Dict[str, Any]] = None
) -> Optional[Decimal]:
    """
    Parse amount from text using bank configuration.
    
    Args:
        amount_text: Text containing amount
        bank_config: Optional bank configuration dictionary
        
    Returns:
        Parsed amount as Decimal, or None if parsing fails
    """
    if not amount_text:
        return None
    
    # Get currency format from bank config
    currency_format = bank_config.get('currency_format', {}) if bank_config else {}
    currency_symbol = bank_config.get('currency_symbol', '$') if bank_config else '$'
    currency_code = bank_config.get('currency', 'USD') if bank_config else 'USD'
    
    # Build currency symbols regex (support multiple common symbols)
    currency_symbols = [currency_symbol, '$', '€', '£', '¥', '₹']
    currency_symbols_str = ''.join(set(currency_symbols))  # Remove duplicates
    
    # Remove currency symbols and whitespace
    cleaned = re.sub(f'[{currency_symbols_str}\\s]', '', str(amount_text))
    
    # Handle decimal/thousands separators (from bank config)
    thousands_sep = currency_format.get('thousands_separator', ',')
    decimal_sep = currency_format.get('decimal_separator', '.')
    
    if thousands_sep in cleaned or decimal_sep in cleaned:
        # Remove thousands separator if present
        if thousands_sep in cleaned:
            cleaned = cleaned.replace(thousands_sep, '')
        
        # Normalize decimal separator to '.'
        if decimal_sep != '.' and decimal_sep in cleaned:
            cleaned = cleaned.replace(decimal_sep, '.')
    
    try:
        return Decimal(cleaned)
    except (ValueError, Exception):
        return None


def extract_amount_pattern(
    text: str,
    bank_config: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """
    Extract amount pattern from text using bank configuration.
    
    Args:
        text: Text to search for amount
        bank_config: Optional bank configuration dictionary
        
    Returns:
        Amount string if found, None otherwise
    """
    if not text:
        return None
    
    currency_format = bank_config.get('currency_format', {}) if bank_config else {}
    thousands_sep = currency_format.get('thousands_separator', ',')
    decimal_sep = currency_format.get('decimal_separator', '.')
    
    # Build pattern based on separators
    if thousands_sep == ',' and decimal_sep == '.':
        # Standard: 1,234.56
        pattern = r'([\d,]+\.\d{2})'
    elif thousands_sep == '.' and decimal_sep == ',':
        # European: 1.234,56
        pattern = r'([\d.]+,\d{2})'
    else:
        # Fallback: flexible pattern
        pattern = r'([\d,' + re.escape(thousands_sep) + r']+' + re.escape(decimal_sep) + r'\d{2})'
    
    match = re.search(pattern, text)
    if match:
        return match.group(1)
    return None


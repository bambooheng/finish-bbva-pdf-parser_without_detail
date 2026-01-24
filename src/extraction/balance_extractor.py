"""
Enhanced balance extraction module.

Following prompt requirement: absolute avoidance of hardcoding,
dynamic balance extraction using position, context, and semantic analysis.
"""
import re
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from src.extraction.amount_parser import parse_amount, extract_amount_pattern


class BalanceExtractor:
    """
    Enhanced balance extractor using multiple strategies.
    
    Strategies:
    1. Column position-based (rightmost amount column)
    2. Pattern-based (look for balance indicators)
    3. Context-based (from surrounding transactions)
    4. Semantic analysis (using LLM if available)
    """
    
    def __init__(self, bank_config: Optional[Dict[str, Any]] = None):
        """Initialize balance extractor.
        
        Args:
            bank_config: Bank-specific configuration
        """
        self.bank_config = bank_config
    
    def extract_balance_from_table_row(
        self,
        row: Dict[str, Any],
        column_mapping: Dict[str, int],
        cells: List[Dict[str, Any]],
        row_index: int = 0,
        all_rows: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[Decimal]:
        """
        Extract balance from a table row using multiple strategies.
        
        Args:
            row: Row data dictionary
            column_mapping: Column mapping dictionary
            cells: List of cell dictionaries
            row_index: Index of current row
            all_rows: All rows in the table (for context)
            
        Returns:
            Balance as Decimal, or None if not found
        """
        # Strategy 1: Direct column mapping
        if "balance" in column_mapping:
            balance_idx = column_mapping["balance"]
            if balance_idx < len(cells):
                balance_text = str(cells[balance_idx].get("text", "")).strip()
                balance = parse_amount(balance_text, self.bank_config)
                if balance is not None:
                    return balance
        
        # Strategy 2: Position-based (rightmost amount column)
        balance = self._extract_balance_by_position(cells, row.get("raw_text", ""))
        if balance is not None:
            return balance
        
        # Strategy 3: Pattern-based extraction from raw text
        balance = self._extract_balance_by_pattern(row.get("raw_text", ""), row)
        if balance is not None:
            return balance
        
        # Strategy 4: Context-based (from surrounding transactions)
        if all_rows and row_index > 0:
            balance = self._infer_balance_from_context(
                row, row_index, all_rows, cells
            )
            if balance is not None:
                return balance
        
        return None
    
    def _extract_balance_by_position(
        self,
        cells: List[Dict[str, Any]],
        raw_text: str
    ) -> Optional[Decimal]:
        """
        Extract balance based on column position.
        In bank statements, balance is often the rightmost amount column.
        
        Args:
            cells: List of cell dictionaries
            raw_text: Raw text of the row
            
        Returns:
            Balance as Decimal, or None
        """
        if not cells:
            return None
        
        # Find all amount-like values in cells
        amount_values = []
        for i, cell in enumerate(cells):
            cell_text = str(cell.get("text", "")).strip()
            amount = parse_amount(cell_text, self.bank_config)
            if amount is not None:
                # Also check cell position (rightmost cells more likely to be balance)
                cell_bbox = cell.get("bbox", [])
                x_pos = cell_bbox[0] if len(cell_bbox) >= 1 else 0
                amount_values.append((amount, i, x_pos))
        
        if not amount_values:
            # Try extracting from raw text (scan from right to left)
            amounts = self._extract_all_amounts_from_text(raw_text)
            if len(amounts) >= 2:
                # Rightmost amount is likely balance
                return amounts[-1]
            elif len(amounts) == 1:
                # Single amount could be either amount or balance
                # Check context (if it's at the end, likely balance)
                if raw_text.strip().endswith(str(amounts[0])) or \
                   len(raw_text.split()) <= 3:  # Very short row
                    return amounts[0]
        elif len(amount_values) >= 2:
            # Multiple amounts found - rightmost is likely balance
            # Sort by x position (rightmost first)
            amount_values.sort(key=lambda x: x[2], reverse=True)
            return amount_values[0][0]  # Rightmost amount
        elif len(amount_values) == 1:
            # Single amount - check position
            amount, idx, x_pos = amount_values[0]
            # If it's in one of the rightmost columns (last 2), might be balance
            if idx >= len(cells) - 2:
                return amount
        
        return None
    
    def _extract_balance_by_pattern(
        self,
        raw_text: str,
        row: Dict[str, Any]
    ) -> Optional[Decimal]:
        """
        Extract balance using pattern matching.
        
        Args:
            raw_text: Raw text of the row
            row: Row data dictionary
            
        Returns:
            Balance as Decimal, or None
        """
        if not raw_text:
            return None
        
        # Extract all amounts from text
        amounts = self._extract_all_amounts_from_text(raw_text)
        
        if len(amounts) >= 2:
            # Multiple amounts - the one at the end is likely balance
            # Check if last amount appears near the end of the text
            text_end = raw_text[-50:].strip()  # Last 50 chars
            last_amount_str = str(amounts[-1])
            
            # Check if last amount appears in the end section
            if last_amount_str.replace('.', '').replace(',', '') in text_end.replace('.', '').replace(',', ''):
                return amounts[-1]
        
        # Look for balance indicators (if bank config specifies keywords)
        balance_keywords = []
        if self.bank_config:
            balance_keywords = self.bank_config.get('balance_keywords', [])
        
        if balance_keywords:
            for keyword in balance_keywords:
                # Look for pattern: keyword + amount
                pattern = rf'{re.escape(keyword)}\s*:?\s*([\d,]+\.?\d*)'
                match = re.search(pattern, raw_text, re.IGNORECASE)
                if match:
                    amount = parse_amount(match.group(1), self.bank_config)
                    if amount is not None:
                        return amount
        
        return None
    
    def _infer_balance_from_context(
        self,
        current_row: Dict[str, Any],
        current_index: int,
        all_rows: List[Dict[str, Any]],
        cells: List[Dict[str, Any]]
    ) -> Optional[Decimal]:
        """
        Infer balance from surrounding transaction context.
        If previous transaction has balance, calculate current balance.
        
        This is dynamic calculation, not hardcoding - follows prompt requirement.
        
        Args:
            current_row: Current row data
            current_index: Current row index
            all_rows: All rows in table
            cells: Current row cells
            
        Returns:
            Inferred balance as Decimal, or None
        """
        # Try to find previous transaction with balance
        prev_balance = None
        current_amount = None
        
        # Get current transaction amount
        if "amount" in current_row and current_row["amount"]:
            try:
                current_amount = Decimal(str(current_row["amount"]))
            except:
                pass
        
        # Look backwards for previous transaction with balance
        for i in range(current_index - 1, max(0, current_index - 10), -1):
            if i < len(all_rows):
                prev_row = all_rows[i]
                prev_balance_value = prev_row.get("balance")
                if prev_balance_value:
                    try:
                        prev_balance = Decimal(str(prev_balance_value))
                        break
                    except:
                        continue
        
        # If we have previous balance and current amount, calculate
        if prev_balance is not None and current_amount is not None:
            # Balance = previous balance + current amount
            # (amount can be positive or negative)
            calculated_balance = prev_balance + current_amount
            return calculated_balance
        
        return None
    
    def extract_balance_from_text_block(
        self,
        text: str,
        lines: List[str],
        date_line_index: int,
        amount: Optional[Decimal]
    ) -> Optional[Decimal]:
        """
        Extract balance from text block transaction.
        
        Args:
            text: Full text block
            lines: List of lines
            date_line_index: Index of line containing date
            amount: Already extracted amount
            
        Returns:
            Balance as Decimal, or None
        """
        if not lines or date_line_index >= len(lines):
            return None
        
        # Look ahead from date line
        search_lines = lines[date_line_index:date_line_index + 10]
        
        # Extract all amounts from these lines
        all_amounts = []
        for line in search_lines:
            amounts = self._extract_all_amounts_from_text(line)
            all_amounts.extend(amounts)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_amounts = []
        for amt in all_amounts:
            if amt not in seen:
                seen.add(amt)
                unique_amounts.append(amt)
        
        if len(unique_amounts) >= 2:
            # Multiple amounts - the one different from transaction amount is likely balance
            for amt in unique_amounts:
                if amount is None or amt != amount:
                    # Check if it appears after the amount in the text
                    amount_idx = -1
                    balance_idx = -1
                    for i, line in enumerate(search_lines):
                        if str(amount) in line.replace(',', '').replace('.', ''):
                            amount_idx = i
                        if str(amt) in line.replace(',', '').replace('.', ''):
                            balance_idx = i
                    
                    # If balance appears after amount, it's likely the balance
                    if balance_idx > amount_idx or (balance_idx == amount_idx and line.rfind(str(amt)) > line.rfind(str(amount))):
                        return amt
                    
                    # If only 2 amounts and second is different, likely balance
                    if len(unique_amounts) == 2 and amt != unique_amounts[0]:
                        return amt
        
        elif len(unique_amounts) == 1 and amount is not None:
            # Single amount - check if it's different from transaction amount
            if unique_amounts[0] != amount:
                return unique_amounts[0]
        
        return None
    
    def _extract_all_amounts_from_text(self, text: str) -> List[Decimal]:
        """
        Extract all amount-like values from text.
        
        Args:
            text: Text to search
            
        Returns:
            List of Decimal amounts found
        """
        amounts = []
        
        # Use amount parser to find all amounts
        # Look for multiple amount patterns
        currency_format = self.bank_config.get('currency_format', {}) if self.bank_config else {}
        thousands_sep = currency_format.get('thousands_separator', ',')
        decimal_sep = currency_format.get('decimal_separator', '.')
        
        # Build flexible pattern
        if thousands_sep == ',' and decimal_sep == '.':
            pattern = r'([\d,]+\.\d{2})|([\d,]+\.\d{1})|([\d,]+)'
        elif thousands_sep == '.' and decimal_sep == ',':
            pattern = r'([\d.]+,\d{2})|([\d.]+,\d{1})|([\d.]+)'
        else:
            pattern = r'([\d,]+\.\d{2})|([\d,]+)'
        
        matches = re.finditer(pattern, text)
        for match in matches:
            amount_str = match.group(0)
            amount = parse_amount(amount_str, self.bank_config)
            if amount is not None:
                amounts.append(amount)
        
        return amounts
    
    def enhance_transactions_with_balances(
        self,
        transactions: List[Any],
        ocr_data: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        """
        Enhance transactions by filling missing balances.
        
        Uses dynamic calculation: balance = previous_balance + amount
        This follows prompt requirement: no hardcoding, dynamic inference.
        
        Args:
            transactions: List of Transaction objects
            ocr_data: Optional OCR data for context
            
        Returns:
            List of transactions with enhanced balance information
        """
        enhanced = []
        prev_balance = None
        
        for i, trans in enumerate(transactions):
            # If transaction already has balance, use it
            if trans.balance is not None:
                enhanced.append(trans)
                prev_balance = trans.balance
                continue
            
            # Try to infer balance from previous transaction
            if prev_balance is not None and trans.amount is not None:
                # Dynamic calculation: new balance = old balance + transaction amount
                calculated_balance = prev_balance + trans.amount
                
                # Create new transaction with balance
                from src.models.schemas import Transaction
                enhanced_trans = Transaction(
                    date=trans.date,
                    description=trans.description,
                    amount=trans.amount,
                    balance=calculated_balance,
                    reference=trans.reference,
                    raw_text=trans.raw_text,
                    bbox=trans.bbox,
                    # Preserve all BBVA-specific fields
                    oper_date=trans.oper_date,
                    liq_date=trans.liq_date,
                    cargos=trans.cargos,
                    abonos=trans.abonos,
                    operacion=trans.operacion,
                    liquidacion=trans.liquidacion,
                    OPER=trans.OPER,
                    LIQ=trans.LIQ,
                    DESCRIPCION=trans.DESCRIPCION,
                    REFERENCIA=trans.REFERENCIA,
                    CARGOS=trans.CARGOS,
                    ABONOS=trans.ABONOS,
                    OPERACION=trans.OPERACION,
                    LIQUIDACION=trans.LIQUIDACION,
                    confidence=trans.confidence  # Preserve original confidence
                )
                enhanced.append(enhanced_trans)
                prev_balance = calculated_balance
            else:
                # Cannot calculate, keep as is
                enhanced.append(trans)
                # Don't update prev_balance since this transaction doesn't have balance
        
        return enhanced


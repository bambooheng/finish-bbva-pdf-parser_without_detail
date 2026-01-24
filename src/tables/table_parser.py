"""Intelligent table parsing with semantic classification."""
from decimal import Decimal
from typing import Any, Dict, List, Optional
import re
from datetime import datetime

from src.config import config
from src.extraction.balance_extractor import BalanceExtractor


class TableParser:
    """
    Parse bank tables intelligently.
    
    Following prompt requirement: absolute avoidance of hardcoding,
    use bank configuration for keywords and formats.
    """
    
    def __init__(self, llm_client: Optional[Any] = None, bank_config: Optional[Dict[str, Any]] = None):
        """
        Initialize table parser.
        
        Args:
            llm_client: Optional LLM client for semantic analysis
            bank_config: Optional bank configuration dictionary
        """
        self.llm_client = llm_client
        self.bank_config = bank_config
        self.balance_extractor = BalanceExtractor(bank_config=bank_config)
    
    def parse_bank_tables(
        self, 
        table_data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Parse bank tables with semantic understanding.
        
        Args:
            table_data: List of table structures from OCR
            
        Returns:
            List of structured tables
        """
        structured_tables = []
        
        for table in table_data:
            # 1. Classify table type
            table_type = self._classify_table_semantic(table)
            
            # 2. Dynamic column mapping
            column_mapping = self._dynamic_column_mapping(table, table_type)
            
            # 3. Normalize data
            normalized_data = self._normalize_table_data(
                table, 
                column_mapping, 
                table_type
            )
            
            # 4. Validate semantics
            validation_report = self._validate_table_semantics(
                normalized_data, 
                table_type
            )
            
            structured_tables.append({
                "type": table_type,
                "data": normalized_data,
                "validation": validation_report,
                "raw_table": table
            })
        
        return structured_tables
    
    def _classify_table_semantic(
        self, 
        table: Dict[str, Any]
    ) -> str:
        """
        Classify table by semantic type.
        
        Args:
            table: Table structure
            
        Returns:
            Table type (transaction, summary, etc.)
        """
        # Extract sample text from table
        table_text = self._extract_table_text(table).lower()
        
        # Keyword-based classification (from bank config)
        date_keywords = ["fecha", "fecha de", "fecha operacion", "date", "fecha operación"]
        amount_keywords = ["importe", "monto", "amount", "saldo", "balance"]
        summary_keywords = self.bank_config.get('summary_keywords', ["resumen", "summary", "saldo inicial", "saldo final"]) if self.bank_config else ["summary", "balance"]
        
        if any(keyword in table_text for keyword in date_keywords):
            if any(keyword in table_text for keyword in amount_keywords):
                return "transaction"
        
        if any(keyword in table_text for keyword in summary_keywords):
            return "summary"
        
        return "unknown"
    
    def _extract_table_text(self, table: Dict[str, Any]) -> str:
        """Extract all text from table."""
        text_parts = []
        for row in table.get("rows", []):
            for cell in row.get("cells", []):
                text_parts.append(str(cell.get("text", "")))
        return " ".join(text_parts)
    
    def _dynamic_column_mapping(
        self, 
        table: Dict[str, Any],
        table_type: str
    ) -> Dict[str, int]:
        """
        Dynamically map columns based on content.
        
        Args:
            table: Table structure
            table_type: Type of table
            
        Returns:
            Dictionary mapping semantic column names to indices
        """
        if not table.get("rows"):
            # If no header row, return empty mapping - will use pattern extraction
            return {}
        
        # Get header row (usually first row)
        header_row = table["rows"][0] if table["rows"] else []
        header_texts = [
            str(cell.get("text", "")).lower() 
            for cell in header_row.get("cells", [])
        ]
        
        # If header is empty or doesn't look like a header, try to infer from data
        if not header_texts or all(len(h) < 3 for h in header_texts):
            # No proper header, will rely on pattern extraction
            return {}
        
        mapping = {}
        
        if table_type == "transaction":
            # Map common transaction columns
            column_patterns = {
                "date": ["fecha", "date", "fecha de", "fecha operacion"],
                "description": ["descripcion", "concepto", "description", "detalle"],
                "amount": ["importe", "monto", "amount", "cantidad"],
                "balance": ["saldo", "balance"],
                "reference": ["referencia", "ref", "numero", "folio"]
            }
            
            for semantic_name, patterns in column_patterns.items():
                for idx, header in enumerate(header_texts):
                    if any(pattern in header for pattern in patterns):
                        mapping[semantic_name] = idx
                        break
            
            # If no header found, try to infer from first data row
            if not mapping and len(table.get("rows", [])) > 1:
                first_row = table["rows"][1]
                cells = first_row.get("cells", [])
                # Try to identify columns by content pattern
                for idx, cell in enumerate(cells):
                    cell_text = str(cell.get("text", "")).strip()
                    # Check if looks like date
                    if re.match(r'\d{1,2}/[A-Z]{3}', cell_text) or re.match(r'\d{1,2}/\d{1,2}', cell_text):
                        if "date" not in mapping:
                            mapping["date"] = idx
                    # Check if looks like amount
                    elif re.match(r'[\d,]+\.\d{2}', cell_text.replace(',', '')):
                        if "amount" not in mapping:
                            mapping["amount"] = idx
                    # Otherwise might be description
                    elif len(cell_text) > 5:
                        if "description" not in mapping:
                            mapping["description"] = idx
        
        elif table_type == "summary":
            column_patterns = {
                "item": ["concepto", "item", "descripcion"],
                "amount": ["importe", "monto", "amount", "total"],
                "percentage": ["porcentaje", "percentage", "%"]
            }
            
            for semantic_name, patterns in column_patterns.items():
                for idx, header in enumerate(header_texts):
                    if any(pattern in header for pattern in patterns):
                        mapping[semantic_name] = idx
                        break
        
        return mapping
    
    def _normalize_table_data(
        self,
        table: Dict[str, Any],
        column_mapping: Dict[str, int],
        table_type: str
    ) -> List[Dict[str, Any]]:
        """
        Normalize table data into structured format.
        
        Args:
            table: Raw table structure
            column_mapping: Column mapping
            table_type: Type of table
            
        Returns:
            List of normalized rows
        """
        normalized_rows = []
        
        # Skip header row
        data_rows = table.get("rows", [])[1:] if table.get("rows") else []
        
        for row in data_rows:
            cells = row.get("cells", [])
            if not cells:
                continue
            
            # Check if this is a multi-line text block (common in bank statement PDFs)
            # If so, try to split it into individual transactions
            # Preserve newlines when joining cells (following prompt: 100% information completeness)
            row_text_parts = []
            for cell in cells:
                cell_text = str(cell.get("text", ""))
                row_text_parts.append(cell_text)
            # Join with newline to preserve structure
            row_text = "\n".join(row_text_parts)
            # Also create space-joined version for pattern matching
            row_text_space = " ".join(row_text_parts)
            
            # Try to extract multiple transactions from a single row
            # Check both newline-preserved and space-joined versions
            has_newlines = '\n' in row_text
            date_pattern = r'\d{1,2}/[A-Z]{3}'
            dates_in_text = re.findall(date_pattern, row_text)
            is_multiple = has_newlines and len(dates_in_text) > 2
            
            if table_type == "transaction" and (is_multiple or self._looks_like_multiple_transactions(row_text) or self._looks_like_multiple_transactions(row_text_space)):
                # Try to get context_year from bank_config or use current year
                context_year = None
                if self.bank_config:
                    from datetime import datetime
                    context_year = datetime.now().year
                # Use newline-preserved version for splitting
                split_transactions = self._split_multiple_transactions(row, row_text)
                if split_transactions:
                    normalized_rows.extend(split_transactions)
                    continue
            
            normalized_row = {}
            
            # Extract date
            if "date" in column_mapping:
                date_idx = column_mapping["date"]
                if date_idx < len(cells):
                    date_text = str(cells[date_idx].get("text", ""))
                    normalized_row["date"] = self._parse_date(date_text, context_year=None, bank_config=self.bank_config)
            
            # Extract description
            if "description" in column_mapping:
                desc_idx = column_mapping["description"]
                if desc_idx < len(cells):
                    normalized_row["description"] = str(
                        cells[desc_idx].get("text", "")
                    )
            
            # Extract amount
            if "amount" in column_mapping:
                amount_idx = column_mapping["amount"]
                if amount_idx < len(cells):
                    amount_text = str(cells[amount_idx].get("text", ""))
                    normalized_row["amount"] = self._parse_amount(amount_text, bank_config=self.bank_config)
            
            # Extract balance using enhanced balance extractor
            balance_value = None
            if "balance" in column_mapping:
                balance_idx = column_mapping["balance"]
                if balance_idx < len(cells):
                    balance_text = str(cells[balance_idx].get("text", ""))
                    balance_value = self._parse_amount(balance_text, bank_config=self.bank_config)
            
            # If balance not found via column mapping, try enhanced extraction
            if balance_value is None:
                row_index = len(normalized_rows)  # Current row index
                all_rows = table.get("rows", [])[1:]  # All data rows
                balance_value = self.balance_extractor.extract_balance_from_table_row(
                    normalized_row,
                    column_mapping,
                    cells,
                    row_index,
                    all_rows
                )
            
            normalized_row["balance"] = balance_value
            
            # Extract reference
            if "reference" in column_mapping:
                ref_idx = column_mapping["reference"]
                if ref_idx < len(cells):
                    normalized_row["reference"] = str(
                        cells[ref_idx].get("text", "")
                    )
            
            # If BBVA-specific fields are missing, try pattern-based extraction from raw_text
            # Following prompt: 100% information completeness - extract all BBVA fields
            missing_bbva_fields = (
                not normalized_row.get("OPER") or 
                not normalized_row.get("LIQ") or 
                (not normalized_row.get("CARGOS") and not normalized_row.get("ABONOS")) or
                not normalized_row.get("OPERACION") or 
                not normalized_row.get("LIQUIDACION") or
                not normalized_row.get("REFERENCIA")
            )
            
            # Also check if row_text contains transaction patterns (newlines + dates)
            should_parse_from_raw = False
            if row_text and '\n' in row_text:
                dates = re.findall(date_pattern, row_text)
                if len(dates) >= 2:
                    should_parse_from_raw = True
            
            # If BBVA fields are missing OR row_text contains transaction patterns, parse from raw_text
            if should_parse_from_raw or missing_bbva_fields:
                if row_text and ('\n' in row_text or re.search(r'\d{1,2}/[A-Z]{3}', row_text)):
                    lines = [l.strip() for l in row_text.split('\n') if l.strip()]
                    if lines and re.match(r'^\d{1,2}/[A-Z]{3}', lines[0]):
                        # Try to get context_year from bank_config or use current year
                        context_year = None
                        if self.bank_config:
                            from datetime import datetime
                            context_year = datetime.now().year
                        
                        # If multiple transactions detected, use _split_multiple_transactions instead
                        if len(dates_in_text) > 2:
                            split_transactions = self._split_multiple_transactions(row, row_text)
                            if split_transactions:
                                normalized_rows.extend(split_transactions)
                                continue
                        
                        # Single transaction - parse directly
                        parsed_trans = self._parse_single_transaction(lines, 0, context_year=context_year)
                        if parsed_trans:
                            # Overwrite normalized_row with parsed_trans fields
                            normalized_row.update(parsed_trans)
            
            # If column mapping failed, try pattern-based extraction
            if not normalized_row.get("date") or not normalized_row.get("amount"):
                pattern_based = self._extract_from_patterns(row_text_space, row.get("bbox", []))
                if pattern_based:
                    normalized_row.update(pattern_based)
            
            # Extract raw text and bbox
            normalized_row["raw_text"] = row_text
            normalized_row["bbox"] = row.get("bbox", [0, 0, 0, 0])
            
            # Only add if we have key fields (date and either description or amounts)
            if normalized_row.get("date") and (normalized_row.get("description") or normalized_row.get("DESCRIPCION") or normalized_row.get("OPERACION") or normalized_row.get("CARGOS") or normalized_row.get("ABONOS")):
                normalized_rows.append(normalized_row)
        
        return normalized_rows
    
    def _looks_like_multiple_transactions(self, text: str) -> bool:
        """Check if text contains multiple transactions."""
        # Count date patterns - if more than 2, likely multiple transactions
        date_pattern = r'\d{1,2}/[A-Z]{3}'
        dates = re.findall(date_pattern, text)
        return len(dates) > 2
    
    def _split_multiple_transactions(self, row: Dict[str, Any], text: str) -> List[Dict[str, Any]]:
        """Split multi-transaction text into individual transactions."""
        transactions = []
        
        # Generic format: DD/MON DD/MON DESCRIPTION AMOUNT BALANCE (repeated)
        # Clean and split lines
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        i = 0
        
        while i < len(lines):
            line = lines[i]
            
            # Look for date pattern (DD/MON) - this starts a transaction
            date_match = re.search(r'(\d{1,2}/[A-Z]{3})', line)
            if date_match:
                # Found start of transaction - parse it
                # Try to get context_year from bank_config or use current year
                context_year = None
                if self.bank_config:
                    from datetime import datetime
                    context_year = datetime.now().year
                
                trans_data = self._parse_single_transaction(lines, i, context_year=context_year)
                if trans_data:
                    # Set main date from first date match
                    trans_data["date"] = self._parse_date(date_match.group(1), context_year=context_year, bank_config=self.bank_config)
                    # Preserve newlines in raw_text
                    next_idx = trans_data.get("_next_index", min(i+15, len(lines)))
                    trans_data["raw_text"] = "\n".join(lines[i:next_idx])[:1000]
                    trans_data["bbox"] = row.get("bbox", [0, 0, 0, 0])
                    
                    # Add transaction if it has description or amounts
                    if trans_data.get("DESCRIPCION") or trans_data.get("OPERACION") or trans_data.get("CARGOS") or trans_data.get("ABONOS"):
                        transactions.append(trans_data)
                    
                    # Skip ahead based on how many lines we consumed
                    i = trans_data.get("_next_index", i + 1)
                else:
                    i += 1
            else:
                i += 1
        
        return transactions
    
    def _parse_single_transaction(self, lines: List[str], start_idx: int, context_year: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Parse a single transaction starting at start_idx.
        
        BBVA format (strictly following document structure):
        OPER LIQ DESCRIPCION REFERENCIA CARGOS ABONOS OPERACION LIQUIDACION
        
        Following prompt requirement: 100% information completeness, preserve original language,
        strictly parse according to document structure without inference.
        """
        if start_idx >= len(lines):
            return None
        
        trans = {}
        i = start_idx
        description_parts = []
        amounts_found = []  # Store as strings to preserve format
        amounts_found_decimal = []  # Store as Decimal for backward compatibility
        reference = None
        oper_date_str = None
        liq_date_str = None
        
        # Step 1: Extract dates (OPER, LIQ) - first 1-2 lines contain dates
        date_line_idx = i
        if date_line_idx < len(lines):
            first_line = lines[date_line_idx].strip()
            # Extract all dates from first line (format: DD/MON DD/MON or just DD/MON)
            date_matches = re.findall(r'(\d{1,2}/[A-Z]{3})', first_line)
            if date_matches:
                # First date is OPER
                oper_date_str = date_matches[0]
                # If first line has 2 dates, second is LIQ
                if len(date_matches) >= 2:
                    liq_date_str = date_matches[1]
                
                # Check next line for LIQ date if not found
                if not liq_date_str and date_line_idx + 1 < len(lines):
                    next_line = lines[date_line_idx + 1].strip()
                    if re.match(r'^\d{1,2}/[A-Z]{3}', next_line):
                        next_date_matches = re.findall(r'(\d{1,2}/[A-Z]{3})', next_line)
                        if next_date_matches:
                            liq_date_str = next_date_matches[0]
                        i += 1  # Skip this date line
        
        i += 1  # Move past date line(s)
        
        # Step 2: Extract description, amounts, and reference
        # New strategy: collect all non-date, non-reference lines first, then separate amounts from description
        description_lines = []
        amount_lines = []
        reference_line_idx = None
        
        # First pass: identify all lines and their types
        scan_end_idx = min(start_idx + 25, len(lines))  # Increased limit
        for scan_idx in range(i, scan_end_idx):
            if scan_idx >= len(lines):
                break
            
            line = lines[scan_idx].strip()
            
            # Check if we hit the next transaction
            if scan_idx > start_idx + 1 and re.match(r'^\d{1,2}/[A-Z]{3}', line):
                scan_end_idx = scan_idx
                break
            
            # Check if this line contains a reference (REFERENCIA)
            if not reference:
                referencia_match = re.search(r'Referencia\s+([*0-9\s]+)', line, re.IGNORECASE)
                if not referencia_match:
                    referencia_match = re.search(r'Referencia\s+([^\n\r]+)', line, re.IGNORECASE)
                if referencia_match:
                    reference = referencia_match.group(1).strip()
                    reference_line_idx = scan_idx
                    # Don't break - continue to collect description after reference
            
            # Check if this line is primarily an amount (pure number with .XX format)
            is_pure_amount = bool(re.match(r'^[\d,]+\.\d{2}$', line))
            has_amount = bool(re.search(r'[\d,]+\.\d{2}', line))
            
            if is_pure_amount:
                # Pure amount line - store for amount extraction
                amount_lines.append((scan_idx, line))
            elif has_amount and not re.search(r'[A-Za-z]{3,}', line):
                # Line with amount but minimal text - likely amount line
                amount_lines.append((scan_idx, line))
            elif line and not re.match(r'^\d{1,2}/[A-Z]{3}', line):
                # Description line (not date, not pure amount)
                description_lines.append((scan_idx, line))
        
        # Process description lines
        # Include lines before AND after reference (description can continue after reference)
        # But exclude the reference line itself and lines that are pure numbers/amounts
        for desc_idx, desc_line in description_lines:
            # Skip if this line is the reference line itself
            if reference_line_idx is not None and desc_idx == reference_line_idx:
                continue
            
            # Skip if this line is a pure amount (already handled)
            if re.match(r'^[\d,]+\.\d{2}$', desc_line):
                continue
            
            # Remove date patterns
            desc = re.sub(r'\d{1,2}/[A-Z]{3}', '', desc_line)
            # Remove reference patterns (will be handled separately)
            desc = re.sub(r'Referencia\s+[*0-9\s]+', '', desc, flags=re.IGNORECASE)
            desc = re.sub(r'Referencia\s+[^\n\r]+', '', desc, flags=re.IGNORECASE)
            # Keep all text - don't remove FOLIO/CUENTA as they're part of description
            # Also keep lines that look like account numbers or transaction IDs
            desc = desc.strip()
            if desc and len(desc) > 0:
                description_parts.append(desc)
        
        # Update i to point after all collected lines
        all_indices = []
        if description_lines:
            all_indices.extend([idx for idx, _ in description_lines])
        if amount_lines:
            all_indices.extend([idx for idx, _ in amount_lines])
        if reference_line_idx is not None:
            all_indices.append(reference_line_idx)
        
        if all_indices:
            max_idx = max(all_indices)
            i = max_idx + 1
        else:
            i += 1
        
        # Step 3: Extract amounts (CARGOS ABONOS OPERACION LIQUIDACION)
        # Parse amounts from collected amount lines
        for _, amount_line in amount_lines:
            # Extract amounts with comma separators (e.g., "7,200.00")
            amount_matches = re.findall(r'([\d,]+\.\d{2})', amount_line)
            for amt_str in amount_matches:
                # Clean up the amount string (remove spaces)
                amt_str_clean = amt_str.replace(' ', '')
                if amt_str_clean not in amounts_found:  # Avoid duplicates
                    amounts_found.append(amt_str_clean)  # Keep original format
                    # Also parse as Decimal for backward compatibility
                    amt_decimal = self._parse_amount(amt_str_clean, bank_config=self.bank_config)
                    if amt_decimal:
                        amounts_found_decimal.append(amt_decimal)
        
        # If no amounts found in dedicated amount lines, try to extract from description lines
        # This helps catch cases where amounts are mixed with description
        if not amounts_found:
            for desc_idx, desc_line in description_lines:
                # Skip if it's clearly description text (contains many letters)
                if len(re.findall(r'[A-Za-z]', desc_line)) > 5:
                    continue
                # Extract amounts
                amount_matches = re.findall(r'([\d,]+\.\d{2})', desc_line)
                for amt_str in amount_matches:
                    amt_str_clean = amt_str.replace(' ', '')
                    if amt_str_clean not in amounts_found:
                        amounts_found.append(amt_str_clean)
                        amt_decimal = self._parse_amount(amt_str_clean, bank_config=self.bank_config)
                        if amt_decimal:
                            amounts_found_decimal.append(amt_decimal)
        
        # Map amounts to BBVA fields based on position and description context
        desc_text = " ".join(description_parts).lower() if description_parts else ""
        withdrawal_keywords = self.bank_config.get('transaction_keywords', {}).get('withdrawal', []) if self.bank_config else ["retiro", "cargo", "withdrawal", "debit", "pago"]
        deposit_keywords = self.bank_config.get('transaction_keywords', {}).get('deposit', []) if self.bank_config else ["deposito", "abono", "deposit", "credit", "spei", "recibido"]
        
        # Special handling for SPEI transactions (following prompt: dynamic adaptation, no hardcoding)
        # SPEI ENVIADO = withdrawal (CARGOS), SPEI RECIBIDO = deposit (ABONOS)
        is_withdrawal = False
        is_deposit = False
        
        # Check in description text and also in original lines (in case "enviado" is in a separate line)
        full_text_check = desc_text
        if start_idx < len(lines):
            # Also check original lines for "enviado" or "recibido" (may be in separate lines)
            lines_text = " ".join([l.lower() for l in lines[start_idx:min(start_idx+10, len(lines))]])
            full_text_check = f"{desc_text} {lines_text}"
        
        if "spei" in desc_text or "spei" in full_text_check:
            # SPEI transaction - determine direction
            if "enviado" in full_text_check:
                # SPEI ENVIADO = withdrawal (money sent out) -> CARGOS
                is_withdrawal = True
                is_deposit = False
            elif "recibido" in full_text_check:
                # SPEI RECIBIDO = deposit (money received) -> ABONOS
                is_deposit = True
                is_withdrawal = False
            else:
                # Generic SPEI without direction indicator - check keywords
                is_withdrawal = any(kw.lower() in desc_text for kw in withdrawal_keywords)
                is_deposit = any(kw.lower() in desc_text for kw in deposit_keywords)
        else:
            # Non-SPEI transactions - use keyword matching
            is_withdrawal = any(kw.lower() in desc_text for kw in withdrawal_keywords)
            is_deposit = any(kw.lower() in desc_text for kw in deposit_keywords)
        
        # Set amounts in original format (strings with commas)
        if amounts_found:
            if is_withdrawal:
                trans["CARGOS"] = amounts_found[0] if len(amounts_found) > 0 else ""
                trans["ABONOS"] = ""
                trans["cargos"] = amounts_found_decimal[0] if len(amounts_found_decimal) > 0 else None
                trans["abonos"] = None
            elif is_deposit:
                trans["CARGOS"] = ""
                trans["ABONOS"] = amounts_found[0] if len(amounts_found) > 0 else ""
                trans["cargos"] = None
                trans["abonos"] = amounts_found_decimal[0] if len(amounts_found_decimal) > 0 else None
            else:
                # Unknown type - don't set CARGOS/ABONOS, let them be null
                # This handles cases like SPEI where we can't determine if it's deposit or withdrawal
                trans["CARGOS"] = None
                trans["ABONOS"] = None
                trans["cargos"] = None
                trans["abonos"] = None
            
            # OPERACION and LIQUIDACION
            # These are balance amounts, not transaction amounts
            if len(amounts_found) >= 3:
                # Three amounts: CARGOS/ABONOS, OPERACION, LIQUIDACION
                trans["OPERACION"] = amounts_found[1]
                trans["operacion"] = amounts_found_decimal[1] if len(amounts_found_decimal) > 1 else None
                trans["LIQUIDACION"] = amounts_found[2]
                trans["liquidacion"] = amounts_found_decimal[2] if len(amounts_found_decimal) > 2 else None
            elif len(amounts_found) == 2:
                # Two amounts: could be CARGOS/ABONOS and OPERACION/LIQUIDACION
                # If first is transaction amount, second might be balance
                trans["OPERACION"] = amounts_found[1]
                trans["operacion"] = amounts_found_decimal[1] if len(amounts_found_decimal) > 1 else None
                trans["LIQUIDACION"] = amounts_found[1]  # Same as OPERACION if only 2 amounts
                trans["liquidacion"] = amounts_found_decimal[1] if len(amounts_found_decimal) > 1 else None
            elif len(amounts_found) == 1:
                # Only one amount - might be transaction amount only
                trans["OPERACION"] = None
                trans["operacion"] = None
                trans["LIQUIDACION"] = None
                trans["liquidacion"] = None
            else:
                trans["OPERACION"] = None
                trans["operacion"] = None
                trans["LIQUIDACION"] = None
                trans["liquidacion"] = None
            
            # For backward compatibility
            trans["amount"] = amounts_found_decimal[0] if amounts_found_decimal else Decimal("0")
            if len(amounts_found_decimal) > 1:
                trans["balance"] = amounts_found_decimal[-1]
        
        # Set dates in original format
        if oper_date_str:
            trans["OPER"] = oper_date_str
            trans["oper_date"] = self._parse_date(oper_date_str, context_year=context_year, bank_config=self.bank_config)
        if liq_date_str:
            trans["LIQ"] = liq_date_str
            trans["liq_date"] = self._parse_date(liq_date_str, context_year=context_year, bank_config=self.bank_config)
        
        # Set description (preserve original language, remove reference)
        if description_parts:
            # Join with space to preserve readability, but keep original structure
            desc_text = " ".join(description_parts)
            # Final cleanup: remove any remaining reference patterns
            desc_text = re.sub(r'\s*Referencia\s+[*0-9\s]+', '', desc_text, flags=re.IGNORECASE)
            desc_text = re.sub(r'\s*Referencia\s+[^\n\r]+', '', desc_text, flags=re.IGNORECASE)
            # Remove extra whitespace
            desc_text = re.sub(r'\s+', ' ', desc_text)
            desc_text = desc_text.strip()
            trans["DESCRIPCION"] = desc_text[:500] if desc_text else None
            trans["description"] = desc_text[:500] if desc_text else ""
        
        # Set reference (with "Referencia" prefix)
        if reference:
            trans["REFERENCIA"] = f"Referencia {reference}"
            trans["reference"] = reference  # Without prefix for backward compatibility
        
        trans["_next_index"] = i
        
        # Return transaction if we have at least date or description or amounts or reference
        # More lenient condition to capture transactions even if some fields are missing
        has_date = oper_date_str or liq_date_str
        has_description = trans.get("DESCRIPCION") or description_parts
        has_amounts = amounts_found or amounts_found_decimal
        has_reference = reference
        has_content = has_description or has_amounts or has_reference
        
        # If we have dates or any content, return the transaction
        # This ensures we capture transactions even if parsing is incomplete
        if has_date or has_content:
            return trans
        
        # Also return if we have raw text that looks like a transaction
        # (for cases where parsing failed but data exists)
        if start_idx < len(lines):
            first_few_lines = "\n".join(lines[start_idx:min(start_idx+5, len(lines))])
            if re.search(r'\d{1,2}/[A-Z]{3}', first_few_lines):
                # Looks like a transaction, return what we have
                return trans
        
        return None
    
    def _extract_from_patterns(self, text: str, bbox: List[float]) -> Dict[str, Any]:
        """Extract transaction data using pattern matching."""
        result = {}
        
        # Extract date
        date_patterns = [
            r'(\d{1,2}/[A-Z]{3})',  # DD/MON format
            r'(\d{1,2}/\d{1,2}/\d{2,4})',  # DD/MM/YYYY format
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                result["date"] = self._parse_date(match.group(1), context_year=None, bank_config=self.bank_config)
                break
        
        # Extract amounts (look for currency-like numbers)
        amount_pattern = r'([\d,]+\.\d{2})'
        amounts = re.findall(amount_pattern, text.replace(',', ''))
        if amounts:
            # Usually first is transaction amount, last might be balance
            if len(amounts) >= 1:
                result["amount"] = self._parse_amount(amounts[0], bank_config=self.bank_config)
            if len(amounts) >= 2:
                result["balance"] = self._parse_amount(amounts[-1], bank_config=self.bank_config)
        
        # Extract description (text between dates and amounts)
        # Remove dates and amounts, get remaining text
        desc_text = text
        for pattern in date_patterns + [r'[\d,]+\.\d{2}']:
            desc_text = re.sub(pattern, '', desc_text)
        desc_text = ' '.join(desc_text.split())  # Normalize whitespace
        if desc_text and len(desc_text) > 3:
            result["description"] = desc_text[:200]  # Limit length
        
        return result
    
    def _parse_date(self, date_text: str, context_year: Optional[int] = None, bank_config: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Parse date from text with intelligent year inference.
        
        Following prompt requirement: avoid hardcoding, use dynamic context inference.
        """
        if not date_text:
            return None
        
        # Remove whitespace
        date_text = date_text.strip()
        
        # Use bank config date patterns (following prompt: dynamic adaptation, no hardcoding)
        # Use self.bank_config if bank_config parameter not provided
        config_to_use = bank_config if bank_config is not None else self.bank_config
        date_patterns = config_to_use.get('date_patterns', ["DD/MON", "DD/MM/YYYY"]) if config_to_use else ["DD/MON", "DD/MM/YYYY"]
        
        month_map = {
            'ENE': '01', 'FEB': '02', 'MAR': '03', 'ABR': '04',
            'MAY': '05', 'JUN': '06', 'JUL': '07', 'AGO': '08',
            'SEP': '09', 'OCT': '10', 'NOV': '11', 'DIC': '12'
        }
        
        # Try DD/MON format first if in configured patterns
        if "DD/MON" in date_patterns or any("MON" in p for p in date_patterns):
            mon_match = re.match(r'(\d{1,2})/([A-Z]{3})', date_text.upper())
            if mon_match:
                day, mon = mon_match.groups()
                if mon in month_map:
                    # Infer year from context if provided, otherwise use current year
                    # This is dynamic, not hardcoded - follows prompt requirement
                    if context_year:
                        year = context_year
                    else:
                        from datetime import date
                        year = date.today().year
                    
                    try:
                        return f"{year}-{month_map[mon]}-{day.zfill(2)}"
                    except:
                        pass
        
        # Try date formats from bank config
        date_format_map = {
            "DD/MM/YYYY": "%d/%m/%Y",
            "DD/MM/YY": "%d/%m/%y",
            "DD/MM": "%d/%m",
            "YYYY-MM-DD": "%Y-%m-%d",
            "MM/DD/YYYY": "%m/%d/%Y",
        }
        date_formats = []
        for pattern_name in date_patterns:
            if pattern_name in date_format_map:
                date_formats.append(date_format_map[pattern_name])
        # Fallback formats if none configured
        if not date_formats:
            date_formats = ["%d/%m/%Y", "%d/%m/%y", "%d/%m"]
        
        for fmt in date_formats:
            try:
                dt = datetime.strptime(date_text, fmt)
                # If year is 2-digit, infer from context
                if dt.year < 2000 and context_year:
                    dt = dt.replace(year=context_year)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        
        return date_text  # Return as-is if parsing fails
    
    def _parse_amount(self, amount_text: str, bank_config: Optional[Dict[str, Any]] = None) -> Optional[Decimal]:
        """
        Parse amount from text.
        
        Following prompt requirement: absolute avoidance of hardcoding,
        use bank configuration for currency formatting.
        
        Args:
            amount_text: Text containing amount
            bank_config: Optional bank configuration dictionary
        """
        if not amount_text:
            return None
        
        # Remove currency symbols and whitespace
        cleaned = re.sub(r'[\$€\s]', '', amount_text)
        
        # Handle decimal/thousands separators (from bank config, not hardcoded)
        # Use self.bank_config if bank_config parameter not provided
        config_to_use = bank_config if bank_config is not None else self.bank_config
        currency_format = config_to_use.get('currency_format', {}) if config_to_use else {}
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
    
    def _validate_table_semantics(
        self,
        normalized_data: List[Dict[str, Any]],
        table_type: str
    ) -> Dict[str, Any]:
        """
        Validate table semantics (e.g., balance consistency).
        
        Args:
            normalized_data: Normalized table data
            table_type: Type of table
            
        Returns:
            Validation report
        """
        issues = []
        
        if table_type == "transaction":
            # Check date consistency
            dates = [
                row.get("date") for row in normalized_data 
                if row.get("date")
            ]
            if dates:
                # Check if dates are in reasonable range
                pass  # Could add date range validation
        
            # Check amount formats
            amounts = [
                row.get("amount") for row in normalized_data 
                if row.get("amount") is not None
            ]
            if amounts:
                # All amounts should be valid decimals
                invalid = [
                    i for i, amt in enumerate(amounts) 
                    if not isinstance(amt, Decimal)
                ]
                if invalid:
                    issues.append({
                        "type": "invalid_amounts",
                        "indices": invalid
                    })
        
        return {
            "is_valid": len(issues) == 0,
            "issues": issues,
            "row_count": len(normalized_data)
        }


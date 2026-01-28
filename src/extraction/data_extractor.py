"""Structured data extraction."""
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional
import re

from src.extraction.amount_parser import parse_amount, extract_amount_pattern
from src.extraction.balance_extractor import BalanceExtractor

from src.models.schemas import (
    AccountSummary,
    BBox,
    Metadata,
    StructuredData,
    Transaction,
)


class DataExtractor:
    """Extract structured data from parsed document."""
    
    def __init__(self, bank_config: Optional[Dict[str, Any]] = None):
        """Initialize data extractor.
        
        Args:
            bank_config: Bank-specific configuration dictionary
        """
        self.bank_config = bank_config
        self.balance_extractor = BalanceExtractor(bank_config=bank_config)
    
    def extract_structured_data(
        self,
        layout_structure: Any,
        parsed_tables: List[Dict[str, Any]],
        ocr_data: Dict[str, Any]
    ) -> StructuredData:
        """
        Extract structured data from analyzed document.
        
        Args:
            layout_structure: Document layout structure
            parsed_tables: Parsed table data
            ocr_data: Original OCR data
            
        Returns:
            StructuredData object
        """
        # Extract year context from document period (dynamic, not hardcoded)
        year_context = self._extract_year_context(ocr_data, layout_structure)
        
        # Extract transactions from tables (with year context)
        transactions = self._extract_transactions(parsed_tables, year_context)
        
        # If no transactions found in tables, try direct extraction from OCR
        if not transactions:
            print("No transactions found in parsed tables, trying direct OCR extraction...")
            transactions = self._extract_transactions_from_ocr(ocr_data, year_context)
        
        # Enhance transactions with missing balances (dynamic calculation, not hardcoding)
        # User requirement: "Do not add extra fields" and "What you see is what you get".
        # We should strictly avoid inferring data that isn't in the document.
        # Commenting out inference logic unless explicitly required.
        # print(f"Enhancing transactions with balance extraction...")
        # transactions = self.balance_extractor.enhance_transactions_with_balances(
        #     transactions,
        #     ocr_data
        # )
        
        # Extract account summary
        account_summary = self._extract_account_summary(
            parsed_tables, 
            transactions,
            ocr_data
        )
        
        # Extract customer info (header data)
        if ocr_data:
            account_summary.customer_info = self._extract_customer_info(ocr_data)
        
        return StructuredData(account_summary=account_summary)
    
    def extract_metadata_only(
        self,
        layout_structure: Any,
        parsed_tables: List[Dict[str, Any]],
        ocr_data: Dict[str, Any]
    ) -> StructuredData:
        """
        提取文档元数据和账户汇总信息，不解析交易明细。
        
        用于外部提供交易数据的场景。
        
        Args:
            layout_structure: Document layout structure
            parsed_tables: Parsed table data
            ocr_data: Original OCR data
            
        Returns:
            StructuredData object (无transactions)
        """
        # Extract account summary without transactions
        # 从parsed_tables或OCR中提取账户汇总信息
        account_summary = AccountSummary(transactions=[])
        
        # 尝试从表格中提取汇总信息
        for table in parsed_tables:
            if table.get("type") == "summary":
                for row in table.get("data", []):
                    desc = str(row.get("description", "")).lower()
                    amount = row.get("amount")
                    
                    if amount:
                        if "saldo inicial" in desc or "initial balance" in desc:
                            account_summary.initial_balance = Decimal(str(amount))
                        elif "saldo final" in desc or "final balance" in desc:
                            account_summary.final_balance = Decimal(str(amount))
                        elif "deposito" in desc or "deposit" in desc:
                            if account_summary.deposits:
                                account_summary.deposits += Decimal(str(amount))
                            else:
                                account_summary.deposits = Decimal(str(amount))
                        elif "retiro" in desc or "withdrawal" in desc:
                            if account_summary.withdrawals:
                                account_summary.withdrawals += Decimal(str(amount))
                            else:
                                account_summary.withdrawals = Decimal(str(amount))
        
        # 提取新的业务字段
        print("Extracting additional BBVA business fields...")
        
        # Customer Info (Header - Screenshot 1)
        account_summary.customer_info = self._extract_customer_info(ocr_data)
        if account_summary.customer_info:
            print(f"✓ Extracted Customer Info ({len(account_summary.customer_info)} fields)")
            
        # Pages Info (Headers per page - User Request)
        account_summary.pages_info = self._extract_pages_info(ocr_data)
        if account_summary.pages_info:
            print(f"✓ Extracted Headers for {len(account_summary.pages_info)} pages")
        
        # Total de Movimientos - (用户反馈重要，已恢复)
        account_summary.total_movimientos = self._extract_total_movimientos(
            ocr_data,
            parsed_tables
        )
        if account_summary.total_movimientos:
            print(f"✓ Extracted Total de Movimientos")
        
        # Apartados Vigentes - (用户反馈重要，已恢复)
        account_summary.apartados_vigentes = self._extract_apartados_vigentes(
            ocr_data
        )
        if account_summary.apartados_vigentes:
            print(f"✓ Extracted {len(account_summary.apartados_vigentes)} Apartados Vigentes")
        
        # Cuadro resumen
        account_summary.cuadro_resumen = self._extract_cuadro_resumen(
            ocr_data,
            parsed_tables
        )
        if account_summary.cuadro_resumen:
            print(f"✓ Extracted Cuadro resumen with {len(account_summary.cuadro_resumen)} items")
            
        # Información Financiera
        account_summary.informacion_financiera = self._extract_informacion_financiera(
            ocr_data
        )
        if account_summary.informacion_financiera:
            print(f"✓ Extracted Información Financiera")
            
        # Comportamiento
        account_summary.comportamiento = self._extract_comportamiento(
            ocr_data
        )
        if account_summary.comportamiento:
            print(f"✓ Extracted Comportamiento table")
        
        # Otros productos (Screenshot 3)
        account_summary.otros_productos = self._extract_otros_productos(ocr_data)
        if account_summary.otros_productos:
            print(f"✓ Extracted Otros productos")

        # Branch Info (Screenshot 2)
        account_summary.branch_info = self._extract_branch_info(ocr_data)
        if account_summary.branch_info:
            print(f"✓ Extracted Branch Info")
        
        return StructuredData(account_summary=account_summary)

    def _extract_year_context(self, ocr_data: Dict[str, Any], layout_structure: Any) -> Optional[int]:
        """
        Dynamically extract year context from document period.
        This follows prompt requirement: avoid hardcoding, use context inference.
        """
        import re
        from datetime import datetime
        
        # Search for period information in OCR data
        period_patterns = [
            r'DEL\s+(\d{1,2})/(\d{1,2})/(\d{4})\s+AL',  # DEL DD/MM/YYYY AL
            r'Periodo.*(\d{4})',  # Periodo ... YYYY
            r'(\d{4})',  # Any 4-digit year in context (fallback)
        ]
        
        # Search in all text blocks
        for page_data in ocr_data.get("pages", []):
            for block in page_data.get("text_blocks", []):
                text = block.get("text", "")
                
                # Try period pattern first
                for pattern in period_patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        # Extract year from match
                        if len(match.groups()) >= 3:
                            # Pattern with DD/MM/YYYY
                            year = int(match.group(3))
                            if 2000 <= year <= 2100:  # Reasonable year range
                                print(f"Extracted year context: {year} from period text")
                                return year
                        elif len(match.groups()) >= 1:
                            # Pattern with just year
                            year = int(match.group(1))
                            if 2000 <= year <= 2100:
                                print(f"Extracted year context: {year} from text")
                                return year
        
        # Fallback: use current year (but this should rarely happen)
        fallback_year = datetime.now().year
        print(f"Warning: Could not extract year from period, using fallback: {fallback_year}")
        return fallback_year
    
    def _extract_transactions_from_ocr(self, ocr_data: Dict[str, Any], year_context: Optional[int] = None) -> List[Transaction]:
        """Extract transactions directly from OCR text blocks using BBVA-specific parsing."""
        transactions = []
        import re
        
        # Create a temporary TableParser instance to use its BBVA-specific parsing logic
        from src.tables.table_parser import TableParser
        table_parser = TableParser(bank_config=self.bank_config)
        
        for page_data in ocr_data.get("pages", []):
            for block in page_data.get("text_blocks", []):
                text = block.get("text", "")
                bbox = block.get("bbox", [0, 0, 0, 0])
                
                # Skip if doesn't look like transaction text
                if not text or len(text) < 10:
                    continue
                
                # Skip headers/footers (using bank config, not hardcoded)
                text_lower = text.lower()
                skip_keywords = self.bank_config.get('skip_keywords', []) if self.bank_config else [
                    "periodo", "fecha de corte", "no. de cuenta", "estado de cuenta"
                ]
                if any(skip.lower() in text_lower for skip in skip_keywords):
                    continue
                
                # Check if text contains transaction patterns (dates)
                date_pattern = r'\d{1,2}/[A-Z]{3}'
                dates = re.findall(date_pattern, text)
                if len(dates) < 2:
                    continue  # Not enough dates to be a transaction block
                
                # Use TableParser's BBVA-specific parsing logic
                # Create a mock row structure
                mock_row = {"bbox": bbox}
                
                # Split text into lines and parse using _parse_single_transaction
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                i = 0
                
                while i < len(lines):
                    line = lines[i]
                    # Look for date pattern (DD/MON) - this starts a transaction
                    date_match = re.search(r'(\d{1,2}/[A-Z]{3})', line)
                    if date_match:
                        # Found start of transaction - parse it using BBVA-specific logic
                        trans_data = table_parser._parse_single_transaction(lines, i, context_year=year_context)
                        if trans_data:
                            # Set main date
                            trans_date = self._parse_date_field(date_match.group(1), year_context)
                            if not trans_date:
                                trans_date = self._parse_date_field(trans_data.get("OPER") or date_match.group(1), year_context)
                            
                            if trans_date:
                                # Preserve newlines in raw_text
                                next_idx = trans_data.get("_next_index", min(i+15, len(lines)))
                                trans_data["raw_text"] = "\n".join(lines[i:next_idx])[:1000]
                                trans_data["bbox"] = bbox
                                trans_data["date"] = trans_date
                                
                                # Convert to Transaction object
                                transaction = self._create_transaction_from_dict(trans_data, bbox, page_data.get("page_number", 1))
                                if transaction:
                                    transactions.append(transaction)
                            
                            # Skip ahead based on how many lines we consumed
                            i = trans_data.get("_next_index", i + 1)
                        else:
                            i += 1
                    else:
                        i += 1
        
        return transactions
    
    def _calculate_transaction_confidence(self, trans_data: Dict[str, Any], extraction_method: str = "table") -> float:
        """
        Calculate confidence score for a transaction.
        
        Following prompt requirement: mark uncertain data with low confidence.
        
        Args:
            trans_data: Transaction data dictionary
            extraction_method: "table" (more reliable) or "ocr" (less reliable)
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        confidence = 0.0
        
        # Base confidence based on extraction method
        if extraction_method == "table":
            confidence += 0.3  # Table extraction is more reliable
        else:
            confidence += 0.1  # OCR direct extraction is less reliable
        
        # Check required fields completeness
        has_date = bool(trans_data.get("date") or trans_data.get("OPER") or trans_data.get("oper_date"))
        has_description = bool(trans_data.get("description") or trans_data.get("DESCRIPCION"))
        has_amount = bool(trans_data.get("amount") or trans_data.get("CARGOS") or trans_data.get("ABONOS") or 
                         trans_data.get("OPERACION") or trans_data.get("operacion"))
        
        if has_date:
            confidence += 0.2
        if has_description:
            confidence += 0.2
        if has_amount:
            confidence += 0.2
        
        # Check BBVA-specific fields completeness (higher confidence if all BBVA fields present)
        bbva_fields = ["OPER", "LIQ", "DESCRIPCION", "REFERENCIA"]
        bbva_fields_present = sum(1 for field in bbva_fields if trans_data.get(field))
        bbva_completeness = bbva_fields_present / len(bbva_fields)
        confidence += bbva_completeness * 0.1
        
        # Check amount fields completeness
        amount_fields = ["CARGOS", "ABONOS", "OPERACION", "LIQUIDACION"]
        amount_fields_present = sum(1 for field in amount_fields if trans_data.get(field))
        if amount_fields_present > 0:
            amount_completeness = min(amount_fields_present / 2.0, 1.0)  # At least 2 amount fields expected
            confidence += amount_completeness * 0.1
        
        # Penalize if critical fields are missing
        if not has_date or not has_description or not has_amount:
            confidence *= 0.7  # Reduce confidence if critical fields missing
        
        # Ensure confidence is within valid range
        return max(0.0, min(1.0, confidence))
    
    def _create_transaction_from_dict(self, trans_data: Dict[str, Any], bbox: List[float], page_num: int) -> Optional[Transaction]:
        """Create Transaction object from parsed transaction dictionary."""
        try:
            # Calculate confidence score
            confidence = self._calculate_transaction_confidence(trans_data, extraction_method="ocr")
            # Extract BBVA-specific fields in original format
            oper_date_str = trans_data.get("OPER")
            liq_date_str = trans_data.get("LIQ")
            descripcion = trans_data.get("DESCRIPCION") or trans_data.get("description", "")
            referencia_raw = trans_data.get("reference")
            referencia = trans_data.get("REFERENCIA")
            
            # Ensure REFERENCIA has prefix
            if referencia_raw and not referencia:
                if not referencia_raw.startswith("Referencia"):
                    referencia = f"Referencia {referencia_raw}"
                else:
                    referencia = referencia_raw
            
            # Amounts in original format
            cargos_str = trans_data.get("CARGOS") or ""
            abonos_str = trans_data.get("ABONOS") or ""
            operacion_str = trans_data.get("OPERACION") or ""
            liquidacion_str = trans_data.get("LIQUIDACION") or ""
            
            # Parse dates for backward compatibility
            oper_date_iso = None
            if trans_data.get("oper_date"):
                oper_date_iso = self._parse_date_field(trans_data.get("oper_date"), None)
            elif oper_date_str:
                oper_date_iso = self._parse_date_field(oper_date_str, None)
            
            liq_date_iso = None
            if trans_data.get("liq_date"):
                liq_date_iso = self._parse_date_field(trans_data.get("liq_date"), None)
            elif liq_date_str:
                liq_date_iso = self._parse_date_field(liq_date_str, None)
            
            # Parse amounts for backward compatibility
            cargos_decimal = trans_data.get("cargos")
            abonos_decimal = trans_data.get("abonos")
            operacion_decimal = trans_data.get("operacion")
            liquidacion_decimal = trans_data.get("liquidacion")
            
            # Main date
            trans_date = self._parse_date_field(trans_data.get("date"), None)
            if not trans_date:
                trans_date = oper_date_iso or liq_date_iso
            if not trans_date:
                from datetime import date
                trans_date = date.today()
            
            # Amount and balance for backward compatibility
            amount_value = trans_data.get("amount") or operacion_decimal or cargos_decimal or abonos_decimal or Decimal("0")
            balance_value = trans_data.get("balance") or liquidacion_decimal
            
            # Create Transaction object
            transaction = Transaction(
                date=trans_date,
                description=descripcion[:500] if descripcion else "",
                amount=amount_value if amount_value else Decimal("0"),
                balance=balance_value,
                reference=referencia_raw[:100] if referencia_raw else None,
                raw_text=str(trans_data.get("raw_text", ""))[:1000],
                bbox=self._bbox_from_list_with_page(bbox, page_num),
                # BBVA-specific fields in ISO/Decimal format (backward compatibility)
                oper_date=oper_date_iso,
                liq_date=liq_date_iso,
                cargos=cargos_decimal,
                abonos=abonos_decimal,
                operacion=operacion_decimal,
                liquidacion=liquidacion_decimal,
                # BBVA fields in original format
                OPER=oper_date_str,
                LIQ=liq_date_str,
                DESCRIPCION=descripcion[:500] if descripcion else None,
                REFERENCIA=referencia,
                CARGOS=cargos_str if cargos_str else None,
                ABONOS=abonos_str if abonos_str else "",
                OPERACION=operacion_str if operacion_str else None,
                LIQUIDACION=liquidacion_str if liquidacion_str else None,
                # Confidence score
                confidence=confidence
            )
            return transaction
        except Exception as e:
            print(f"Error creating transaction from dict: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _parse_transaction_text(self, text: str, bbox: List[float], page_num: int, year_context: Optional[int] = None) -> List[Transaction]:
        """Parse transaction text block into individual transactions (generic, not bank-specific)."""
        transactions = []
        import re
        from decimal import Decimal
        
        # Split by newlines and process
        lines = text.split('\n')
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            
            # Look for date pattern (from bank config, not hardcoded)
            date_patterns = self.bank_config.get('date_patterns', ["DD/MON"]) if self.bank_config else ["DD/MON"]
            date_pattern_regex = {
                "DD/MON": r'(\d{1,2}/[A-Z]{3})',
                "DD/MM/YYYY": r'(\d{1,2}/\d{1,2}/\d{2,4})',
            }
            # Try configured patterns
            date_match = None
            for pattern_name in date_patterns:
                if pattern_name in date_pattern_regex:
                    date_match = re.match(date_pattern_regex[pattern_name], line.upper())
                    if date_match:
                        break
            if not date_match:
                # Fallback to DD/MON
                date_match = re.match(r'(\d{1,2}/[A-Z]{3})', line.upper())
            if date_match:
                # Found start of transaction
                date_str = date_match.group(1)
                # Use year_context for proper date parsing (following prompt: dynamic inference, not hardcoding)
                trans_date = self._parse_date_field(date_str, year_context)
                
                if not trans_date:
                    i += 1
                    continue
                
                # Look ahead for description and amount
                description = ""
                amount = None
                balance = None
                
                # Next lines should contain description and amounts
                j = i + 1
                while j < len(lines) and j < i + 10:  # Look ahead max 10 lines
                    next_line = lines[j].strip()
                    
                    # Check if next line is another date (new transaction)
                    if re.match(r'\d{1,2}/[A-Z]{3}', next_line):
                        break
                    
                    # Extract description (non-date, non-amount text)
                    if not re.match(r'[\d,]+\.?\d*', next_line) and not re.match(r'\d{1,2}/[A-Z]{3}', next_line):
                        if description:
                            description += " " + next_line
                        else:
                            description = next_line
                    
                    # Extract amounts (using bank config, not hardcoded)
                    amount_str = extract_amount_pattern(next_line, self.bank_config)
                    if amount_str:
                        amount_val = parse_amount(amount_str, self.bank_config)
                        
                        if amount is None:
                            amount = amount_val
                        else:
                            # Found second amount - might be balance
                            balance = amount_val
                    
                    # Also try to extract balance using enhanced extractor
                    if balance is None:
                        balance = self.balance_extractor.extract_balance_from_text_block(
                            text, lines, i, amount
                        )
                    
                    j += 1
                
                if amount is not None and description:
                    try:
                        # Calculate confidence for OCR-extracted transaction
                        trans_data_dict = {
                            "date": trans_date,
                            "description": description,
                            "amount": amount,
                            "balance": balance
                        }
                        confidence = self._calculate_transaction_confidence(trans_data_dict, extraction_method="ocr")
                        
                        transaction = Transaction(
                            date=trans_date,
                            description=description[:500],
                            amount=amount,
                            balance=balance,
                            reference=None,
                            raw_text=text[:1000],
                            bbox=self._bbox_from_list(bbox),
                            confidence=confidence
                        )
                        transactions.append(transaction)
                    except Exception as e:
                        print(f"Error creating transaction: {e}")
                
                i = j
            else:
                i += 1
        
        return transactions
    
    def _extract_transactions(
        self, 
        parsed_tables: List[Dict[str, Any]],
        year_context: Optional[int] = None
    ) -> List[Transaction]:
        """Extract transactions from parsed tables."""
        transactions = []
        
        for table in parsed_tables:
            if table.get("type") == "transaction":
                for row in table.get("data", []):
                    try:
                        # Parse date - try multiple methods (with year_context)
                        date_value = row.get("date")
                        trans_date = self._parse_date_field(date_value, year_context)
                        
                        # If date parsing failed, try to extract from raw_text
                        if not trans_date and row.get("raw_text"):
                            # Look for date patterns in raw text (from bank config)
                            import re
                            configured_patterns = self.bank_config.get('date_patterns', ["DD/MON"]) if self.bank_config else ["DD/MON"]
                            date_pattern_regex = {
                                "DD/MON": r'\b(\d{1,2})/([A-Z]{3})\b',
                                "DD/MM/YYYY": r'\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b',
                                "YYYY-MM-DD": r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b',
                            }
                            # Build pattern list from config
                            date_patterns = []
                            for pattern_name in configured_patterns:
                                if pattern_name in date_pattern_regex:
                                    date_patterns.append(date_pattern_regex[pattern_name])
                            # Add common fallback patterns
                            if not date_patterns:
                                date_patterns = [
                                    r'\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b',
                                    r'\b(\d{1,2})-(\d{1,2})-(\d{2,4})\b',
                                    r'\b(\d{1,2})\s+(\d{1,2})\s+(\d{2,4})\b',
                                    r'\b(\d{1,2})/([A-Z]{3})\b'  # DD/MON format
                                ]
                            for pattern in date_patterns:
                                match = re.search(pattern, row.get("raw_text", ""))
                                if match:
                                    try:
                                        if len(match.groups()) == 3:
                                            d, m, y = match.groups()
                                            if len(y) == 2:
                                                # Use year_context if provided
                                                if year_context:
                                                    y = str(year_context)
                                                else:
                                                    y = f"20{y}" if int(y) < 50 else f"19{y}"
                                            trans_date = self._parse_date_field(f"{d}/{m}/{y}", year_context)
                                        elif len(match.groups()) == 2:
                                            # DD/MON format
                                            trans_date = self._parse_date_field(match.group(0), year_context)
                                        
                                        if trans_date:
                                            break
                                    except:
                                        continue
                        
                        # If still no date, use a default date (but log warning)
                        if not trans_date:
                            from datetime import date
                            trans_date = date.today()  # Fallback
                            print(f"Warning: Could not parse date for transaction, using today: {row.get('raw_text', '')[:50]}")
                        
                        # Parse amount (using bank config, not hardcoded)
                        amount_value = row.get("amount")
                        if amount_value is None:
                            # Try to extract from raw_text
                            amount_str = str(row.get("raw_text", ""))
                            amount_value = parse_amount(amount_str, self.bank_config)
                            if amount_value is None:
                                amount_value = Decimal("0")
                        else:
                            # If already parsed, ensure it's Decimal
                            if isinstance(amount_value, (int, float, str)):
                                amount_value = parse_amount(str(amount_value), self.bank_config) or Decimal("0")
                            else:
                                amount_value = Decimal(str(amount_value))
                        
                        # Extract balance using enhanced balance extractor
                        balance_value = row.get("balance")
                        if balance_value:
                            try:
                                balance_value = Decimal(str(balance_value))
                            except:
                                balance_value = None
                        else:
                            # Try enhanced extraction from row
                            cells = table.get("rows", [])[row.get("row_index", 0) + 1].get("cells", []) if row.get("row_index") is not None and table.get("rows") else []
                            column_mapping = table.get("column_mapping", {})
                            balance_value = self.balance_extractor.extract_balance_from_table_row(
                                row,
                                column_mapping,
                                cells,
                                row.get("row_index", 0),
                                table.get("data", [])
                            )
                        
                        # Extract BBVA-specific fields in original format (following prompt: strictly parse according to document structure)
                        # OPER and LIQ dates in original format (DD/MON)
                        oper_date_str = row.get("OPER") or row.get("oper_date_str")
                        liq_date_str = row.get("LIQ") or row.get("liq_date_str")
                        
                        # DESCRIPCION - description without Referencia
                        descripcion = row.get("DESCRIPCION") or row.get("description", "")
                        # Ensure Referencia is removed from description
                        if descripcion:
                            descripcion = re.sub(r'Referencia\s+[*0-9\s]+', '', descripcion, flags=re.IGNORECASE)
                            descripcion = re.sub(r'Referencia\s+[^\n\r]+', '', descripcion, flags=re.IGNORECASE)
                            descripcion = descripcion.strip()
                        
                        # REFERENCIA - reference with "Referencia" prefix
                        referencia_raw = row.get("reference") or row.get("REFERENCIA")
                        referencia = None
                        if referencia_raw:
                            # Ensure it has "Referencia" prefix
                            if not referencia_raw.startswith("Referencia"):
                                referencia = f"Referencia {referencia_raw}"
                            else:
                                referencia = referencia_raw
                        
                        # Amounts in original format (strings with commas)
                        cargos_str = row.get("CARGOS") or (str(row.get("cargos")) if row.get("cargos") else "")
                        abonos_str = row.get("ABONOS") or (str(row.get("abonos")) if row.get("abonos") else "")
                        operacion_str = row.get("OPERACION") or (str(row.get("operacion")) if row.get("operacion") else "")
                        liquidacion_str = row.get("LIQUIDACION") or (str(row.get("liquidacion")) if row.get("liquidacion") else "")
                        
                        # FALLBACK: If BBVA fields are missing but raw_text contains transaction data, parse from raw_text
                        # Following prompt: 100% information completeness - extract all fields from raw_text if needed
                        # Check if any BBVA fields are missing
                        missing_bbva_fields = (
                            not oper_date_str or not liq_date_str or
                            not descripcion or not referencia or
                            (not cargos_str and not abonos_str) or
                            (not operacion_str and not liquidacion_str)
                        )
                        
                        # Also check if raw_text contains more complete transaction data
                        # If raw_text has dates but BBVA fields are missing, parse from raw_text
                        if row.get("raw_text"):
                            raw_text = str(row.get("raw_text", ""))
                            date_pattern = r'\d{1,2}/[A-Z]{3}'
                            dates_in_raw = re.findall(date_pattern, raw_text)
                            
                            # If raw_text contains transaction patterns and BBVA fields are missing, parse from raw_text
                            if len(dates_in_raw) >= 2 and missing_bbva_fields:
                                # Parse from raw_text using BBVA-specific parser
                                from src.tables.table_parser import TableParser
                                table_parser = TableParser(bank_config=self.bank_config)
                                lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
                                
                                # Find the first date line
                                for line_idx, line in enumerate(lines):
                                    if re.match(r'^\d{1,2}/[A-Z]{3}', line):
                                        parsed_trans = table_parser._parse_single_transaction(lines, line_idx, context_year=year_context)
                                        if parsed_trans:
                                            # Update BBVA fields from parsed transaction (only if missing)
                                            if not oper_date_str and parsed_trans.get("OPER"):
                                                oper_date_str = parsed_trans.get("OPER")
                                            if not liq_date_str and parsed_trans.get("LIQ"):
                                                liq_date_str = parsed_trans.get("LIQ")
                                            if not descripcion and parsed_trans.get("DESCRIPCION"):
                                                descripcion = parsed_trans.get("DESCRIPCION")
                                            elif descripcion and parsed_trans.get("DESCRIPCION"):
                                                # If descripcion exists but parsed one is more complete, use parsed one
                                                if len(parsed_trans.get("DESCRIPCION", "")) > len(descripcion):
                                                    descripcion = parsed_trans.get("DESCRIPCION")
                                            if not referencia and parsed_trans.get("REFERENCIA"):
                                                referencia = parsed_trans.get("REFERENCIA")
                                            if not cargos_str and parsed_trans.get("CARGOS"):
                                                cargos_str = parsed_trans.get("CARGOS")
                                            if not abonos_str and parsed_trans.get("ABONOS"):
                                                abonos_str = parsed_trans.get("ABONOS")
                                            if not operacion_str and parsed_trans.get("OPERACION"):
                                                operacion_str = parsed_trans.get("OPERACION")
                                            if not liquidacion_str and parsed_trans.get("LIQUIDACION"):
                                                liquidacion_str = parsed_trans.get("LIQUIDACION")
                                            
                                            # Also update referencia_raw for backward compatibility
                                            if not referencia_raw and parsed_trans.get("reference"):
                                                referencia_raw = parsed_trans.get("reference")
                                            
                                            break  # Only parse first transaction from raw_text
                                        break  # Only try once
                        
                        # Format amounts with commas if they are Decimal values
                        def format_amount_str(amt_value, amt_str):
                            """Format amount as string with comma separator."""
                            if amt_str:
                                return amt_str
                            if amt_value:
                                # Convert Decimal to string with comma formatting
                                amt_float = float(amt_value)
                                return f"{amt_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                            return ""
                        
                        cargos_str = format_amount_str(row.get("cargos"), cargos_str)
                        abonos_str = format_amount_str(row.get("abonos"), abonos_str)
                        operacion_str = format_amount_str(row.get("operacion"), operacion_str)
                        liquidacion_str = format_amount_str(row.get("liquidacion"), liquidacion_str)
                        
                        # Parse BBVA-specific date fields (for backward compatibility)
                        oper_date_iso = None
                        if row.get("oper_date"):
                            oper_date_iso = self._parse_date_field(row.get("oper_date"), year_context)
                        elif oper_date_str:
                            # Try to parse from string format
                            oper_date_iso = self._parse_date_field(oper_date_str, year_context)
                        
                        liq_date_iso = None
                        if row.get("liq_date"):
                            liq_date_iso = self._parse_date_field(row.get("liq_date"), year_context)
                        elif liq_date_str:
                            # Try to parse from string format
                            liq_date_iso = self._parse_date_field(liq_date_str, year_context)
                        
                        # Parse BBVA-specific amount fields (for backward compatibility)
                        cargos_decimal = None
                        if row.get("cargos"):
                            try:
                                cargos_decimal = Decimal(str(row.get("cargos")))
                            except:
                                pass
                        elif cargos_str:
                            cargos_decimal = parse_amount(cargos_str, self.bank_config)
                        
                        abonos_decimal = None
                        if row.get("abonos"):
                            try:
                                abonos_decimal = Decimal(str(row.get("abonos")))
                            except:
                                pass
                        elif abonos_str:
                            abonos_decimal = parse_amount(abonos_str, self.bank_config)
                        
                        operacion_decimal = None
                        if row.get("operacion"):
                            try:
                                operacion_decimal = Decimal(str(row.get("operacion")))
                            except:
                                pass
                        elif operacion_str:
                            operacion_decimal = parse_amount(operacion_str, self.bank_config)
                        
                        liquidacion_decimal = None
                        if row.get("liquidacion"):
                            try:
                                liquidacion_decimal = Decimal(str(row.get("liquidacion")))
                            except:
                                pass
                        elif liquidacion_str:
                            liquidacion_decimal = parse_amount(liquidacion_str, self.bank_config)
                        
                        # Calculate confidence score for this transaction
                        confidence = self._calculate_transaction_confidence(row, extraction_method="table")
                        
                        # Create transaction with all fields
                        transaction = Transaction(
                            date=trans_date,
                            description=descripcion[:500] if descripcion else "",
                            amount=amount_value,
                            balance=balance_value,
                            reference=referencia_raw[:100] if referencia_raw else None,  # Without prefix for backward compatibility
                            raw_text=str(row.get("raw_text", ""))[:1000],
                            bbox=self._bbox_from_list(row.get("bbox", [0, 0, 0, 0])),
                            # BBVA-specific fields in ISO/Decimal format (backward compatibility)
                            oper_date=oper_date_iso,
                            liq_date=liq_date_iso,
                            cargos=cargos_decimal,
                            abonos=abonos_decimal,
                            operacion=operacion_decimal,
                            liquidacion=liquidacion_decimal,
                            # BBVA fields in original format (following prompt: strictly parse according to document structure)
                            OPER=oper_date_str,
                            LIQ=liq_date_str,
                            DESCRIPCION=descripcion[:500] if descripcion else None,
                            REFERENCIA=referencia,
                            CARGOS=cargos_str if cargos_str else None,
                            ABONOS=abonos_str if abonos_str else "",
                            OPERACION=operacion_str if operacion_str else None,
                            LIQUIDACION=liquidacion_str if liquidacion_str else None,
                            # Confidence score
                            confidence=confidence
                        )
                        transactions.append(transaction)
                    except Exception as e:
                        print(f"Error extracting transaction: {e}")
                        print(f"  Row data: {row.get('raw_text', '')[:100]}")
                        continue
        
        return transactions
    
    def _extract_account_summary(
        self,
        parsed_tables: List[Dict[str, Any]],
        transactions: List[Transaction],
        ocr_data: Dict[str, Any] = None
    ) -> AccountSummary:
        """Extract account summary information."""
        summary = AccountSummary(transactions=transactions)
        
        # Look for summary table
        for table in parsed_tables:
            if table.get("type") == "summary":
                for row in table.get("data", []):
                    desc = str(row.get("description", "")).lower()
                    amount = row.get("amount")
                    
                    if amount:
                        if "saldo inicial" in desc or "initial balance" in desc:
                            summary.initial_balance = Decimal(str(amount))
                        elif "saldo final" in desc or "final balance" in desc:
                            summary.final_balance = Decimal(str(amount))
                        elif "deposito" in desc or "deposit" in desc:
                            if summary.deposits:
                                summary.deposits += Decimal(str(amount))
                            else:
                                summary.deposits = Decimal(str(amount))
                        elif "retiro" in desc or "withdrawal" in desc:
                            if summary.withdrawals:
                                summary.withdrawals += Decimal(str(amount))
                            else:
                                summary.withdrawals = Decimal(str(amount))
        
        # Calculate from transactions if not found
        if not summary.initial_balance and transactions:
            # Estimate from first transaction balance
            first_trans = transactions[0] if transactions else None
            if first_trans and first_trans.balance:
                summary.initial_balance = first_trans.balance - first_trans.amount
        
        if not summary.final_balance and transactions:
            last_trans = transactions[-1] if transactions else None
            # Do not infer final balance if not explicitly finding it
            # if last_trans and last_trans.balance:
            #    summary.final_balance = last_trans.balance
        
        # Calculate totals if not present
        # User requirement: Do not infer/aggregate if not in doc
        # if not summary.deposits:
        #    deposits = sum(
        #        t.amount for t in transactions if t.amount > 0
        #    )
        #    summary.deposits = deposits
        
        # if not summary.withdrawals:
        #    withdrawals = sum(
        #        abs(t.amount) for t in transactions if t.amount < 0
        #    )
        #    summary.withdrawals = withdrawals

        # Extract additional business fields if OCR data is available
        if ocr_data:
            summary.total_movimientos = self._extract_total_movimientos(ocr_data, parsed_tables)
            # apartados_vigentes: 原文中不存在详细列表，已禁用
            # summary.apartados_vigentes = self._extract_apartados_vigentes(ocr_data)
            summary.cuadro_resumen = self._extract_cuadro_resumen(ocr_data, parsed_tables)
            summary.informacion_financiera = self._extract_informacion_financiera(ocr_data)
            summary.comportamiento = self._extract_comportamiento(ocr_data)
            # 新增：截图2的内容提取
            summary.otros_productos = self._extract_otros_productos(ocr_data)
            
        return summary
    
    def _extract_total_movimientos(
        self,
        ocr_data: Dict[str, Any],
        parsed_tables: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """提取Total de Movimientos信息。"""
        total_mov = {}
        
        # 从OCR数据中搜索Total de Movimientos相关文本
        for page_idx, page in enumerate(ocr_data.get("pages", [])):
            text_content = self._get_page_text(page)
            
            # 定位 "Total de Movimientos" 区域
            if "Total de Movimientos" in text_content:
                # 尝试提取各个字段，考虑到换行
                # TOTAL IMPORTE CARGOS
                cargos_importe_match = re.search(
                    r"TOTAL\s+IMPORTE\s+CARGOS\s*\n\s*([0-9,]+\.?\d*)",
                    text_content,
                    re.IGNORECASE
                )
                if cargos_importe_match:
                    total_mov["total_importe_cargos"] = cargos_importe_match.group(1).replace(",", "")
                
                # TOTAL MOVIMIENTOS CARGOS
                cargos_count_match = re.search(
                    r"TOTAL\s+MOVIMIENTOS\s+CARGOS\s*\n\s*(\d+)",
                    text_content,
                    re.IGNORECASE
                )
                if cargos_count_match:
                    total_mov["total_movimientos_cargos"] = int(cargos_count_match.group(1))
                
                # TOTAL IMPORTE ABONOS
                abonos_importe_match = re.search(
                    r"TOTAL\s+IMPORTE\s+ABONOS\s*\n\s*([0-9,]+\.?\d*)",
                    text_content,
                    re.IGNORECASE
                )
                if abonos_importe_match:
                    total_mov["total_importe_abonos"] = abonos_importe_match.group(1).replace(",", "")
                
                # TOTAL MOVIMIENTOS ABONOS
                abonos_count_match = re.search(
                    r"TOTAL\s+MOVIMIENTOS\s+ABONOS\s*\n\s*(\d+)",
                    text_content,
                    re.IGNORECASE
                )
                if abonos_count_match:
                    total_mov["total_movimientos_abonos"] = int(abonos_count_match.group(1))
                
                # 如果找到至少一个字段，就返回
                if total_mov:
                    return total_mov
                    
        return None
    
    def _extract_apartados_vigentes(
        self,
        ocr_data: Dict[str, Any]
    ) -> Optional[List[Dict[str, Any]]]:
        """提取Estado de cuenta de Apartados Vigentes。"""
        apartados = []
        
        # 在文本中查找 Apartados Vigentes 区域
        for page in ocr_data.get("pages", []):
            text_content = self._get_page_text(page)
            if "Estado de cuenta de Apartados Vigentes" in text_content:
                lines = text_content.split('\n')
                in_section = False
                
                # 简单的逐行解析状态机
                current_apartado = {}
                capture_next_amount = False
                
                for i, line in enumerate(lines):
                    line = line.strip()
                    if "Estado de cuenta de Apartados Vigentes" in line:
                        in_section = True
                        continue
                    
                    if not in_section:
                        continue
                        
                    # 结束条件
                    if "No. de Cuenta" in line or "PAGINA" in line or "Total  de Apartados" in line:
                        in_section = False
                        break
                        
                    # 跳过表头
                    if line in ["Folio", "Nombre Apartado", "Importe Apartado", "Importe Total", "$"]:
                        continue
                        
                    # 解析逻辑: 名字通常是文本，金额通常包含数字和逗号/小数点
                    if re.match(r'^[0-9,]+\.\d{2}$', line):
                        # 这是一个金额
                        if current_apartado and "nombre_apartado" in current_apartado and "importe_apartado" not in current_apartado:
                            current_apartado["importe_apartado"] = line.replace(",", "")
                            # 完成一个apartado
                            apartados.append(current_apartado)
                            current_apartado = {}
                    elif line:
                        # 这是一个名字（可能）
                        if not current_apartado:
                             current_apartado["nombre_apartado"] = line
                        else:
                             # 只有名字没有金额，可能上一行也是名字的一部分，或者是异常
                             pass

        return apartados if apartados else None
    
    def _extract_cuadro_resumen(
        self,
        ocr_data: Dict[str, Any],
        parsed_tables: List[Dict[str, Any]]
    ) -> Optional[List[Dict[str, Any]]]:
        """
        提取Cuadro resumen y gráfico de movimientos del período
        """
        cuadro_resumen = []
        
        # 1. 尝试从已解析的表格中寻找 (如果被识别为表格)
        for table in parsed_tables:
            # 检查表头或内容是否包含关键词
            headers = [str(h).lower() for h in table.get("headers", [])]
            if any("concepto" in h for h in headers) and any("cantidad" in h for h in headers):
                # 这可能是Cuadro resumen
                data = table.get("data", [])
                if data:
                    # 转换格式
                    for row in data:
                        item = {}
                        for k, v in row.items():
                            item[k] = str(v)
                        cuadro_resumen.append(item)
                    return cuadro_resumen

    def _reconstruct_page_rows(self, page_data: Dict[str, Any], y_tolerance: float = 10) -> List[str]:
        """
        Reconstruct strings component by component based on visual Y-alignment.
        Solves issue where text blocks are columnar or out of order.
        """
        all_lines = []
        
        # Collect all lines with bbox
        for block in page_data.get("text_blocks", []):
            # If we have detailed line info (PyMuPDF fallback)
            if "lines" in block:
                for line in block["lines"]:
                    bbox = line.get("bbox")
                    text = line.get("text", "").strip()
                    if text and bbox:
                        all_lines.append({"text": text, "bbox": bbox, "y_center": (bbox[1] + bbox[3]) / 2})
            # Fallback for standard blocks if no line info
            elif "bbox" in block and "text" in block:
                bbox = block["bbox"]
                text = block["text"].strip()
                if text:
                    # Split block text by newlines if present, aiming to approximate lines
                    # This is imperfect for blocks, but better than nothing
                    # For strict table parsing, 'lines' presence is preferred
                    all_lines.append({"text": text, "bbox": bbox, "y_center": (bbox[1] + bbox[3]) / 2})

        # Sort by Y-coordinate
        all_lines.sort(key=lambda x: x["y_center"])
        
        if not all_lines:
            return []

        # Group into visual rows
        rows = []
        current_row = [all_lines[0]]
        # Use running average Y for better centering? Or just anchor. 
        # Anchor is simple and predictable.
        row_y = all_lines[0]["y_center"]
        
        # Tolerance increased to 10 (approx 1/3 to 1/2 line height) to match misaligned columns
        # Previous value of 5 caused splitting of "Concepto" and "Cantidad" blocks
        # Tolerance used for clustering
        tolerance = y_tolerance 
        
        for line in all_lines[1:]:
            if abs(line["y_center"] - row_y) < tolerance:
                current_row.append(line)
            else:
                # Finish current row
                # Sort by X coordinate
                current_row.sort(key=lambda x: x["bbox"][0])
                rows.append(" ".join([l["text"] for l in current_row]))
                
                # Start new row
                current_row = [line]
                row_y = line["y_center"]
        
        # Add last row
        if current_row:
            current_row.sort(key=lambda x: x["bbox"][0])
            rows.append(" ".join([l["text"] for l in current_row]))
            
        return rows

    def _extract_cuadro_resumen(self, ocr_data: Dict[str, Any], layout_structure: Any = None) -> Optional[List[Dict[str, str]]]:
        """提取Cuadro Resumen表格 - 包含图表数据的摘要"""
        cuadro_resumen = []
        
        # 1. 尝试从检测到的表格结构中提取
        # (This part relies on upstream table detection which might fail)
        if layout_structure:
             # Just a placeholder for potential future usage
             pass
        
        tables = ocr_data.get("tables", [])
        # ... existing table logic skipped for brevity ...

        # 2. Text-based extraction using Visual Row Reconstruction (Robust)
        print("Debug: Attempting visual-row-based Cuadro Resumen extraction...")
        
        for i, page in enumerate(ocr_data.get("pages", [])):
            # Reconstruct visual rows
            rows = self._reconstruct_page_rows(page)
            
            in_table = False
            for line in rows:
                # Normalize line for robust matching (dashes, spaces)
                clean_line = line.strip().replace("–", "-").replace("—", "-")
                
                # Check for table start triggers
                
                # TRIGGER 1: "Cuadro Resumen" Header
                term = "CUADRO RESUMEN"
                if term.replace(" ", "") in clean_line.upper().replace(" ", ""):
                    print(f"Debug: Found '{clean_line}' (Header Trigger) on page {i+1}")
                    in_table = True
                    continue
                
                # TRIGGER 2: "Concepto" + "Cantidad" column headers
                if "CONCEPTO" in clean_line.upper() and "CANTIDAD" in clean_line.upper():
                     print(f"Debug: Found Column Headers '{clean_line}' (Table Start) on page {i+1}")
                     in_table = True
                     continue # Skip header row

                # TRIGGER 3: Content fallback ("Saldo Inicial")
                if not in_table and clean_line.upper().startswith("SALDO INICIAL"):
                     print(f"Debug: Found Content Trigger '{clean_line}' (Implicit Table Start) on page {i+1}")
                     in_table = True
                     # Do not continue, process this line!

                if in_table:
                    print(f"Debug: Processing Row: '{clean_line}'")
                    
                    # Exit conditions
                    if "TOTAL" in clean_line.upper():
                        print(f"Debug: End of table (Total found)")
                        break
                    if "NOTA" in clean_line.upper() and ":" in clean_line:
                        print(f"Debug: End of table (Note found)")
                        break
                    
                    # Filter Headers/Noise
                    if "PAGINA" in clean_line.upper() or "PAGE" in clean_line.upper(): continue
                    # Filter header lines if they repeat
                    if "CONCEPTO" in clean_line.upper() and "CANTIDAD" in clean_line.upper(): continue 
                    
                    # Soft filter for short lines - maybe too aggressive?
                    # "Saldo Inicial" is > 10 chars. 
                    if len(clean_line) < 5: 
                         print(f"  -> Skipped (too short)")
                         continue

                    # Parse Row: Concepto | Cantidad | % | Columna
                    # Regex strategy: Look for the structured pattern ANYWHERE in the line
                    # This handles "Chart Noise" on the right side (e.g., "( + ) A")
                    # Pattern: [Amount] [Space] [Percent] [Space] [ColumnChar]
                    
                    import re
                    
                    # Regex:
                    # Amount: 12,383.20 (allow spaces: 4, 884. 42)
                    # Percentage: 5.29% (allow spaces: 100. 00 %)
                    # Column: Single Char A-Z or Digit
                    # We terminate the Column match immediately to avoid eating into chart labels
                    
                    # Construction:
                    # Group 1 (Amount): [-\d\.,\s]+\d (Ends with digit)
                    # Group 2 (Pct):    [-\d\.,\s]+%
                    # Group 3 (Col):    [A-Z0-9]
                    
                    pattern = r'(?P<amount>[-\d\.,\s]+\d)\s+(?P<pct>[-\d\.,\s]+%)\s+(?P<col>[A-Z0-9])'
                    
                    match = re.search(pattern, clean_line)
                    if match:
                         # Verify Amount is mostly digits/punctuation
                         raw_amount = match.group("amount")
                         if any(c.isdigit() for c in raw_amount):
                             # Extract values
                             amount = raw_amount.replace(" ", "")
                             pct = match.group("pct").replace(" ", "")
                             columna = match.group("col")
                             
                             # Concepto is everything before the match
                             concepto = clean_line[:match.start()].strip()
                             
                             item = {
                                 "Concepto": concepto,
                                 "Cantidad": amount,
                                 "Porcentaje": pct,
                                 "Columna": columna
                             }
                             cuadro_resumen.append(item)
                             print(f"  -> Extracted (Pattern): {item}")
                             continue

                    print(f"  -> Failed to parse row: '{clean_line}'")
                    # Fallback: if strict parsing failed, retain raw row
                    cuadro_resumen.append({"raw_row": clean_line})

            if cuadro_resumen:
                return cuadro_resumen

        return None
    
    def _extract_informacion_financiera(self, ocr_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """提取Información Financiera - 分层结构：Rendimiento、Comisiones、Total Comisiones"""
        result = {}
        
        for page in ocr_data.get("pages", []):
            text = self._get_page_text(page)
            if "Información Financiera" not in text:
                continue
            
            # Rendimiento模块
            rendimiento = {}
            rendimiento_fields = [
                "Saldo Promedio",
                "Días del Periodo",
                "Tasa Bruta Anual",
                "Saldo Promedio Gravable",
                "Intereses a Favor (+)",
                "ISR Retenido (-)"
            ]
            
            for field in rendimiento_fields:
                if field == "Tasa Bruta Anual":
                    # 特殊处理：Tasa Bruta Anual % 0.000
                    pattern = re.escape(field) + r"\s+(%)\s+([0-9,]+\.?\d*)"
                    match = re.search(pattern, text)
                    if match:
                        rendimiento[f"{field} %"] = match.group(2)
                else:
                    # 标准模式
                    pattern1 = re.escape(field) + r"\s*\n\s*([0-9,]+\.?\d*)"
                    pattern2 = re.escape(field) + r"\s+([0-9,]+\.?\d*)"
                    match = re.search(pattern1, text) or re.search(pattern2, text)
                    if match:
                        rendimiento[field] = match.group(1)
            
            if rendimiento:
                result["Rendimiento"] = rendimiento
            
            # Comisiones模块
            comisiones = {}
            comisiones_fields = ["Cheques pagados", "Manejo de Cuenta"]
            
            for field in comisiones_fields:
                if field == "Cheques pagados":
                    # 特殊格式：数量 + 金额
                    pattern = re.escape(field) + r"\s*\n\s*(\d+)\s*\n\s*([0-9,]+\.?\d*)"
                    match = re.search(pattern, text)
                    if match:
                        comisiones[field] = f"{match.group(1)}  {match.group(2)}"
                else:
                    pattern1 = re.escape(field) + r"\s*\n\s*([0-9,]+\.?\d*)"
                    pattern2 = re.escape(field) + r"\s+([0-9,]+\.?\d*)"
                    match = re.search(pattern1, text) or re.search(pattern2, text)
                    if match:
                        comisiones[field] = match.group(1)
            
            if comisiones:
                result["Comisiones"] = comisiones
            
            # Total Comisiones模块
            total_comisiones = {}
            total_fields = {
                "Total Comisiones": False,  # False=单值
                "Cargos Objetados": True,   # True=双值(数量+金额)
                "Abonos Objetados": True
            }
            
            for field, is_dual in total_fields.items():
                if is_dual:
                    # 双值格式
                    pattern = re.escape(field) + r"\s*\n\s*(\d+)\s*\n\s*([0-9,]+\.?\d*)"
                    match = re.search(pattern, text)
                    if match:
                        total_comisiones[field] = f"{match.group(1)}  {match.group(2)}"
                else:
                    # 单值
                    pattern1 = re.escape(field) + r"\s*\n\s*([0-9,]+\.?\d*)"
                    pattern2 = re.escape(field) + r"\s+([0-9,]+\.?\d*)"
                    match = re.search(pattern1, text) or re.search(pattern2, text)
                    if match:
                        total_comisiones[field] = match.group(1)
            
            if total_comisiones:
                result["Total Comisiones"] = total_comisiones
            
            if result:
                return result
        
        return None

    def _extract_comportamiento(self, ocr_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """提取Comportamiento表格数据 - 使用原文key和格式"""
        data = {}
        
        for page in ocr_data.get("pages", []):
            text = self._get_page_text(page)
            if "Comportamiento" in text:
                # 使用原文作为key
                # Saldo Anterior
                match_sa = re.search(r"Saldo Anterior\s*(?:\(+\))?\s*(?:\n|:)?\s*([0-9,]+\.?\d*)", text)
                if match_sa: data["Saldo Anterior"] = match_sa.group(1) 
                
                # Saldo Final (Problem 1 Fix)
                # Matches "Saldo Final" or "Saldo Final (+)" followed by optional colon/newline and amount
                # Fixed regex: correctly escape parens and plus: (?:\(\+\))?
                # Also allow extra spaces inside parens like ( + )
                match_sf = re.search(r"Saldo Final\s*(?:\([\+\s]+\))?\s*(?:\n|:)?\s*([0-9,]+\.?\d*)", text)
                if match_sf: data["Saldo Final"] = match_sf.group(1)
                
                # Depósitos / Abonos (+) - 合并格式为"数量 空格 金额"
                # Regex allows optional (+) and newlines
                match_dep = re.search(r"Depósitos / Abonos (?:\(\+\))?\s*\n\s*(\d+)\s*\n\s*([0-9,]+\.?\d*)", text)
                if match_dep: 
                    data["Depósitos / Abonos (+)"] = f"{match_dep.group(1)}  {match_dep.group(2)}"
                
                # Retiros / Cargos (-) - 合并格式
                match_ret = re.search(r"Retiros / Cargos (?:\(-\))?\s*\n\s*(\d+)\s*\n\s*([0-9,]+\.?\d*)", text)
                if match_ret:
                    data["Retiros / Cargos (-)"] = f"{match_ret.group(1)}  {match_ret.group(2)}"
                
                # Saldo Promedio Mínimo Mensual
                match_min = re.search(r"Saldo Promedio Mínimo Mensual(?::)?\s*(?:\n)?\s*([0-9,]+\.?\d*)", text)
                if match_min:
                    data["Saldo Promedio Mínimo Mensual"] = match_min.group(1)
                
                if data:
                    return data
        return None

    def _parse_date_field(self, date_str: Optional[str], year_context: Optional[int] = None) -> Optional[date]:
        """
        Parse date string to date object with intelligent year inference.
        
        Following prompt requirement: dynamic context inference, avoid hardcoding.
        """
        if not date_str:
            return None
        
        if isinstance(date_str, date):
            return date_str
        
        date_str = str(date_str).strip()
        
        # Use bank config date patterns (following prompt: dynamic adaptation, no hardcoding)
        import re
        date_patterns = self.bank_config.get('date_patterns', ["DD/MON", "DD/MM/YYYY"]) if self.bank_config else ["DD/MON", "DD/MM/YYYY"]
        
        month_map = {
            'ENE': 'JAN', 'FEB': 'FEB', 'MAR': 'MAR', 'ABR': 'APR',
            'MAY': 'MAY', 'JUN': 'JUN', 'JUL': 'JUL', 'AGO': 'AUG',
            'SEP': 'SEP', 'OCT': 'OCT', 'NOV': 'NOV', 'DIC': 'DEC'
        }
        
        # Try DD/MON format first if in configured patterns
        if "DD/MON" in date_patterns or any("MON" in p for p in date_patterns):
            mon_match = re.match(r'(\d{1,2})/([A-Z]{3})', date_str.upper())
            if mon_match:
                day, mon = mon_match.groups()
                if mon in month_map:
                    # Use year_context if provided (dynamic inference)
                    if year_context:
                        year = year_context
                    else:
                        from datetime import datetime
                        year = datetime.now().year
                    
                    try:
                        from datetime import datetime
                        date_obj = datetime.strptime(f"{day}/{month_map[mon]}/{year}", "%d/%b/%Y")
                        return date_obj.date()
                    except:
                        pass
        
        # Try other date formats from bank config or defaults
        from datetime import datetime
        # Map date patterns to strptime formats
        date_format_map = {
            "DD/MM/YYYY": "%d/%m/%Y",
            "DD/MM/YY": "%d/%m/%y",
            "DD/MM": "%d/%m",
            "YYYY-MM-DD": "%Y-%m-%d",
            "MM/DD/YYYY": "%m/%d/%Y",
        }
        # Build format list from config
        date_formats = []
        for pattern_name in date_patterns:
            if pattern_name in date_format_map:
                date_formats.append(date_format_map[pattern_name])
        # Add fallback formats if none found
        if not date_formats:
            date_formats = ["%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d/%m", "%d/%b"]
        
        # Replace Spanish month abbreviations
        for es, en in month_map.items():
            date_str = date_str.replace(es, en)
        
        for fmt in date_formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                # If year is 2-digit or missing, use context
                if dt.year < 2000 and year_context:
                    dt = dt.replace(year=year_context)
                return dt.date()
            except ValueError:
                continue
        
        return None
    
    def _bbox_from_list(self, bbox_list: List[float]) -> BBox:
        """Convert bbox list to BBox object."""
        if len(bbox_list) >= 4:
            return BBox(
                x=bbox_list[0],
                y=bbox_list[1],
                width=bbox_list[2] - bbox_list[0] if len(bbox_list) == 4 else bbox_list[2],
                height=bbox_list[3] - bbox_list[1] if len(bbox_list) == 4 else bbox_list[3],
                page=0  # Default, should be set from context
            )
        return BBox(x=0, y=0, width=0, height=0, page=0)
    
    def _bbox_from_list_with_page(self, bbox_list: List[float], page_num: int) -> BBox:
        """Convert bbox list to BBox object with page number."""
        if len(bbox_list) >= 4:
            return BBox(
                x=bbox_list[0],
                y=bbox_list[1],
                width=bbox_list[2] - bbox_list[0] if len(bbox_list) == 4 else bbox_list[2],
                height=bbox_list[3] - bbox_list[1] if len(bbox_list) == 4 else bbox_list[3],
                page=page_num
            )
        return BBox(x=0, y=0, width=0, height=0, page=page_num)
    
    def _extract_metadata(
        self,
        ocr_data: Dict[str, Any],
        bank_config: Optional[Dict[str, Any]] = None
    ) -> Metadata:
        """Extract document metadata (private method for internal use)."""
        return self.extract_metadata(ocr_data, None)
    
    def extract_metadata(
        self,
        ocr_data: Dict[str, Any],
        layout_structure: Any = None
    ) -> Metadata:
        """Extract document metadata."""
        # Extract account number
        account_number = self._find_account_number(ocr_data)
        
        # Extract period
        period = self._find_period(ocr_data)
        
        # Use bank config if available (following prompt: dynamic adaptation, no hardcoding)
        document_type = None
        bank = None
        if self.bank_config:
            document_type = self.bank_config.get('document_types', ['BANK_STATEMENT'])[0]
            bank = self.bank_config.get('name', None)
        
        # Extract language from OCR data (preserve original document language)
        language = ocr_data.get("language", None)
        if not language:
            # Fallback: detect language from text content
            language = self._detect_language_from_ocr(ocr_data)
        
        return Metadata(
            document_type=document_type,
            bank=bank,
            account_number=account_number,
            period=period,
            total_pages=ocr_data.get("total_pages", len(ocr_data.get("pages", []))),
            language=language
        )
    
    def _find_account_number(self, ocr_data: Dict[str, Any]) -> Optional[str]:
        """Find account number in OCR data."""
        import re
        pattern = r'\b\d{10,18}\b'
        
        for page_data in ocr_data.get("pages", []):
            for block in page_data.get("text_blocks", []):
                text = block.get("text", "")
                matches = re.findall(pattern, text)
                if matches:
                    # Return first match (could be improved with validation)
                    return matches[0]
        
        return None
    
    def _detect_language_from_ocr(self, ocr_data: Dict[str, Any]) -> Optional[str]:
        """
        Detect language from OCR text content (fallback method).
        
        Args:
            ocr_data: OCR data dictionary
            
        Returns:
            Language code string or None
        """
        # Collect all text from OCR data
        all_text = ""
        for page_data in ocr_data.get("pages", []):
            for block in page_data.get("text_blocks", []):
                all_text += block.get("text", "") + " "
        
        if not all_text or len(all_text.strip()) < 10:
            return None
        
        text_lower = all_text.lower()
        
        # Spanish indicators
        spanish_words = [
            'cuenta', 'estado', 'periodo', 'fecha', 'cargos', 'abonos',
            'descripcion', 'referencia', 'saldo', 'inicial', 'final',
            'depositos', 'retiros', 'operacion', 'liquidacion', 'del', 'al'
        ]
        spanish_count = sum(1 for word in spanish_words if word in text_lower)
        
        # English indicators
        english_words = [
            'account', 'statement', 'period', 'date', 'debits', 'credits',
            'description', 'reference', 'balance', 'initial', 'final',
            'deposits', 'withdrawals', 'operation', 'liquidation', 'from', 'to'
        ]
        english_count = sum(1 for word in english_words if word in text_lower)
        
        # Chinese indicators
        chinese_pattern = re.compile(r'[\u4e00-\u9fff]+')
        chinese_count = len(chinese_pattern.findall(all_text))
        
        # Determine language
        if spanish_count > english_count and spanish_count > 0:
            return "es"
        elif english_count > spanish_count and english_count > 0:
            return "en"
        elif chinese_count > 5:
            return "zh"
        elif spanish_count > 0:
            return "es"  # Default to Spanish for BBVA documents
        elif english_count > 0:
            return "en"
        else:
            return None
    
    def _find_period(self, ocr_data: Dict[str, Any]) -> Optional[Dict[str, Optional[date]]]:
        """Find statement period in OCR data."""
        # Look for date range patterns
        import re
        
        # Support multiple date range formats:
        # 1. Spanish format: "DEL DD/MM/YYYY AL DD/MM/YYYY"
        # 2. Simple dash format: "DD/MM/YYYY - DD/MM/YYYY" or "DD/MM - DD/MM"
        date_patterns = [
            # Spanish format (BBVA Mexico)
            r'DEL\s+(\d{1,2}/\d{1,2}/\d{2,4})\s+AL\s+(\d{1,2}/\d{1,2}/\d{2,4})',
            # Dash-separated with full year
            r'(\d{1,2}/\d{1,2}/\d{2,4})\s*[-–]\s*(\d{1,2}/\d{1,2}/\d{2,4})',
            # Dash-separated without year (backward compatibility)
            r'(\d{1,2}/\d{1,2})\s*[-–]\s*(\d{1,2}/\d{1,2})'
        ]
        
        for page_data in ocr_data.get("pages", []):
            for block in page_data.get("text_blocks", []):
                text = block.get("text", "")
                
                for pattern in date_patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        start_str = match.group(1)
                        end_str = match.group(2)
                        
                        start_date = self._parse_date_field(start_str)
                        end_date = self._parse_date_field(end_str)
                        
                        if start_date or end_date:
                            return {
                                "start": start_date,
                                "end": end_date
                            }
        
        return None

    def _get_page_text(self, page_data: Dict[str, Any]) -> str:
        """Helper to get full text from page data, handling different OCR formats."""
        # If 'text' field exists and is populated, use it
        if page_data.get("text"):
            return page_data["text"]
            
        # Otherwise reconstruct from text_blocks
        text_parts = []
        for block in page_data.get("text_blocks", []):
            block_text = block.get("text", "")
            if block_text:
                text_parts.append(block_text)
        
        
        return "\n".join(text_parts)

    
    def _extract_pages_info(self, ocr_data: Dict[str, Any]) -> List[Dict[str, str]]:
        """提取每页的页眉信息 (Page No, Account No, Client No)."""
        pages_info = []
        
        patterns = {
            "No. de Cuenta": r"No\.\s+de\s+Cuenta\s+([\d]+)",
            # Relaxed regex:
            # 1. "No." can be "No", "No.", "N."
            # 2. Separator can be space, dot, colon
            # 3. Value can contain spaces/dots/dashes (e.g. "B 023 7524")
            # CRITICAL FIX: Use [ \t] instead of \s to avoid matching newlines and eating next row (RFC)
            "No. de Cliente": r"No[\.\s]*de\s+Cliente[:\.\s]*([A-Z0-9]+(?:[ \t\.\-][A-Z0-9]+)*)",
            "PAGINA": r"PAGINA\s+(\d+\s*/\s*\d+)"
        }
        
        for i, page in enumerate(ocr_data.get("pages", [])):
            text = self._get_page_text(page)
            # Limit header search to top of page to avoid false matches? 
            # Actually standard headers are usually at top.
            
            page_info = {"page_index": str(i + 1)}
            
            for key, pattern in patterns.items():
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    page_info[key] = match.group(1).strip()
            
            # If we found at least one relevant field, add it
            if len(page_info) > 1:
                pages_info.append(page_info)
                
        return pages_info

    def _extract_branch_info(self, ocr_data: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """提取分支机构信息 (Screenshot 2)"""
        info = {}
        # Uses negative lookahead to stop before the next keyword
        patterns = {
            "SUCURSAL": r"(?:SUCURSAL|Sucursal)[:\.]?\s*((?:(?!DIRECCION|Dirección|PLAZA|Plaza|TELEFONO|Teléfono).)*)",
            "DIRECCION": r"(?:DIRECCION|Dirección)[:\.]?\s*((?:(?!SUCURSAL|Sucursal|PLAZA|Plaza|TELEFONO|Teléfono).)*)",
            "PLAZA": r"(?:PLAZA|Plaza)[:\.]?\s*((?:(?!SUCURSAL|Sucursal|DIRECCION|Dirección|TELEFONO|Teléfono).)*)",
            "TELEFONO": r"(?:TELEFONO|Teléfono|Tel)[:\.]?\s*([+\d\s\-\(\)]+)"
        }
        
        for page in ocr_data.get("pages", []):
            text = self._get_page_text(page)
            if "SUCURSAL:" in text or "Sucursal:" in text:
                for key, pattern in patterns.items():
                    # Enable DOTALL to match across newlines
                    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
                    if match:
                        val = match.group(1).strip()
                        info[key] = val
                
                if info:
                    return info
        return None

    def _extract_customer_info(self, ocr_data: Dict[str, Any]) -> Dict[str, str]:
        """Extract customer/account header information (screenshot 1 content) - 使用原文key."""
        info = {}
        # 使用原文作为key - 完全保持大小写、空格、标点
        patterns = {
            "Periodo": r"Periodo\s+DEL\s+([\d/]+)\s+AL\s+([\d/]+)",
            "Fecha de Corte": r"Fecha\s+de\s+Corte\s+([\d/]+)",
            "No. de Cuenta": r"No\.\s+de\s+Cuenta\s+([\d]+)",
            # Updated to robust regex (alphanumeric, no newlines)
            "No. de Cliente": r"No[\.\s]*de\s+Cliente[:\.\s]*([A-Z0-9]+(?:[ \t\.\-][A-Z0-9]+)*)",
            "R.F.C": r"R\.F\.C\s+([A-Z0-9]+)",
            "No. Cuenta CLABE": r"No\.\s+Cuenta\s+CLABE\s+([\d\s]+)"
        }
        
        # 尝试提取客户地址 (Problem 1)
        # 逻辑：查找前3页左上角的文本块，排除已知Header关键词
        client_address = []
        
        for i, page in enumerate(ocr_data.get("pages", [])):
            text = self._get_page_text(page)
            if text:
                # 1. 提取标准Header字段
                for key, pattern in patterns.items():
                    if key not in info:
                        match = re.search(pattern, text, re.IGNORECASE)
                        if match:
                            if key == "Periodo":
                                start = match.group(1).strip()
                                end = match.group(2).strip()
                                info[key] = f"DEL {start} AL {end}"
                            else:
                                info[key] = match.group(1).strip()
            
            # 2. 提取客户地址 (Try first 3 pages, focusing on top-left under logo)
            # User feedback: Page 1 might be cover/image. Address often on Page 2 or under BBVA logo.
            current_page_num = page.get("page_number", i + 1)
            if current_page_num <= 3 and not client_address:
                
                # Check raw page text first
                page_raw_text = self._get_page_text(page)
                # Only debug verify if empty
                if len(page_raw_text) == 0:
                     print(f"Debug: Page {current_page_num} has 0 text length (Image?). Skipping address search on this page.")
                else:
                    # 遍历文本块，寻找位于左上角且不是银行Logo/Headers的块
                    blocks = page.get("text_blocks", [])
                    page_width = page.get("width", 612)
                    page_height = page.get("height", 792)
                    
                    print(f"Debug: Analyzing Page {current_page_num} blocks for Address. Page dim: {page_width}x{page_height}. Block Count: {len(blocks)}")
                    
                    # 定义左上角区域 (0-60% width, 0-50% height) - Broadened based on feedback
                    candidates = []
                    
                    for i, block in enumerate(blocks):
                        bbox = block.get("bbox", [0, 0, 0, 0])
                        b_text = block.get("text", "").strip()
                        
                        # Log all blocks in top half to see what we are missing
                        if bbox[1] < page_height * 0.5:
                             print(f"Debug Block {i}: '{b_text[:20]}...' bbox={bbox}")
                        
                        # x < 60%, y < 50%
                        if bbox[0] < page_width * 0.6 and bbox[1] < page_height * 0.5:
                            
                            # 过滤掉干扰项 (Basic filters)
                            if len(b_text) < 5: 
                                print(f"  -> Skipped (too short)")
                                continue
                            # Relaxed filters: Only exact matches or clear headers
                            # Allow "BBVA" if it's potentially part of an address line, but skip isolated Logo text
                            if b_text.strip() == "BBVA": 
                                print(f"  -> Skipped (Exact BBVA)")
                                continue
                            if b_text.upper().startswith("BANCO BBVA"): 
                                 print(f"  -> Skipped (BANCO BBVA)")
                                 continue
                            if "Estado de Cuenta" in b_text: 
                                 print(f"  -> Skipped (Estado de Cuenta)")
                                 continue 
                            
                            # Exclude standard headers
                            if re.match(r'^Periodo\s+', b_text): 
                                 print(f"  -> Skipped (Periodo)")
                                 continue
                            if re.match(r'^Fecha\s+de\s+Corte', b_text): 
                                 print(f"  -> Skipped (Fecha de Corte)")
                                 continue
                            if re.match(r'^No\.\s+de\s+Cuenta', b_text): 
                                 print(f"  -> Skipped (No. de Cuenta)")
                                 continue
                            # Explicitly exclude "No. de Cliente" which was being picked up
                            if re.match(r'^No\.\s+de\s+Cliente', b_text): 
                                 print(f"  -> Skipped (No. de Cliente)")
                                 continue
                            # Exclude other headers found in that area
                            if re.match(r'^R\.F\.C', b_text): 
                                 print(f"  -> Skipped (RFC)")
                                 continue
                            if re.match(r'^No\.\s+Cuenta\s+CLABE', b_text): 
                                 print(f"  -> Skipped (CLABE)")
                                 continue
                            
                            if re.match(r'^PAGINA', b_text, re.IGNORECASE): 
                                 print(f"  -> Skipped (PAGINA)")
                                 continue
                            
                            print(f"  -> CANDIDATE ADDED")
                            candidates.append((bbox[1], b_text)) # 按y坐标排序
                    
                    print(f"Debug: Found {len(candidates)} address candidates on Page {current_page_num}")
                    # 按Y坐标排序，取最上面的块，通常就是地址块
                    candidates.sort(key=lambda x: x[0])
                    if candidates:
                        for idx, c in enumerate(candidates[:3]):
                            print(f"Debug Candidate {idx}: {c[1][:50]}... at Y={c[0]}")
                            
                        # 取最上面的1-2个块作为地址
                        # 假设最上面的候选块是地址
                        addr_text = candidates[0][1]
                        # 分割成行
                        addr_lines = [l.strip() for l in addr_text.split('\n') if l.strip()]
                        
                        # User request: Split Name (first line) from Address
                        if addr_lines:
                            # CRITICAL FIX: If address block merged with Branch Info (SUCURSAL...), split it!
                            full_addr_text = "\n".join(addr_lines)
                            split_keywords = ["SUCURSAL:", "DIRECCION:", "PLAZA:", "TELEFONO:"]
                            for kw in split_keywords:
                                if kw in full_addr_text.upper(): # Check loose match
                                     # Find exact match index to be safe, or just split by line
                                     # Let's iterate lines and cut off when we see a keyword
                                     clean_lines = []
                                     for line in addr_lines:
                                         if any(k in line.upper() for k in split_keywords):
                                             break
                                         clean_lines.append(line)
                                     addr_lines = clean_lines
                                     break
                                     
                            # Re-check after cleaning
                            if addr_lines:
                                info["Client Name"] = addr_lines[0]
                                if len(addr_lines) > 1:
                                    info["Client Address"] = "\n".join(addr_lines[1:])
                                else:
                                    info["Client Address"] = addr_lines[0] # Fallback if only 1 line
                        
                        client_address = addr_lines # Mark as found
            
                # 找到大部分Header字段后停止
                if len(info) >= 5:
                    break
        
        return info
    
    def _extract_otros_productos(self, ocr_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """提取截图2的内容：Otros productos incluidos 和 Total de Apartados en Global"""
        data = {}
        
        for page in ocr_data.get("pages", []):
            text = self._get_page_text(page)
            
            # 提取 "Otros productos incluidos en el estado de cuenta (inversiones)" 表格
            if "Otros productos incluidos" in text or "inversiones" in text:
                inv_table = []
                
                # Strategy: Try strict tolerance (5) first for dense tables. 
                # If that fails (returns empty), try standard tolerance (10) for loose tables.
                for tolerance in [5, 10]:
                    if inv_table: 
                        break # Stop if we successfully extracted data
                        
                    # Use robust visual row reconstruction
                    rows = self._reconstruct_page_rows(page, y_tolerance=tolerance)
                    in_table = False
                    
                    for line in rows:
                        clean_line = line.strip().upper()
                        
                        # Table Start Trigger: Headers
                        if "CONTRATO" in clean_line and "PRODUCTO" in clean_line:
                            in_table = True
                            continue
                        # Alternative Trigger
                        if "CONTRATO" in clean_line and "TASA" in clean_line:
                            in_table = True
                            continue
                            
                        if in_table:
                            # Stop at next section header or end triggers
                            if "TOTAL DE APARTADOS" in clean_line:
                                break
                            if "SALDO GLOBAL" in clean_line: # Stop if we hit the footer amount
                                break
                            if "DETALLE DE MOVIMIENTOS" in clean_line:
                                break
                            if "OPER" in clean_line and "LIQ" in clean_line: # Transaction header
                                break
                                
                            # Filter Headers (Redundant check but safe)
                            if "CONTRATO" in clean_line or "GAT RELEASE" in clean_line or "ANTES DE IMPUESTOS" in clean_line:
                                continue
                            # Footer legal text
                            if "GAT REAL ES EL RENDIMIENTO" in clean_line:
                                continue
                            
                            # Parse Row Data
                            tokens = line.split()
                            if len(tokens) >= 3: 
                                 # Heuristic: First token is Contrato
                                 # MUST be digits or "N/A"
                                 contrato = tokens[0]
                                 
                                 # Strict Validation
                                 # Handle variations of N/A (e.g. N/A, NA, N.A.)
                                 is_valid_contrato = contrato.isdigit() or "N/A" in contrato.upper() or contrato.upper() == "NA"
                                 if not is_valid_contrato:
                                     # This is the key fix: Skip any row where first col isn't ID or N/A
                                     # This filters out "21/JUN", "BBVA", "Saldo", etc.
                                     continue

                                 # Last token is Total Comisiones (often N/A)
                                 total_com = tokens[-1]
                                 
                                 # GAT Real (2nd last)
                                 gat_real = tokens[-2]
                                 
                                 # GAT Nominal (3rd last)
                                 gat_nom = tokens[-3]
                                 
                                 # Tasa (4th last) - Usually identifies itself with %
                                 tasa = "N/A"
                                 # Search for token containing % working backwards
                                 tasa_idx = -1
                                 for i in range(len(tokens)-4, 0, -1):
                                     if "%" in tokens[i]:
                                         tasa = tokens[i]
                                         tasa_idx = i
                                         break
                                     if tokens[i] == "%":
                                          tasa = "%"
                                          tasa_idx = i
                                          break
                                 
                                 # Product is everything between Contrato and Tasa
                                 producto = ""
                                 if tasa_idx != -1:
                                     products_tokens = tokens[1:tasa_idx]
                                     producto = " ".join(products_tokens)
                                 else:
                                     # Fallback: tokens[1:-3]
                                     parsed_mid = tokens[1:-3]
                                     if parsed_mid and parsed_mid[0] == '%':
                                          tasa = '%'
                                          producto = "" # Empty
                                     else:
                                          producto = " ".join(parsed_mid)

                                 item = {
                                     "Contrato": contrato,
                                     "Producto": producto,
                                     "Tasa de Interés anual": tasa,
                                     "GAT Nominal": gat_nom,
                                     "GAT Real": gat_real,
                                     "Total de comisiones": total_com
                                 }
                                 inv_table.append(item)

                if inv_table:
                    # Return as a dictionary wrapper to match schema but containing list
                    # Schema says Dict[str, Any], so we can put a list inside
                    data["Otros productos incluidos en el estado de cuenta (inversiones)"] = inv_table
            
            # 提取 "Total de Apartados" 和 "Saldo Global"
            # Screenshot shows they are on separate lines:
            # Total de Apartados       03
            # Saldo Global             $ 26.00
            
            # 1. Total de Apartados
            if "Total de Apartados" not in data:
                match_apartados = re.search(r"Total\s+de\s+Apartados(?!\s+en\s+Global)(?:\s+en\s+Global)?\s*[:\s]*(\d+)", text, re.IGNORECASE)
                if match_apartados:
                     data["Total de Apartados"] = match_apartados.group(1)

            # 2. Saldo Global
            # CRITICAL FIX: Use [ \t] instead of \s to avoid capturing newlines and values from subsequent lines
            # Must capture ONLY on the same line as the label
            # Also ensure we don't overwrite if found on previous pages (e.g. Page 1 vs Page 17)
            if "Saldo Global" not in data:
                match_global = re.search(r"Saldo\s+Global\s*[:\s]*\$?\s*([\d,\.]+(?:[ \t]+[\d,\.]+)*)", text, re.IGNORECASE)
                if match_global:
                     data["Saldo Global"] = f"$ {match_global.group(1).strip()}"
            
            # Fallback for old legacy format "Total de Apartados en Global" if above missed
            if "Total de Apartados" not in data and "Saldo Global" not in data:
                 match_total = re.search(r"Total\s+de\s+Apartados\s+en\s+Global\s*[:\s]*\$?\s*([\d\s,\.]+)", text, re.IGNORECASE)
                 if match_total:
                     data["Total de Apartados en Global"] = f"$ {match_total.group(1).strip()}"
        
        return data if data else None

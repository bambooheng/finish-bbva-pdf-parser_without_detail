"""Parse MinerU markdown files to extract transaction data from 'Detalle de Movimientos Realizados' section."""
import re
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from src.models.schemas import Transaction, TransactionRawFields, TransactionExtendedFields


class MarkdownTransactionParser:
    """Parse transactions from MinerU markdown files.
    
    Following user requirement: 
    - Extract "Detalle de Movimientos Realizados" section
    - Parse OPER, LIQ, DESCRIPCION, REFERENCIA, CARGOS, ABONOS, OPERACION, LIQUIDACION as separate core fields
    - Ensure absolute data accuracy
    """
    
    def __init__(self, bank_config: Optional[Dict[str, Any]] = None, year_context: Optional[int] = None):
        """Initialize markdown parser.
        
        Args:
            bank_config: Bank-specific configuration
            year_context: Year context for date parsing
        """
        self.bank_config = bank_config or {}
        self.year_context = year_context
    
    def parse_markdown_transactions(
        self, 
        markdown_content: str,
        year_context: Optional[int] = None
    ) -> List[Transaction]:
        """
        Parse transactions from markdown content.
        
        Args:
            markdown_content: Full markdown content from MinerU
            year_context: Optional year context for date parsing
            
        Returns:
            List of Transaction objects
        """
        if not markdown_content:
            return []
        
        # Use provided year_context or fallback to instance year_context
        year = year_context or self.year_context
        
        # Find "Detalle de Movimientos Realizados" section
        detalle_section = self._extract_detalle_section(markdown_content)
        if not detalle_section:
            print("[DEBUG] No 'Detalle de Movimientos Realizados' section found in markdown")
            return []
        
        print(f"[DEBUG] Found 'Detalle de Movimientos Realizados' section: {len(detalle_section)} chars")
        
        # Parse transactions from the section
        transactions = self._parse_transactions_from_section(detalle_section, year)
        
        print(f"[DEBUG] Extracted {len(transactions)} transactions from markdown")
        return transactions
    
    def _extract_detalle_section(self, markdown_content: str) -> Optional[str]:
        """Extract 'Detalle de Movimientos Realizados' section from markdown.
        
        Args:
            markdown_content: Full markdown content
            
        Returns:
            Section content or None
        """
        # Look for section header (case-insensitive, flexible matching)
        patterns = [
            r'(?:^|\n)#+\s*Detalle\s+de\s+Movimientos\s+Realizados[^\n]*(?:\n|$)',
            r'(?:^|\n)##+\s*Detalle\s+de\s+Movimientos\s+Realizados[^\n]*(?:\n|$)',
            r'(?:^|\n)\*\*Detalle\s+de\s+Movimientos\s+Realizados\*\*[^\n]*(?:\n|$)',
            r'(?:^|\n)Detalle\s+de\s+Movimientos\s+Realizados[^\n]*(?:\n|$)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, markdown_content, re.IGNORECASE | re.MULTILINE)
            if match:
                start_pos = match.end()
                # Find next major section or end of document
                next_section_patterns = [
                    r'\n#+\s+[A-Z]',  # Next heading
                    r'\n\*\*[A-Z]',  # Next bold heading
                    r'\n[A-Z][A-Z\s]{10,}',  # Next all-caps heading
                ]
                
                end_pos = len(markdown_content)
                for next_pattern in next_section_patterns:
                    next_match = re.search(next_pattern, markdown_content[start_pos:], re.MULTILINE)
                    if next_match:
                        end_pos = start_pos + next_match.start()
                        break
                
                section = markdown_content[start_pos:end_pos].strip()
                if section:
                    return section
        
        # If no section header found, try to find table-like content
        # Look for patterns that suggest transaction data
        table_patterns = [
            r'(?:OPER|LIQ|DESCRIPCION|CARGOS|ABONOS)[\s\S]{100,}',  # Contains transaction column headers
        ]
        
        for pattern in table_patterns:
            match = re.search(pattern, markdown_content, re.IGNORECASE | re.MULTILINE)
            if match:
                # Extract a reasonable chunk around the match
                start_pos = max(0, match.start() - 500)
                end_pos = min(len(markdown_content), match.end() + 5000)
                section = markdown_content[start_pos:end_pos].strip()
                if section:
                    return section
        
        return None
    
    def _parse_transactions_from_section(self, section_content: str, year_context: Optional[int]) -> List[Transaction]:
        """Parse individual transactions from section content.
        
        Args:
            section_content: Content of the Detalle section
            year_context: Year for date parsing
            
        Returns:
            List of Transaction objects
        """
        transactions = []
        
        # Split into lines for processing
        lines = section_content.split('\n')
        
        # Look for table structure (markdown tables or text tables)
        # Pattern 1: Markdown table format
        if '|' in section_content:
            transactions.extend(self._parse_markdown_table(section_content, year_context))
        
        # Pattern 2: Text table format (space-separated columns)
        if not transactions:
            transactions.extend(self._parse_text_table(lines, year_context))
        
        # Pattern 3: Line-by-line parsing (fallback)
        if not transactions:
            transactions.extend(self._parse_line_by_line(lines, year_context))
        
        return transactions
    
    def _parse_markdown_table(self, content: str, year_context: Optional[int]) -> List[Transaction]:
        """Parse markdown table format.
        
        Args:
            content: Table content
            year_context: Year for date parsing
            
        Returns:
            List of Transaction objects
        """
        transactions = []
        
        # Find table rows (lines with |)
        table_lines = [line for line in content.split('\n') if '|' in line and line.strip().startswith('|')]
        if len(table_lines) < 2:  # Need at least header + 1 data row
            return transactions
        
        # Parse header to find column indices
        header_line = table_lines[0]
        header_cells = [cell.strip() for cell in header_line.split('|')[1:-1]]  # Remove empty first/last
        
        # Find column indices
        col_indices = {}
        for idx, header in enumerate(header_cells):
            header_upper = header.upper()
            if 'OPER' in header_upper or 'OPERACION' in header_upper:
                col_indices['OPER'] = idx
            elif 'LIQ' in header_upper or 'LIQUIDACION' in header_upper:
                col_indices['LIQ'] = idx
            elif 'DESCRIPCION' in header_upper or 'DESCRIPCIÓN' in header_upper:
                col_indices['DESCRIPCION'] = idx
            elif 'REFERENCIA' in header_upper:
                col_indices['REFERENCIA'] = idx
            elif 'CARGOS' in header_upper:
                col_indices['CARGOS'] = idx
            elif 'ABONOS' in header_upper:
                col_indices['ABONOS'] = idx
            elif 'OPERACION' in header_upper:
                col_indices['OPERACION'] = idx
            elif 'LIQUIDACION' in header_upper:
                col_indices['LIQUIDACION'] = idx
        
        # Skip separator line (usually second line with ---)
        data_start = 2 if len(table_lines) > 1 and '---' in table_lines[1] else 1
        
        # Parse data rows
        for line in table_lines[data_start:]:
            cells = [cell.strip() for cell in line.split('|')[1:-1]]
            if len(cells) < max(col_indices.values(), default=0) + 1:
                continue
            
            transaction = self._create_transaction_from_cells(cells, col_indices, year_context)
            if transaction:
                transactions.append(transaction)
        
        return transactions
    
    def _parse_text_table(self, lines: List[str], year_context: Optional[int]) -> List[Transaction]:
        """Parse text table format (space-separated columns).
        
        Args:
            lines: Content lines
            year_context: Year for date parsing
            
        Returns:
            List of Transaction objects
        """
        transactions = []
        
        # Find header line
        header_idx = None
        for idx, line in enumerate(lines):
            if re.search(r'OPER|LIQ|DESCRIPCION|CARGOS|ABONOS', line, re.IGNORECASE):
                header_idx = idx
                break
        
        if header_idx is None:
            return transactions
        
        # Parse header to find column positions
        header_line = lines[header_idx]
        col_positions = self._find_column_positions(header_line)
        
        # Parse data rows
        for line in lines[header_idx + 1:]:
            # Skip separator lines
            if re.match(r'^[\s\-]+$', line):
                continue
            
            # Check if line looks like a transaction (starts with date pattern)
            if not re.match(r'^\d{1,2}/[A-Z]{3}', line, re.IGNORECASE):
                continue
            
            transaction = self._create_transaction_from_text_line(line, col_positions, year_context)
            if transaction:
                transactions.append(transaction)
        
        return transactions
    
    def _parse_line_by_line(self, lines: List[str], year_context: Optional[int]) -> List[Transaction]:
        """Parse transactions line by line (fallback method).
        
        Args:
            lines: Content lines
            year_context: Year for date parsing
            
        Returns:
            List of Transaction objects
        """
        transactions = []
        current_transaction = {}
        
        for line in lines:
            line = line.strip()
            if not line:
                if current_transaction:
                    transaction = self._create_transaction_from_dict(current_transaction, year_context)
                    if transaction:
                        transactions.append(transaction)
                    current_transaction = {}
                continue
            
            # Try to extract fields from line
            # Date patterns
            date_match = re.match(r'^(\d{1,2}/[A-Z]{3})', line, re.IGNORECASE)
            if date_match:
                if current_transaction:
                    transaction = self._create_transaction_from_dict(current_transaction, year_context)
                    if transaction:
                        transactions.append(transaction)
                current_transaction = {'OPER': date_match.group(1)}
            
            # Amount patterns
            amount_match = re.search(r'([\d,]+\.?\d*)', line)
            if amount_match:
                amount_str = amount_match.group(1)
                if 'CARGOS' not in current_transaction:
                    current_transaction['CARGOS'] = amount_str
                elif 'ABONOS' not in current_transaction:
                    current_transaction['ABONOS'] = amount_str
                elif 'OPERACION' not in current_transaction:
                    current_transaction['OPERACION'] = amount_str
                elif 'LIQUIDACION' not in current_transaction:
                    current_transaction['LIQUIDACION'] = amount_str
            
            # Description
            if not any(key in current_transaction for key in ['DESCRIPCION', 'CARGOS', 'ABONOS']):
                if len(line) > 10:
                    current_transaction['DESCRIPCION'] = line
        
        # Add last transaction
        if current_transaction:
            transaction = self._create_transaction_from_dict(current_transaction, year_context)
            if transaction:
                transactions.append(transaction)
        
        return transactions
    
    def _find_column_positions(self, header_line: str) -> Dict[str, Tuple[int, int]]:
        """Find column positions in text table header.
        
        Args:
            header_line: Header line text
            
        Returns:
            Dict mapping field names to (start, end) positions
        """
        positions = {}
        
        # Find each column header
        patterns = {
            'OPER': r'OPER',
            'LIQ': r'LIQ',
            'DESCRIPCION': r'DESCRIPCION|DESCRIPCIÓN',
            'REFERENCIA': r'REFERENCIA',
            'CARGOS': r'CARGOS',
            'ABONOS': r'ABONOS',
            'OPERACION': r'OPERACION|OPERACIÓN',
            'LIQUIDACION': r'LIQUIDACION|LIQUIDACIÓN',
        }
        
        for field, pattern in patterns.items():
            match = re.search(pattern, header_line, re.IGNORECASE)
            if match:
                start = match.start()
                # Find end position (next column start or end of line)
                end_match = re.search(r'\s{2,}', header_line[start:])
                if end_match:
                    end = start + end_match.start()
                else:
                    end = len(header_line)
                positions[field] = (start, end)
        
        return positions
    
    def _create_transaction_from_cells(
        self, 
        cells: List[str], 
        col_indices: Dict[str, int],
        year_context: Optional[int]
    ) -> Optional[Transaction]:
        """Create Transaction from table cells.
        
        Args:
            cells: Table cells
            col_indices: Column index mapping
            year_context: Year for date parsing
            
        Returns:
            Transaction object or None
        """
        trans_data = {}
        
        for field, idx in col_indices.items():
            if idx < len(cells):
                trans_data[field] = cells[idx]
        
        return self._create_transaction_from_dict(trans_data, year_context)
    
    def _create_transaction_from_text_line(
        self,
        line: str,
        col_positions: Dict[str, Tuple[int, int]],
        year_context: Optional[int]
    ) -> Optional[Transaction]:
        """Create Transaction from text line.
        
        Args:
            line: Text line
            col_positions: Column position mapping
            year_context: Year for date parsing
            
        Returns:
            Transaction object or None
        """
        trans_data = {}
        
        for field, (start, end) in col_positions.items():
            if start < len(line):
                value = line[start:min(end, len(line))].strip()
                if value:
                    trans_data[field] = value
        
        return self._create_transaction_from_dict(trans_data, year_context)
    
    def _create_transaction_from_dict(
        self,
        trans_data: Dict[str, str],
        year_context: Optional[int]
    ) -> Optional[Transaction]:
        """Create Transaction object from dictionary.
        
        Args:
            trans_data: Transaction data dictionary
            year_context: Year for date parsing
            
        Returns:
            Transaction object or None
        """
        # Extract raw fields
        oper_str = trans_data.get('OPER', '').strip()
        liq_str = trans_data.get('LIQ', '').strip()
        descripcion = trans_data.get('DESCRIPCION', '').strip()
        referencia = trans_data.get('REFERENCIA', '').strip()
        cargos_str = trans_data.get('CARGOS', '').strip()
        abonos_str = trans_data.get('ABONOS', '').strip()
        operacion_str = trans_data.get('OPERACION', '').strip()
        liquidacion_str = trans_data.get('LIQUIDACION', '').strip()
        
        # Parse dates
        oper_date = self._parse_date(oper_str, year_context) if oper_str else None
        liq_date = self._parse_date(liq_str, year_context) if liq_str else None
        
        # Parse amounts
        cargos = self._parse_amount(cargos_str) if cargos_str else None
        abonos = self._parse_amount(abonos_str) if abonos_str else None
        operacion = self._parse_amount(operacion_str) if operacion_str else None
        liquidacion = self._parse_amount(liquidacion_str) if liquidacion_str else None
        
        # Ensure we have at least some data
        if not any([oper_date, liq_date, descripcion, cargos, abonos, operacion, liquidacion]):
            return None
        
        # Create raw fields
        raw_fields = TransactionRawFields(
            OPER=oper_str if oper_str else None,
            LIQ=liq_str if liq_str else None,
            DESCRIPCION=descripcion if descripcion else None,
            REFERENCIA=referencia if referencia else None,
            CARGOS=cargos_str if cargos_str else None,
            ABONOS=abonos_str if abonos_str else None,
            OPERACION=operacion_str if operacion_str else None,
            LIQUIDACION=liquidacion_str if liquidacion_str else None
        )
        
        # Create extended fields
        extended_fields = TransactionExtendedFields(
            oper_date=oper_date,
            liq_date=liq_date,
            cargos=cargos,
            abonos=abonos,
            operacion=operacion,
            liquidacion=liquidacion
        )
        
        # Create position (minimal, as markdown doesn't have bbox)
        position = {
            "bbox": {"x": 0, "y": 0, "width": 0, "height": 0, "page": 0},
            "page": 0
        }
        
        # Create raw text
        raw_text_parts = [oper_str, liq_str, descripcion, referencia, cargos_str, abonos_str, operacion_str, liquidacion_str]
        raw_text = " ".join([p for p in raw_text_parts if p])
        
        # Create transaction
        try:
            # CRITICAL: Ensure date field is never None for DEPRECATED field
            # Pydantic may require explicit value even for Optional fields
            trans_date = oper_date or liq_date
            if trans_date is None:
                trans_date = date.today()
            
            transaction = Transaction(
                oper_date=oper_date,
                liq_date=liq_date,
                cargos=cargos,
                abonos=abonos,
                operacion=operacion,
                liquidacion=liquidacion,
                raw_fields=raw_fields,
                extended_fields=extended_fields,
                position=position,
                raw_text=raw_text,
                confidence=0.9,  # Markdown parsing has high confidence
                extraction_method="markdown_parser",
                source="markdown",
                # DEPRECATED fields (for backward compatibility)
                date=trans_date,  # Always set to a date object, never None
                description=descripcion if descripcion else None,
                amount=cargos or abonos or operacion or liquidacion,
                balance=liquidacion,
                reference=referencia if referencia else None,
                OPER=oper_str if oper_str else None,
                LIQ=liq_str if liq_str else None,
                DESCRIPCION=descripcion if descripcion else None,
                REFERENCIA=referencia if referencia else None,
                CARGOS=cargos_str if cargos_str else None,
                ABONOS=abonos_str if abonos_str else None,
                OPERACION=operacion_str if operacion_str else None,
                LIQUIDACION=liquidacion_str if liquidacion_str else None
            )
            return transaction
        except Exception as e:
            print(f"[WARNING] Failed to create transaction from markdown: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _parse_date(self, date_str: str, year_context: Optional[int]) -> Optional[date]:
        """Parse date string (e.g., '11/JUL' or '11/07/2025').
        
        Args:
            date_str: Date string
            year_context: Year context
            
        Returns:
            date object or None
        """
        if not date_str:
            return None
        
        # Pattern 1: DD/MON format (e.g., '11/JUL')
        match = re.match(r'(\d{1,2})/([A-Z]{3})', date_str.upper())
        if match:
            day = int(match.group(1))
            month_str = match.group(2)
            month_map = {
                'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
                'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
            }
            month = month_map.get(month_str)
            if month:
                year = year_context or date.today().year
                try:
                    return date(year, month, day)
                except ValueError:
                    return None
        
        # Pattern 2: DD/MM/YYYY format
        match = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', date_str)
        if match:
            day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
            try:
                return date(year, month, day)
            except ValueError:
                return None
        
        return None
    
    def _parse_amount(self, amount_str: str) -> Optional[Decimal]:
        """Parse amount string (e.g., '1,000.00' or '1000.00').
        
        Args:
            amount_str: Amount string
            
        Returns:
            Decimal or None
        """
        if not amount_str:
            return None
        
        # Remove commas and spaces
        cleaned = amount_str.replace(',', '').replace(' ', '').strip()
        
        try:
            return Decimal(cleaned)
        except:
            return None


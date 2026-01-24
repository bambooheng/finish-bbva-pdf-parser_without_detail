"""Extract table data from images in MinerU output images folder.
    
Following user requirement:
- Images folder contains tables that were recognized as images during OCR
- Exclude logos and QR codes (pure images)
- Extract and parse table data from these images
"""
import base64
import io
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from PIL import Image
    import pytesseract
    HAS_OCR_LIBS = True
except ImportError:
    HAS_OCR_LIBS = False
    print("[WARNING] PIL/pytesseract not available. Image table extraction will be limited.")


class ImageTableExtractor:
    """Extract table data from images that are actually tables.
    
    Following user requirement:
    - Identify table images (exclude logos and QR codes)
    - Perform OCR on table images
    - Parse extracted text into structured transaction data
    """
    
    def __init__(self, bank_config: Optional[Dict[str, Any]] = None):
        """Initialize image table extractor.
        
        Args:
            bank_config: Bank-specific configuration
        """
        self.bank_config = bank_config or {}
        self.logo_patterns = [
            r'logo', r'bbva', r'banco', r'bank',
        ]
        self.qr_code_size_threshold = 200  # QR codes are typically small square images
    
    def extract_tables_from_images(
        self,
        images_dir: Path,
        exclude_patterns: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract table data from images in directory.
        
        Args:
            images_dir: Path to images directory
            exclude_patterns: Optional list of filename patterns to exclude
            
        Returns:
            List of extracted table data dictionaries
        """
        if not images_dir.exists():
            return []
        
        if not HAS_OCR_LIBS:
            print("[WARNING] OCR libraries not available. Cannot extract tables from images.")
            return []
        
        tables = []
        exclude_patterns = exclude_patterns or []
        
        # Get all image files
        image_files = list(images_dir.glob("*.jpg")) + list(images_dir.glob("*.png")) + \
                     list(images_dir.glob("*.jpeg")) + list(images_dir.glob("*.bmp"))
        
        print(f"[DEBUG] Found {len(image_files)} image files in {images_dir}")
        
        for img_file in image_files:
            # Check if should be excluded
            if self._should_exclude_image(img_file, exclude_patterns):
                print(f"[DEBUG] Excluding image (logo/QR code): {img_file.name}")
                continue
            
            # Check if image looks like a table
            if not self._is_likely_table_image(img_file):
                print(f"[DEBUG] Image does not appear to be a table: {img_file.name}")
                continue
            
            # Extract table data from image
            table_data = self._extract_table_from_image(img_file)
            if table_data:
                tables.append(table_data)
                print(f"[DEBUG] Extracted table from image: {img_file.name}")
        
        print(f"[DEBUG] Extracted {len(tables)} tables from images")
        return tables
    
    def _should_exclude_image(self, img_file: Path, exclude_patterns: List[str]) -> bool:
        """Check if image should be excluded (logo or QR code).
        
        Args:
            img_file: Image file path
            exclude_patterns: Patterns to exclude
            
        Returns:
            True if should be excluded
        """
        filename_lower = img_file.name.lower()
        
        # Check exclude patterns
        for pattern in exclude_patterns:
            if pattern.lower() in filename_lower:
                return True
        
        # Check logo patterns
        for pattern in self.logo_patterns:
            if pattern.lower() in filename_lower:
                return True
        
        # Check if likely QR code (small square image)
        try:
            if HAS_OCR_LIBS:
                with Image.open(img_file) as img:
                    width, height = img.size
                    # QR codes are typically small and square
                    if width < self.qr_code_size_threshold and height < self.qr_code_size_threshold:
                        if abs(width - height) < 10:  # Nearly square
                            return True
        except Exception as e:
            print(f"[WARNING] Could not check image size for {img_file.name}: {e}")
        
        return False
    
    def _is_likely_table_image(self, img_file: Path) -> bool:
        """Check if image is likely a table (not a logo/QR code).
        
        Args:
            img_file: Image file path
            
        Returns:
            True if likely a table
        """
        try:
            if not HAS_OCR_LIBS:
                return False
            
            with Image.open(img_file) as img:
                width, height = img.size
                
                # Tables are typically wider than they are tall, or at least not tiny
                if width < 100 or height < 100:
                    return False
                
                # Tables usually have reasonable aspect ratio (not extremely wide or tall)
                aspect_ratio = width / height if height > 0 else 1
                if aspect_ratio < 0.3 or aspect_ratio > 10:
                    return False
                
                # Try OCR to see if there's structured text (table-like content)
                # Quick check: if we can find table-like patterns in OCR, it's likely a table
                try:
                    ocr_text = pytesseract.image_to_string(img, lang='spa+eng')
                    # Look for table indicators
                    table_indicators = [
                        r'\d{1,2}/[A-Z]{3}',  # Date patterns
                        r'CARGOS|ABONOS|OPERACION|LIQUIDACION',  # Column headers
                        r'\d+\.\d{2}',  # Amount patterns
                        r'\|\s*\d',  # Pipe-separated numbers (markdown table)
                    ]
                    
                    for pattern in table_indicators:
                        if re.search(pattern, ocr_text, re.IGNORECASE):
                            return True
                except Exception as e:
                    print(f"[WARNING] OCR check failed for {img_file.name}: {e}")
                
                # If image is reasonably large and has reasonable aspect ratio, assume it might be a table
                return width > 200 and height > 100
        except Exception as e:
            print(f"[WARNING] Could not analyze image {img_file.name}: {e}")
            return False
    
    def _extract_table_from_image(self, img_file: Path) -> Optional[Dict[str, Any]]:
        """Extract table data from image using OCR.
        
        Args:
            img_file: Image file path
            
        Returns:
            Table data dictionary or None
        """
        try:
            if not HAS_OCR_LIBS:
                return None
            
            with Image.open(img_file) as img:
                # Perform OCR
                ocr_text = pytesseract.image_to_string(img, lang='spa+eng')
                
                if not ocr_text or len(ocr_text.strip()) < 10:
                    return None
                
                # Try to parse as structured table
                table_data = self._parse_ocr_text_as_table(ocr_text, img_file)
                
                if table_data:
                    # Add image metadata
                    table_data['source_image'] = str(img_file.name)
                    table_data['image_size'] = {'width': img.size[0], 'height': img.size[1]}
                    
                    # Store image data as base64 for reference
                    img_bytes = io.BytesIO()
                    img.save(img_bytes, format='PNG')
                    img_bytes.seek(0)
                    table_data['image_data'] = base64.b64encode(img_bytes.read()).decode('utf-8')
                
                return table_data
        except Exception as e:
            print(f"[WARNING] Failed to extract table from image {img_file.name}: {e}")
            return None
    
    def _parse_ocr_text_as_table(self, ocr_text: str, img_file: Path) -> Optional[Dict[str, Any]]:
        """Parse OCR text as structured table.
        
        Args:
            ocr_text: OCR extracted text
            img_file: Source image file (for reference)
            
        Returns:
            Table data dictionary or None
        """
        import re
        
        lines = [line.strip() for line in ocr_text.split('\n') if line.strip()]
        if len(lines) < 2:
            return None
        
        # Look for header row
        header_idx = None
        for idx, line in enumerate(lines):
            if re.search(r'OPER|LIQ|DESCRIPCION|CARGOS|ABONOS|OPERACION|LIQUIDACION', line, re.IGNORECASE):
                header_idx = idx
                break
        
        if header_idx is None:
            # No clear header, try to parse as transaction data anyway
            return self._parse_without_header(lines)
        
        # Parse with header
        header_line = lines[header_idx]
        col_positions = self._find_column_positions(header_line)
        
        # Extract rows
        rows = []
        for line in lines[header_idx + 1:]:
            # Skip separator lines
            if re.match(r'^[\s\-]+$', line):
                continue
            
            # Check if line looks like data (contains date or amount)
            if not (re.search(r'\d{1,2}/[A-Z]{3}', line, re.IGNORECASE) or 
                    re.search(r'\d+\.\d{2}', line)):
                continue
            
            row_data = {}
            for field, (start, end) in col_positions.items():
                if start < len(line):
                    value = line[start:min(end, len(line))].strip()
                    if value:
                        row_data[field] = value
            
            if row_data:
                rows.append(row_data)
        
        if not rows:
            return None
        
        return {
            'type': 'table',
            'rows': rows,
            'source': 'image_ocr',
            'image_file': str(img_file.name),
            'row_count': len(rows)
        }
    
    def _parse_without_header(self, lines: List[str]) -> Optional[Dict[str, Any]]:
        """Parse lines without clear header (fallback method).
        
        Args:
            lines: Text lines
            
        Returns:
            Table data dictionary or None
        """
        import re
        
        rows = []
        for line in lines:
            # Look for transaction-like patterns
            # Pattern: date description amount
            date_match = re.search(r'(\d{1,2}/[A-Z]{3})', line, re.IGNORECASE)
            amount_match = re.search(r'([\d,]+\.?\d{2})', line)
            
            if date_match or amount_match:
                row_data = {}
                if date_match:
                    row_data['OPER'] = date_match.group(1)
                
                if amount_match:
                    amount_str = amount_match.group(1)
                    # Try to determine if it's CARGOS, ABONOS, etc. based on context
                    # For now, assign to first available field
                    if 'CARGOS' not in row_data:
                        row_data['CARGOS'] = amount_str
                
                # Extract description (text between date and amount)
                if date_match and amount_match:
                    desc_start = date_match.end()
                    desc_end = amount_match.start()
                    description = line[desc_start:desc_end].strip()
                    if description:
                        row_data['DESCRIPCION'] = description
                
                if row_data:
                    rows.append(row_data)
        
        if not rows:
            return None
        
        return {
            'type': 'table',
            'rows': rows,
            'source': 'image_ocr',
            'row_count': len(rows)
        }
    
    def _find_column_positions(self, header_line: str) -> Dict[str, Tuple[int, int]]:
        """Find column positions in header line.
        
        Args:
            header_line: Header line text
            
        Returns:
            Dict mapping field names to (start, end) positions
        """
        positions = {}
        
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


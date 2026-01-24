"""MinerU OCR integration."""
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
import re

from src.config import config



class MinerUHandler:
    """Handler for MinerU OCR processing."""
    
    def __init__(self):
        """Initialize MinerU handler."""
        self.python_path = config.get_mineru_python()
        self.timeout = config.mineru_timeout
    
    def _detect_language(self, text: str) -> str:
        """
        Detect document language from text content.
        
        Uses heuristics based on common words and patterns to identify language.
        Returns ISO 639-1 language code (e.g., 'es', 'en', 'zh').
        
        Args:
            text: Text content from OCR
            
        Returns:
            Language code string
        """
        if not text or len(text.strip()) < 10:
            return "unknown"
        
        text_lower = text.lower()
        
        # Spanish indicators (BBVA Mexico documents are typically in Spanish)
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
        chinese_count = len(chinese_pattern.findall(text))
        
        # Count occurrences
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
            return "unknown"
    
    def process_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """
        Process PDF using MinerU OCR.
        
        Args:
            pdf_path: Path to input PDF file
            
        Returns:
            Dictionary containing OCR results with layout information
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        # MinerU typically outputs JSON or structured data
        # This is a placeholder implementation that should be adapted
        # to your specific MinerU setup
        
        # For now, we'll create a structure that represents what MinerU should output
        # In practice, you would call MinerU via subprocess or Python API
        
        try:
            # Attempt to call MinerU if it's available
            print("正在使用 MinerU OCR 引擎进行识别...")
            result = self._call_mineru(pdf_path)
            engine = result.get("engine", "mineru")
            language = result.get("language", "unknown")
            print(f"✓ OCR 识别完成，使用的引擎: {engine}")
            print(f"✓ 检测到的文档语言: {language}")
            return result
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
            # Fallback: use PyMuPDF for basic extraction
            print(f"MinerU call failed: {e}. Using fallback extraction.")
            print("正在使用 PyMuPDF 回退引擎进行识别...")
            result = self._fallback_extraction(pdf_path)
            engine = result.get("engine", "pymupdf_fallback")
            language = result.get("language", "unknown")
            print(f"✓ OCR 识别完成，使用的引擎: {engine}")
            print(f"✓ 检测到的文档语言: {language}")
            return result
    
    def _call_mineru(self, pdf_path: str) -> Dict[str, Any]:
        """
        Call MinerU executable/script.
        
        Note: This implementation supports MinerU as a Python package
        or command-line tool. Adapt as needed for your setup.
        """
        # Try Python package import first
        try:
            # MinerU might be available as a Python package
            import sys
            import importlib.util
            
            # Try to import mineru if available
            try:
                import mineru
                # If MinerU has a direct API
                if hasattr(mineru, 'extract'):
                    result = mineru.extract(pdf_path)
                    return self._parse_mineru_output(result)
            except ImportError:
                pass
            
            # Fallback to command-line invocation
            # MinerU CLI typically: python -m mineru.cli input.pdf --output output_dir
            with tempfile.TemporaryDirectory() as temp_dir:
                output_dir = os.path.join(temp_dir, "mineru_output")
                os.makedirs(output_dir, exist_ok=True)
                
                # Try common MinerU invocation patterns
                cmd_patterns = [
                    [self.python_path, "-m", "mineru", "extract", pdf_path, "--output", output_dir],
                    [self.python_path, "-m", "mineru.cli", pdf_path, "--output", output_dir],
                    [self.python_path, "-c", f"import mineru; mineru.extract('{pdf_path}', '{output_dir}')"],
                ]
                
                for cmd in cmd_patterns:
                    try:
                        result = subprocess.run(
                            cmd,
                            capture_output=True,
                            text=True,
                            timeout=self.timeout,
                            check=False
                        )
                        if result.returncode == 0 or os.path.exists(output_dir):
                            # Look for JSON output in output directory
                            json_files = list(Path(output_dir).glob("*.json"))
                            if json_files:
                                with open(json_files[0], 'r', encoding='utf-8') as f:
                                    mineru_result = json.load(f)
                                    # Ensure engine and language fields are set
                                    if isinstance(mineru_result, dict):
                                        mineru_result["engine"] = "mineru"
                                    return self._parse_mineru_output(mineru_result)
                            # Or parse stdout if JSON is there
                            if result.stdout:
                                try:
                                    mineru_result = json.loads(result.stdout)
                                    # Ensure engine and language fields are set
                                    if isinstance(mineru_result, dict):
                                        mineru_result["engine"] = "mineru"
                                    return self._parse_mineru_output(mineru_result)
                                except json.JSONDecodeError:
                                    pass
                    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
                        continue
                
        except Exception as e:
            print(f"MinerU package/CLI not available: {e}")
        
        # If all methods fail, raise to use fallback
        raise NotImplementedError(
            "MinerU integration failed. Please check MinerU installation or use fallback."
        )
    
    def _parse_mineru_output(self, mineru_result: Any) -> Dict[str, Any]:
        """
        Parse MinerU output into standardized format.
        
        Args:
            mineru_result: Raw MinerU output (dict, file path, etc.)
            
        Returns:
            Standardized OCR output dictionary
        """
        # If it's already a dict, try to standardize it
        if isinstance(mineru_result, dict):
            # Check if it's already in the right format
            if "pages" in mineru_result:
                # Ensure engine field is set
                if "engine" not in mineru_result:
                    mineru_result["engine"] = "mineru"
                # Detect language if not already set
                if "language" not in mineru_result:
                    all_text = ""
                    for page_data in mineru_result.get("pages", []):
                        for block in page_data.get("text_blocks", page_data.get("blocks", [])):
                            text = block.get("text", block.get("content", ""))
                            all_text += text + " "
                    mineru_result["language"] = self._detect_language(all_text)
                return mineru_result
            
            # Try to convert MinerU format to our format
            pages_data = []
            # MinerU might use different field names
            # Adapt based on actual MinerU output structure
            for page_num, page_data in enumerate(mineru_result.get("pages", []), 1):
                text_blocks = []
                
                # Extract text blocks (adapt field names as needed)
                for block in page_data.get("blocks", page_data.get("text_blocks", [])):
                    bbox = block.get("bbox", block.get("bounding_box", [0, 0, 0, 0]))
                    text = block.get("text", block.get("content", ""))
                    confidence = block.get("confidence", block.get("score", 0.8))
                    
                    text_blocks.append({
                        "type": "text",
                        "text": text,
                        "bbox": bbox,
                        "confidence": confidence
                    })
                
                pages_data.append({
                    "page_number": page_num,
                    "text_blocks": text_blocks,
                    "images": page_data.get("images", []),
                    "width": page_data.get("width", 612),
                    "height": page_data.get("height", 792)
                })
            
            # Detect language from all text content
            all_text = ""
            for page_data in pages_data:
                for block in page_data.get("text_blocks", []):
                    all_text += block.get("text", "") + " "
            
            detected_language = self._detect_language(all_text)
            
            return {
                "pages": pages_data,
                "total_pages": len(pages_data),
                "engine": "mineru",
                "language": detected_language
            }
        
        # If it's a file path, read it
        if isinstance(mineru_result, (str, Path)):
            path = Path(mineru_result)
            if path.exists() and path.suffix == '.json':
                with open(path, 'r', encoding='utf-8') as f:
                    return self._parse_mineru_output(json.load(f))
        
        raise ValueError(f"Unsupported MinerU output format: {type(mineru_result)}")
    
    def _fallback_extraction(self, pdf_path: str) -> Dict[str, Any]:
        """
        Fallback extraction using PyMuPDF.
        Extracts text and basic layout information.
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError(
                "PyMuPDF (fitz) is required. Install with: pip install PyMuPDF"
            )
        
        doc = fitz.open(pdf_path)
        pages_data = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # Extract text blocks with positions
            blocks = page.get_text("dict")
            
            # CRITICAL: Extract drawings/shapes FIRST (charts, graphics, logos drawn as paths)
            # These are important visual elements that must be captured (100% information capture)
            drawings_data = []
            try:
                drawings = page.get_drawings()
                for drawing in drawings:
                    # PyMuPDF's get_drawings() returns dictionaries
                    # Each drawing has: "type", "rect", "items", etc.
                    if isinstance(drawing, dict):
                        drawing_rect = drawing.get("rect")
                        drawing_items = drawing.get("items", [])
                        
                        # Extract rect - it's a fitz.Rect object
                        if drawing_rect:
                            rect_list = [drawing_rect.x0, drawing_rect.y0, drawing_rect.x1, drawing_rect.y1]
                        else:
                            rect_list = None
                        
                        # CRITICAL: Store more items for complex drawings (charts/graphs)
                        # Previous limit of 10 items was too restrictive for charts
                        # Increase limit but still cap it to prevent excessive storage
                        max_items = 50 if len(drawing_items) > 10 else len(drawing_items)
                        
                        drawing_info = {
                            "type": "drawing",
                            "rect": rect_list,
                            "items": drawing_items[:max_items] if isinstance(drawing_items, list) else [],
                            "total_items": len(drawing_items) if isinstance(drawing_items, list) else 0,
                            "color": drawing.get("color"),  # Store color information
                            "fill": drawing.get("fill"),
                            "stroke": drawing.get("stroke"),
                            "width": drawing.get("width")  # Line width
                        }
                        drawings_data.append(drawing_info)
            except Exception as e:
                # Drawings extraction not critical, but should work for most PDFs
                print(f"Warning: Could not extract drawings for page {page_num + 1}: {e}")
                import traceback
                traceback.print_exc()
            
            # Extract images with proper bbox
            # CRITICAL: Extract ALL images on the page with their exact positions
            images = []
            image_list = page.get_images()
            
            for img_index, img in enumerate(image_list):
                xref = img[0]
                try:
                    base_image = doc.extract_image(xref)
                    
                    # CRITICAL: Get actual image bbox on the page
                    # get_image_rects returns a list of fitz.Rect objects
                    image_bbox = None
                    try:
                        image_rects = page.get_image_rects(xref)
                        if image_rects and len(image_rects) > 0:
                            # Use the first rectangle (usually there's only one per image per page)
                            rect = image_rects[0]
                            # CRITICAL: Convert fitz.Rect to list [x0, y0, x1, y1]
                            # Rect has attributes: x0, y0, x1, y1
                            image_bbox = [rect.x0, rect.y0, rect.x1, rect.y1]
                        else:
                            # Fallback: If no rects found, check if it's a full-page image
                            page_rect = page.rect
                            if base_image.get("width", 0) > page_rect.width * 3 or \
                               base_image.get("height", 0) > page_rect.height * 3:
                                # Very large image, likely background - use page dimensions
                                image_bbox = [0, 0, page_rect.width, page_rect.height]
                    except Exception as e:
                        # If extraction fails, leave as None
                        pass
                    
                    images.append({
                        "index": img_index,
                        "xref": xref,
                        "ext": base_image["ext"],
                        "width": base_image["width"],
                        "height": base_image["height"],
                        "bbox": image_bbox  # Now properly converted to list [x0, y0, x1, y1]
                    })
                except Exception as e:
                    # Still add entry with None bbox to ensure we don't lose track
                    images.append({
                        "index": img_index,
                        "xref": xref,
                        "ext": "unknown",
                        "width": 0,
                        "height": 0,
                        "bbox": None
                    })
            
            # Organize text blocks with complete format information
            text_blocks = []
            for block in blocks.get("blocks", []):
                if block.get("type") == 0:  # Text block
                    bbox = block.get("bbox", [0, 0, 0, 0])
                    
                    # Extract text and format info from spans - collect ALL information
                    # IMPORTANT: Extract line-level info for precise reconstruction
                    lines_text = []
                    lines_info = []  # Store detailed line information
                    font_info = {}
                    font_sizes = []
                    colors = []
                    
                    for line in block.get("lines", []):
                        line_bbox = line.get("bbox", [0, 0, 0, 0])
                        line_text = ""
                        line_format = {}
                        line_spans = []
                        
                        for span in line.get("spans", []):
                            span_text = span.get("text", "")
                            line_text += span_text  # Preserve all text including spaces
                            
                            # Collect format information from all spans
                            span_font = span.get("font", "")
                            span_size = span.get("size", 0)
                            span_flags = span.get("flags", 0)
                            span_color = span.get("color", 0)
                            span_ascender = span.get("ascender", 0)
                            span_descender = span.get("descender", 0)
                            
                            # Store span-level format info
                            if span_text.strip() or span_size > 0:
                                span_format = {
                                    "font": span_font,
                                    "size": span_size,
                                    "flags": span_flags,
                                    "color": span_color,
                                    "ascender": span_ascender,
                                    "descender": span_descender
                                }
                                line_spans.append({
                                    "text": span_text,
                                    "format": span_format
                                })
                                
                                # Use first non-empty span's info for block-level format
                                if span_text.strip() or (not font_info.get("size") and span_size > 0):
                                    if not font_info or (span_text.strip() and not font_info.get("size")):
                                        font_info = span_format.copy()
                                
                                # Collect sizes and colors for block-level average
                                if span_size > 0:
                                    font_sizes.append(span_size)
                                if span_color != 0:
                                    colors.append(span_color)
                        
                        # Store line-level information (for precise reconstruction)
                        # Use first span's format as line format if line_format is empty
                        if not line_format and line_spans:
                            first_span_format = line_spans[0].get("format", {})
                            if first_span_format:
                                line_format = first_span_format.copy()
                        
                        line_info = {
                            "text": line_text if line_text else " ",  # Preserve empty lines
                            "bbox": line_bbox,
                            "format": line_format if line_format else font_info.copy(),
                            "spans": line_spans  # Span-level info for maximum precision
                        }
                        lines_info.append(line_info)
                        
                        # Include ALL lines, even if empty (for 100% capture)
                        lines_text.append(line_text if line_text else " ")
                    
                    # Use most common font size if available
                    if font_sizes and not font_info.get("size"):
                        from collections import Counter
                        most_common_size = Counter(font_sizes).most_common(1)[0][0]
                        if not font_info:
                            font_info = {}
                        font_info["size"] = most_common_size
                    
                    # Use most common color if available
                    if colors and (not font_info.get("color") or font_info.get("color") == 0):
                        from collections import Counter
                        most_common_color = Counter(colors).most_common(1)[0][0]
                        if not font_info:
                            font_info = {}
                        font_info["color"] = most_common_color
                    
                    # Combine all lines
                    full_text = "\n".join(lines_text)
                    
                    # Store block-level info with line-level details
                    block_info = {
                        "type": "text",
                        "text": full_text,
                        "bbox": bbox,
                        "confidence": 1.0,  # PyMuPDF doesn't provide confidence
                        "format": font_info,  # Block-level format (dominant)
                        "lines": lines_info  # Line-level info for precise reconstruction
                    }
                    text_blocks.append(block_info)
            
            # Store page dimensions
            page_rect = page.rect
            
            pages_data.append({
                "page_number": page_num + 1,
                "text_blocks": text_blocks,
                "images": images,
                "drawings": drawings_data,  # Include drawings for graphics/charts
                "width": page_rect.width,
                "height": page_rect.height
            })
        
        total_pages = len(doc)
        doc.close()
        
        # Detect language from all text content
        all_text = ""
        for page_data in pages_data:
            for block in page_data.get("text_blocks", []):
                all_text += block.get("text", "") + " "
        
        detected_language = self._detect_language(all_text)
        
        return {
            "pages": pages_data,
            "total_pages": total_pages,
            "engine": "pymupdf_fallback",
            "language": detected_language
        }
    
    def extract_critical_fields(self, ocr_output: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract critical fields that need dual verification.
        
        Args:
            ocr_output: Raw OCR output
            
        Returns:
            Dictionary of critical fields with their locations
        """
        critical_fields = {
            "account_numbers": [],
            "amounts": [],
            "dates": [],
            "balances": []
        }
        
        # Extract from all pages
        for page_data in ocr_output.get("pages", []):
            text_blocks = page_data.get("text_blocks", [])
            
            for block in text_blocks:
                text = block.get("text", "")
                bbox = block.get("bbox", [])
                
                # Simple pattern matching (can be enhanced with regex)
                # Account numbers (10-18 digits)
                import re
                account_pattern = r'\b\d{10,18}\b'
                for match in re.finditer(account_pattern, text):
                    critical_fields["account_numbers"].append({
                        "value": match.group(),
                        "bbox": bbox,
                        "page": page_data["page_number"]
                    })
                
                # Amounts (currency symbols with numbers)
                amount_pattern = r'[\$€]?\s*[\d,]+\.?\d*'
                for match in re.finditer(amount_pattern, text):
                    critical_fields["amounts"].append({
                        "value": match.group(),
                        "bbox": bbox,
                        "page": page_data["page_number"]
                    })
                
                # Dates (DD/MM/YYYY or DD/MM)
                date_pattern = r'\b\d{1,2}/\d{1,2}(/\d{2,4})?\b'
                for match in re.finditer(date_pattern, text):
                    critical_fields["dates"].append({
                        "value": match.group(),
                        "bbox": bbox,
                        "page": page_data["page_number"]
                    })
        
        return critical_fields
    
    def process_tables(self, ocr_output: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract and process tables from OCR output.
        
        Args:
            ocr_output: Raw OCR output
            
        Returns:
            List of processed tables
        """
        tables = []
        
        # Try to use tabula-py if available
        try:
            import tabula
            from pathlib import Path
            # This requires original PDF path, so we'll use OCR text blocks instead
            pass
        except ImportError:
            pass
        
        # Detect tables from text blocks by looking for tabular patterns
        for page_data in ocr_output.get("pages", []):
            page_num = page_data.get("page_number", 1)
            text_blocks = page_data.get("text_blocks", [])
            
            # Group text blocks that might form a table
            # Look for blocks that are aligned and have similar y-coordinates
            potential_table_rows = self._detect_table_rows(text_blocks, page_num)
            
            if potential_table_rows:
                table = {
                    "page": page_num,
                    "rows": potential_table_rows,
                    "bbox": self._calculate_table_bbox(potential_table_rows),
                    "type": "detected"
                }
                tables.append(table)
            
        return tables
    
    def _detect_table_rows(self, text_blocks: List[Dict[str, Any]], page_num: int) -> List[Dict[str, Any]]:
        """Detect table rows from text blocks."""
        if not text_blocks:
            return []
        
        # Group blocks by y-coordinate (same row if y is similar)
        rows = {}
        row_tolerance = 5  # pixels
        
        for block in text_blocks:
            bbox = block.get("bbox", [0, 0, 0, 0])
            if len(bbox) < 4:
                continue
            
            y_center = (bbox[1] + bbox[3]) / 2
            text = block.get("text", "").strip()
            
            if not text:
                continue
            
            # Find existing row or create new
            row_key = None
            for key in rows.keys():
                if abs(key - y_center) < row_tolerance:
                    row_key = key
                    break
            
            if row_key is None:
                row_key = y_center
            
            if row_key not in rows:
                rows[row_key] = []
            
            rows[row_key].append({
                "text": text,
                "bbox": bbox,
                "x": bbox[0],
                "width": bbox[2] - bbox[0] if len(bbox) >= 4 else 0
            })
        
        # Convert to table rows format
        table_rows = []
        for y, cells in sorted(rows.items()):
            # Sort cells by x position
            cells.sort(key=lambda c: c["x"])
            
            # Check if this looks like a transaction row
            row_text = " ".join(c["text"] for c in cells).lower()
            
            # Skip if it's clearly not a transaction row (headers, footers, etc.)
            if any(skip in row_text for skip in ["periodo", "fecha de corte", "no. de cuenta", "resumen", "total"]):
                continue
            
            # Check if row has date pattern and amount pattern (likely transaction)
            import re
            has_date = bool(re.search(r'\d{1,2}/\d{1,2}/\d{2,4}', row_text))
            has_amount = bool(re.search(r'[\$]?\s*[\d,]+\.[\d]{2}', row_text) or re.search(r'[\$]?\s*[\d,]+', row_text))
            
            if has_date and has_amount:
                # Format as table row
                table_rows.append({
                    "cells": [{"text": c["text"], "bbox": c["bbox"]} for c in cells],
                    "bbox": self._calculate_row_bbox(cells),
                    "page": page_num
                })
        
        return table_rows
    
    def _calculate_table_bbox(self, rows: List[Dict[str, Any]]) -> List[float]:
        """Calculate bounding box for entire table."""
        if not rows:
            return [0, 0, 0, 0]
        
        all_x = []
        all_y = []
        
        for row in rows:
            bbox = row.get("bbox", [])
            if len(bbox) >= 4:
                all_x.extend([bbox[0], bbox[2]])
                all_y.extend([bbox[1], bbox[3]])
        
        if all_x and all_y:
            return [min(all_x), min(all_y), max(all_x), max(all_y)]
        return [0, 0, 0, 0]
    
    def _calculate_row_bbox(self, cells: List[Dict[str, Any]]) -> List[float]:
        """Calculate bounding box for a row."""
        if not cells:
            return [0, 0, 0, 0]
        
        all_x = []
        all_y = []
        
        for cell in cells:
            bbox = cell.get("bbox", [])
            if len(bbox) >= 4:
                all_x.extend([bbox[0], bbox[2]])
                all_y.extend([bbox[1], bbox[3]])
        
        if all_x and all_y:
            return [min(all_x), min(all_y), max(all_x), max(all_y)]
        return [0, 0, 0, 0]


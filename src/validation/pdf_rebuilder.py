"""PDF reconstruction from structured data."""
import io
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

from src.models.schemas import BankDocument, ElementType, LayoutElement


class PDFRebuilder:
    """Rebuild PDF from structured data."""
    
    def __init__(self):
        """Initialize PDF rebuilder."""
        self.page_width, self.page_height = letter
        # Will be updated based on actual PDF page size
        # Track rendered text positions to avoid overlaps (per page)
        self.rendered_regions: Dict[int, List[Dict[str, Any]]] = {}  # page_idx -> regions
        # Page margins (safety margins to prevent overflow)
        self.margin = 5  # Reduced margin for better accuracy
        # Overlap detection tolerance
        self.overlap_tolerance = 2  # pixels
    
    def rebuild_pdf(
        self,
        document: BankDocument
    ) -> bytes:
        """
        Rebuild PDF from structured document data.
        
        Following prompt requirement: must precisely recreate text position and appearance
        using all layout information from MinerU/PyMuPDF.
        
        This method uses ONLY the structured data from the document, without accessing
        the original PDF file.
        
        Args:
            document: Complete bank document structure with all necessary information
            
        Returns:
            PDF file as bytes
        """
        buffer = io.BytesIO()
        
        # Get actual page size from PageData (from OCR extraction)
        page_size = letter  # Default fallback
        
        if document.pages:
            first_page = document.pages[0]
            if hasattr(first_page, 'page_width') and first_page.page_width:
                page_size = (first_page.page_width, first_page.page_height or 792)
            else:
                # If page dimensions not available, use default letter size
                # This should ideally be set during OCR extraction
                page_size = letter
        
        self.page_width, self.page_height = page_size
        c = canvas.Canvas(buffer, pagesize=page_size)
        
        # Process each page
        for page_idx, page_data in enumerate(document.pages):
            # Update page size if this page has different dimensions
            if hasattr(page_data, 'page_width') and page_data.page_width:
                page_size = (page_data.page_width, page_data.page_height or self.page_height)
                self.page_width, self.page_height = page_size
                # Note: ReportLab doesn't support per-page sizes easily, so we use first page size
                # For multi-page documents with different sizes, this is a limitation
            
            # Reset rendered regions for each page
            self.rendered_regions[page_idx] = []
            self._render_page(c, page_data, document, page_idx)
            c.showPage()
        
        c.save()
        buffer.seek(0)
        return buffer.read()
    
    def rebuild_pdf_to_file(
        self,
        document: BankDocument,
        output_path: str
    ) -> None:
        """Rebuild PDF and save to file."""
        pdf_bytes = self.rebuild_pdf(document)
        with open(output_path, 'wb') as f:
            f.write(pdf_bytes)
    
    def _render_page(
        self,
        canvas_obj: canvas.Canvas,
        page_data: Any,
        document: BankDocument,
        page_idx: int = 0
    ):
        """
        Render a single page.
        
        Args:
            canvas_obj: ReportLab canvas
            page_data: Page data with layout elements
            document: Complete document (for metadata)
            page_idx: Page index (0-based)
        """
        # Sort elements by Y position (top to bottom) to ensure correct rendering order
        elements = sorted(
            page_data.layout_elements,
            key=lambda e: (e.bbox.y, e.bbox.x)
        )
        
        # CRITICAL: Final deduplication pass at render time
        # Even though deduplication was done in pipeline, we need another pass here
        # because table elements might have partial overlaps that weren't caught,
        # or rendering coordinates might reveal overlaps not visible in raw bbox data
        # This is especially critical for table elements which may be over-segmented
        elements = self._final_render_time_deduplicate(elements, page_idx)
        
        # Render layout elements in order (following prompt: preserve exact order)
        for element in elements:
            self._render_element(
                canvas_obj, 
                element, 
                page_data.page_number,
                page_idx
            )
    
    def _render_element(
        self,
        canvas_obj: canvas.Canvas,
        element: LayoutElement,
        page_num: int = 1,
        page_idx: int = 0
    ):
        """
        Render a single layout element.
        
        Following prompt requirement: use all layout information for precise reconstruction.
        This method uses ONLY the structured data from the element, without accessing
        the original PDF file.
        """
        bbox = element.bbox
        
        # Calculate precise position with proper coordinate transformation
        # PyMuPDF coordinates: (0,0) at top-left, Y increases downward
        # ReportLab coordinates: (0,0) at bottom-left, Y increases upward
        
        # X coordinate: keep as-is (left to right)
        # CRITICAL: For elements at left edge (like "BBVA" logo), preserve exact position
        x = bbox.x
        
        # Y coordinate: transform from PyMuPDF to ReportLab
        # In PyMuPDF: y is distance from top
        # In ReportLab: y is distance from bottom
        # So: y_pdf = page_height - (y_pymupdf + height)
        y_pdf = self.page_height - (bbox.y + bbox.height)
        
        # For elements near edges, be more careful with boundary adjustments
        # Don't shift critical header elements (like "BBVA" at top-left)
        # CRITICAL: Use absolute pixel thresholds, not percentages, because page dimensions vary
        # Typical header: y < 100px and x < 150px (or < 20% of width, whichever is larger)
        y_threshold = min(100, self.page_height * 0.15)  # Use 100px or 15% of height, whichever is smaller
        x_threshold = max(150, self.page_width * 0.25)  # Use 150px or 25% of width, whichever is larger
        is_header_element = (bbox.y < y_threshold) and (bbox.x < x_threshold)
        
        # Also check if content suggests it's a header (like "BBVA")
        if element and element.type == ElementType.TEXT:
            content_str = str(element.content or "").upper()
            if any(keyword in content_str for keyword in ["BBVA", "IPAB", "LOGO", "HEADER"]):
                is_header_element = True
        
        # Strict boundary checks - but preserve exact positions for header elements
        if is_header_element:
            # For header elements, only clip if absolutely necessary
            x = max(0, min(x, self.page_width - bbox.width))
            y_pdf = max(0, min(y_pdf, self.page_height - bbox.height))
        else:
            # For other elements, apply normal margin
            x = max(self.margin, min(x, self.page_width - self.margin - bbox.width))
            y_pdf = max(self.margin, min(y_pdf, self.page_height - self.margin - bbox.height))
        
        # Ensure element fits within page
        element_width = min(bbox.width, self.page_width - (x if is_header_element else 2 * self.margin))
        element_height = min(bbox.height, self.page_height - (y_pdf if is_header_element else 2 * self.margin))
        
        if not is_header_element:
            # Normal boundary adjustment for non-header elements
            if x + element_width > self.page_width - self.margin:
                x = self.page_width - self.margin - element_width
            if y_pdf + element_height > self.page_height - self.margin:
                y_pdf = self.page_height - self.margin - element_height
        
        
        
        if element.type == ElementType.TEXT:
            # Render text with format information
            self._render_text(
                canvas_obj,
                str(element.content),
                x,
                y_pdf,
                element_width,
                element_height,
                element,  # Pass element for format info
                page_idx
            )
        
        elif element.type == ElementType.TABLE:
            # Render table
            self._render_table(
                canvas_obj,
                element.content,
                x,
                y_pdf,
                element_width,
                element_height
            )
        
        elif element.type == ElementType.IMAGE:
            # Render image - use stored image data from OCR extraction
            # Check if this is a drawing (graphics/chart) or actual image
            content = element.content
            if isinstance(content, dict) and content.get("type") == "drawing":
                # This is a drawing element (chart, graphics, paths)
                # Use stored drawing data from OCR extraction
                self._render_drawing_placeholder(
                    canvas_obj,
                    element,
                    x,
                    y_pdf,
                    element_width,
                    element_height,
                    page_num
                )
            else:
                # Actual image - use stored image data
                self._render_image(
                    canvas_obj, 
                    element, 
                    x, 
                    y_pdf, 
                    element_width, 
                    element_height, 
                    page_num,
                    page_idx
                )
    
    def _render_text(
        self,
        canvas_obj: canvas.Canvas,
        text: str,
        x: float,
        y: float,
        width: float,
        height: float,
        element: Optional[LayoutElement] = None,
        page_idx: int = 0
    ):
        """
        Render text element using original format information.
        
        Following prompt requirement: must precisely recreate text position and appearance
        using all layout information from extraction.
        
        Improved version with:
        - Precise coordinate calculation
        - Overlap detection
        - Better Unicode/QR code support
        - Boundary checking
        """
        if not text or not text.strip():
            return
        
        # Clean and normalize text for rendering
        text = self._clean_text_for_rendering(text)
        
        # Use original font information if available
        # CRITICAL: Trust OCR-extracted font size, don't estimate from bbox
        # Bbox height can be larger than font size due to line spacing
        if element and element.font_size and element.font_size > 0:
            font_size = float(element.font_size)
        elif element and element.lines:
            # Try to get font size from first line format
            first_line = element.lines[0] if element.lines else None
            if first_line and isinstance(first_line, dict):
                line_format = first_line.get("format", {})
                line_size = line_format.get("size")
                if line_size and line_size > 0:
                    font_size = float(line_size)
                else:
                    # Last resort: estimate from bbox, but be more conservative
                    font_size = max(6, min(height / 1.5, 24)) if height > 0 else 10
            else:
                font_size = max(6, min(height / 1.5, 24)) if height > 0 else 10
        elif height > 0:
            # Conservative fallback: bbox height often includes line spacing
            # Use a more conservative ratio
            font_size = max(6, min(height / 1.5, 24))
        else:
            font_size = 10
        
        # Use original font name if available
        if element and element.font_name:
            # Map PyMuPDF font names to ReportLab fonts
            font_name = self._map_font_name(element.font_name)
        else:
            font_name = "Courier"  # Default fallback
        
        # Apply font flags (bold, italic)
        if element and element.font_flags:
            flags = element.font_flags
            # PyMuPDF flags: bit 16 = bold, bit 1 = italic
            if flags & 16:  # Bold
                if "Bold" not in font_name and "Helvetica" in font_name:
                    font_name = font_name.replace("Helvetica", "Helvetica-Bold")
                elif "Bold" not in font_name:
                    font_name = font_name + "-Bold"
            if flags & 1:  # Italic
                if "Oblique" not in font_name and "Italic" not in font_name:
                    if "Bold" in font_name:
                        font_name = font_name.replace("Bold", "BoldOblique")
                    else:
                        font_name = font_name + "-Oblique"
        
        canvas_obj.setFont(font_name, font_size)
        
        # Set color if available
        if element and element.color:
            canvas_obj.setFillColorRGB(
                element.color[0],
                element.color[1],
                element.color[2]
            )
        else:
            canvas_obj.setFillColorRGB(0, 0, 0)  # Black default
        
        # Handle multi-line text (preserve line breaks from raw_text)
        lines = text.split('\n')
        
        # Use original line spacing if available
        if element and element.line_spacing:
            line_height = font_size * element.line_spacing
        else:
            line_height = font_size * 1.2  # Default
        
        # Render each line - use line-level info if available for maximum precision
        if element and element.lines:
            # CRITICAL: Pre-cluster lines that are on the same row (different columns)
            # This ensures all columns on the same row use the exact same Y coordinate
            # Strategy: Group lines by Y coordinate, then identify which groups have multiple columns
            lines_by_y = {}  # y_key (rounded) -> list of (line_idx, x, y)
            
            # First pass: Group all lines by Y coordinate
            for i, line_info in enumerate(element.lines):
                if not line_info or len(line_info.get("bbox", [])) < 4:
                    continue
                
                line_bbox = line_info.get("bbox", [])
                line_y_top = line_bbox[1]
                line_x = line_bbox[0]
                
                # CRITICAL: Round Y to nearest 0.5px to group similar Y values
                # This ensures lines with very close Y values (e.g., 388.756 vs 388.760) are grouped together
                # Using 0.5px precision instead of 1px for better accuracy
                y_key = round(line_y_top * 2) / 2
                
                if y_key not in lines_by_y:
                    lines_by_y[y_key] = []
                lines_by_y[y_key].append((i, line_x, line_y_top))
            
            # Second pass: Build cluster map - for each line, find its cluster Y (first line's Y on same row)
            same_row_clusters = {}  # line_index -> cluster_y (first line's Y on this row)
            same_row_first_line = {}  # line_index -> first_line_idx (for baseline calculation)
            
            for y_key, lines in lines_by_y.items():
                if len(lines) > 1:
                    # Multiple lines on same Y - check X differences
                    x_positions = [x for _, x, _ in lines]
                    x_min = min(x_positions)
                    x_max = max(x_positions)
                    x_diff = x_max - x_min
                    
                    if x_diff > 30.0:  # Significant X difference = different columns on same row
                        # Find the first line (smallest index) in this group
                        first_line_idx = min(i for i, _, _ in lines)
                        # Get the actual Y from the first line
                        first_line_y = None
                        for line_idx, _, y_val in lines:
                            if line_idx == first_line_idx:
                                first_line_y = y_val
                                break
                        
                        if first_line_y is not None:
                            # CRITICAL: All lines in this group should use the first line's Y
                            # Even if their original Y values are the same, we need to ensure
                            # they all use the exact same baseline calculation
                            for line_idx, _, _ in lines:
                                same_row_clusters[line_idx] = first_line_y
                                same_row_first_line[line_idx] = first_line_idx
                                # CRITICAL: Mark ALL lines in this group, including the first one
                                # This ensures they all go through the same baseline calculation path
                else:
                    # Single line on this Y - use its own Y (not part of multi-column row)
                    line_idx = lines[0][0]
                    line_y = lines[0][2]
                    same_row_clusters[line_idx] = line_y
                    # Don't add to same_row_first_line - it's not a multi-column row
            
            # Use precise line-level information (bbox, format per line)
            for i, line_info in enumerate(element.lines):
                if not line_info:
                    continue
                
                line_text = line_info.get("text", "")
                line_bbox_list = line_info.get("bbox", [])
                line_format = line_info.get("format", {})
                
                # CRITICAL: Check if this line is part of a multi-column row FIRST
                # This must be done before font size calculation to ensure consistency
                same_row_y = None
                same_row_first_line_idx = None
                
                # Check clustering (needs to be done before font calculation)
                if i in same_row_first_line:
                    cluster_y = same_row_clusters[i]
                    same_row_y = cluster_y
                    same_row_first_line_idx = same_row_first_line[i]
                
                # Use line-specific format if available
                # CRITICAL: For same-row lines, use the first line's font size to ensure consistency
                if same_row_first_line_idx is not None:
                    # This line is on the same row - use first line's font size
                    first_line_info = element.lines[same_row_first_line_idx]
                    first_line_format = first_line_info.get("format", {}) if first_line_info else {}
                    line_font_size = float(first_line_format.get("size", font_size)) if first_line_format.get("size") else font_size
                    if line_font_size <= 0:
                        line_font_size = font_size
                    
                    # Use first line's font name too
                    first_line_font = first_line_format.get("font", "") if first_line_format.get("font") else font_name
                    if first_line_font:
                        line_font_name = self._map_font_name(first_line_font)
                        # Apply font flags from first line
                        first_line_flags = first_line_format.get("flags", 0)
                        if first_line_flags & 16:  # Bold
                            if "Bold" not in line_font_name:
                                line_font_name = line_font_name.replace("Helvetica", "Helvetica-Bold")
                                if "Helvetica" not in line_font_name:
                                    line_font_name = line_font_name + "-Bold"
                        if first_line_flags & 1:  # Italic
                            if "Oblique" not in line_font_name and "Italic" not in line_font_name:
                                line_font_name = line_font_name.replace("Bold", "BoldOblique") if "Bold" in line_font_name else line_font_name + "-Oblique"
                    else:
                        line_font_name = font_name
                else:
                    # Not on same row - use this line's own format
                    line_font_size = float(line_format.get("size", font_size)) if line_format.get("size") else font_size
                    if line_font_size <= 0:
                        line_font_size = font_size
                    line_font_name = line_format.get("font", "") if line_format.get("font") else font_name
                    if line_font_name:
                        line_font_name = self._map_font_name(line_font_name)
                        # Apply font flags
                        line_flags = line_format.get("flags", 0)
                        if line_flags & 16:  # Bold
                            if "Bold" not in line_font_name:
                                line_font_name = line_font_name.replace("Helvetica", "Helvetica-Bold")
                                if "Helvetica" not in line_font_name:
                                    line_font_name = line_font_name + "-Bold"
                        if line_flags & 1:  # Italic
                            if "Oblique" not in line_font_name and "Italic" not in line_font_name:
                                line_font_name = line_font_name.replace("Bold", "BoldOblique") if "Bold" in line_font_name else line_font_name + "-Oblique"
                    else:
                        line_font_name = font_name
                
                canvas_obj.setFont(line_font_name, line_font_size)
                
                # Use line-specific color if available
                if line_format.get("color"):
                    line_color_val = line_format.get("color", 0)
                    if isinstance(line_color_val, (list, tuple)) and len(line_color_val) >= 3:
                        canvas_obj.setFillColorRGB(float(line_color_val[0]), float(line_color_val[1]), float(line_color_val[2]))
                    elif isinstance(line_color_val, (int, float)) and line_color_val != 0:
                        if line_color_val < 256:
                            gray = line_color_val / 255.0
                            canvas_obj.setFillColorRGB(gray, gray, gray)
                        else:
                            r = ((int(line_color_val) >> 16) & 0xFF) / 255.0
                            g = ((int(line_color_val) >> 8) & 0xFF) / 255.0
                            b = (int(line_color_val) & 0xFF) / 255.0
                            canvas_obj.setFillColorRGB(r, g, b)
                elif element and element.color:
                    canvas_obj.setFillColorRGB(element.color[0], element.color[1], element.color[2])
                else:
                    canvas_obj.setFillColorRGB(0, 0, 0)
                
                # Use precise line bbox if available - correct coordinate transformation
                if len(line_bbox_list) >= 4:
                    # Line bbox: [x0, y0_top, x1, y1_bottom] in PyMuPDF coordinates (top-left origin)
                    # Where y0_top is distance from top, y1_bottom is also from top
                    line_x = line_bbox_list[0]
                    line_y_top_pymupdf = line_bbox_list[1]  # Distance from top in PyMuPDF
                    line_y_bottom_pymupdf = line_bbox_list[3]  # Bottom Y (also from top)
                    
                    # CRITICAL: Use pre-clustered Y coordinate if this line is on the same row
                    # This ensures all columns on the same row use the exact same Y coordinate
                    same_row_y = None
                    same_row_first_line_idx = None
                    
                    # CRITICAL: Check if this line is part of a multi-column row FIRST
                    # This ensures ALL columns (including the first one) use the same baseline calculation
                    if i in same_row_first_line:
                        # This line is part of a multi-column row
                        cluster_y = same_row_clusters[i]
                        same_row_y = cluster_y
                        same_row_first_line_idx = same_row_first_line[i]
                    
                    if same_row_y is not None and same_row_first_line_idx is not None:
                        # This line is on the same row as other lines (different columns)
                        # CRITICAL: Use the exact same Y position and baseline calculation as the first line on this row
                        # This ensures all columns on the same row are perfectly aligned
                        line_y_top_pymupdf = same_row_y
                        
                        # Get the first line's bottom Y and format for consistency
                        first_line_info = element.lines[same_row_first_line_idx]
                        if first_line_info and len(first_line_info.get("bbox", [])) >= 4:
                            line_y_bottom_pymupdf = first_line_info.get("bbox", [])[3]
                            
                            # Use the same baseline calculation as the first line on this row
                            # This ensures perfect alignment even if font sizes differ slightly
                            first_line_format = first_line_info.get("format", {})
                            first_line_font_size = float(first_line_format.get("size", line_font_size)) if first_line_format.get("size") else line_font_size
                            if first_line_font_size > 0:
                                baseline_offset = first_line_font_size * 0.8
                            else:
                                baseline_offset = line_font_size * 0.8 if line_font_size > 0 else 10
                        else:
                            # Fallback: use current line's font size
                            baseline_offset = line_font_size * 0.8 if line_font_size > 0 else 10
                    else:
                        # Not on same row - calculate normally
                        line_height_pymupdf = line_y_bottom_pymupdf - line_y_top_pymupdf
                        
                        # Calculate baseline - prefer using actual font size
                        if line_font_size > 0:
                            # Use font size with baseline ratio
                            baseline_offset = line_font_size * 0.8
                        elif line_height_pymupdf > 0:
                            # Fallback: use line height
                            baseline_offset = line_height_pymupdf * 0.8
                        else:
                            # Last resort: small default
                            baseline_offset = 10
                    
                    baseline_y_pymupdf = line_y_top_pymupdf + baseline_offset
                    
                    # Convert to ReportLab coordinates (bottom-left origin)
                    # In ReportLab, y is distance from bottom
                    # So: y_pdf = page_height - y_pymupdf
                    line_y = self.page_height - baseline_y_pymupdf
                else:
                    # Fallback to calculated position
                    line_x = x
                    # Calculate Y from top of element, going upward in PDF coordinates
                    line_y = y + height - ((i + 1) * line_height)
                    
                    # Calculate alignment
                    if element and element.alignment and width > 0:
                        text_width = canvas_obj.stringWidth(line_text, line_font_name, line_font_size)
                        if element.alignment == "center":
                            line_x = x + (width - text_width) / 2
                        elif element.alignment == "right":
                            line_x = x + width - text_width
                
                # Clean text for rendering (handle special characters)
                line_text_clean = self._clean_text_for_rendering(line_text)
                
                # Only check overlap if position seems suspicious (not for precise line-level bbox)
                # If we have precise line bbox, trust it - don't adjust to avoid overlap
                # Overlap detection should only be used as a safety check, not to override precise positions
                # CRITICAL: If this line is on the same row as a previous line, never adjust Y position
                # This ensures perfect alignment for table columns
                check_overlap = len(line_bbox_list) < 4 and same_row_y is None  # Only check if we don't have precise bbox AND not on same row
                if check_overlap:
                    if self._would_overlap(line_x, line_y, line_text_clean, line_font_name, line_font_size, page_idx):
                        # For calculated positions, try to avoid overlap, but only slightly
                        # Don't override precise bbox positions
                        adjusted_y = self._find_non_overlapping_y(
                            line_x, line_y, line_text_clean, line_font_name, line_font_size, page_idx
                        )
                        # Only use adjusted position if it's very close (within 2 font sizes)
                        if abs(adjusted_y - line_y) < line_font_size * 2:
                            line_y = adjusted_y
                
                # Strict boundary check with text width consideration
                text_width = canvas_obj.stringWidth(line_text_clean, line_font_name, line_font_size)
                
                # X boundary check
                if line_x < self.margin:
                    line_x = self.margin
                if line_x + text_width > self.page_width - self.margin:
                    # Try to fit by truncating if too long
                    if text_width > self.page_width - 2 * self.margin:
                        # Truncate text with ellipsis if too long
                        max_width = self.page_width - 2 * self.margin
                        line_text_clean = self._truncate_text(line_text_clean, line_font_name, line_font_size, max_width, canvas_obj)
                        text_width = canvas_obj.stringWidth(line_text_clean, line_font_name, line_font_size)
                    line_x = self.page_width - self.margin - text_width
                
                # Y boundary check - use stricter check for baseline position
                # drawString draws from baseline, so we need to ensure:
                # - baseline is not too low (below margin)
                # - text height above baseline doesn't exceed page
                text_ascent = line_font_size * 0.8  # Approximate ascent
                text_descent = line_font_size * 0.2  # Approximate descent
                
                # Check if baseline is valid
                # CRITICAL: If this line is on the same row, NEVER adjust Y position
                # This ensures perfect alignment for table columns
                if line_y < self.margin + text_descent:
                    # Baseline too low, skip or adjust minimally
                    if same_row_y is not None:
                        # On same row - keep Y position even if slightly outside margin
                        # This ensures alignment with other columns
                        pass
                    elif check_overlap:  # Only adjust if we don't have precise bbox
                        line_y = self.margin + text_descent
                    else:
                        continue  # Skip if precise position is outside
                
                # Check if text extends beyond top of page
                if line_y + text_ascent > self.page_height - self.margin:
                    if same_row_y is not None:
                        # On same row - keep Y position even if slightly outside margin
                        # This ensures alignment with other columns
                        pass
                    elif check_overlap:
                        # Adjust if we can
                        line_y = self.page_height - self.margin - text_ascent
                        if line_y < self.margin + text_descent:
                            continue  # Can't fit, skip
                    else:
                        continue  # Precise position doesn't fit, skip
                
                # Render line at precise position
                try:
                    # Try to render with UTF-8 support first
                    canvas_obj.drawString(line_x, line_y, line_text_clean)
                    # Record rendered region for overlap detection
                    # height parameter is font size for overlap calculation
                    self._record_rendered_region(
                        line_x, line_y, text_width, line_font_size, page_idx
                    )
                except (UnicodeEncodeError, TypeError, ValueError) as e:
                    # Fallback for encoding issues (e.g., QR codes, special characters)
                    try:
                        # Try with ASCII replacement
                        line_text_encoded = line_text_clean.encode('ascii', 'replace').decode('ascii')
                        if line_text_encoded:  # Only render if we have something left
                            canvas_obj.drawString(line_x, line_y, line_text_encoded)
                            self._record_rendered_region(
                                line_x, line_y, text_width, line_font_size, page_idx
                            )
                        else:
                            # If encoding removes everything, try latin1
                            try:
                                line_text_latin1 = line_text_clean.encode('latin1', 'replace').decode('latin1')
                                canvas_obj.drawString(line_x, line_y, line_text_latin1)
                                self._record_rendered_region(
                                    line_x, line_y, text_width, line_font_size, page_idx
                                )
                            except:
                                # Last resort: render placeholder for QR code/special content
                                if 'BBVA' not in line_text_clean and 'IPAB' not in line_text_clean:
                                    # Don't skip BBVA or IPAB, these are important
                                    pass
                    except Exception:
                        # If all encoding attempts fail, check if it's critical text
                        if 'BBVA' in line_text_clean or 'IPAB' in line_text_clean:
                            # For critical text, try one more time with error handling
                            try:
                                # Force ASCII representation
                                safe_text = ''.join(c if ord(c) < 128 else '?' for c in line_text_clean)
                                canvas_obj.drawString(line_x, line_y, safe_text)
                                self._record_rendered_region(
                                    line_x, line_y, text_width, line_font_size, page_idx
                                )
                            except:
                                pass  # Skip if still fails
                        pass  # Skip problematic text
        else:
            # Fallback: render using block-level info
            max_lines = int(height / line_height) if height > 0 else len(lines)
            for i, line in enumerate(lines[:max_lines]):
                # Preserve empty lines for structure
                # if not line.strip():
                #     continue
                
                # Calculate x position based on alignment
                line_x = x
                if element and element.alignment and width > 0:
                    text_width = canvas_obj.stringWidth(line, font_name, font_size)
                    if element.alignment == "center":
                        line_x = x + (width - text_width) / 2
                    elif element.alignment == "right":
                        line_x = x + width - text_width
                
                # Draw line at correct y position (going upward from bottom)
                # Calculate baseline position for this line
                # Element's y is bottom-left in PDF coordinates
                # We want baseline, which is typically 80% of font size from top of text
                text_ascent = font_size * 0.8
                text_descent = font_size * 0.2
                
                # Calculate Y position: from bottom of element, going upward
                # For each line, we need: element_bottom + line_height * line_index + text_ascent
                line_y = y + (i * line_height) + text_ascent
                
                # Clean text
                line_clean = self._clean_text_for_rendering(line)
                
                # Boundary check - X
                text_width = canvas_obj.stringWidth(line_clean, font_name, font_size)
                if line_x + text_width > self.page_width - self.margin:
                    max_width = self.page_width - 2 * self.margin
                    line_clean = self._truncate_text(line_clean, font_name, font_size, max_width, canvas_obj)
                    text_width = canvas_obj.stringWidth(line_clean, font_name, font_size)
                    line_x = self.page_width - self.margin - text_width
                
                # Boundary check - Y (baseline position)
                if line_y < self.margin + text_descent:
                    # Baseline too low
                    line_y = self.margin + text_descent
                    # Check if we've exceeded the element bounds
                    if line_y - text_ascent > y + height:
                        break  # Stop if we've gone past the element
                
                # Check if text extends beyond top of page
                if line_y + text_ascent > self.page_height - self.margin:
                    # Can't fit this line, stop
                    break
                
                # Check overlap only as a safety check (not overriding position)
                if self._would_overlap(line_x, line_y, line_clean, font_name, font_size, page_idx):
                    # Only adjust if overlap is severe and position was calculated (not from bbox)
                    adjusted_y = self._find_non_overlapping_y(
                        line_x, line_y, line_clean, font_name, font_size, page_idx
                    )
                    # Only use if adjustment is small (within 1.5 font sizes)
                    if abs(adjusted_y - line_y) < font_size * 1.5:
                        line_y = adjusted_y
                    # Otherwise, render at original position (trust the calculation)
                    
                try:
                    canvas_obj.drawString(line_x, line_y, line_clean)
                    # Record with font size as height for overlap detection
                    self._record_rendered_region(line_x, line_y, text_width, font_size, page_idx)
                except Exception:
                    try:
                        line_encoded = line_clean.encode('ascii', 'replace').decode('ascii')
                        canvas_obj.drawString(line_x, line_y, line_encoded)
                        self._record_rendered_region(line_x, line_y, text_width, font_size, page_idx)
                    except Exception:
                        pass
    
    def _render_image(
        self,
        canvas_obj: canvas.Canvas,
        element: LayoutElement,
        x: float,
        y: float,
        width: float,
        height: float,
        page_num: int = 1,
        page_idx: int = 0
    ):
        """
        Render image element using stored image data from OCR extraction.
        
        Following prompt requirement: must precisely recreate all visual elements.
        This method uses ONLY the structured data from the element, without accessing
        the original PDF file.
        """
        if width <= 0 or height <= 0:
            return
        
        # Try to use stored image data from OCR extraction
        if isinstance(element.content, dict):
            img_info = element.content
            
            # Check for stored image data (base64 encoded or bytes)
            image_data = None
            image_ext = img_info.get("ext", "png")
            
            # Try to get image data from various possible fields
            if "image_data" in img_info:
                # Image data stored as base64 string or bytes
                import base64
                img_data_raw = img_info["image_data"]
                if isinstance(img_data_raw, str):
                    # Base64 encoded string
                    try:
                        image_data = base64.b64decode(img_data_raw)
                    except Exception:
                        pass
                elif isinstance(img_data_raw, bytes):
                    # Already bytes
                    image_data = img_data_raw
            
            if image_data:
                try:
                    from reportlab.lib.utils import ImageReader
                    from io import BytesIO
                    from PIL import Image
                    
                    # Create PIL Image from bytes
                    img = Image.open(BytesIO(image_data))
                    
                    # Calculate scaling to fit bbox
                    img_width, img_height = img.size
                    scale_x = width / img_width if img_width > 0 else 1.0
                    scale_y = height / img_height if img_height > 0 else 1.0
                    scale = min(scale_x, scale_y)  # Maintain aspect ratio
                    
                    # Scale image
                    if scale != 1.0:
                        new_width = int(img_width * scale)
                        new_height = int(img_height * scale)
                        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    
                    # Convert to ReportLab format
                    img_buffer = BytesIO()
                    img.save(img_buffer, format=image_ext.upper() if image_ext else 'PNG')
                    img_buffer.seek(0)
                    
                    # Draw image at exact position
                    # CRITICAL: For logos (like IPAB), preserve exact position
                    # Check if this is likely a logo (small image near top or edges)
                    # Note: y parameter is already in PDF coordinates (bottom-left origin)
                    is_logo = (height < 100) and (width < 200) and (
                        (y > self.page_height * 0.9) or  # Near top
                        (y < self.page_height * 0.1) or  # Near bottom
                        (x < self.page_width * 0.2) or       # Near left
                        (x > self.page_width * 0.8)         # Near right
                    )
                    
                    # Ensure image fits within page boundaries
                    if is_logo:
                        # For logos, preserve exact position, only clip if absolutely necessary
                        img_draw_width = min(width, self.page_width - x)
                        img_draw_height = min(height, self.page_height - y)
                        img_x = max(0, min(x, self.page_width - img_draw_width))
                        img_y = max(0, min(y, self.page_height - img_draw_height))
                    else:
                        # For other images, apply normal margin
                        img_draw_width = min(width, self.page_width - x - self.margin)
                        img_draw_height = min(height, self.page_height - y - self.margin)
                        img_x = max(self.margin, min(x, self.page_width - img_draw_width - self.margin))
                        img_y = max(self.margin, min(y, self.page_height - img_draw_height - self.margin))
                    
                    if img_draw_width > 0 and img_draw_height > 0:
                        canvas_obj.drawImage(
                            ImageReader(img_buffer),
                            img_x,
                            img_y,
                            width=img_draw_width,
                            height=img_draw_height,
                            preserveAspectRatio=True,
                            mask='auto'
                        )
                        return
                except Exception as e:
                    print(f"Warning: Could not render stored image data: {e}")
        
        # Fallback: Draw placeholder rectangle (only if image data not available)
        # Ensure placeholder fits within page
        placeholder_width = min(width, self.page_width - x - self.margin)
        placeholder_height = min(height, self.page_height - y - self.margin)
        
        if placeholder_width > 0 and placeholder_height > 0:
            placeholder_x = max(self.margin, min(x, self.page_width - placeholder_width - self.margin))
            placeholder_y = max(self.margin, min(y, self.page_height - placeholder_height - self.margin))
            
            canvas_obj.setStrokeColorRGB(0.8, 0.8, 0.8)  # Light gray border
            canvas_obj.setFillColorRGB(0.95, 0.95, 0.95)  # Light gray fill
            canvas_obj.rect(placeholder_x, placeholder_y, placeholder_width, placeholder_height, fill=1, stroke=1)
            
            # Add text label if image info available
            if isinstance(element.content, dict):
                img_info = element.content
                label = f"Image {img_info.get('index', '?')}"
                canvas_obj.setFillColorRGB(0.5, 0.5, 0.5)
                canvas_obj.setFont("Helvetica", 8)
                canvas_obj.drawCentredString(
                    placeholder_x + placeholder_width/2, 
                    placeholder_y + placeholder_height/2, 
                    label
                )
    
    def _render_drawing_placeholder(
        self,
        canvas_obj: canvas.Canvas,
        element: LayoutElement,
        x: float,
        y: float,
        width: float,
        height: float,
        page_num: int = 1
    ):
        """
        Render drawing elements (charts, graphics, paths).
        
        Following prompt requirement: must capture all visual elements.
        
        This method uses ONLY the structured data from the element, without accessing
        the original PDF file. It uses stored drawing data from OCR extraction.
        """
        if width <= 0 or height <= 0:
            return
        
        # Try to use stored drawing image data if available
        if isinstance(element.content, dict):
            drawing_data = element.content
            
            # Check for stored drawing image data (base64 encoded or bytes)
            image_data = None
            if "image_data" in drawing_data:
                # Drawing rendered as image during OCR extraction
                import base64
                img_data_raw = drawing_data["image_data"]
                if isinstance(img_data_raw, str):
                    # Base64 encoded string
                    try:
                        image_data = base64.b64decode(img_data_raw)
                    except Exception:
                        pass
                elif isinstance(img_data_raw, bytes):
                    # Already bytes
                    image_data = img_data_raw
            
            if image_data:
                try:
                    from reportlab.lib.utils import ImageReader
                    from io import BytesIO
                    from PIL import Image
                    
                    # Create PIL Image from bytes
                    img = Image.open(BytesIO(image_data))
                    
                    # Scale to fit the target size
                    img_width, img_height = img.size
                    if img_width != width or img_height != height:
                        img = img.resize((int(width), int(height)), Image.Resampling.LANCZOS)
                    
                    # Convert to ReportLab format
                    img_buffer = BytesIO()
                    img.save(img_buffer, format='PNG')
                    img_buffer.seek(0)
                    
                    # Ensure image fits within page boundaries
                    img_draw_width = min(width, self.page_width - x - self.margin)
                    img_draw_height = min(height, self.page_height - y - self.margin)
                    
                    if img_draw_width > 0 and img_draw_height > 0:
                        img_x = max(0, min(x, self.page_width - img_draw_width))
                        img_y = max(0, min(y, self.page_height - img_draw_height))
                        
                        # Draw the stored drawing image at exact position
                        canvas_obj.drawImage(
                            ImageReader(img_buffer),
                            img_x,
                            img_y,
                            width=img_draw_width,
                            height=img_draw_height,
                            preserveAspectRatio=False,
                            mask='auto'
                        )
                        return
                except Exception as e:
                    # If image rendering fails, fall back to rendering paths or placeholder
                    print(f"Warning: Could not render stored drawing image: {e}")
        
        # Fallback: Try to render basic paths from drawing data
        drawing_data = element.content.get("drawing_data", {}) if isinstance(element.content, dict) else {}
        items = drawing_data.get("items", [])
        
        if items:
            try:
                # Try to render basic drawing items (lines, rectangles, etc.)
                self._render_drawing_items(canvas_obj, items, x, y, width, height)
                return
            except Exception:
                pass
        
        # Last resort: Render a placeholder
        # For very small drawings (thin lines), just draw a line
        if height < 1 or width < 1:
            canvas_obj.setStrokeColorRGB(0.3, 0.3, 0.3)
            canvas_obj.setLineWidth(0.5)
            if width < 1:
                # Vertical line
                canvas_obj.line(x, y, x, y + height)
            else:
                # Horizontal line
                canvas_obj.line(x, y, x + width, y)
            return
        
        # For larger drawings (charts, graphics), draw a light border
        # Use light gray to indicate drawing area without obscuring
        canvas_obj.setStrokeColorRGB(0.7, 0.7, 0.9)  # Light blue border
        canvas_obj.setFillColorRGB(0.95, 0.95, 0.98)  # Very light blue fill
        canvas_obj.setLineWidth(0.5)
        canvas_obj.rect(x, y, width, height, fill=1, stroke=1)
        
        # Add a subtle label for larger drawings
        if width > 50 and height > 20:
            items_count = len(items) if items else 0
            if items_count > 0:
                label = f"Drawing ({items_count} items)"
                canvas_obj.setFillColorRGB(0.5, 0.5, 0.5)
                canvas_obj.setFont("Helvetica", 7)
                try:
                    canvas_obj.drawCentredString(x + width/2, y + height/2, label)
                except:
                    pass
    
    def _render_drawing_items(
        self,
        canvas_obj: canvas.Canvas,
        items: List[Dict[str, Any]],
        offset_x: float,
        offset_y: float,
        width: float,
        height: float
    ):
        """
        Render basic drawing items (lines, rectangles, paths).
        
        This is a simplified renderer for basic vector graphics.
        Complex paths may not be fully reconstructed.
        """
        for item in items[:100]:  # Limit to first 100 items for performance
            try:
                item_type = item.get("type", "")
                
                if item_type == "l":  # Line
                    points = item.get("points", [])
                    if len(points) >= 4:
                        x1, y1 = points[0], points[1]
                        x2, y2 = points[2], points[3]
                        # Convert coordinates and draw
                        canvas_obj.setStrokeColorRGB(0, 0, 0)
                        canvas_obj.setLineWidth(0.5)
                        canvas_obj.line(x1 + offset_x, offset_y + height - y1, 
                                       x2 + offset_x, offset_y + height - y2)
                        
            except Exception:
                continue
    
    def _map_font_name(self, pymupdf_font: str) -> str:
        """Map PyMuPDF font names to ReportLab font names."""
        if not pymupdf_font:
            return "Helvetica"  # Default
        
        font_lower = pymupdf_font.lower()
        
        # Common mappings
        if "helvetica" in font_lower or "arial" in font_lower:
            return "Helvetica"
        elif "times" in font_lower:
            return "Times-Roman"
        elif "courier" in font_lower or "mono" in font_lower:
            return "Courier"
        elif "calibri" in font_lower:
            return "Helvetica"  # Calibri not in ReportLab, use Helvetica
        else:
            return "Helvetica"  # Default
    
    def _render_table(
        self,
        canvas_obj: canvas.Canvas,
        table_data: Any,
        x: float,
        y: float,
        width: float,
        height: float
    ):
        """Render table element."""
        # Convert table data to ReportLab Table format
        if isinstance(table_data, dict):
            rows = table_data.get("rows", [])
            if rows:
                table = self._create_reportlab_table(rows, width, height)
                table.wrapOn(canvas_obj, width, height)
                table.drawOn(canvas_obj, x, y - height)
    
    def _create_reportlab_table(
        self,
        rows: List[List[str]],
        width: float,
        height: float
    ) -> Table:
        """Create ReportLab Table from rows."""
        # Create table
        table = Table(rows, colWidths=None)
        
        # Apply style
        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ])
        table.setStyle(style)
        
        return table
    
    def _clean_text_for_rendering(self, text: str) -> str:
        """
        Clean text for rendering, handling special characters and Unicode.
        
        This helps with QR codes and special symbols that might cause encoding issues.
        """
        if not text:
            return ""
        
        # Replace problematic control characters
        text = text.replace('\x00', '')  # Remove null bytes
        
        # Handle common special characters that ReportLab might have issues with
        # Replace with similar ASCII equivalents where possible
        replacements = {
            '\u200b': '',  # Zero-width space
            '\u200c': '',  # Zero-width non-joiner
            '\u200d': '',  # Zero-width joiner
            '\ufeff': '',  # BOM
        }
        
        for old, new in replacements.items():
            text = text.replace(old, new)
        
        # For QR codes: Check if text contains QR code-like patterns
        # QR codes in PDFs often appear as special symbols or blocks
        # If the text looks like binary/encoded data, we might need to skip it
        # or render it as a placeholder
        if len(text) > 50 and not any(c.isalnum() or c.isspace() for c in text[:20]):
            # Text might be QR code data - try to preserve as-is but be ready for encoding issues
            pass
        
        return text.strip()
    
    def _final_render_time_deduplicate(
        self,
        elements: List[LayoutElement],
        page_idx: int
    ) -> List[LayoutElement]:
        """
        Final deduplication pass at render time.
        
        This method is specifically designed to catch table overlaps that might not
        have been detected during initial deduplication, especially when elements
        are segmented into multiple pieces or have slight coordinate differences.
        
        CRITICAL: For tables, if there's a table element and a text block below it
        with similar content, remove the text block below to avoid visual overlap.
        
        Following prompt requirement: preserve table form, remove duplicates, keep upper layer.
        
        Args:
            elements: List of layout elements to deduplicate
            page_idx: Page index for reference
            
        Returns:
            Deduplicated list of elements
        """
        if not elements:
            return []
        
        # Sort by Y position (upper layer first) to preserve correct order
        sorted_elements = sorted(elements, key=lambda e: (e.bbox.y, e.bbox.x))
        
        kept_elements = []
        
        for i, elem1 in enumerate(sorted_elements):
            if elem1.type != ElementType.TEXT:
                # Non-text elements always keep (images, drawings)
                kept_elements.append(elem1)
                continue
            
            content1 = str(elem1.content or "").strip()
            if not content1:
                continue
                
            bbox1 = elem1.bbox
            x1_min, y1_min = bbox1.x, bbox1.y
            x1_max = x1_min + bbox1.width
            y1_max = y1_min + bbox1.height
            area1 = bbox1.width * bbox1.height
            
            # Check if table-like
            lines1 = content1.split('\n') if content1 else []
            is_table1 = len(lines1) > 2 or any(kw in content1.lower() for kw in 
                ['periodo', 'saldo', 'depósito', 'retiro', 'fecha', 'cuenta', 
                 'rendimiento', 'comportamiento', 'comisión'])
            
            is_duplicate = False
            
            # CRITICAL: Check if this is a text block below a table element
            # If there's a table above this element with similar content, skip this text block
            for kept_elem in kept_elements:
                if kept_elem.type != ElementType.TEXT:
                    continue
                
                content2 = str(kept_elem.content or "").strip()
                if not content2:
                    continue
                    
                bbox2 = kept_elem.bbox
                x2_min, y2_min = bbox2.x, bbox2.y
                x2_max = x2_min + bbox2.width
                y2_max = y2_min + bbox2.height
                
                # Check if kept_elem is a table-like element ABOVE current element
                lines2 = content2.split('\n') if content2 else []
                is_table2 = len(lines2) > 2 or any(kw in content2.lower() for kw in 
                    ['periodo', 'saldo', 'depósito', 'retiro', 'fecha', 'cuenta', 
                     'rendimiento', 'comportamiento', 'comisión'])
                
                # CRITICAL: If kept_elem is a table and elem1 is below it
                # Check if they have similar content (same table data in different format)
                if is_table2 and y1_min > y2_max:  # elem1 is below kept_elem
                    # Check if they're in similar X positions (same column region)
                    x_center1 = (x1_min + x1_max) / 2
                    x_center2 = (x2_min + x2_max) / 2
                    x_distance = abs(x_center1 - x_center2)
                    max_width = max(bbox1.width, bbox2.width)
                    
                    # If in same column region (within 30% of width)
                    if x_distance < max_width * 0.3:
                        # Check content similarity
                        words1 = set(content1.lower().split())
                        words2 = set(content2.lower().split())
                        word_sim = len(words1 & words2) / max(len(words1 | words2), 1) if (words1 or words2) else 0
                        
                        # Check if content is subset or has high similarity
                        content_is_subset = content1.lower() in content2.lower() and len(content2) > len(content1) * 1.1
                        content_contains = content2.lower() in content1.lower() and len(content1) > len(content2) * 1.1
                        
                        # For tables, check structural similarity (same data, different formatting)
                        structural_sim = 0.0
                        if len(lines1) > 1 and len(lines2) > 1:
                            # Compare key data (numbers, dates, keywords)
                            key_words = ['periodo', 'saldo', 'depósito', 'retiro', 'fecha', 'cuenta', 
                                        'rendimiento', 'comportamiento']
                            key_words1 = [w for w in key_words if w in content1.lower()]
                            key_words2 = [w for w in key_words if w in content2.lower()]
                            if key_words1 and key_words2:
                                # If they share key table keywords
                                shared_keys = set(key_words1) & set(key_words2)
                                if len(shared_keys) >= 2:  # At least 2 shared keywords
                                    structural_sim = 0.6  # Consider it similar
                        
                        # If content is similar enough, this is likely a duplicate representation
                        # Remove the text block below the table (elem1)
                        if word_sim > 0.3 or content_is_subset or content_contains or structural_sim > 0.5:
                            is_duplicate = True
                            break
            
            # If not a duplicate below a table, check for standard overlaps
            if not is_duplicate:
                for kept_elem in reversed(kept_elements):
                    if kept_elem.type != ElementType.TEXT:
                        continue
                    
                    content2 = str(kept_elem.content or "").strip()
                    if not content2:
                        continue
                        
                    bbox2 = kept_elem.bbox
                    x2_min, y2_min = bbox2.x, bbox2.y
                    x2_max = x2_min + bbox2.width
                    y2_max = y2_min + bbox2.height
                    area2 = bbox2.width * bbox2.height
                    
                    # Calculate overlap
                    x_overlap = max(0, min(x1_max, x2_max) - max(x1_min, x2_min))
                    y_overlap = max(0, min(y1_max, y2_max) - max(y1_min, y2_min))
                    overlap_area = x_overlap * y_overlap
                    
                    min_area = min(area1, area2)
                    overlap_ratio = overlap_area / min_area if min_area > 0 else 0
                    
                    # For table elements, use more aggressive overlap detection
                    if is_table1 and overlap_area > 30 and overlap_ratio > 0.20:  # 20% for tables
                        # Check content similarity
                        words1 = set(content1.lower().split())
                        words2 = set(content2.lower().split())
                        word_sim = len(words1 & words2) / max(len(words1 | words2), 1) if (words1 or words2) else 0
                        
                        # Check if one content is subset of another
                        content_is_subset = content1.lower() in content2.lower() and len(content2) > len(content1) * 1.2
                        content_is_superset = content2.lower() in content1.lower() and len(content1) > len(content2) * 1.2
                        
                        # Check line structure similarity for tables
                        lines2 = content2.split('\n') if content2 else []
                        structural_sim = 0.0
                        if len(lines1) > 1 and len(lines2) > 1:
                            # Compare first few lines
                            matching_lines = sum(1 for l1, l2 in zip(lines1[:5], lines2[:5]) 
                                               if l1.strip() and l2.strip() and l1.strip() == l2.strip())
                            structural_sim = matching_lines / max(len(lines1[:5]), len(lines2[:5]))
                        
                        # Determine if duplicate
                        if word_sim > 0.4 or structural_sim > 0.5 or content_is_subset or content_is_superset:
                            # Keep upper layer (smaller Y) and more complete content
                            keep_current = False
                            
                            if y1_min < y2_min - 2:  # Current is clearly upper
                                keep_current = True
                            elif abs(y1_min - y2_min) <= 2:  # Same Y level
                                # Compare completeness
                                if len(lines1) > len(lines2):
                                    keep_current = True
                                elif len(lines1) == len(lines2):
                                    if len(content1) > len(content2) * 1.1:
                                        keep_current = True
                                    elif content_is_superset:
                                        keep_current = True
                                    elif content_is_subset:
                                        keep_current = False
                            
                            if keep_current:
                                # Replace the kept element with current (current is better)
                                kept_elements.remove(kept_elem)
                                # Will add elem1 later
                                break
                            else:
                                # Kept element is better, skip current
                                is_duplicate = True
                                break
                    
                    # For non-table elements, use standard overlap threshold
                    elif not is_table1 and overlap_area > 50 and overlap_ratio > 0.30:
                        # Check content similarity
                        words1 = set(content1.lower().split())
                        words2 = set(content2.lower().split())
                        word_sim = len(words1 & words2) / max(len(words1 | words2), 1) if (words1 or words2) else 0
                        
                        if word_sim > 0.5:  # Higher threshold for non-table
                            # Keep upper layer
                            if y1_min <= y2_min:
                                # Current is upper, replace kept
                                kept_elements.remove(kept_elem)
                                break
                            else:
                                # Kept is upper, skip current
                                is_duplicate = True
                                break
            
            if not is_duplicate:
                kept_elements.append(elem1)
        
        return kept_elements
    
    def _would_overlap(
        self,
        x: float,
        y: float,
        text: str,
        font_name: str,
        font_size: float,
        page_idx: int
    ) -> bool:
        """
        Check if text at position (x, y) would overlap with previously rendered text.
        
        Note: y is baseline position for drawString.
        """
        if page_idx not in self.rendered_regions:
            return False
        
        # Estimate text dimensions
        # For drawString, y is baseline position
        # Text extends from (y - descent) to (y + ascent)
        text_ascent = font_size * 0.8
        text_descent = font_size * 0.2
        text_height = text_ascent + text_descent
        
        # Width estimate - use character count with font-dependent width
        # Helvetica: ~0.6 * font_size per char, Courier: ~0.6, Times: ~0.5
        char_width_ratio = 0.6 if 'Courier' not in font_name else 0.6
        estimated_width = len(text) * font_size * char_width_ratio
        
        # Text bounding box in PDF coordinates (bottom-left origin)
        text_bbox_bottom = y - text_descent  # Bottom of text
        text_bbox_top = y + text_ascent      # Top of text
        
        # Check against all previously rendered regions
        for region in self.rendered_regions[page_idx]:
            reg_x = region.get('x', 0)
            reg_y = region.get('y', 0)  # This is also baseline
            reg_width = region.get('width', 0)
            reg_height = region.get('height', font_size)  # Default to font size if not set
            
            # Calculate region bounding box
            # Assume region y is also baseline
            reg_ascent = reg_height * 0.8
            reg_descent = reg_height * 0.2
            reg_bbox_bottom = reg_y - reg_descent
            reg_bbox_top = reg_y + reg_ascent
            
            # Check if rectangles overlap (with tolerance)
            # X overlap
            x_overlap = (x < reg_x + reg_width + self.overlap_tolerance and
                        x + estimated_width + self.overlap_tolerance > reg_x)
            
            # Y overlap (considering baseline-based positions)
            y_overlap = (text_bbox_bottom < reg_bbox_top + self.overlap_tolerance and
                        text_bbox_top + self.overlap_tolerance > reg_bbox_bottom)
            
            if x_overlap and y_overlap:
                return True
        
        return False
    
    def _find_non_overlapping_y(
        self,
        x: float,
        preferred_y: float,
        text: str,
        font_name: str,
        font_size: float,
        page_idx: int
    ) -> float:
        """
        Find a Y position that doesn't overlap with existing text.
        
        Tries moving upward first, then downward if necessary.
        """
        text_height = font_size * 1.2
        step = text_height * 0.5  # Small steps
        
        # Try moving upward first
        test_y = preferred_y
        for _ in range(10):  # Try up to 10 positions
            if not self._would_overlap(x, test_y, text, font_name, font_size, page_idx):
                return test_y
            test_y += step
            if test_y + text_height > self.page_height - self.margin:
                break
        
        # Try moving downward
        test_y = preferred_y
        for _ in range(10):
            if not self._would_overlap(x, test_y, text, font_name, font_size, page_idx):
                return test_y
            test_y -= step
            if test_y < self.margin:
                break
        
        # If all attempts fail, return original position (will render anyway)
        return preferred_y
    
    def _record_rendered_region(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        page_idx: int
    ) -> None:
        """
        Record a rendered text region for overlap detection.
        
        Note: y is baseline position, height is font size (approximate text height).
        """
        if page_idx not in self.rendered_regions:
            self.rendered_regions[page_idx] = []
        
        self.rendered_regions[page_idx].append({
            'x': x,
            'y': y,  # Baseline position
            'width': width,  # Actual text width
            'height': height  # Font size (used to estimate text bbox)
        })
    
    def _truncate_text(
        self,
        text: str,
        font_name: str,
        font_size: float,
        max_width: float,
        canvas_obj: canvas.Canvas
    ) -> str:
        """
        Truncate text to fit within max_width, adding ellipsis if needed.
        """
        if not text:
            return ""
        
        # Check if text already fits
        if canvas_obj.stringWidth(text, font_name, font_size) <= max_width:
            return text
        
        # Binary search for the maximum length that fits
        ellipsis = "..."
        ellipsis_width = canvas_obj.stringWidth(ellipsis, font_name, font_size)
        available_width = max_width - ellipsis_width
        
        if available_width <= 0:
            return ellipsis
        
        # Find the longest prefix that fits
        left, right = 0, len(text)
        best_len = 0
        
        while left < right:
            mid = (left + right + 1) // 2
            test_text = text[:mid] + ellipsis
            width = canvas_obj.stringWidth(test_text, font_name, font_size)
            
            if width <= max_width:
                best_len = mid
                left = mid
            else:
                right = mid - 1
        
        if best_len > 0:
            return text[:best_len] + ellipsis
        else:
            return ellipsis


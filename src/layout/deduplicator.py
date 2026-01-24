"""Deduplicate overlapping layout elements."""
from typing import List, Dict, Any, Tuple, Optional
from src.models.schemas import LayoutElement, ElementType, BBox


class ElementDeduplicator:
    """Deduplicate overlapping or duplicate layout elements."""
    
    def __init__(self, position_tolerance: float = 5.0, content_similarity_threshold: float = 0.9):
        """
        Initialize deduplicator.
        
        Args:
            position_tolerance: Maximum distance (in pixels) for considering elements at same position
            content_similarity_threshold: Minimum similarity (0-1) for considering content duplicate
        """
        self.position_tolerance = position_tolerance
        self.content_similarity_threshold = content_similarity_threshold
        # CRITICAL: Lower threshold for table detection (following prompt requirement)
        self.table_overlap_threshold = 0.3  # 30% overlap for tables
        self.table_content_similarity_threshold = 0.5  # 50% for table content
    
    def deduplicate_elements(self, elements: List[LayoutElement]) -> List[LayoutElement]:
        """
        Remove duplicate elements, keeping the one that appears "on top" or has higher confidence.
        
        Following prompt requirement: preserve exact order and keep upper layer elements.
        
        Args:
            elements: List of layout elements (may contain duplicates)
            
        Returns:
            Deduplicated list of elements
        """
        if not elements:
            return []
        
        # Group elements by position and content similarity
        # Elements are considered duplicates if:
        # 1. They overlap significantly in position
        # 2. Their content is very similar
        
        deduplicated = []
        processed_indices = set()
        
        for i, elem1 in enumerate(elements):
            if i in processed_indices:
                continue
            
            # Check if this element overlaps with any already processed element
            is_duplicate = False
            best_match_idx = None
            best_overlap_score = 0
            
            for j, elem2 in enumerate(deduplicated):
                if self._are_duplicates(elem1, elem2):
                    # Calculate overlap score (higher = more overlap)
                    overlap_score = self._calculate_overlap_score(elem1, elem2)
                    if overlap_score > best_overlap_score:
                        best_overlap_score = overlap_score
                        best_match_idx = j
                        is_duplicate = True
            
            if is_duplicate:
                # Keep the element that is "on top" (upper layer = smaller Y coordinate)
                # Following prompt requirement: preserve table form, keep upper layer elements
                existing_elem = deduplicated[best_match_idx]
                
                # CRITICAL: For overlapping elements, always keep the upper layer (smaller Y)
                # Y coordinate in PDF: smaller Y = higher on page = upper layer
                if elem1.bbox.y < existing_elem.bbox.y:
                    # elem1 is upper layer - replace with it
                    deduplicated[best_match_idx] = elem1
                elif elem1.bbox.y == existing_elem.bbox.y:
                    # Same Y - use other criteria (confidence, completeness)
                    if (elem1.confidence > existing_elem.confidence or
                        (elem1.confidence == existing_elem.confidence and 
                         self._is_more_complete(elem1, existing_elem))):
                        deduplicated[best_match_idx] = elem1
                # else: existing_elem is upper layer, keep it
            else:
                # New element, add it
                deduplicated.append(elem1)
            
            processed_indices.add(i)
        
        return deduplicated
    
    def _are_duplicates(self, elem1: LayoutElement, elem2: LayoutElement) -> bool:
        """
        Check if two elements are duplicates.
        
        Elements are duplicates if:
        1. They are of the same type
        2. Their positions overlap significantly
        3. Their content is similar
        """
        # Must be same type
        if elem1.type != elem2.type:
            return False
        
        # CRITICAL: For table-like elements, use different similarity threshold
        is_table_like = False
        if elem1.type == ElementType.TEXT:
            is_table_like = self._is_table_like_element(elem1) or self._is_table_like_element(elem2)
        
        # Check position overlap (pass is_table_like flag for more aggressive detection)
        if not self._positions_overlap(elem1.bbox, elem2.bbox, is_table_like=is_table_like):
            return False
        
        # Check content similarity
        if elem1.type == ElementType.TEXT:
            if is_table_like:
                # Use lower threshold for tables
                return self._text_content_similar(
                    elem1.content, 
                    elem2.content, 
                    threshold=self.table_content_similarity_threshold
                )
            return self._text_content_similar(elem1.content, elem2.content)
        elif elem1.type == ElementType.IMAGE:
            # For images, check if same xref or similar position
            if isinstance(elem1.content, dict) and isinstance(elem2.content, dict):
                xref1 = elem1.content.get("xref")
                xref2 = elem2.content.get("xref")
                if xref1 and xref2 and xref1 == xref2:
                    return True
            # Same position = likely duplicate
            return True
        else:
            # For other types, position overlap is sufficient
            return True
    
    def _positions_overlap(self, bbox1: BBox, bbox2: BBox, is_table_like: bool = False) -> bool:
        """
        Check if two bounding boxes overlap significantly.
        
        Following prompt requirement: detect table overlaps more aggressively.
        
        Args:
            bbox1: First bounding box
            bbox2: Second bounding box
            is_table_like: Whether this is a table-like element (more aggressive detection)
        """
        # Calculate overlap area
        x_overlap = max(0, min(bbox1.x + bbox1.width, bbox2.x + bbox2.width) - max(bbox1.x, bbox2.x))
        y_overlap = max(0, min(bbox1.y + bbox1.height, bbox2.y + bbox2.height) - max(bbox1.y, bbox2.y))
        overlap_area = x_overlap * y_overlap
        
        # Calculate individual areas
        area1 = bbox1.width * bbox1.height
        area2 = bbox2.width * bbox2.height
        
        if area1 == 0 or area2 == 0:
            # Check if positions are very close (within tolerance)
            center1_x = bbox1.x + bbox1.width / 2
            center1_y = bbox1.y + bbox1.height / 2
            center2_x = bbox2.x + bbox2.width / 2
            center2_y = bbox2.y + bbox2.height / 2
            
            distance = ((center1_x - center2_x)**2 + (center1_y - center2_y)**2)**0.5
            # For table-like elements, use larger tolerance
            tolerance = self.position_tolerance * (2.0 if is_table_like else 1.0)
            return distance < tolerance
        
        # Calculate overlap ratio (how much of smaller element is covered)
        min_area = min(area1, area2)
        overlap_ratio = overlap_area / min_area if min_area > 0 else 0
        
        # CRITICAL: For table detection, use lower threshold (25% instead of 30-50%)
        # Tables might have partial overlaps that still need to be detected
        # Also check minimum overlap area to avoid false positives
        if is_table_like:
            # More aggressive for tables: 25% overlap threshold, lower area threshold
            min_overlap_threshold = 0.25  # Lower threshold for tables
            min_area_threshold = 20  # Lower area threshold for tables (to catch small overlaps)
        else:
            min_overlap_threshold = 0.3 if min_area > 100 else 0.5
            min_area_threshold = 30
        
        return overlap_ratio > min_overlap_threshold and overlap_area > min_area_threshold
    
    def _text_content_similar(self, content1: Any, content2: Any, threshold: Optional[float] = None) -> bool:
        """
        Check if two text contents are similar.
        
        Args:
            content1: First content
            content2: Second content
            threshold: Optional similarity threshold (overrides default)
        """
        if threshold is None:
            threshold = self.content_similarity_threshold
        
        text1 = str(content1 or "").strip()
        text2 = str(content2 or "").strip()
        
        if not text1 or not text2:
            return False
        
        # Exact match
        if text1 == text2:
            return True
        
        # Normalize for comparison (remove extra whitespace, lowercase)
        normalized1 = ' '.join(text1.lower().split())
        normalized2 = ' '.join(text2.lower().split())
        
        if normalized1 == normalized2:
            return True
        
        # Calculate similarity using word-based method (better for tables)
        words1 = set(normalized1.split())
        words2 = set(normalized2.split())
        if words1 or words2:
            word_similarity = len(words1 & words2) / max(len(words1 | words2), 1)
            if word_similarity >= threshold:
                return True
        
        # Also check character-based similarity
        similarity = self._calculate_text_similarity(normalized1, normalized2)
        return similarity >= threshold
    
    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts (0-1)."""
        if not text1 or not text2:
            return 0.0
        
        # Simple character-based similarity
        # Count common characters
        chars1 = set(text1)
        chars2 = set(text2)
        
        if not chars1 or not chars2:
            return 0.0
        
        intersection = len(chars1 & chars2)
        union = len(chars1 | chars2)
        
        return intersection / union if union > 0 else 0.0
    
    def _calculate_overlap_score(self, elem1: LayoutElement, elem2: LayoutElement) -> float:
        """Calculate overlap score between two elements (0-1, higher = more overlap)."""
        bbox1 = elem1.bbox
        bbox2 = elem2.bbox
        
        # Calculate overlap area
        x_overlap = max(0, min(bbox1.x + bbox1.width, bbox2.x + bbox2.width) - max(bbox1.x, bbox2.x))
        y_overlap = max(0, min(bbox1.y + bbox1.height, bbox2.y + bbox2.height) - max(bbox1.y, bbox2.y))
        overlap_area = x_overlap * y_overlap
        
        # Normalize by smaller area
        area1 = bbox1.width * bbox1.height
        area2 = bbox2.width * bbox2.height
        min_area = min(area1, area2)
        
        if min_area == 0:
            return 0.0
        
        return overlap_area / min_area
    
    def _is_more_complete(self, elem1: LayoutElement, elem2: LayoutElement) -> bool:
        """Check if elem1 has more complete content than elem2."""
        if elem1.type == ElementType.TEXT:
            content1 = str(elem1.content or "")
            content2 = str(elem2.content or "")
            # Longer text is usually more complete
            return len(content1) > len(content2)
        elif elem1.type == ElementType.IMAGE:
            # For images, check if has more metadata
            if isinstance(elem1.content, dict) and isinstance(elem2.content, dict):
                return len(elem1.content) >= len(elem2.content)
        return False
    
    def _is_table_like_element(self, elem: LayoutElement) -> bool:
        """Check if element is table-like (multi-line structured content)."""
        if elem.type != ElementType.TEXT:
            return False
        
        content = str(elem.content or "")
        
        # Check if has multiple lines
        if '\n' in content:
            lines = content.split('\n')
            if len(lines) > 1:
                # Additional check: look for structured patterns (dates, amounts, keywords)
                import re
                date_pattern = r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}'
                amount_pattern = r'[\d,]+\.?\d*'
                table_keywords = ['periodo', 'saldo', 'depósito', 'retiro', 'fecha', 'cuenta', 
                                'rendimiento', 'comportamiento', 'comisión']
                
                structured_lines = 0
                for line in lines[:5]:  # Check first 5 lines
                    line_lower = line.lower()
                    if any(keyword in line_lower for keyword in table_keywords):
                        structured_lines += 1
                    elif re.search(date_pattern, line) or re.search(amount_pattern, line):
                        structured_lines += 1
                
                # If multiple lines AND has structured patterns, it's table-like
                if structured_lines >= 2:
                    return True
                
                # Even without clear patterns, if enough lines, consider table-like
                if len(lines) >= 3:
                    return True
        
        # Check if has lines attribute with multiple entries
        if hasattr(elem, 'lines') and elem.lines:
            if len(elem.lines) > 1:
                return True
        
        return False


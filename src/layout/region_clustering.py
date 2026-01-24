"""Visual feature extraction and region clustering."""
from typing import Any, Dict, List, Tuple

import numpy as np
try:
    from sklearn.cluster import DBSCAN
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    DBSCAN = None


class RegionClustering:
    """Cluster document regions based on visual features."""
    
    def __init__(self):
        """Initialize region clustering."""
        if SKLEARN_AVAILABLE:
            self.clusterer = DBSCAN(eps=20, min_samples=2)
        else:
            self.clusterer = None
    
    def extract_visual_features(
        self, 
        ocr_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Extract visual features from OCR data.
        
        Args:
            ocr_data: OCR output with layout information
            
        Returns:
            List of visual features for each element
        """
        features = []
        
        for page_data in ocr_data.get("pages", []):
            page_num = page_data.get("page_number", 1)
            
            for block in page_data.get("text_blocks", []):
                bbox = block.get("bbox", [0, 0, 0, 0])
                text = block.get("text", "")
                
                # Extract visual features
                feature = {
                    "x": bbox[0],
                    "y": bbox[1],
                    "width": bbox[2] - bbox[0],
                    "height": bbox[3] - bbox[1],
                    "text_length": len(text),
                    "font_size": self._estimate_font_size(bbox, text),
                    "is_bold": False,  # Would need OCR metadata
                    "alignment": self._estimate_alignment(bbox, page_data),
                    "page": page_num,
                    "raw_data": block
                }
                features.append(feature)
        
        return features
    
    def cluster_regions(
        self, 
        features: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Cluster visual features into regions.
        
        Args:
            features: List of visual features
            
        Returns:
            Clustered regions with metadata
        """
        if not features:
            return []
        
        # Prepare feature matrix (x, y, width, height, font_size)
        X = np.array([
            [
                f["x"],
                f["y"],
                f["width"],
                f["height"],
                f.get("font_size", 10)
            ]
            for f in features
        ])
        
        # Normalize features
        X_norm = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-8)
        
        # Cluster
        if self.clusterer is not None:
            labels = self.clusterer.fit_predict(X_norm)
        else:
            # Simple distance-based clustering fallback
            labels = self._simple_clustering(X_norm)
        
        # Group by cluster
        regions = {}
        for idx, label in enumerate(labels):
            if label not in regions:
                regions[label] = {
                    "cluster_id": int(label),
                    "elements": [],
                    "bbox": None
                }
            regions[label]["elements"].append(features[idx])
        
        # Calculate region bounding boxes
        for region in regions.values():
            if region["elements"]:
                x_min = min(e["x"] for e in region["elements"])
                y_min = min(e["y"] for e in region["elements"])
                x_max = max(e["x"] + e["width"] for e in region["elements"])
                y_max = max(e["y"] + e["height"] for e in region["elements"])
                region["bbox"] = [x_min, y_min, x_max, y_max]
        
        return list(regions.values())
    
    def _estimate_font_size(
        self, 
        bbox: List[float], 
        text: str
    ) -> float:
        """Estimate font size from bounding box and text."""
        if not text or not bbox:
            return 10.0
        
        height = bbox[3] - bbox[1]
        # Rough estimate: font size ≈ height / 1.2
        return max(8.0, height / 1.2)
    
    def _estimate_alignment(
        self, 
        bbox: List[float], 
        page_data: Dict[str, Any]
    ) -> str:
        """Estimate text alignment."""
        if not bbox:
            return "left"
        
        page_width = page_data.get("width", 612)  # Default letter size
        x_center = (bbox[0] + bbox[2]) / 2
        page_center = page_width / 2
        
        if abs(x_center - page_center) < page_width * 0.1:
            return "center"
        elif x_center > page_center:
            return "right"
        else:
            return "left"
    
    def _simple_clustering(self, X_norm: np.ndarray, eps: float = 0.5) -> np.ndarray:
        """Simple distance-based clustering fallback."""
        n = len(X_norm)
        labels = np.full(n, -1)
        cluster_id = 0
        
        for i in range(n):
            if labels[i] != -1:
                continue
            labels[i] = cluster_id
            for j in range(i + 1, n):
                if labels[j] == -1:
                    dist = np.linalg.norm(X_norm[i] - X_norm[j])
                    if dist < eps:
                        labels[j] = cluster_id
            cluster_id += 1
        
        return labels


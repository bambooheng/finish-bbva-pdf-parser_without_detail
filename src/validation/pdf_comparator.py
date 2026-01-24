"""Pixel-level PDF comparison."""
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

import fitz
import numpy as np
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
try:
    from pdf2image import convert_from_path
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False


class PDFComparator:
    """Compare PDFs at pixel level."""
    
    def __init__(self, tolerance: int = 1):
        """Initialize PDF comparator.
        
        Args:
            tolerance: Pixel tolerance for comparison
        """
        self.tolerance = tolerance
    
    def compare_pdfs(
        self,
        original_path: str,
        reconstructed_path: str
    ) -> Dict[str, Any]:
        """
        Compare two PDFs pixel by pixel.
        
        Args:
            original_path: Path to original PDF
            reconstructed_path: Path to reconstructed PDF
            
        Returns:
            Comparison report with differences
        """
        # Convert PDFs to images
        original_images = self._pdf_to_images(original_path)
        reconstructed_images = self._pdf_to_images(reconstructed_path)
        
        comparison_results = []
        total_diff_pixels = 0
        total_pixels = 0
        
        # Compare each page
        min_pages = min(len(original_images), len(reconstructed_images))
        for page_num in range(min_pages):
            orig_img = original_images[page_num]
            recon_img = reconstructed_images[page_num]
            
            # Resize if dimensions differ
            if orig_img.shape != recon_img.shape:
                recon_img = cv2.resize(
                    recon_img, 
                    (orig_img.shape[1], orig_img.shape[0])
                )
            
            # Compare images
            diff, diff_pixels, total = self._compare_images(orig_img, recon_img)
            
            comparison_results.append({
                "page": page_num + 1,
                "diff_pixels": int(diff_pixels),
                "total_pixels": int(total),
                "diff_percentage": (diff_pixels / total) * 100 if total > 0 else 0
            })
            
            total_diff_pixels += diff_pixels
            total_pixels += total
        
        # Calculate overall accuracy
        pixel_accuracy = (
            (total_pixels - total_diff_pixels) / total_pixels * 100
            if total_pixels > 0
            else 0
        )
        
        return {
            "pixel_accuracy": pixel_accuracy,
            "total_diff_pixels": int(total_diff_pixels),
            "total_pixels": int(total_pixels),
            "pages": comparison_results,
            "is_valid": pixel_accuracy >= (100 - self.tolerance * 0.1)
        }
    
    def _pdf_to_images(self, pdf_path: str) -> List[np.ndarray]:
        """Convert PDF to list of images."""
        if PDF2IMAGE_AVAILABLE:
            try:
                # Use pdf2image
                images = convert_from_path(pdf_path, dpi=150)
                return [np.array(img) for img in images]
            except Exception as e:
                print(f"Error converting PDF to images with pdf2image: {e}")
                # Fallback: use PyMuPDF
                return self._pdf_to_images_pymupdf(pdf_path)
        else:
            # Use PyMuPDF fallback
            return self._pdf_to_images_pymupdf(pdf_path)
    
    def _pdf_to_images_pymupdf(self, pdf_path: str) -> List[np.ndarray]:
        """Convert PDF to images using PyMuPDF."""
        doc = fitz.open(pdf_path)
        images = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom for quality
            img_data = pix.samples
            if pix.n == 1:  # Grayscale
                img = np.frombuffer(img_data, dtype=np.uint8).reshape(
                    pix.height, pix.width
                )
            elif pix.n == 3:  # RGB
                img = np.frombuffer(img_data, dtype=np.uint8).reshape(
                    pix.height, pix.width, pix.n
                )
            else:  # RGBA or other
                img = np.frombuffer(img_data, dtype=np.uint8).reshape(
                pix.height, pix.width, pix.n
            )
                if pix.n == 4:
                    img = img[:, :, :3]  # Convert RGBA to RGB
            images.append(img)
        
        doc.close()
        return images
    
    def _compare_images(
        self,
        img1: np.ndarray,
        img2: np.ndarray
    ) -> Tuple[np.ndarray, int, int]:
        """
        Compare two images.
        
        Args:
            img1: First image
            img2: Second image
            
        Returns:
            Tuple of (diff image, diff pixel count, total pixels)
        """
        # Ensure same shape
        if img1.shape != img2.shape:
            if CV2_AVAILABLE:
                img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))
            else:
                # Simple numpy resize fallback
                from scipy.ndimage import zoom
                try:
                    zoom_factors = [img1.shape[0]/img2.shape[0], img1.shape[1]/img2.shape[1]]
                    if len(img2.shape) == 3:
                        zoom_factors.append(1)
                    img2 = zoom(img2, zoom_factors)
                except:
                    # If resize fails, return high difference
                    return np.zeros_like(img1), img1.size, img1.size
        
        # Convert to grayscale if needed
        if len(img1.shape) == 3:
            if CV2_AVAILABLE:
                img1_gray = cv2.cvtColor(img1, cv2.COLOR_RGB2GRAY)
            else:
                img1_gray = np.mean(img1, axis=2).astype(np.uint8)
        else:
            img1_gray = img1
        
        if len(img2.shape) == 3:
            if CV2_AVAILABLE:
                img2_gray = cv2.cvtColor(img2, cv2.COLOR_RGB2GRAY)
            else:
                img2_gray = np.mean(img2, axis=2).astype(np.uint8)
        else:
            img2_gray = img2
        
        # Calculate absolute difference
        if CV2_AVAILABLE:
            diff = cv2.absdiff(img1_gray, img2_gray)
        else:
            diff = np.abs(img1_gray.astype(np.int16) - img2_gray.astype(np.int16)).astype(np.uint8)
        
        # Apply tolerance
        diff_binary = (diff > self.tolerance).astype(np.uint8)
        diff_pixels = np.sum(diff_binary)
        total_pixels = img1_gray.size
        
        return diff, diff_pixels, total_pixels
    
    def generate_diff_image(
        self,
        original_path: str,
        reconstructed_path: str,
        output_path: str,
        page_num: int = 0
    ) -> None:
        """
        Generate visual diff image.
        
        Args:
            original_path: Original PDF path
            reconstructed_path: Reconstructed PDF path
            output_path: Output diff image path
            page_num: Page number to compare (0-indexed)
        """
        original_images = self._pdf_to_images(original_path)
        reconstructed_images = self._pdf_to_images(reconstructed_path)
        
        if page_num >= len(original_images) or page_num >= len(reconstructed_images):
            raise ValueError(f"Page {page_num} not available")
        
        orig_img = original_images[page_num]
        recon_img = reconstructed_images[page_num]
        
        # Resize if needed
        if orig_img.shape != recon_img.shape:
            if CV2_AVAILABLE:
                recon_img = cv2.resize(recon_img, (orig_img.shape[1], orig_img.shape[0]))
            else:
                # Fallback resize using scipy
                from scipy.ndimage import zoom
                try:
                    zoom_factors = [orig_img.shape[0]/recon_img.shape[0], orig_img.shape[1]/recon_img.shape[1]]
                    if len(recon_img.shape) == 3:
                        zoom_factors.append(1)
                    recon_img = zoom(recon_img, zoom_factors).astype(recon_img.dtype)
                except:
                    print("Warning: Could not resize images for comparison")
        
        # Create diff visualization
        if CV2_AVAILABLE:
            diff = cv2.absdiff(orig_img, recon_img)
            diff_colored = cv2.applyColorMap(
                cv2.cvtColor(diff, cv2.COLOR_GRAY2BGR) if len(diff.shape) == 2 else diff,
                cv2.COLORMAP_HOT
            )
            cv2.imwrite(output_path, diff_colored)
        else:
            # Fallback: save as numpy array
            diff = np.abs(orig_img.astype(np.int16) - recon_img.astype(np.int16))
            try:
                from PIL import Image
                Image.fromarray(diff.astype(np.uint8)).save(output_path)
            except:
                print(f"Warning: Could not save diff image, cv2 and PIL not available")


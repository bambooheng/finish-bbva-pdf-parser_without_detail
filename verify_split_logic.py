
import sys
import os
# Add current dir to path to import pipeline
sys.path.append(os.getcwd())

from src.pipeline import BankDocumentPipeline

def test_splitting_logic():
    pipeline = BankDocumentPipeline()
    
    # Simulate OCR data for a 3-part merged document
    # Doc 1: Pages 1-8
    # Doc 2: Pages 9-16
    # Doc 3: Pages 17-20
    
    # We simulate "PAGINA 1 / 8" text in the first page of each chunk
    pages = []
    
    # Chunk 1 (Pages 0-7)
    for i in range(8):
        text = "Some content"
        if i == 0:
            text = "Estado de Cuenta\nPAGINA 1 / 8"
        pages.append({
            "text_blocks": [{"text": text}],
            "page_number": i + 1
        })
        
    # Chunk 2 (Pages 8-15) - Mimic restart
    for i in range(8):
        text = "Some content"
        if i == 0:
            text = "Estado de Cuenta\nPAGINA 1 / 8"
        pages.append({
            "text_blocks": [{"text": text}],
            "page_number": 8 + i + 1
        })
        
    # Chunk 3 (Pages 16-19) - Mimic restart
    for i in range(4):
        text = "Some content"
        if i == 0:
            text = "Estado de Cuenta\nPAGINA 1 / 4"
        pages.append({
            "text_blocks": [{"text": text}],
            "page_number": 16 + i + 1
        })
        
    fake_ocr_data = {"pages": pages}
    
    print(f"Simulated {len(pages)} pages total.")
    
    # Test Split
    print("Testing _split_ocr_data...")
    chunks = pipeline._split_ocr_data(fake_ocr_data)
    
    print(f"Result: {len(chunks)} chunks returned.")
    
    assert len(chunks) == 3, f"Expected 3 chunks, got {len(chunks)}"
    assert len(chunks[0]["pages"]) == 8, f"Chunk 1 should have 8 pages, got {len(chunks[0]['pages'])}"
    assert len(chunks[1]["pages"]) == 8, f"Chunk 2 should have 8 pages, got {len(chunks[1]['pages'])}"
    assert len(chunks[2]["pages"]) == 4, f"Chunk 3 should have 4 pages, got {len(chunks[2]['pages'])}"
    
    print("✓ Logic Verification Passed: Successfully detected and split merged documents.")

if __name__ == "__main__":
    test_splitting_logic()

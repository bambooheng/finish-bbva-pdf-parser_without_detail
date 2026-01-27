
import sys
import os

# Add src to path
sys.path.append(os.getcwd())

from src.ocr.mineru_handler import MinerUHandler

def debug_ocr_text(pdf_path):
    handler = MinerUHandler()
    ocr_data = handler.process_pdf(pdf_path)
    
    print(f"--- Page 1 Text (First 2000 chars) ---")
    page1 = ocr_data["pages"][0]
    text1 = ""
    for block in page1.get("text_blocks", []):
        text1 += block.get("text", "") + "\n"
    print(text1[:2000])
    
    print(f"\n--- Checking specific keywords ---")
    
    # 1. Address Block
    print(f"Checking for 'ALMA RUTH CORONA HUERTA'...")
    found_address = False
    for i, p in enumerate(ocr_data["pages"]):
        p_text = ""
        for block in p.get("text_blocks", []):
            p_text += block.get("text", "") + "\n"
        
        if "ALMA RUTH" in p_text or "CORONA HUERTA" in p_text:
            print(f"Found Address on page {i+1}")
            # Find the block containing it and print bbox
            for block in p.get("text_blocks", []):
                if "ALMA RUTH" in block.get("text", "") or "CORONA HUERTA" in block.get("text", ""):
                    print(f"Block: {block.get('text', '')}")
                    print(f"BBox: {block.get('bbox')}")
                    print(f"Page size: {p.get('width')}, {p.get('height')}")
            found_address = True
    
    if not found_address:
         print("Address NOT found in any page text.")

    # 2. Branch Info
    print(f"\nChecking for 'SUCURSAL'...")
    for i, p in enumerate(ocr_data["pages"]):
         p_text = ""
         for block in p.get("text_blocks", []):
            block_text = block.get("text", "")
            if "SUCURSAL" in block_text or "CIHUATLAN" in block_text:
                 print(f"Found Branch Keyword on page {i+1} block: {block_text}")

    # 3. Cuadro Resumen
    print(f"\nChecking for 'Cuadro resumen'...")
    for i, p in enumerate(ocr_data["pages"]):
         p_text = ""
         for block in p.get("text_blocks", []):
            block_text = block.get("text", "")
            if "Cuadro resumen" in block_text:
                 print(f"Found Cuadro resumen on page {i+1} block: {block_text}")


if __name__ == "__main__":
    # Use the test.pdf that was hopefully copied
    pdf_path = "test.pdf" 
    # Fallback to absolute path if test.pdf doesn't exist (but use proper escaping)
    if not os.path.exists(pdf_path):
        # Try finding any pdf in the directory
        import glob
        pdfs = glob.glob("*.pdf")
        if pdfs:
            pdf_path = pdfs[0]
            print(f"Using found pdf: {pdf_path}")
        else:
            # Try the original path again but careful with chars
            pdf_path = r"D:\Mstar\银行审核要点\BBVA流水测试-真实样例1022\BBVA JUN-JUL 真实1-MSN20251016154.pdf"
            
    try:
        debug_ocr_text(pdf_path)
    except Exception as e:
        print(f"Error: {e}")

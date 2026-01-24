import sys
import os
import json

# Add src to path
sys.path.insert(0, 'src')

from extraction.data_extractor import DataExtractor

def test_extraction():
    print("Loading debug text...")
    with open("debug_text.txt", "r", encoding="utf-8") as f:
        text_content = f.read()
    
    # Mock OCR data
    # Split by pages roughly for simulation
    pages = text_content.split("--- PAGE")
    ocr_pages = []
    for p in pages:
        if not p.strip(): continue
        ocr_pages.append({"text": p})
    
    ocr_data = {"pages": ocr_pages}
    
    extractor = DataExtractor()
    
    print("\n--- Testing Total de Movimientos ---")
    total_mov = extractor._extract_total_movimientos(ocr_data, [])
    print(json.dumps(total_mov, indent=2, ensure_ascii=False))
    
    print("\n--- Testing Apartados Vigentes ---")
    apartados = extractor._extract_apartados_vigentes(ocr_data)
    print(json.dumps(apartados, indent=2, ensure_ascii=False))
    
    print("\n--- Testing Información Financiera ---")
    info = extractor._extract_informacion_financiera(ocr_data)
    print(json.dumps(info, indent=2, ensure_ascii=False))
    
    print("\n--- Testing Comportamiento ---")
    comp = extractor._extract_comportamiento(ocr_data)
    print(json.dumps(comp, indent=2, ensure_ascii=False))
    
    # Check if we got data
    if total_mov and apartados and info and comp:
        print("\nSUCCESS: All fields extracted!")
    else:
        print("\nPARTIAL SUCCESS: Some fields missing.")

if __name__ == "__main__":
    test_extraction()

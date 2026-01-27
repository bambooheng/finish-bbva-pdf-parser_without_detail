
import re
from typing import Dict, Any, List

def parse_cuadro_resumen_v3(lines):
    print("\n--- Testing Cuadro Resumen Logic V3 ---")
    results = []
    
    # Text lines based on User Screenshot
    # Columns: Concepto | Cantidad | Porcentaje | Columna
    # Example Row: "Retiros efectivo (-) -67,300.00 -28.78% E"
    
    for line in lines:
        clean = line.strip()
        # Skip empty or headers
        if not clean or "Concepto" in clean: continue
        
        # Regex to match: 
        # Group 1: Concepto (Text, spaces, parenthesis)
        # Group 2: Cantidad (Money, signed, commas)
        # Group 3: Porcentaje (%, signed)
        # Group 4: Columna (Word/Char)
        
        # Strategy: Work backwards?
        # End: Single word/char (Columna)
        # Before that: Percentage
        # Before that: Amount
        # Remainder: Concepto
        
        # Regex:
        # \s+([A-Z0-9]+)$  -> Columna
        # \s+([-\d\.]+%)\s+ -> Percentage
        # \s+([-\d,]+\.\d{2})\s+ -> Amount
        
        # Attempt matching
        col_match = re.search(r'\s+([A-Z0-9]+)$', clean)
        if col_match:
            columna = col_match.group(1)
            rem1 = clean[:col_match.start()].strip()
            
            pct_match = re.search(r'\s+([-\d\.]+%)\s*$', rem1)
            if pct_match:
                pct = pct_match.group(1)
                rem2 = rem1[:pct_match.start()].strip()
                
                amt_match = re.search(r'\s+([-\d,]+\.\d{2})\s*$', rem2)
                if amt_match:
                    amount = amt_match.group(1)
                    concepto = rem2[:amt_match.start()].strip()
                    
                    results.append({
                        "Concepto": concepto,
                        "Cantidad": amount,
                        "Porcentaje": pct,
                        "Columna": columna
                    })
                    continue
        
        # If strict match fails, try fallback (maybe Columna is missing?)
        # For now, print failed lines
        print(f"Failed to parse line: {clean}")

    import json
    print(json.dumps(results, indent=2))

def test_address_extraction_v3():
    print("\n--- Testing Address Extraction V3 ---")
    # Simulate the "BBVA" logo being a separate block, and address below it
    blocks = [
        {"text": "BBVA", "bbox": [40, 40, 100, 60]}, # Logo
        {"text": "ALMA RUTH CORONA HUERTA\nJUAREZ 9\nCIHUATLAN\nJAL MEXICO CP 48970", 
         "bbox": [40, 80, 250, 180]}, # Address
        {"text": "Periodo...", "bbox": [400, 80, 500, 100]}
    ]
    
    # Current Logic Simulation
    candidates = []
    page_width = 612
    page_height = 792
    
    for block in blocks:
        bbox = block.get("bbox")
        text = block.get("text")
        
        # Geometric check
        if bbox[0] < page_width * 0.6 and bbox[1] < page_height * 0.5:
             # Filters
             if text == "BBVA": continue # Exact match filter
             candidates.append((bbox[1], text))
    
    candidates.sort(key=lambda x: x[0])
    if candidates:
        print("Top Candidate for Address:")
        print(candidates[0][1])
    else:
        print("No candidates found.")

if __name__ == "__main__":
    lines = [
        "Saldo Inicial 12,383.20 5.29% A",
        "Depósitos / Abonos (+) 233,768.72 100.00% B",
        "Retiros efectivo (-) -67,300.00 -28.78% E",
    ]
    parse_cuadro_resumen_v3(lines)
    test_address_extraction_v3()

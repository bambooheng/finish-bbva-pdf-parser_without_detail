
import re
from typing import Dict, Any, List

# --- Address Extraction Test ---
def test_address_extraction_v2():
    print("\n--- Testing Address Extraction (V2) ---")
    page_width = 612
    page_height = 792
    
    # Mock blocks based on User Image/Description
    blocks = [
        {"text": "BBVA", "bbox": [50, 40, 150, 60]}, # Logo usually top left
        {"text": "ALMA RUTH CORONA HUERTA\nJUAREZ 9\nCIHUATLAN\nCIHUATLAN\nJAL MEXICO CP 48970", 
         "bbox": [50, 100, 300, 200]},
        {"text": "Periodo...", "bbox": [400, 100, 500, 120]}, # Right side header
        {"text": "Fecha de Corte...", "bbox": [400, 120, 500, 140]}
    ]
    
    candidates = []
    # Logic from data_extractor.py (current state)
    for block in blocks:
        bbox = block.get("bbox", [0, 0, 0, 0])
        # x < 60%, y < 50%
        if bbox[0] < page_width * 0.6 and bbox[1] < page_height * 0.5:
            b_text = block.get("text", "").strip()
            
            # Filters
            if len(b_text) < 5: continue
            if "BBVA" in b_text or "BANCO" in b_text: continue
            if "Estado de Cuenta" in b_text: continue 
            
            if re.match(r'^Periodo\s+', b_text): continue
            if re.match(r'^Fecha\s+de\s+Corte', b_text): continue
            
            candidates.append((bbox[1], b_text))
            
    candidates.sort(key=lambda x: x[0])
    
    if candidates:
        print("Found Candidates:")
        for c in candidates:
            print(f" - {c[1][:20]}...")
        
        # Verify if the address is the first one
        if "ALMA RUTH" in candidates[0][1]:
            print("PASSED: Address found as top candidate.")
        else:
            print("FAILED: Address not top candidate.")
    else:
        print("FAILED: No candidates found.")

# --- Cuadro Resumen Test ---
def extract_cuadro_resumen_rows(lines):
    print("\n--- Testing Cuadro Resumen Parsing ---")
    cuadro_resumen = []
    in_table = False
    
    for line in lines:
        clean_line = line.strip()
        if "Cuadro resumen" in clean_line:
            in_table = True
            continue
        
        if in_table:
            if "Total" in line:
                break
            
            if "PAGINA" in line.upper(): continue
            if len(clean_line) < 3: continue

            # My proposed logic:
            # Check if line ends with a number (Amount)
            amount_match = re.search(r'([\d,]+\.\d{2})$', clean_line)
            if amount_match:
                amount = amount_match.group(1)
                remaining = clean_line[:amount_match.start()].strip()
                
                # Check for Percentage
                pct_match = re.search(r'([\d\.]+%)\s*$', remaining)
                if pct_match:
                    pct = pct_match.group(1)
                    remaining = remaining[:pct_match.start()].strip()
                else:
                    pct = ""
                
                # Check for Count (Integer)
                cnt_match = re.search(r'(\d+)\s*$', remaining)
                if cnt_match:
                    cnt = cnt_match.group(1)
                    concept = remaining[:cnt_match.start()].strip()
                else:
                    cnt = ""
                    concept = remaining
                
                # If everything else is empty but we have Amount, Concept is likely empty or "-" implied?
                # Screenshot 6 shows: "Cheques 5 1.25% 12,000.00"
                # But some rows might be just "12,383.20" (maybe Summary headers?)
                # User complaint: "raw_row": "12,383.20"
                
                cuadro_resumen.append({
                    "Concepto": concept,
                    "Cantidad": cnt,
                    "Porcentaje": pct,
                    "Saldo": amount
                })
            else:
                cuadro_resumen.append({"raw_row": clean_line})
    
    import json
    print(json.dumps(cuadro_resumen, indent=2))
    
    # Assertions for the problematic rows mentioned by user
    # "12,383.20" -> Should it be parsed?
    # User says: "Concepto Cantidad Porcentaje Columna四列解析不完整"
    # This implies even the rows with just numbers should be mapped?
    # Or maybe "12,383.20" is actually part of a row like "Saldo Inicial ... 12,383.20" but "Saldo Inicial" was split to another line?
    # If so, we need to merge lines?

if __name__ == "__main__":
    test_address_extraction_v2()
    
    # Mock text based on user issue
    # "12,383.20"
    # "233,768.72"
    # ...
    # "-" "" "" "67,300.00"
    # "-" "" "" "72,469.27"
    # "106,382.65"
    
    # Hypothetical OCR text where lines are split?
    # Or maybe the column alignment is such that Concepto is far left and Amount is far right.
    # If they are on the same line "word...   number", my regex should work.
    # If they are distinct lines, that's a problem.
    # Let's verify regex behavior on the successful rows vs failed lines.
    
    lines = [
        "Cuadro resumen y gráfico",
        "Saldo Inicial 12,383.20", # Assumption: This is how it SHOULD look
        "12,383.20",               # Reality? User says "raw_row": "12,383.20"
        "Depósitos / Abonos (+) 5 100.0% 233,768.72",
        "Retiros / Cargos (-) 30 59.8% 139,769.27",
        "Saldo Final 106,382.65"
    ]
    extract_cuadro_resumen_rows(lines)


import re
import json

def test_final_parser():
    print("Testing Final Parser Logic...")
    
    # Lines from user screenshot
    lines = [
        "Saldo Inicial 12,383.20 5.29% A",
        "Depósitos / Abonos (+) 233,768.72 100.00% B", 
        "Retiros efectivo (-) -67,300.00 -28.78% E",
    ]
    
    results = []
    for clean_line in lines:
        # New Logic from data_extractor.py
        col_match = re.search(r'\s+([A-Z0-9]+)$', clean_line)
        if col_match:
            columna = col_match.group(1)
            remaining = clean_line[:col_match.start()].strip()
            
            pct_match = re.search(r'\s+([-\d\.]+%)\s*$', remaining)
            if pct_match:
                pct = pct_match.group(1)
                remaining = remaining[:pct_match.start()].strip()
                
                amt_match = re.search(r'\s+([-\d,]+\.\d{2})\s*$', remaining)
                if amt_match:
                    amount = amt_match.group(1)
                    concepto = remaining[:amt_match.start()].strip()
                    
                    results.append({
                        "Concepto": concepto,
                        "Cantidad": amount,
                        "Porcentaje": pct,
                        "Columna": columna
                    })
    
    print(json.dumps(results, indent=2))
    assert len(results) == 3
    assert results[0]["Concepto"] == "Saldo Inicial"
    assert results[0]["Columna"] == "A"
    assert results[2]["Cantidad"] == "-67,300.00"

if __name__ == "__main__":
    test_final_parser()

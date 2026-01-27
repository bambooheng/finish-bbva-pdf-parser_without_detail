
import re
from typing import Dict, Any, List, Optional

# Mock Data Extractor Methods (Simplified counterparts of actual code)

def extract_branch_info(text: str) -> Dict[str, str]:
    info = {}
    # Current (Flawed) Regex
    # patterns = {
    #     "SUCURSAL": r"(?:SUCURSAL|Sucursal)[:\.]?\s*(\d+\s+[A-Z\s]+)",
    #     "DIRECCION": r"(?:DIRECCION|Dirección)[:\.]?\s*([A-Z0-9\s\.]+)(?:PLAZA|$)",
    #     "PLAZA": r"(?:PLAZA|Plaza)[:\.]?\s*([A-Z\s]+)",
    #     "TELEFONO": r"(?:TELEFONO|Teléfono|Tel)[:\.]?\s*([\d\s\-]+)"
    # }
    
    # Proposed Fix: Negative Lookahead / Stop at next keyword
    patterns = {
        "SUCURSAL": r"(?:SUCURSAL|Sucursal)[:\.]?\s*((?:(?!DIRECCION|Dirección|PLAZA|Plaza|TELEFONO|Teléfono).)*)",
        "DIRECCION": r"(?:DIRECCION|Dirección)[:\.]?\s*((?:(?!SUCURSAL|Sucursal|PLAZA|Plaza|TELEFONO|Teléfono).)*)",
        "PLAZA": r"(?:PLAZA|Plaza)[:\.]?\s*((?:(?!SUCURSAL|Sucursal|DIRECCION|Dirección|TELEFONO|Teléfono).)*)",
        "TELEFONO": r"(?:TELEFONO|Teléfono|Tel)[:\.]?\s*([\d\s\-]+)"
    }
    
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
             val = match.group(1).strip()
             info[key] = val
    return info

def test_branch_extraction():
    # User provided bad output source
    mock_text = """
    SUCURSAL: 5389
    CIHUATLAN
    DIRECCION: ALVARO OBREGON 26 COL. CENTRO MEX JA
    PLAZA: CIHUATLAN
    TELEFONO: 6890000
    """
    
    print("--- Testing Branch Info Extraction ---")
    info = extract_branch_info(mock_text)
    print("Extracted:", info)
    
    # Assertions
    assert "DIRECCION" not in info.get("SUCURSAL", ""), "SUCURSAL should not contain DIRECCION"
    assert "TELEFONO" not in info.get("PLAZA", ""), "PLAZA should not contain TELEFONO"
    print("PASSED")

def extract_address_info(blocks: List[Dict]):
    # Mock logic from data_extractor
    candidates = []
    page_width = 612
    page_height = 792
    
    for block in blocks:
        bbox = block.get("bbox", [0, 0, 0, 0])
        # Broadened search area
        if bbox[0] < page_width * 0.6 and bbox[1] < page_height * 0.5:
            b_text = block.get("text", "").strip()
            if len(b_text) < 5: continue
            if "BBVA" in b_text or "BANCO" in b_text: continue
            if "Estado de Cuenta" in b_text: continue
            # Exclude strict headers but allow Address-like content
            # Address often has "Col." or "CP" or "CALLE"
            
            candidates.append((bbox[1], b_text))
            
    candidates.sort(key=lambda x: x[0])
    return candidates

def test_address_extraction():
    print("\n--- Testing Address Extraction ---")
    # Mock blocks
    blocks = [
        {"text": "BBVA BANCOMER", "bbox": [50, 50, 200, 70]},
        {"text": "Estado de Cuenta", "bbox": [400, 50, 500, 70]},
        {"text": "ALMA RUTH CORONA HUERTA\nJUAREZ 9\nCIHUATLAN\nJAL MEXICO CP 48970", "bbox": [50, 100, 300, 200]},
        {"text": "Periodo DEL...", "bbox": [400, 100, 500, 150]}
    ]
    
    candidates = extract_address_info(blocks)
    print("Candidates:", candidates)
    if candidates:
        print("Top Candidate:", candidates[0][1])
        assert "ALMA RUTH" in candidates[0][1]
        print("PASSED")
    else:
        print("FAILED: No candidate found")

if __name__ == "__main__":
    test_branch_extraction()
    test_address_extraction()

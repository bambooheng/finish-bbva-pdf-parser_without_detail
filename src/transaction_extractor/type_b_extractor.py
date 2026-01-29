"""
Final Grid Extractor V72.0 - TypeB Engine

专注处理TypeB文档（如3038.pdf）

Type B REFERENCIA提取策略：
1. Uncapped Scan: 扫描"Referencia"右侧的所有内容
2. Row-Level Blacklist: 收集当前行的已知值
3. Semantic Subtraction: 过滤数值匹配的词

ARCHITECTURE:
- V86调度器将TypeB文档路由到此引擎
- V72专门处理TypeB类型文档
- TypeA文档由V84引擎处理

Usage:
    通过V86调度: python final_grid_extractor_v86.py <pdf_path>
"""

import fitz  # PyMuPDF
from pathlib import Path
import sys
import re
import json
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict


@dataclass
class HeaderBox:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass
class RowSlice:
    index: int
    y_top: float
    y_bottom: float
    date_text: str
    date_y1: float


@dataclass
class MasterGrid:
    vertical_lines: List[float]
    header_boxes: Dict[str, HeaderBox]
    start_page: int
    pollution_zone_x0: float
    pollution_zone_x1: float
    header_row_y: float
    header_bottom_y: float


@dataclass
class TransactionRow:
    fecha_oper: str
    fecha_liq: str
    descripcion: str
    referencia: str
    cargos: float
    abonos: float
    saldo_operacion: float
    saldo_liquidacion: float


class FinalGridExtractorV72:
    """V65 Semantic Subtraction - Value-Based Filtering"""
    
    DATE_PATTERN = re.compile(r'^\d{2}/[A-Z]{3}$', re.IGNORECASE)
    DATE_INLINE_PATTERN = re.compile(r'\d{2}/[A-Z]{3}', re.IGNORECASE)
    
    # V70: Currency Fingerprint
    CURRENCY_REGEX = re.compile(r'^\d{1,3}(,\d{3})*\.\d{2}$')
    NUMERIC_ROW_HEIGHT = 15
    ROW_HEIGHT_DEFAULT = 25
    
    # V55: Centroid-Based Filtering Constants (Type A only)
    CENTROID_TOLERANCE = 5  # Max delta between word center Y and row center Y (pixels)
    GENEROUS_SCAN_HEIGHT = 25  # Wide capture window for initial word collection
    
    # V65: Type B Referencia Zone with SEMANTIC SUBTRACTION
    REF_ZONE_LEFT_TYPE_B = 280   # Left boundary for capture
    REF_ZONE_RIGHT_TYPE_B = 1000 # V65: Effectively infinite (uncapped) to capture tail data like "638"
                                 # We rely on Blacklist to remove the numeric columns in between.
    
    # Step 2: Referencia patterns for destructive migration
    # Patterns are carefully crafted to NOT capture time digits (like 16 from "16:14")
    REFERENCIA_DESTRUCTIVE_PATTERNS = [
        re.compile(r'\*{4,}\d+'),                           # ****2410 or ******2410
        re.compile(r'RFC:\s*[A-Z]{3}\s+[A-Z0-9]+'),         # RFC: AME 970109GW0 (3-letter prefix + alphanumeric code)
        re.compile(r'AUT:\s*[A-Z0-9]+'),                    # AUT: 583588 or AUT: 1WXIRC
    ]
    
    HEADER_BLACKLIST = [
        "OPER", "LIQ", "DESCRIPCION", "DESCRIPCIÓN", "REFERENCIA",
        "CARGOS", "ABONOS", "OPERACION", "OPERACIÓN", "LIQUIDACION",
        "LIQUIDACIÓN", "SALDO", "FECHA"
    ]
    
    PAGE_HEADER_PATTERNS = [
        re.compile(r'BBVA', re.IGNORECASE),
        re.compile(r'Estado\s+de\s+Cuenta', re.IGNORECASE),
        re.compile(r'PAGINA', re.IGNORECASE),
        re.compile(r'Libret[oó]n', re.IGNORECASE),
        re.compile(r'B[aá]sico', re.IGNORECASE),
        re.compile(r'Digital', re.IGNORECASE),
        re.compile(r'Cuenta', re.IGNORECASE),
        re.compile(r'Cliente', re.IGNORECASE),
        re.compile(r'No\.', re.IGNORECASE),
        re.compile(r'^\d{10}$'),
        re.compile(r'^[A-Z]\d{7}$'),
    ]
    
    START_TRIGGER = "Detalle de Movimientos Realizados"
    
    STOP_TRIGGERS = [
        re.compile(r'Total\s+de\s+Movimientos', re.IGNORECASE),
        re.compile(r'TOTAL\s+IMPORTE', re.IGNORECASE),
        re.compile(r'Subtotal', re.IGNORECASE)
    ]
    
    FOOTER_PATTERNS = [
        re.compile(r'La\s+GAT\s+Real', re.IGNORECASE),
        re.compile(r'que\s+obtendr[ií]a', re.IGNORECASE),
        re.compile(r'BBVA\s+MEXICO.*Reforma', re.IGNORECASE),
        re.compile(r'PAGINA\s+\d+/\d+', re.IGNORECASE),
        re.compile(r'Paseo\s+de\s+la\s+Reforma', re.IGNORECASE),
        re.compile(r'inflación\s+estimada', re.IGNORECASE)
    ]
    
    Y_TOLERANCE = 20
    DEBUG_VISUAL = True
    
    def __init__(self):
        self.doc_type = "A"
        self.is_recording = False
        self.master_grid = None
        self.pages_in_session = 0
        self.page_width = 612
        self.purged_words = None
        self.referencia_y_positions = []
        self.session_count = 0
        self.all_transactions = []
        self.debug_pages = []
        self.pending_orphaned_text = ""
        self.cell_boxes_per_page = {}  # V55: For debug cell visualization
        self.referencia_debug_per_page = {}  # V57: For Type B referencia debug
        
        # V59: Immutable Source Policy
        self.original_source_path = None  # NEVER modified, read-only
        self.pdf_path = None  # May point to temp file for Type B processing
    
    # ==================== V63: DYNAMIC SPATIAL FUSE ====================
    
    def is_fallback_referencia_word(self, text: str) -> bool:
        """
        V63: Fallback filter when no Ref anchor found.
        Keep words starting with * or pure numerics >5 digits.
        """
        text_clean = text.strip()
        
        # Fallback 1: Starts with asterisk
        if text_clean.startswith('*'):
            return True
        
        # Fallback 2: Long numerics (>5 pure digits)
        if text_clean.isdigit() and len(text_clean) > 5:
            return True
        
        return False
    
    def backfill_referencia_type_b(self, page_num: int, y_top: float, y_bottom: float, 
                                    row_values: dict,           # V68: Dict of known values {'cargos':x, 'abonos':y...}
                                    grid_lines: List[float],    # V68: Grid lines for spatial validation
                                    is_first_row: bool = False) -> Tuple[str, list]:
        """
        V69: Iron Curtain (Spatial Hard Stop).
        
        Logic:
        1. Define IRON_CURTAIN_X at Start of Saldo Column (L5 - 5).
        2. Scanning words from left to right:
           - IF word.x0 > IRON_CURTAIN_X: STOP SCANNING IMMEDIATELY (Break).
             (Prevents Saldo/Liquidacion values from ever being considered).
        3. For words BEFORE the curtain:
           - Apply V68 Spatio-Semantic Logic (Check against Cargos/Abonos).
        """
        if not self.original_source_path:
            return "", []
            
        try:
            doc_orig = fitz.open(self.original_source_path)
            if page_num > len(doc_orig):
                return "", []
            page_orig = doc_orig[page_num - 1]
            
            # V65: Uncapped Right Boundary (Scan to end of page)
            words = page_orig.get_text("words")
            
            # V71: Ceiling Filter (Vertical Pre-Filter)
            # Ensure words belong to THIS row, not the one above.
            CEILING_Y = y_top - 5
            
            zone_words = []
            for w in words:
                x0, y0, x1, y1, text = w[:5]
                # Y-Range check (Original V65) + V71 Ceiling
                if y1 < y_top or y0 > y_bottom:
                    continue
                
                # V71: Ceiling Check (Strict Top)
                # If word starts ABOVE the ceiling, it's an intruder from upstairs.
                if y0 < CEILING_Y:
                    if "Referencia" in text:
                        print(f"    [V71 CEILING] Row {y_top:.0f}: Dropped '{text}' (y0={y0:.1f} < ceiling={CEILING_Y:.1f})")
                    continue
                
                # X-Range check (Start at REF_ZONE_LEFT, No Right Limit)
                if x0 < self.REF_ZONE_LEFT_TYPE_B:
                    continue
                
                zone_words.append({'x0': x0, 'y0': y0, 'x1': x1, 'y1': y1, 'text': text})
            
            doc_orig.close()
            
            # Sort by X
            sorted_words = sorted(zone_words, key=lambda w: w['x0'])
            
            # Find anchor "Referencia"
            anchor_idx = -1
            for i, w in enumerate(sorted_words):
                if "Referencia" in w['text'] or "Refer" in w['text']:
                    anchor_idx = i
                    break
            
            if anchor_idx == -1:
                return "", []
            
            # Implementation of Subtraction Sweep (Loop all words after anchor)
            final_words = []
            dropped_words = []
            
            # Keep the "Referencia" word itself? Usually yes.
            # But we process what follows.
            # Actually, "Referencia" is the label. We keep "Referencia" + subsequent.
            # Let's keep anchor and subsequent.
            
            # V69: Define Iron Curtain (Start of Saldo Zone)
            # grid_lines: [L1, L2, L3, L4, L5, L6]
            # L5 (index 4) is Start of Operacion (Saldo)
            L5_SALDO_START = grid_lines[4]
            IRON_CURTAIN_X = L5_SALDO_START - 5
            
            candidate_words = sorted_words[anchor_idx:]
            
            for w in candidate_words:
                # V69: Spatial Hard Stop
                if w['x0'] > IRON_CURTAIN_X:
                     # Stop scanning entirely. Do not process this word or any subsequent words.
                     # This effectively truncates the Referencia string at the Saldo border.
                     break
                
                text_clean = w['text'].strip()
                should_keep = True
                
                # Check against Blacklist
                # 1. Parse word to float
                try:
                    val_str = text_clean.replace(',', '').replace('$', '').replace('€', '')
                    val = float(val_str)
                    
                    # V68: Spatio-Semantic Check
                    # Zones (indices from lines list):
                    # L2 (idx 2) = Start of Cargos
                    # L3 (idx 3) = Start of Abonos
                    # L4 (idx 4) = Start of Saldo(Oper)
                    
                    L2_CARGOS_START = grid_lines[2]
                    L3_ABONOS_START = grid_lines[3]
                    L4_SALDO_START = grid_lines[4]
                    
                    word_center_x = (w['x0'] + w['x1']) / 2
                    
                    # V70 FIREWALL: Currency Format Check in Numeric Zone
                    # If we are in Cargos zone or right of it (x > L2 - 5)
                    if word_center_x > L2_CARGOS_START - 5:
                        if self.CURRENCY_REGEX.match(text_clean):
                            should_keep = False
                            dropped_words.append(f"{text_clean}(V70 Firewall)")
                            # Continue to next word (skip remaining checks check)
                            continue
                            
                    # Check Cargos
                    cargos_val = row_values.get('cargos', 0)
                    if abs(val - cargos_val) < 0.01:
                        # V72: Zero Guard
                        if cargos_val == 0 and "." not in text_clean:
                             print(f"    [V72 PROTECT] Row {y_top:.0f}: Kept '{text_clean}' (Integer Zero Format Protection)")
                        else:
                            # Must be right of Cargos Start
                            if word_center_x > L2_CARGOS_START - 5:
                                should_keep = False
                                dropped_words.append(f"{text_clean}(=Cargos {cargos_val} @ {word_center_x:.0f})")
                    
                    # Check Abonos
                    abonos_val = row_values.get('abonos', 0)
                    if abs(val - abonos_val) < 0.01:
                        # V72: Zero Guard
                        if abonos_val == 0 and "." not in text_clean:
                             print(f"    [V72 PROTECT] Row {y_top:.0f}: Kept '{text_clean}' (Integer Zero Format Protection)")
                        else:
                            # Must be right of Abonos Start
                            if word_center_x > L3_ABONOS_START - 5:
                                should_keep = False
                                dropped_words.append(f"{text_clean}(=Abonos {abonos_val} @ {word_center_x:.0f})")

                    # Check Saldos
                    saldo_val = row_values.get('saldo_operacion', 0)
                    if abs(val - saldo_val) < 0.01:
                         # V72: Zero Guard for Saldo too (why not?)
                         if saldo_val == 0 and "." not in text_clean:
                             pass
                         else:
                             if word_center_x > L4_SALDO_START - 5:
                                should_keep = False
                                dropped_words.append(f"{text_clean}(=Saldo {saldo_val} @ {word_center_x:.0f})")
                            
                    # Check Liquidacion (if exists)
                    liq_val = row_values.get('saldo_liquidacion', 0)
                    if abs(val - liq_val) < 0.01:
                        if word_center_x > L4_SALDO_START + 50: # Gross check
                             should_keep = False
                             dropped_words.append(f"{text_clean}(=Liq {liq_val})")

                except ValueError:
                    # Not a number -> Keep
                    pass
                
                if should_keep:
                    final_words.append(w)
            
            ref_parts = [w['text'] for w in final_words]
            referencia = " ".join(ref_parts).strip()
            
            # V65: Debug output for first row (or if interesting)
            if is_first_row:
                print(f"    [V70 DEBUG] Row Values: {row_values}")
                print(f"    [V69 IRON CURTAIN] Limit X: {IRON_CURTAIN_X:.1f}")
                print(f"    [V70 FIREWALL] Dropped: {dropped_words}")
                
                if referencia:
                    print(f"    [V65 SUCCESS] First row referencia: '{referencia}'")
                else:
                    print(f"\n    [V65 WARNING] First row referencia missing number? '{referencia}'")
            
            return referencia, final_words

        except Exception as e:
            print(f"    [V65 ERROR] Backfill crash: {str(e)}")
            return "", []
    
    def identify_document_type(self, doc) -> str:
        """
        V67: Data Probe Classification.
        Probe Zone: X [280, 380] (Reference Column Core).
        Logic: If we find "Referencia" key or Digits in this zone -> Type B.
        Else -> Type A.
        Scans first 3 pages.
        """
        try:
            probe_hit = False
            check_limit = min(3, len(doc))
            
            for page_idx in range(check_limit):
                page = doc[page_idx]
                words = page.get_text("words")
                
                # Probe the specific column zone
                zone_words = []
                for w in words:
                    x0, y0, x1, y1, text = w[:5]
                    # Probe Window: X=280 to 380
                    if x0 > 280 and x0 < 380:
                        zone_words.append(text)
                
                zone_text_blob = " ".join(zone_words)
                
                # Check 1: Explicit "Referencia" keyword
                if "Referencia" in zone_text_blob or "REFERENCIA" in zone_text_blob.upper():
                    print(f"  [V67 PROBE] Page {page_idx+1}: Found 'Referencia' keyword.")
                    probe_hit = True
                    break
                
                # Check 2: Long digits (8+)
                long_digit_match = re.search(r'\b\d{8,}\b', zone_text_blob)
                if long_digit_match:
                    print(f"  [V67 PROBE] Page {page_idx+1}: Found data '{long_digit_match.group()}'.")
                    probe_hit = True
                    break

            if probe_hit:
                print("  [V67 PROBE] Result: Type B (Hit)")
                return "B"
            else:
                print("  [V67 PROBE] Result: Type A (Miss)")
                return "A"
                
        except Exception as e:
            print(f"  [V67 ERROR] Probe failed: {e}, defaulting to A")
            return "A"
    
    # ==================== STEP 2: DESTRUCTIVE MIGRATION (Type A) ====================
    
    def destructive_migration_type_a(self, descripcion: str) -> Tuple[str, str]:
        """
        Step 2: Destructive Migration for Type A
        
        Rule: Everything starting from the first **** pattern to end of string 
        belongs to referencia. descripcion contains only the content BEFORE ****.
        
        Example:
            Input:  "AUTOZONE 7188 ******2410 RFC: AME 970109GW0 16:14 AUT: 583588"
            Output: descripcion="AUTOZONE 7188"
                    referencia="******2410 RFC: AME 970109GW0 16:14 AUT: 583588"
        """
        if not descripcion:
            return "", ""
        
        # Find the first occurrence of **** pattern (4+ asterisks followed by digits)
        match = re.search(r'\*{4,}\d+', descripcion)
        
        if match:
            # Split at the start of the **** pattern
            split_pos = match.start()
            
            # Everything BEFORE **** is descripcion (clean)
            clean_desc = descripcion[:split_pos].strip()
            
            # Everything FROM **** to END is referencia
            referencia = descripcion[split_pos:].strip()
            
            return clean_desc, referencia
        
        # No **** pattern found - no referencia to extract
        return descripcion.strip(), ""
    
    def clean_fecha_liq_type_a(self, fecha_liq: str) -> str:
        """
        Clean fecha_liq to only contain date (Type A).
        Any non-date content is discarded (not merged elsewhere to avoid duplicates).
        """
        if not fecha_liq:
            return ""
        
        # Find the first valid date
        match = self.DATE_INLINE_PATTERN.search(fecha_liq)
        if match:
            return match.group()
        
        return ""
    
    def post_process_row_type_a(self, row_dict: dict) -> dict:
        """
        Apply Type A post-extraction cleaning to a row.
        V60 FIX: For Type B, PRESERVE the already-extracted referencia!
        """
        if self.doc_type != "A":
            # V60: DO NOT overwrite referencia! It was already extracted by backfill
            return row_dict
        
        # Step 1: Clean fecha_liq (just keep date, discard rest)
        row_dict['fecha_liq'] = self.clean_fecha_liq_type_a(row_dict.get('fecha_liq', ''))
        
        # Step 2: Destructive Migration - extract referencia and REMOVE from descripcion
        clean_desc, referencia = self.destructive_migration_type_a(row_dict.get('descripcion', ''))
        row_dict['descripcion'] = clean_desc
        row_dict['referencia'] = referencia
        
        return row_dict
    
    # ==================== STEP 3: DOUBLE VALIDATION ====================
    
    def validate_no_referencia_in_descripcion(self, row_dict: dict) -> bool:
        """
        Step 3: Validate that no referencia patterns exist in descripcion.
        Returns True if clean, False if contaminated.
        """
        desc = row_dict.get('descripcion', '')
        
        # Check for stars pattern
        if re.search(r'\*{4,}\d+', desc):
            return False
        
        # Check for RFC pattern
        if re.search(r'RFC:', desc):
            return False
        
        return True
    
    # ==================== FOOTER FUSE ====================
    
    def find_footer_limit(self, page) -> float:
        page_height = page.rect.height
        page_text = page.get_text()
        footer_y = page_height
        
        for pattern in self.FOOTER_PATTERNS:
            for match in pattern.finditer(page_text):
                instances = page.search_for(match.group())
                for inst in instances:
                    if inst.y0 > page_height * 0.30:
                        if inst.y0 < footer_y:
                            footer_y = inst.y0
        
        return footer_y
    
    def find_stop_trigger_y(self, page) -> Optional[float]:
        page_text = page.get_text()
        for pattern in self.STOP_TRIGGERS:
            for match in pattern.finditer(page_text):
                instances = page.search_for(match.group())
                for inst in instances:
                    if inst.y0 > page.rect.height * 0.30:
                        return inst.y0
        return None
    
    def calculate_effective_limit(self, page, stop_y: Optional[float] = None) -> float:
        page_height = page.rect.height
        footer_y = self.find_footer_limit(page)
        limit_y = page_height * 0.95
        
        if stop_y is not None:
            limit_y = min(limit_y, stop_y - 5)
        if footer_y < page_height:
            limit_y = min(limit_y, footer_y - 5)
        
        return limit_y
    
    # ==================== ZONE-BASED PURGE ====================
    
    def purge_pollution_zone(self, page, grid) -> List[tuple]:
        all_words = page.get_text("words")
        
        zone_x0 = grid.pollution_zone_x0
        zone_x1 = grid.pollution_zone_x1
        
        self.referencia_y_positions = []
        for word in all_words:
            wx0, wy0, wx1, wy1, text = word[:5]
            if "Referencia" in text or "referencia" in text:
                self.referencia_y_positions.append(wy0)
        
        purged = []
        for word in all_words:
            wx0, wy0, wx1, wy1, text = word[:5]
            
            if self.doc_type == "B":
                if wx0 >= zone_x0 and wx0 < zone_x1:
                    continue
            
            purged.append(word)
        
        return purged
    
    def is_header_noise(self, text: str) -> bool:
        text_upper = text.upper().strip()
        for keyword in self.HEADER_BLACKLIST:
            if keyword == text_upper or keyword in text_upper:
                return True
        return False
    
    def is_page_header_text(self, text: str) -> bool:
        for pattern in self.PAGE_HEADER_PATTERNS:
            if pattern.search(text):
                return True
        return False
    
    # ==================== GRID BUILDING ====================
    
    def find_horizon(self, page):
        for term in ["Detalle de Movimientos Realizados", "Detalle de Movimientos"]:
            instances = page.search_for(term)
            if instances:
                return instances[0].y1
        return page.rect.height * 0.15
    
    def find_header_row_y(self, page, horizon_y):
        for term in ["CARGOS", "ABONOS", "OPER"]:
            instances = page.search_for(term)
            for inst in instances:
                if inst.y0 > horizon_y and inst.y0 < page.rect.height * 0.80:
                    return inst.y0
        return horizon_y + 20
    
    def extract_headers(self, page, horizon_y, header_row_y):
        header_boxes = {}
        keywords = {
            "OPER": ["OPER"], "LIQ": ["LIQ"],
            "DESCRIPCION": ["DESCRIPCION", "DESCRIPCI"],
            "REFERENCIA": ["REFERENCIA"],
            "CARGOS": ["CARGOS"], "ABONOS": ["ABONOS"],
            "OPERACION": ["OPERACION", "OPERACI"],
            "LIQUIDACION": ["LIQUIDACION", "LIQUIDACI"]
        }
        
        for key, terms in keywords.items():
            for term in terms:
                instances = page.search_for(term)
                for inst in instances:
                    if inst.y0 < horizon_y:
                        continue
                    if abs(inst.y0 - header_row_y) > self.Y_TOLERANCE:
                        continue
                    if key == "OPERACION" and inst.x0 < 400:
                        continue
                    if key == "LIQUIDACION" and inst.x0 < 500:
                        continue
                    if key not in header_boxes:
                        header_boxes[key] = HeaderBox(term, inst.x0, inst.y0, inst.x1, inst.y1)
                        break
                if key in header_boxes:
                    break
        return header_boxes
    
    def calculate_strict_header_bottom(self, header_boxes) -> float:
        max_y1 = 0
        for hb in header_boxes.values():
            if hb.y1 > max_y1:
                max_y1 = hb.y1
        return max_y1
    
    def calculate_lines_type_a(self, header_boxes):
        oper = header_boxes.get("OPER")
        liq = header_boxes.get("LIQ")
        desc = header_boxes.get("DESCRIPCION")
        cargos = header_boxes.get("CARGOS")
        abonos = header_boxes.get("ABONOS")
        operacion = header_boxes.get("OPERACION")
        liquidacion = header_boxes.get("LIQUIDACION")
        
        return [
            oper.x1 + 3 if oper else 48,
            (liq.x1 + desc.x0) / 2 if liq and desc else 80,
            cargos.x0 - 15 if cargos else 358,
            abonos.x0 - 10 if abonos else 420,
            (abonos.x1 + operacion.x0) / 2 if abonos and operacion else 471,
            (operacion.x1 + liquidacion.x0) / 2 if operacion and liquidacion else 530
        ]
    
    def calculate_lines_type_b(self, header_boxes):
        oper = header_boxes.get("OPER")
        liq = header_boxes.get("LIQ")
        desc = header_boxes.get("DESCRIPCION")
        cargos = header_boxes.get("CARGOS")
        abonos = header_boxes.get("ABONOS")
        operacion = header_boxes.get("OPERACION")
        liquidacion = header_boxes.get("LIQUIDACION")
        
        return [
            (oper.x1 + liq.x0) / 2 if oper and liq else 57,
            (liq.x1 + desc.x0) / 2 if liq and desc else 94,
            cargos.x0 - 15 if cargos else 366,
            abonos.x0 - 5 if abonos else 418,
            (abonos.x1 + operacion.x0) / 2 if abonos and operacion else 462,
            (operacion.x1 + liquidacion.x0) / 2 if operacion and liquidacion else 525
        ]
    
    def build_master_grid(self, page, page_num):
        horizon_y = self.find_horizon(page)
        header_row_y = self.find_header_row_y(page, horizon_y)
        header_boxes = self.extract_headers(page, horizon_y, header_row_y)
        
        header_bottom = self.calculate_strict_header_bottom(header_boxes)
        if header_bottom == 0:
            header_bottom = header_row_y + 15
        
        if self.doc_type == "B":
            lines = self.calculate_lines_type_b(header_boxes)
            ref_header = header_boxes.get("REFERENCIA")
            pollution_x0 = ref_header.x0 - 5 if ref_header else 315
            pollution_x1 = lines[2]
        else:
            lines = self.calculate_lines_type_a(header_boxes)
            pollution_x0 = 0
            pollution_x1 = 0
        
        print(f"  [LOCK GRID] Page {page_num}: {[f'{x:.1f}' for x in lines]}")
        print(f"    Header Row Y: {header_row_y:.0f}, Header Bottom Y: {header_bottom:.0f}")
        
        return MasterGrid(
            vertical_lines=lines,
            header_boxes=header_boxes,
            start_page=page_num,
            pollution_zone_x0=pollution_x0,
            pollution_zone_x1=pollution_x1,
            header_row_y=header_row_y,
            header_bottom_y=header_bottom
        )
    
    # ==================== STATE MACHINE ====================
    
    def check_start_trigger(self, page_text):
        return self.START_TRIGGER in page_text
    
    def check_stop_trigger(self, page_text):
        for pattern in self.STOP_TRIGGERS:
            if pattern.search(page_text):
                return True
        return False
    
    # ==================== DATE BEACON LOCK ====================
    
    def find_date_beacon(self, words, header_top_y, limit_y) -> Optional[float]:
        L1 = self.master_grid.vertical_lines[0]
        
        date_candidates = []
        for word in words:
            x0, y0, x1, y1, text = word[:5]
            if x0 > L1 + 10:
                continue
            if y0 < header_top_y - 10:
                continue
            if y0 > limit_y:
                continue
            if self.DATE_PATTERN.match(text.strip()):
                date_candidates.append({
                    'text': text.strip(),
                    'y0': y0,
                    'y1': y1,
                    'x0': x0
                })
        
        if not date_candidates:
            return None
        
        date_candidates.sort(key=lambda d: d['y0'])
        first_date = date_candidates[0]
        
        print(f"    [DATE BEACON] Locked first date '{first_date['text']}' at Y={first_date['y0']:.0f}")
        return first_date['y0']
    
    # ==================== OVERHEAD SCAN (Type B) ====================
    
    def full_overhead_scan_type_b(self, page, grid, first_date_y, page_num) -> Tuple[str, dict]:
        if first_date_y is None:
            return "", {}
        
        L2 = grid.vertical_lines[1]
        L3 = grid.vertical_lines[2]
        L5 = grid.vertical_lines[4]
        
        zone_top = 0
        zone_bottom = first_date_y - 2
        
        debug_info = {
            'zone_rect': (L2, zone_top, L5, zone_bottom),
            'page_num': page_num,
            'found_words': [],
            'scan_type': 'Type B Full Overhead'
        }
        
        if zone_bottom <= zone_top:
            return "", debug_info
        
        orphaned_parts = []
        for word in self.purged_words:
            wx0, wy0, wx1, wy1, text = word[:5]
            
            if wy0 < zone_top or wy0 >= zone_bottom:
                continue
            if wx0 < L2 - 3 or wx0 > L5 + 3:
                continue
            if wx0 >= L3:
                continue
            if self.is_page_header_text(text):
                continue
            if self.is_header_noise(text):
                continue
            
            orphaned_parts.append(text)
            debug_info['found_words'].append({'text': text, 'x0': wx0, 'y0': wy0})
        
        result = " ".join(orphaned_parts).strip()
        if result:
            print(f"    [OVERHEAD SCAN] Found orphaned text: '{result[:50]}...'")
        
        return result, debug_info
    
    # ==================== STEP 1: ZERO-GAP SCAN (Type A) RE-ACTIVATED ====================
    
    def find_continuation_header_bottom(self, page) -> Optional[float]:
        """Find header bottom on Type A continuation page."""
        all_words = page.get_text("words")
        max_y1 = None
        
        for word in all_words:
            wx0, wy0, wx1, wy1, text = word[:5]
            text_upper = text.upper()
            
            for keyword in self.HEADER_BLACKLIST:
                if keyword in text_upper:
                    if wy0 < page.rect.height * 0.30:
                        if max_y1 is None or wy1 > max_y1:
                            max_y1 = wy1
                        break
        
        return max_y1
    
    def zero_gap_scan_type_a(self, page, grid, first_date_y, page_num) -> Tuple[str, dict]:
        """
        Step 1: Re-activated Header-Bottom Scan for Type A continuation pages.
        Scan from header_bottom to first_date_y to capture cross-page orphaned text.
        """
        if first_date_y is None:
            return "", {}
        
        # Find header bottom on this continuation page
        header_bottom = self.find_continuation_header_bottom(page)
        if header_bottom is None:
            header_bottom = 150  # Default fallback
        
        L2 = grid.vertical_lines[1]
        L3 = grid.vertical_lines[2]
        L5 = grid.vertical_lines[4]
        
        zone_top = header_bottom
        zone_bottom = first_date_y - 2
        
        debug_info = {
            'zone_rect': (L2, zone_top, L5, zone_bottom),
            'page_num': page_num,
            'found_words': [],
            'scan_type': 'Type A Zero-Gap',
            'header_bottom': header_bottom
        }
        
        if zone_bottom <= zone_top:
            print(f"    [ZERO-GAP] No blind spot (header={header_bottom:.0f}, date={first_date_y:.0f})")
            return "", debug_info
        
        orphaned_parts = []
        for word in self.purged_words:
            wx0, wy0, wx1, wy1, text = word[:5]
            
            # Must be in zone Y range
            if wy0 < zone_top or wy0 >= zone_bottom:
                continue
            
            # Wide-net X range: L2 to L5
            if wx0 < L2 - 3 or wx0 > L5 + 3:
                continue
            
            # Left-origin rule: Keep only if x0 < L3 (descripcion zone)
            if wx0 >= L3:
                continue
            
            # Filter header keywords
            if self.is_header_noise(text):
                continue
            
            orphaned_parts.append(text)
            debug_info['found_words'].append({'text': text, 'x0': wx0, 'y0': wy0})
        
        result = " ".join(orphaned_parts).strip()
        
        if result:
            print(f"    [ZERO-GAP SCAN] Found orphaned text: '{result[:60]}...'")
            print(f"    [ZERO-GAP SCAN] Rect: ({L2:.0f}, {zone_top:.0f}, {L3:.0f}, {zone_bottom:.0f})")
        
        return result, debug_info
    
    # ==================== ROW SLICES ====================
    
    def build_row_slices_with_beacon(self, limit_y, header_top_y) -> List[RowSlice]:
        L1 = self.master_grid.vertical_lines[0]
        
        date_entries = []
        for word in self.purged_words:
            x0, y0, x1, y1, text = word[:5]
            if x0 > L1 + 10:
                continue
            if y0 < header_top_y - 10:
                continue
            if y0 > limit_y:
                continue
            if self.DATE_PATTERN.match(text.strip()):
                date_entries.append({
                    'text': text.strip(),
                    'y0': y0,
                    'y1': y1,
                    'x0': x0
                })
        
        date_entries.sort(key=lambda d: d['y0'])
        
        unique_dates = []
        last_y = -100
        for d in date_entries:
            if d['y0'] - last_y > 5:
                unique_dates.append(d)
                last_y = d['y0']
        
        slices = []
        for i, d in enumerate(unique_dates):
            y_top = d['y0']
            date_y1 = d['y1']
            
            if i < len(unique_dates) - 1:
                y_bottom = min(unique_dates[i + 1]['y0'] - 1, limit_y)
            else:
                y_bottom = limit_y
            
            slices.append(RowSlice(
                index=i, y_top=y_top, y_bottom=y_bottom,
                date_text=d['text'], date_y1=date_y1
            ))
        
        return slices
    
    # ==================== CELL EXTRACTION ====================
    
    def extract_cell_with_filter(self, x0, y0, x1, y1, limit_y) -> str:
        result_parts = []
        
        for word in self.purged_words:
            wx0, wy0, wx1, wy1, text = word[:5]
            
            if wy0 > limit_y:
                continue
            if wy0 < y0 - 2 or wy0 > y1:
                continue
            if wx0 < x0 - 3 or wx0 > x1 + 3:
                continue
            if self.is_header_noise(text):
                continue
            
            result_parts.append(text)
        
        return " ".join(result_parts).strip()
    
    def extract_numeric_cell_centroid_v55(self, col_left, col_right, row_center_y, col_name="") -> Tuple[str, list]:
        """
        V55: Centroid-Based Extraction - Filter by Vertical Center Alignment
        
        Logic:
        1. Use a generous scan window to collect all candidate words
        2. For each word, calculate its center Y
        3. Only keep words where |Word_Center_Y - Row_Center_Y| <= 5px
        4. Words with larger delta are "intruders" from adjacent rows
        
        Returns: (extracted_text, list_of_kept_centroids)
        """
        # Step 1: Use generous scan window for initial word collection
        scan_top = row_center_y - self.GENEROUS_SCAN_HEIGHT / 2
        scan_bottom = row_center_y + self.GENEROUS_SCAN_HEIGHT / 2
        
        result_parts = []
        kept_centroids = []  # For debug visualization
        
        for word in self.purged_words:
            wx0, wy0, wx1, wy1, text = word[:5]
            
            # Initial generous Y range filter
            if wy0 < scan_top or wy0 > scan_bottom:
                continue
            
            # Must contain a digit
            if not re.search(r'\d', text):
                continue
            
            # X-axis: centroid must be within column bounds
            center_x = (wx0 + wx1) / 2
            if center_x < col_left or center_x >= col_right:
                continue
            
            # Step 2: Calculate word center Y (the "heart" of the word)
            word_center_y = (wy0 + wy1) / 2
            
            # Step 3: Centroid Distance Check - V55 Core Filter
            delta = abs(word_center_y - row_center_y)
            
            if delta > self.CENTROID_TOLERANCE:
                # Intruder from another row - reject
                continue
            
            # Type B specific: Referencia adjacency check
            is_referencia_adjacent = False
            if self.doc_type == "B":
                for ref_y in self.referencia_y_positions:
                    if abs(wy0 - ref_y) < 5:
                        is_referencia_adjacent = True
                        break
            
            if is_referencia_adjacent:
                continue
            if self.is_header_noise(text):
                continue
            
            # Passed all filters - keep this word
            result_parts.append(text)
            kept_centroids.append({
                'x': center_x,
                'y': word_center_y,
                'text': text,
                'col': col_name,
                'delta': delta
            })
        
        result_text = " ".join(result_parts).strip()
        
        return result_text, kept_centroids
    
    def extract_numeric_cell_absolute(self, col_left, col_right, y_top, col_name="") -> Tuple[str, dict]:
        """
        V55: Wrapper that calls centroid-based extraction.
        Calculates Row_Center_Y from date position (y_top is date_top).
        """
        if self.doc_type == "A":
            # Type A: Use V55 centroid-based logic
            # Row_Center_Y = center of the date row (approximately y_top + 5px for ~10px tall date)
            row_center_y = y_top + 5  # Date is ~10px tall, center is ~5px from top
            
            result, centroids = self.extract_numeric_cell_centroid_v55(col_left, col_right, row_center_y, col_name)
            
            # Return compatible cell_box structure for debug
            cell_box = {
                'col_name': col_name,
                'x0': col_left,
                'y0': y_top,
                'x1': col_right,
                'y1': y_top + 13,  # Nominal height for reference
                'type': 'numeric',
                'row_center_y': row_center_y,
                'centroids': centroids
            }
            return result, cell_box
        else:
            # Type B: Original logic unchanged
            y_bottom = y_top + self.NUMERIC_ROW_HEIGHT
            
            cell_box = {
                'col_name': col_name,
                'x0': col_left,
                'y0': y_top,
                'x1': col_right,
                'y1': y_bottom,
                'type': 'numeric'
            }
            
            result_parts = []
            for word in self.purged_words:
                wx0, wy0, wx1, wy1, text = word[:5]
                
                if wy0 < y_top - 2 or wy0 > y_bottom:
                    continue
                if not re.search(r'\d', text):
                    continue
                
                center_x = (wx0 + wx1) / 2
                if center_x < col_left or center_x >= col_right:
                    continue
                
                is_referencia_adjacent = False
                for ref_y in self.referencia_y_positions:
                    if abs(wy0 - ref_y) < 5:
                        is_referencia_adjacent = True
                        break
                
                if is_referencia_adjacent:
                    continue
                if self.is_header_noise(text):
                    continue
                
                result_parts.append(text)
            
            return " ".join(result_parts).strip(), cell_box
    
    def extract_numeric_cell_centroid(self, col_left, col_right, y_top, date_y1) -> str:
        """
        Compatibility wrapper for V55 - calls extract_numeric_cell_absolute.
        """
        result, _ = self.extract_numeric_cell_absolute(col_left, col_right, y_top)
        return result
    
    def parse_money(self, text: str) -> float:
        if not text or text.strip() == '':
            return 0.00
        cleaned = text.replace(',', '').replace(' ', '').strip()
        match = re.search(r'(\d+\.?\d*)', cleaned)
        if match:
            try:
                return round(float(match.group(1)), 2)
            except ValueError:
                return 0.00
        return 0.00
    
    # ==================== PAGE EXTRACTION ====================
    
    def extract_page(self, page, page_num, grid, limit_y, is_start_page=False) -> List[TransactionRow]:
        self.purged_words = self.purge_pollution_zone(page, grid)
        # V69: Store grid lines for visualization
        self.grid_lines_per_page[page_num] = grid.vertical_lines
        
        if is_start_page:
            scan_start_y = grid.header_row_y
        else:
            if self.doc_type == "B":
                scan_start_y = 130
            else:
                header_bottom = self.find_continuation_header_bottom(page)
                scan_start_y = header_bottom if header_bottom else 150
        
        first_date_y = self.find_date_beacon(self.purged_words, scan_start_y, limit_y)
        
        # Step 1: Cross-page orphaned text scanning (for continuation pages)
        orphaned_desc = ""
        radar_debug = {}
        if not is_start_page and first_date_y is not None:
            if self.doc_type == "B":
                orphaned_desc, radar_debug = self.full_overhead_scan_type_b(
                    page, grid, first_date_y, page_num
                )
            else:
                # Type A: Re-activated zero-gap scan
                orphaned_desc, radar_debug = self.zero_gap_scan_type_a(
                    page, grid, first_date_y, page_num
                )
            
            # Stitch orphaned text to previous page's last row (no marker, clean join)
            if orphaned_desc:
                if self.all_transactions:
                    prev_row = self.all_transactions[-1]
                    prev_row['descripcion'] = prev_row['descripcion'] + " " + orphaned_desc
                    print(f"    [STITCH] Appended to prev row (seamless)")
                else:
                    self.pending_orphaned_text = orphaned_desc
        
        if radar_debug:
            radar_debug['grid_lines'] = grid.vertical_lines
            self.debug_pages.append(radar_debug)
        
        row_slices = self.build_row_slices_with_beacon(limit_y, scan_start_y)
        
        if not row_slices:
            return []
        
        L1, L2, L3, L4, L5, L6 = grid.vertical_lines
        
        transactions = []
        
        for idx, row in enumerate(row_slices):
            y_top = row.y_top
            y_bottom = min(row.y_bottom, limit_y)
            date_y1 = row.date_y1
            
            fecha_oper = row.date_text
            fecha_liq = self.extract_cell_with_filter(L1, y_top, L2, date_y1 + 3, limit_y)
            
            desc_x1 = grid.pollution_zone_x0 - 5 if self.doc_type == "B" else L3
            descripcion = self.extract_cell_with_filter(L2, y_top, desc_x1, y_bottom, limit_y)
            
            if idx == 0 and self.pending_orphaned_text:
                descripcion = self.pending_orphaned_text + " " + descripcion
                self.pending_orphaned_text = ""
            
            cargos_text, cargos_box = self.extract_numeric_cell_absolute(L3, L4, y_top, "CARGOS")
            abonos_text, abonos_box = self.extract_numeric_cell_absolute(L4, L5, y_top, "ABONOS")
            operacion_text, operacion_box = self.extract_numeric_cell_absolute(L5, L6, y_top, "OPERACION")
            liquidacion_text, liquidacion_box = self.extract_numeric_cell_absolute(L6, self.page_width, y_top, "LIQUIDACION")
            
            # V65: Parse all numerics early for Blacklist construction
            cargos = self.parse_money(cargos_text)
            abonos = self.parse_money(abonos_text)
            saldo_oper = self.parse_money(operacion_text)
            saldo_liq = self.parse_money(liquidacion_text)
            
            # V65: Construct Row-Level Blacklist (Non-zero values)
            blacklist = [v for v in [cargos, abonos, saldo_oper, saldo_liq] if v > 0.01]

            # V65: Type B Referencia Backfill (SEMANTIC SUBTRACTION)
            referencia = ""
            if self.doc_type == "B":
                is_first_row = (idx == 0 and is_start_page)
                
                referencia, ref_words = self.backfill_referencia_type_b(
                    page_num, y_top, y_bottom, 
                    row_values={
                        'cargos': cargos,
                        'abonos': abonos,
                        'saldo_operacion': saldo_oper,
                        'saldo_liquidacion': saldo_liq
                    },
                    grid_lines=grid.vertical_lines,
                    is_first_row=is_first_row
                )
                
                # Collect for debug visualization
                if ref_words:
                    if page_num not in self.referencia_debug_per_page:
                        self.referencia_debug_per_page[page_num] = []
                    self.referencia_debug_per_page[page_num].extend(ref_words)
            
            # Collect cell boxes for V55 debug visualization (Type A only)
            if self.doc_type == "A":
                # Description box (tall - uses full row height)
                desc_box = {
                    'col_name': 'DESCRIPCION',
                    'x0': L2, 'y0': y_top, 'x1': L3, 'y1': y_bottom,
                    'type': 'text'
                }
                row_boxes = [desc_box, cargos_box, abonos_box, operacion_box, liquidacion_box]
                if page_num not in self.cell_boxes_per_page:
                    self.cell_boxes_per_page[page_num] = []
                self.cell_boxes_per_page[page_num].extend(row_boxes)
            
            # V65: All numerics already parsed above
            # cargos, abonos, saldo_oper, saldo_liq are ready
            
            row_dict = {
                'fecha_oper': fecha_oper,
                'fecha_liq': fecha_liq,
                'descripcion': descripcion,
                'referencia': referencia,  # V57: Pre-filled for Type B
                'cargos': cargos,
                'abonos': abonos,
                'saldo_operacion': saldo_oper,
                'saldo_liquidacion': saldo_liq,
                '_page': page_num
            }
            
            # Step 2 & 3: Apply Type A post-extraction cleaning (destructive migration)
            row_dict = self.post_process_row_type_a(row_dict)
            
            # Step 3: Double validation
            if self.doc_type == "A" and not self.validate_no_referencia_in_descripcion(row_dict):
                print(f"    [WARN] Row {idx+1} still has referencia content in descripcion!")
            
            transactions.append(TransactionRow(**{k: v for k, v in row_dict.items() if not k.startswith('_')}))
            self.all_transactions.append(row_dict)
        
        return transactions
    
    # ==================== VISUAL DEBUG ====================
    
    def generate_debug_centroids_image(self, doc, output_path):
        """
        V55: Generate debug image showing centroid-based extraction.
        - Red horizontal line = Row Center Y (the "gravity center" of each row)
        - Green dots = Kept word centroids (passed the Delta <= 5px filter)
        
        Expected: CHEQUE PAGADO row should have red line only, no green dots
        (because the intruder words from next row failed the centroid filter)
        """
        if not self.cell_boxes_per_page:
            print("  [DEBUG] No centroid data to visualize (Type B has no centroid debug)")
            return
        
        for page_num, boxes in self.cell_boxes_per_page.items():
            if page_num > len(doc):
                continue
            
            page = doc[page_num - 1]
            shape = page.new_shape()
            
            # Track row center Y positions for drawing horizontal lines
            row_centers_drawn = set()
            
            for box in boxes:
                col_type = box.get('type', 'unknown')
                
                if col_type == 'text':
                    # Description column: Just draw a light box
                    x0, y0, x1, y1 = box['x0'], box['y0'], box['x1'], box['y1']
                    cell_rect = fitz.Rect(x0, y0, x1, y1)
                    shape.draw_rect(cell_rect)
                    shape.finish(color=(0.5, 0.5, 0.5), fill=None, width=0.5)
                else:
                    # Numeric columns: Draw row center line and centroids
                    row_center_y = box.get('row_center_y')
                    centroids = box.get('centroids', [])
                    
                    # Draw row center line (red) - only once per row
                    if row_center_y and row_center_y not in row_centers_drawn:
                        shape.draw_line((0, row_center_y), (page.rect.width, row_center_y))
                        shape.finish(color=(1, 0, 0), width=1)
                        row_centers_drawn.add(row_center_y)
                    
                    # Draw kept centroids (green dots)
                    for centroid in centroids:
                        cx, cy = centroid['x'], centroid['y']
                        shape.draw_circle((cx, cy), 2)
                        shape.finish(color=(0, 0.8, 0), fill=(0, 1, 0), width=1)
            
            shape.commit()
            
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            
            img_path = output_path.parent / f"debug_v57_centroids_page{page_num}.png"
            pix.save(str(img_path))
            print(f"  [DEBUG] Saved V57 centroid visualization: {img_path}")
    
    def generate_referencia_debug_image(self, doc, output_path):
        """
        V57: Generate debug image showing Type B referencia backfill.
        - Blue boxes = Captured REFERENCIA words (passed left-origin rule)
        
        Expected: Blue boxes should align left at ~310px (Referencia zone)
        and may overflow right into CARGOS zone (this is correct).
        """
        if not self.referencia_debug_per_page:
            print("  [DEBUG] No referencia data to visualize (Type A has no referencia debug)")
            return
        
        for page_num, words in self.referencia_debug_per_page.items():
            if page_num > len(doc):
                continue
            
            page = doc[page_num - 1]
            shape = page.new_shape()
            
            for word in words:
                x0, y0, x1, y1 = word['x0'], word['y0'], word['x1'], word['y1']
                word_rect = fitz.Rect(x0, y0, x1, y1)
                
                # Blue box for referencia words
                shape.draw_rect(word_rect)
                shape.finish(color=(0, 0, 0.8), fill=(0.3, 0.3, 1), fill_opacity=0.3, width=1.5)
            
            shape.commit()
            
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            
            img_path = output_path.parent / f"debug_v57_referencia_fill_page{page_num}.png"
            
            # V69: Draw Grid Lines on top of words
            lines = self.grid_lines_per_page.get(page_num)
            if lines:
                # lines: [L1, L2, L3, L4, L5, L6]
                page_h = page.rect.height
                
                # Draw Iron Curtain (L5) in RED
                if len(lines) > 4:
                    l5 = lines[4]
                    curtain_x = l5 - 5
                    shape.draw_line((curtain_x, 0), (curtain_x, page_h))
                    shape.finish(color=(1, 0, 0), width=2) # Red Thick
                
                # Draw other lines (Cargos/Abonos start) in Green
                for i, x in enumerate(lines):
                    if i == 4: continue # Skip L5 (already drawn)
                    shape.draw_line((x, 0), (x, page_h))
                    shape.finish(color=(0, 0.5, 0), width=0.5) # Thin Green

            shape.commit()
            
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            pix.save(str(img_path))
            print(f"  [DEBUG] Saved V69 detailed visualization: {img_path}")
    
    # ==================== MAIN EXTRACTION ====================
    
    def extract_document(self, pdf_path):
        """V72 TypeB专用提取方法"""
        doc = fitz.open(pdf_path)
        
        # IMMUTABLE SOURCE POLICY
        self.original_source_path = pdf_path
        self.pdf_path = pdf_path
        
        stem = Path(pdf_path).stem
        self.page_width = doc[0].rect.width
        
        print(f"\n{'='*70}")
        print(f"V72.0 TypeB Engine")
        print(f"{'='*70}")
        print(f"Document: {stem}")
        print(f"Pages: {len(doc)}")
        
        # V72固定处理TypeB文档
        self.doc_type = "B"
        
        self.is_recording = False
        self.master_grid = None
        self.pages_in_session = 0
        self.session_count = 0
        self.all_transactions = []
        self.debug_pages = []
        self.pending_orphaned_text = ""
        self.cell_boxes_per_page = {}  # V55: For Type A debug
        self.referencia_debug_per_page = {}  # V59: For Type B debug
        self.grid_lines_per_page = {}   # V69: For Grid Viz
        
        all_pages = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            page_text = page.get_text()
            human_page = page_num + 1
            
            if self.check_start_trigger(page_text):
                self.is_recording = True
                self.master_grid = self.build_master_grid(page, human_page)
                print(f"  [V72虚拟GRID已锁定] {self.master_grid.vertical_lines}")
                self.pages_in_session = 1
                self.session_count += 1
                
                has_stop = self.check_stop_trigger(page_text)
                stop_y = self.find_stop_trigger_y(page) if has_stop else None
                limit_y = self.calculate_effective_limit(page, stop_y)
                
                transactions = self.extract_page(page, human_page, self.master_grid, limit_y, 
                                                  is_start_page=True)
                if transactions:
                    all_pages.append({
                        "page": human_page,
                        "rows": [asdict(t) for t in transactions]
                    })
                    status = f"[START S{self.session_count}]"
                    if has_stop:
                        status += " [STOP]"
                    print(f"  Page {human_page}: {len(transactions)} rows {status}")
                
                if has_stop:
                    self.is_recording = False
                continue
            
            if not self.is_recording:
                continue
            
            if self.master_grid:
                has_stop = self.check_stop_trigger(page_text)
                stop_y = self.find_stop_trigger_y(page) if has_stop else None
                limit_y = self.calculate_effective_limit(page, stop_y)
                
                self.pages_in_session += 1
                transactions = self.extract_page(page, human_page, self.master_grid, limit_y,
                                                  is_start_page=False)
                
                if transactions:
                    all_pages.append({
                        "page": human_page,
                        "rows": [asdict(t) for t in transactions]
                    })
                    status = "[CONT]"
                    if has_stop:
                        status = "[STOP]"
                    print(f"  Page {human_page}: {len(transactions)} rows {status}")
                
                if has_stop:
                    self.is_recording = False
        
        # 输出路径
        output_base = Path(r"D:\GEMINI_PDF_TO_JSON_BBVA\output\20260112BBVA_GEMINI_验证结果")
        output_folder = output_base / f"{stem}_TypeB"
        output_folder.mkdir(parents=True, exist_ok=True)
        
        output_path = output_folder / f"{stem}_v72_extracted.json"
        
        # 调试可视化（仅TypeB）
        if self.DEBUG_VISUAL:
            self.generate_referencia_debug_image(doc, output_path)
        
        doc.close()
        
        # Generate grid visualization images
        try:
            from final_grid_visualizer_v37 import FinalGridVisualizerV37
            visualizer = FinalGridVisualizerV37()
            visualizer.process_document(pdf_path, str(output_folder))
            print(f"  [GRID] Saved grid visualizations to {output_folder}")
        except Exception as e:
            print(f"  [GRID WARNING] Failed to generate grid visualization: {e}")
        
        
        # 统一输出格式：所有交易都放到page 0中（与V84保持一致）
        all_pages = [{
            "page": 0,
            "rows": [
                {k: v for k, v in tx.items() if not k.startswith('_')}
                for tx in self.all_transactions
            ]
        }]
        
        total_rows = len(self.all_transactions)
        
        output = {
            "source_file": stem,
            "document_type": self.doc_type,
            "total_pages": len(all_pages),
            "total_rows": total_rows,
            "sessions": self.session_count,
            "pages": all_pages
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        
        print(f"\n{'='*70}")
        print(f"[OK] Extracted {total_rows} transactions from {len(all_pages)} pages")
        print(f"  Type: {self.doc_type}")
        print(f"  Sessions: {self.session_count}")
        print(f"  Output: {output_path}")
        print(f"{'='*70}")
        
        # Validation output for Type A
        if self.doc_type == "A" and all_pages:
            print(f"\n[VALIDATION - Type A Sample Data]")
            
            # Find cross-page row (with [CONT] marker)
            for pg in all_pages:
                for row in pg['rows']:
                    if '[CONT]' in row.get('descripcion', ''):
                        print(f"\n  [Cross-Page Row] Page {pg['page']} last row:")
                        print(f"    descripcion: {row['descripcion'][:80]}...")
                        break
            
            # Find a row with RFC in referencia
            for pg in all_pages:
                for row in pg['rows']:
                    if 'RFC:' in row.get('referencia', ''):
                        print(f"\n  [Referencia Row] Page {pg['page']}:")
                        print(f"    descripcion: {row['descripcion']}")
                        print(f"    referencia: {row['referencia']}")
                        # Verify no RFC in descripcion
                        if 'RFC:' in row.get('descripcion', ''):
                            print(f"    [FAIL] RFC still in descripcion!")
                        else:
                            print(f"    [PASS] No RFC in descripcion")
                        break
                else:
                    continue
                break
        
        return output, str(output_path)


def main():
    if len(sys.argv) < 2:
        print("Usage: python final_grid_extractor_v72.py <pdf_path>")
        print("\nV72.0 - Zero Guard (Integer Format Protection)")
        print("  Protects '00' or '0' codes from being dropped as zero values.")
        print("  Only drops '0.00' if matching zero column.")
        sys.exit(1)
    
    try:
        extractor = FinalGridExtractorV72()
        data, output_path = extractor.extract_document(sys.argv[1])
        print(f"\n[OK] JSON saved to: {output_path}")
    except Exception as e:
        print(f"\n[X] CRASHED: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

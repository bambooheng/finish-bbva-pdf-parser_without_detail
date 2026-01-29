"""
Final Grid Extractor V84.0 - TypeA Engine

专注处理TypeA文档（如3030.pdf, 8359.pdf）

STRATEGY:
- 基于V82逻辑
- 特性：Row Coherence, Smart Stop, Global Fuse, Header Wake-up
- 目标：处理复杂表头、偏移数据和严格终止条件

ARCHITECTURE:
- V86调度器将TypeA文档路由到此引擎
- V84专门且仅处理TypeA类型文档
- TypeB文档由V72引擎处理

Usage:
    python final_grid_extractor_v84.py <pdf_path>
    或通过V86调度: python final_grid_extractor_v86.py <pdf_path>
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


class FinalGridExtractorV84:
    """V84 Twin-Engine - Physical Isolation of Logic"""
    
    # Shared Constants
    DATE_PATTERN = re.compile(r'^\d{2}\s*/\s*[A-Z]{3}$', re.IGNORECASE)
    DATE_INLINE_PATTERN = re.compile(r'\d{2}/[A-Z]{3}', re.IGNORECASE)
    CURRENCY_REGEX = re.compile(r'^-?\d{1,3}(,\d{3})*\.\d{2}$')
    
    NUMERIC_MIN_X = 310.0 # For Type A Coherence
    REF_ZONE_LEFT_TYPE_B = 280   
    REF_ZONE_RIGHT_TYPE_B = 1000 
    
    HEADER_BLACKLIST = [
        "OPER", "LIQ", "DESCRIPCION", "DESCRIPCIÓN", "REFERENCIA",
        "CARGOS", "ABONOS", "OPERACION", "OPERACIÓN", "LIQUIDACION",
        "LIQUIDACIÓN", "SALDO", "FECHA"
    ]
    
    WAKEUP_HEADERS = ["FECHA", "OPER", "LIQ", "CARGOS", "ABONOS", "SALDO"]
    
    PAGE_HEADER_PATTERNS = [
        re.compile(r'BBVA', re.IGNORECASE),
        re.compile(r'Estado\s+de\s+Cuenta', re.IGNORECASE),
        re.compile(r'PAGINA', re.IGNORECASE),
        re.compile(r'Cuenta', re.IGNORECASE),
        re.compile(r'Cliente', re.IGNORECASE),
    ]
    
    START_TRIGGER = "Detalle de Movimientos Realizados"
    
    STOP_TRIGGERS = [
        re.compile(r'Total\s+de\s+Movimientos', re.IGNORECASE),
        re.compile(r'TOTAL\s+IMPORTE', re.IGNORECASE)
    ]
    
    FOOTER_PATTERNS = [
        re.compile(r'La\s+GAT\s+Real', re.IGNORECASE),
        re.compile(r'BBVA\s+MEXICO', re.IGNORECASE),
        re.compile(r'PAGINA\s+\d+/\d+', re.IGNORECASE)
    ]
    
    Y_TOLERANCE = 20
    DEBUG_VISUAL = True
    
    def __init__(self):
        self.doc_type = "A"
        self.master_grid = None
        self.page_width = 612
        self.purged_words = None
        self.referencia_y_positions = []
        self.all_transactions = []
        self.cell_boxes_per_page = {} 
        self.referencia_debug_per_page = {} 
        self.original_source_path = None
        self.grid_lines_per_page = {}
        self.is_recording = False
        self.global_stop_fuse = False
        self.limit_y_context = 700
        self.session_count = 0
    
    # Missing constants
    NUMERIC_ROW_HEIGHT = 15
    GENEROUS_SCAN_HEIGHT = 30
    CENTROID_TOLERANCE = 5

    def calculate_effective_limit(self, page, stop_y: Optional[float] = None) -> float:
        page_height = page.rect.height
        footer_y = self.find_footer_limit(page)
        limit_y = page_height * 0.95
        if stop_y is not None: limit_y = min(limit_y, stop_y - 5)
        if footer_y < page_height: limit_y = min(limit_y, footer_y - 5)
        return limit_y
    
    def find_stop_trigger_y(self, page) -> Optional[float]:
        page_text = page.get_text()
        for pattern in self.STOP_TRIGGERS:
            for match in pattern.finditer(page_text):
                instances = page.search_for(match.group())
                for inst in instances:
                    if inst.y0 > page.rect.height * 0.30: return inst.y0
        return None
    
    def check_page_has_headers(self, page) -> bool:
        words = page.get_text("words")
        found_keywords = 0
        limit_y = page.rect.height * 0.3
        for w in words:
            if w[1] > limit_y: continue
            text_clean = w[4].upper().replace(" ", "").replace(".", "").strip()
            if text_clean in self.WAKEUP_HEADERS:
                found_keywords += 1
        return found_keywords >= 2

    # ==================== SHARED: CLASSIFICATION ====================
    
    def identify_document_type(self, doc) -> str:
        """
        V84 Dispatch Logic (Expert Definition - Synced with V86):
        
        Type A:
        - REFERENCIA column does NOT have content starting with "Referencia".
        - Contains content starting with "******" (usually in/near Description).
        
        Type B:
        - REFERENCIA column (X: 280-380) HAS content starting with "Referencia".
        - Distinct separation between Description and Reference.
        """
        try:
            check_limit = min(3, len(doc))
            
            # Scores
            type_b_signals = 0
            type_a_signals = 0
            
            for page_idx in range(check_limit):
                page = doc[page_idx]
                words = page.get_text("words")
                
                # Scan for Type B Signature: "Referencia" in the column
                for w in words:
                    x0 = w[0]
                    text = w[4]
                    if 280 < x0 < 380:
                        # User Rule: REFERENCIA column has content starting with "Referencia"
                        if text.lower().startswith("referencia"):
                            type_b_signals += 1
                            print(f"  [V84 DETECT] Page {page_idx+1}: Found 'Referencia' in col (x={x0:.1f}) -> Type B Signal")
                
                # Scan for Type A Signature: "******" content
                # User Rule: Referencia content is "******..."
                # We search the whole page text for this pattern
                text_content = page.get_text("text")
                if "******" in text_content:
                    type_a_signals += 1
                    print(f"  [V84 DETECT] Page {page_idx+1}: Found '******' pattern -> Type A Signal")

            print(f"  [V84 DECISION] Signals -> Type A: {type_a_signals} | Type B: {type_b_signals}")
            
            # Decision Matrix
            if type_b_signals > 0:
                return "B"
            
            return "A"
                
        except Exception as e:
            print(f"  [V84 PROBE ERROR] {e}, defaulting to A")
            return "A"

    # ==================== SHARED: GRID & HELPERS ====================

    def find_horizon(self, page):
        for term in ["Detalle de Movimientos Realizados", "Detalle de Movimientos"]:
            instances = page.search_for(term)
            if instances: return instances[0].y1
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
                    if inst.y0 < horizon_y: continue
                    if abs(inst.y0 - header_row_y) > self.Y_TOLERANCE: continue
                    if key == "OPERACION" and inst.x0 < 400: continue
                    if key == "LIQUIDACION" and inst.x0 < 500: continue
                    if key not in header_boxes:
                        header_boxes[key] = HeaderBox(term, inst.x0, inst.y0, inst.x1, inst.y1)
                        break
                if key in header_boxes: break
        return header_boxes
    
    def calculate_strict_header_bottom(self, header_boxes) -> float:
        max_y1 = 0
        for hb in header_boxes.values():
            if hb.y1 > max_y1: max_y1 = hb.y1
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
        if header_bottom == 0: header_bottom = header_row_y + 15
        
        if self.doc_type == "B":
            lines = self.calculate_lines_type_b(header_boxes)
            ref_header = header_boxes.get("REFERENCIA")
            pollution_x0 = ref_header.x0 - 5 if ref_header else 315
            pollution_x1 = lines[2]
        else:
            lines = self.calculate_lines_type_a(header_boxes)
            pollution_x0 = 0
            pollution_x1 = 0
        
        return MasterGrid(
            vertical_lines=lines, header_boxes=header_boxes, start_page=page_num,
            pollution_zone_x0=pollution_x0, pollution_zone_x1=pollution_x1,
            header_row_y=header_row_y, header_bottom_y=header_bottom
        )

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
                if wx0 >= zone_x0 and wx0 < zone_x1: continue
            purged.append(word)
        return purged

    def find_date_beacon(self, words, header_top_y, limit_y) -> Optional[float]:
        # Shared logic, but X limit may vary. Using wide 200 for safety.
        DATE_MAX_X = 200.0 
        date_candidates = []
        for word in words:
            x0, y0, x1, y1, text = word[:5]
            if x0 > DATE_MAX_X: continue
            if y0 < header_top_y - 10: continue
            if y0 > limit_y: continue
            if self.DATE_PATTERN.match(text.strip()):
                date_candidates.append({'text': text.strip(), 'y0': y0, 'y1': y1, 'x0': x0})
        
        if not date_candidates: return None
        date_candidates.sort(key=lambda d: d['y0'])
        return date_candidates[0]['y0']

    def is_header_noise(self, text: str) -> bool:
        text_clean = text.upper().replace(" ", "").replace(".", "").replace(":", "").strip()
        for keyword in self.HEADER_BLACKLIST:
            if keyword == text_clean or keyword in text_clean: return True
        return False
        
    def is_page_header_text(self, text: str) -> bool:
        for pattern in self.PAGE_HEADER_PATTERNS:
            if pattern.search(text): return True
        return False

    def check_start_trigger(self, page_text):
        return self.START_TRIGGER in page_text
    
    def check_stop_trigger(self, page_text):
        for pattern in self.STOP_TRIGGERS:
            if pattern.search(page_text): return True
        return False

    def parse_money(self, text: str) -> float:
        if not text or text.strip() == '': return 0.00
        cleaned = text.replace(',', '').replace(' ', '').strip()
        match = re.search(r'(-?\d+\.?\d*)', cleaned)
        if match:
            try: return round(float(match.group(1)), 2)
            except ValueError: return 0.00
        return 0.00
    
    def clean_fecha_liq_type_a(self, fecha_liq: str) -> str:
        """清洗fecha_liq字段，只保留日期部分（与V82保持一致）"""
        if not fecha_liq: return ""
        match = self.DATE_INLINE_PATTERN.search(fecha_liq)
        if match: return match.group()
        return ""

    def find_footer_limit(self, page) -> float:
        page_height = page.rect.height
        page_text = page.get_text()
        footer_y = page_height
        for pattern in self.FOOTER_PATTERNS:
            for match in pattern.finditer(page_text):
                instances = page.search_for(match.group())
                for inst in instances:
                    if inst.y0 > page_height * 0.30:
                        if inst.y0 < footer_y: footer_y = inst.y0
        return footer_y

    # ==================== ENGINE A COMPONENTS (For 3030.pdf, 8359.pdf) ====================

    def scan_page_limits_engine_a(self, page) -> Tuple[Optional[float], Optional[float]]:
        # V82 Coherence Logic
        words = page.get_text("words")
        dates = []
        for w in words:
            if w[0] > 200: continue
            if self.DATE_PATTERN.match(w[4].strip()): dates.append(w)
        
        if not dates: return None, None
        
        valid_rows_y = []
        for d in dates:
            d_y_center = (d[1] + d[3]) / 2
            has_number = False
            for w in words:
                if w[0] < self.NUMERIC_MIN_X: continue 
                w_y_center = (w[1] + w[3]) / 2
                if abs(w_y_center - d_y_center) < 10: 
                    clean_num = w[4].replace(",", "").replace("$", "")
                    if self.CURRENCY_REGEX.match(clean_num):
                        has_number = True
                        break
            if has_number: valid_rows_y.append(d)
        
        if not valid_rows_y: valid_rows_y = dates
        valid_rows_y.sort(key=lambda w: w[1])
        return valid_rows_y[0][1], valid_rows_y[-1][3]

    def find_smart_stop_y_engine_a(self, page, data_end_y: float) -> Tuple[Optional[float], bool]:
        # V82 Context Aware Stop
        page_text = page.get_text()
        best_stop_y = None
        for pattern in self.STOP_TRIGGERS:
            for match in pattern.finditer(page_text):
                instances = page.search_for(match.group())
                for inst in instances:
                    if inst.y0 < data_end_y: continue
                    if best_stop_y is None or inst.y0 < best_stop_y:
                        best_stop_y = inst.y0
        if best_stop_y: return best_stop_y, True
        return None, False

    def zero_gap_scan_type_a(self, page, grid, first_date_y, page_num) -> Tuple[str, dict]:
        if first_date_y is None: return "", {}
        header_bottom = self.find_continuation_header_bottom_engine_a(page)
        if header_bottom is None: header_bottom = first_date_y - 20 if first_date_y > 30 else 0
        L2, L3 = grid.vertical_lines[1], grid.vertical_lines[2]
        zone_top, zone_bottom = header_bottom, first_date_y - 2
        if zone_bottom <= zone_top: return "", {}
        orphaned_parts = []
        for word in self.purged_words:
            wx0, wy0, wx1, wy1, text = word[:5]
            if wy0 < zone_top or wy0 >= zone_bottom: continue
            if wx0 < L2 - 3 or wx0 > L3 + 3: continue # Strict desc col check
            if self.is_header_noise(text): continue
            orphaned_parts.append(text)
        return " ".join(orphaned_parts).strip(), {}

    def find_continuation_header_bottom_engine_a(self, page) -> Optional[float]:
        all_words = page.get_text("words")
        max_y1 = None
        for word in all_words:
            wx0, wy0, wx1, wy1, text = word[:5]
            text_clean = text.upper().replace(" ", "").replace(".", "").replace(":", "")
            for keyword in self.HEADER_BLACKLIST:
                if keyword in text_clean:
                    if wy0 < page.rect.height * 0.30:
                        if max_y1 is None or wy1 > max_y1: max_y1 = wy1
                        break
        return max_y1

    def extract_numeric_cell_centroid_engine_a(self, col_left, col_right, row_center_y, col_name="") -> Tuple[str, list]:
        scan_top = row_center_y - self.GENEROUS_SCAN_HEIGHT / 2
        scan_bottom = row_center_y + self.GENEROUS_SCAN_HEIGHT / 2
        result_parts = []
        kept_centroids = []
        for word in self.purged_words:
            wx0, wy0, wx1, wy1, text = word[:5]
            if wy0 < scan_top or wy0 > scan_bottom: continue
            if not re.search(r'\d', text): continue
            center_x = (wx0 + wx1) / 2
            if center_x < col_left or center_x >= col_right: continue
            word_center_y = (wy0 + wy1) / 2
            delta = abs(word_center_y - row_center_y)
            if delta > self.CENTROID_TOLERANCE: continue
            if self.is_header_noise(text): continue
            result_parts.append(text)
            kept_centroids.append({'x': center_x, 'y': word_center_y, 'text': text, 'col': col_name, 'delta': delta})
        return " ".join(result_parts).strip(), kept_centroids

    def extract_row_type_a(self, row, grid, page) -> TransactionRow:
        L1, L2, L3, L4, L5, L6 = grid.vertical_lines
        y_top, y_bottom = row.y_top, row.y_bottom
        row_center_y = y_top + 5
        
        fecha_oper = row.date_text
        # 修复：fecha_liq应该只提取日期单元格，不应该扩展到描述区域
        # 使用固定高度15px而不是row.date_y1+3，避免捕获描述列的内容
        fecha_liq = self.extract_cell_with_filter(L1, y_top, L2, y_top + 15, self.limit_y_context, page)
        descripcion = self.extract_cell_with_filter(L2, y_top, L3, y_bottom, self.limit_y_context, page)
        
        # Centroid Extraction
        cargos_text, c_box = self.extract_numeric_cell_centroid_engine_a(L3, L4, row_center_y, "CARGOS")
        abonos_text, a_box = self.extract_numeric_cell_centroid_engine_a(L4, L5, row_center_y, "ABONOS")
        oper_text, o_box = self.extract_numeric_cell_centroid_engine_a(L5, L6, row_center_y, "OPERACION")
        liq_text, l_box = self.extract_numeric_cell_centroid_engine_a(L6, self.page_width, row_center_y, "LIQUIDACION")
        
        # Debug boxes (Stored in class state for visualizer)
        pg = getattr(row, 'page_num', 0)
        if pg not in self.cell_boxes_per_page: self.cell_boxes_per_page[pg] = []
        # 添加所有列的boxes,包括日期列(用于红线绘制)
        # CRITICAL FIX: 数值列必须存储row_center_y,这是数值实际的y轴中心,用于准确绘制红线
        self.cell_boxes_per_page[pg].extend([
            {'x0': 0, 'y0': y_top, 'x1': L1, 'y1': y_top + 15, 'type': 'date'},  # fecha_oper列
            {'x0': L1, 'y0': y_top, 'x1': L2, 'y1': y_top + 15, 'type': 'date'},  # fecha_liq列
            {'x0': L2, 'y0': y_top, 'x1': L3, 'y1': y_bottom, 'type': 'text'},  # Desc
            {'x0': L3, 'y0': y_top, 'x1': L4, 'y1': y_bottom, 'type': 'num', 'row_center_y': row_center_y, 'centroids': c_box},
            {'x0': L4, 'y0': y_top, 'x1': L5, 'y1': y_bottom, 'type': 'num', 'row_center_y': row_center_y, 'centroids': a_box},
            {'x0': L5, 'y0': y_top, 'x1': L6, 'y1': y_bottom, 'type': 'num', 'row_center_y': row_center_y, 'centroids': o_box},
            {'x0': L6, 'y0': y_top, 'x1': self.page_width, 'y1': y_bottom, 'type': 'num', 'row_center_y': row_center_y, 'centroids': l_box}
        ])

        # Destructive Migration
        referencia = ""
        if re.search(r'\*{4,}\d+', descripcion):
            match = re.search(r'\*{4,}\d+', descripcion)
            split_pos = match.start()
            referencia = descripcion[split_pos:].strip()
            descripcion = descripcion[:split_pos].strip()
            
        return TransactionRow(
            fecha_oper=fecha_oper, fecha_liq=self.clean_fecha_liq_type_a(fecha_liq), descripcion=descripcion,
            referencia=referencia, 
            cargos=self.parse_money(cargos_text), abonos=self.parse_money(abonos_text),
            saldo_operacion=self.parse_money(oper_text), saldo_liquidacion=self.parse_money(liq_text)
        )

    # ==================== ENGINE B COMPONENTS (For 3038.pdf - V72 Logic) ====================

    def full_overhead_scan_type_b(self, page, grid, first_date_y, page_num) -> Tuple[str, dict]:
        if first_date_y is None: return "", {}
        L2, L3, L5 = grid.vertical_lines[1], grid.vertical_lines[2], grid.vertical_lines[4]
        zone_top, zone_bottom = 0, first_date_y - 2
        if zone_bottom <= zone_top: return "", {}
        orphaned_parts = []
        for word in self.purged_words:
            wx0, wy0, wx1, wy1, text = word[:5]
            if wy0 < zone_top or wy0 >= zone_bottom: continue
            if wx0 < L2 - 3 or wx0 > L5 + 3: continue
            if wx0 >= L3: continue
            if self.is_page_header_text(text): continue
            if self.is_header_noise(text): continue
            orphaned_parts.append(text)
        return " ".join(orphaned_parts).strip(), {}

    def extract_numeric_cell_grid_engine_b(self, col_left, col_right, y_top) -> str:
        y_bottom = y_top + self.NUMERIC_ROW_HEIGHT
        result_parts = []
        for word in self.purged_words:
            wx0, wy0, wx1, wy1, text = word[:5]
            if wy0 < y_top - 2 or wy0 > y_bottom: continue
            if not re.search(r'\d', text): continue
            center_x = (wx0 + wx1) / 2
            if center_x < col_left or center_x >= col_right: continue
            
            # Ref adjacency check (Critical for Type B)
            is_adj = False
            for ref_y in self.referencia_y_positions:
                if abs(wy0 - ref_y) < 5: is_adj = True; break
            if is_adj: continue
            
            if self.is_header_noise(text): continue
            result_parts.append(text)
        return " ".join(result_parts).strip()

    def backfill_referencia_type_b(self, page_num: int, y_top: float, y_bottom: float, 
                                    row_values: dict, grid_lines: List[float], 
                                    is_first_row: bool = False) -> Tuple[str, list]:
        if not self.original_source_path: return "", []
        try:
            doc_orig = fitz.open(self.original_source_path)
            if page_num > len(doc_orig): return "", []
            page_orig = doc_orig[page_num - 1]
            words = page_orig.get_text("words")
            CEILING_Y = y_top - 5
            
            # 动态检测Footer边界（通用逻辑）
            footer_limit_y = self.find_footer_limit(page_orig)
            
            zone_words = []
            for w in words:
                x0, y0, x1, y1, text = w[:5]
                if y1 < y_top or y0 > y_bottom: continue
                if y0 < CEILING_Y: continue
                if x0 < self.REF_ZONE_LEFT_TYPE_B: continue
                # 通用Footer过滤：排除Y坐标进入footer区域的文本
                if y0 >= footer_limit_y: continue
                zone_words.append({'x0': x0, 'y0': y0, 'x1': x1, 'y1': y1, 'text': text})
            
            doc_orig.close()
            sorted_words = sorted(zone_words, key=lambda w: w['x0'])
            anchor_idx = -1
            for i, w in enumerate(sorted_words):
                if "Referencia" in w['text'] or "Refer" in w['text']: anchor_idx = i; break
            if anchor_idx == -1: return "", []
            
            final_words = []
            L2_CARGOS = grid_lines[2]
            L3_ABONOS = grid_lines[3]
            L4_SALDO = grid_lines[4]
            IRON_CURTAIN_X = L4_SALDO - 5
            candidate_words = sorted_words[anchor_idx:]
            
            for w in candidate_words:
                if w['x0'] > IRON_CURTAIN_X: break
                text_clean = w['text'].strip()
                should_keep = True
                try:
                    val_str = text_clean.replace(',', '').replace('$', '').replace('€', '')
                    val = float(val_str)
                    word_center_x = (w['x0'] + w['x1']) / 2
                    if word_center_x > L2_CARGOS - 5:
                        if self.CURRENCY_REGEX.match(text_clean): should_keep = False
                    cargos_val = row_values.get('cargos', 0)
                    if abs(val - cargos_val) < 0.01:
                        if not (cargos_val == 0 and "." not in text_clean):
                            if word_center_x > L2_CARGOS - 5: should_keep = False
                    abonos_val = row_values.get('abonos', 0)
                    if abs(val - abonos_val) < 0.01:
                        if not (abonos_val == 0 and "." not in text_clean):
                            if word_center_x > L3_ABONOS - 5: should_keep = False
                    saldo_val = row_values.get('saldo_operacion', 0)
                    if abs(val - saldo_val) < 0.01:
                         if not (saldo_val == 0 and "." not in text_clean):
                             if word_center_x > L4_SALDO - 5: should_keep = False
                except ValueError: pass
                if should_keep: final_words.append(w)
            
            ref_parts = [w['text'] for w in final_words]
            return " ".join(ref_parts).strip(), final_words
        except Exception: return "", []

    def extract_row_type_b(self, row, grid, page_num, is_first_row=False) -> TransactionRow:
        L1, L2, L3, L4, L5, L6 = grid.vertical_lines
        y_top, y_bottom = row.y_top, row.y_bottom
        
        fecha_oper = row.date_text
        fecha_liq = self.extract_cell_with_filter(L1, y_top, L2, row.date_y1 + 3, self.limit_y_context)
        desc_x1 = grid.pollution_zone_x0 - 5
        descripcion = self.extract_cell_with_filter(L2, y_top, desc_x1, y_bottom, self.limit_y_context)
        
        cargos = self.parse_money(self.extract_numeric_cell_grid_engine_b(L3, L4, y_top))
        abonos = self.parse_money(self.extract_numeric_cell_grid_engine_b(L4, L5, y_top))
        saldo_oper = self.parse_money(self.extract_numeric_cell_grid_engine_b(L5, L6, y_top))
        saldo_liq = self.parse_money(self.extract_numeric_cell_grid_engine_b(L6, self.page_width, y_top))
        
        referencia, ref_words = self.backfill_referencia_type_b(
            page_num, y_top, y_bottom,
            row_values={'cargos': cargos, 'abonos': abonos, 'saldo_operacion': saldo_oper, 'saldo_liquidacion': saldo_liq},
            grid_lines=grid.vertical_lines, is_first_row=is_first_row
        )
        if ref_words:
            if page_num not in self.referencia_debug_per_page: self.referencia_debug_per_page[page_num] = []
            self.referencia_debug_per_page[page_num].extend(ref_words)
            
        return TransactionRow(
            fecha_oper=fecha_oper, fecha_liq=fecha_liq, descripcion=descripcion,
            referencia=referencia, cargos=cargos, abonos=abonos,
            saldo_operacion=saldo_oper, saldo_liquidacion=saldo_liq
        )

    def extract_cell_with_filter(self, x0, y0, x1, y1, limit_y, page=None) -> str:
        """
        Extract text from cell with Y-gap detection to exclude notification boxes.
        
        Gap Detection Logic:
        - Normal transaction line spacing: ~11-12px
        - Notification box gaps: typically 25-40px
        - Threshold: 20px (conservative, won't affect multi-line descriptions)
        """
        # 动态检测footer边界（通用逻辑）
        footer_limit_y = limit_y  # 默认使用传入的limit_y
        if page is not None:
            footer_limit_y = min(limit_y, self.find_footer_limit(page))
        
        # Collect candidate words with Y-coordinate filtering
        candidates = []
        for word in self.purged_words:
            wx0, wy0, wx1, wy1, text = word[:5]
            if wy0 > limit_y: continue
            # 通用Footer过滤：排除Y坐标进入footer区域的文本
            if wy0 >= footer_limit_y: continue
            if wy0 < y0 - 2 or wy0 > y1: continue
            if wx0 < x0 - 3 or wx0 > x1 + 3: continue
            if self.is_header_noise(text): continue
            candidates.append((wy0, text))
        
        # Sort by Y coordinate to detect gaps
        candidates.sort(key=lambda x: x[0])
        
        # Apply gap detection to stop at notification boxes
        result_parts = []
        GAP_THRESHOLD = 20.0  # px - significantly larger than normal line spacing (~12px)
        
        for i, (wy0, text) in enumerate(candidates):
            # Check gap from previous line
            if i > 0:
                previous_y = candidates[i-1][0]
                gap = wy0 - previous_y
                
                # If gap exceeds threshold, stop here (likely notification box or footer)
                if gap > GAP_THRESHOLD:
                    print(f"    [GAP DETECTION] Stopped at y={wy0:.1f} (gap={gap:.1f}px from y={previous_y:.1f})")
                    break
            
            result_parts.append(text)
        
        return " ".join(result_parts).strip()

    def build_row_slices(self, header_top_y, limit_y) -> List[RowSlice]:
        # Using strict 200px limit for simplicity
        DATE_MAX_X = 200.0 
        
        # STEP 1: 扫描所有referencia行的Y坐标（修复问题2、3、4：排除referencia中的日期）
        ref_line_y_positions = []
        for word in self.purged_words:
            wx0, wy0, wx1, wy1, text = word[:5]
            # 检测到"******"后跟数字（referencia的典型pattern）
            if re.search(r'\*{5,}\d', text):
                ref_line_y_positions.append(wy0)
        
        # STEP 2: 提取日期，但排除referencia行
        date_entries = []
        for word in self.purged_words:
            x0, y0, x1, y1, text = word[:5]
            if x0 > DATE_MAX_X: continue
            if y0 < header_top_y - 10: continue
            if y0 > limit_y: continue
            
            # 检查是否在referencia行（容差3px）
            is_ref_line = any(abs(y0 - ref_y) < 3 for ref_y in ref_line_y_positions)
            
            # 只有不在referencia行的日期才添加
            if not is_ref_line and self.DATE_PATTERN.match(text.strip()):
                date_entries.append({'text': text.strip(), 'y0': y0, 'y1': y1, 'x0': x0})
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
            slices.append(RowSlice(index=i, y_top=y_top, y_bottom=y_bottom, date_text=d['text'], date_y1=date_y1))
        return slices

    # ==================== ENGINE RUNNERS ====================

    def run_engine_type_a(self, doc):
        """Engine A: Based on V82 (Coherence + Smart Stop + Fuse)"""
        print("  [ENGINE A] Starting V82 Logic...")
        for page_num in range(len(doc)):
            page = doc[page_num]
            page_text = page.get_text()
            human_page = page_num + 1
            
            if self.global_stop_fuse:
                print(f"  Page {human_page}: [IGNORED] Fuse Blown")
                continue
            
            # Start Trigger
            is_start = self.check_start_trigger(page_text)
            is_wakeup = (not self.is_recording and self.check_page_has_headers(page))
            
            if is_start or is_wakeup:
                self.is_recording = True
                if not self.master_grid: 
                    self.master_grid = self.build_master_grid(page, human_page)
                    print(f"  [V84虚拟GRID已锁定] {self.master_grid.vertical_lines}")
                print(f"  [DEBUG] Using grid lines: {self.master_grid.vertical_lines}")
                
                # Hybrid Start
                header_bottom = self.find_continuation_header_bottom_engine_a(page)
                data_start, data_end = self.scan_page_limits_engine_a(page)
                
                scan_start_y = 150
                if header_bottom: scan_start_y = header_bottom
                elif data_start: scan_start_y = data_start - 5
                
                # Smart Stop
                limit_y = page.rect.height * 0.98
                if data_end:
                    stop_y, found_stop = self.find_smart_stop_y_engine_a(page, data_end)
                    if found_stop: limit_y = self.calculate_effective_limit(page, stop_y)
                
                self.extract_page_type_a(page, human_page, self.master_grid, scan_start_y, limit_y, is_start_page=is_start)
                
                # Fuse Check
                if data_end:
                    stop_y, found_stop = self.find_smart_stop_y_engine_a(page, data_end)
                    if found_stop:
                        self.is_recording = False
                        self.global_stop_fuse = True
                        print(f"  [STOP] Fuse Blown on Page {human_page}")
                continue
            
            if self.is_recording:
                # Cont Page
                header_bottom = self.find_continuation_header_bottom_engine_a(page)
                data_start, data_end = self.scan_page_limits_engine_a(page)
                scan_start_y = header_bottom if header_bottom else (data_start - 5 if data_start else 150)
                
                limit_y = page.rect.height * 0.98
                if data_end:
                    stop_y, found_stop = self.find_smart_stop_y_engine_a(page, data_end)
                    if found_stop: limit_y = self.calculate_effective_limit(page, stop_y)
                
                self.extract_page_type_a(page, human_page, self.master_grid, scan_start_y, limit_y, is_start_page=False)
                
                if data_end:
                    stop_y, found_stop = self.find_smart_stop_y_engine_a(page, data_end)
                    if found_stop:
                        self.is_recording = False
                        self.global_stop_fuse = True
                        print(f"  [STOP] Fuse Blown on Page {human_page}")

    def extract_page_type_a(self, page, page_num, grid, start_y, limit_y, is_start_page):
        self.purged_words = self.purge_pollution_zone(page, grid)
        self.limit_y_context = limit_y
        
        # Overhead Scan
        if not is_start_page:
            first_date = self.find_date_beacon(self.purged_words, start_y, limit_y)
            if first_date:
                desc, _ = self.zero_gap_scan_type_a(page, grid, first_date, page_num)
                if desc and self.all_transactions:
                    # 合并跨页描述
                    self.all_transactions[-1]['descripcion'] += " " + desc
                    
                    # 重新执行referencia分离（修复问题1&5：跨页时referencia未提取）
                    last_tx = self.all_transactions[-1]
                    if re.search(r'\*{4,}\d+', last_tx['descripcion']):
                        match = re.search(r'\*{4,}\d+', last_tx['descripcion'])
                        split_pos = match.start()
                        last_tx['referencia'] = last_tx['descripcion'][split_pos:].strip()
                        last_tx['descripcion'] = last_tx['descripcion'][:split_pos].strip()
        
        slices = self.build_row_slices(start_y, limit_y)
        for i, sl in enumerate(slices):
            sl.page_num = page_num
            tx = self.extract_row_type_a(sl, grid, page)
            self.all_transactions.append(asdict(tx))
        print(f"  Page {page_num}: Extracted {len(slices)} rows (Type A)")

    def run_engine_type_b(self, doc):
        """Engine B: Based on V72 (Strict Grid + Simple Stop) - NO FUSE"""
        print("  [ENGINE B] Starting V72 Logic...")
        for page_num in range(len(doc)):
            page = doc[page_num]
            page_text = page.get_text()
            human_page = page_num + 1
            
            # Classic V72 Logic: Check start trigger
            if self.check_start_trigger(page_text):
                self.is_recording = True
                self.master_grid = self.build_master_grid(page, human_page)
                
                has_stop = self.check_stop_trigger(page_text)
                stop_y = self.find_stop_trigger_y(page) if has_stop else None
                limit_y = self.calculate_effective_limit(page, stop_y)
                
                start_y = self.master_grid.header_row_y + 10
                self.extract_page_type_b(page, human_page, self.master_grid, start_y, limit_y, is_start_page=True)
                
                if has_stop: self.is_recording = False
                continue
            
            if self.is_recording:
                has_stop = self.check_stop_trigger(page_text)
                stop_y = self.find_stop_trigger_y(page) if has_stop else None
                limit_y = self.calculate_effective_limit(page, stop_y)
                
                self.extract_page_type_b(page, human_page, self.master_grid, 130, limit_y, is_start_page=False)
                
                if has_stop: self.is_recording = False

    def extract_page_type_b(self, page, page_num, grid, start_y, limit_y, is_start_page):
        self.purged_words = self.purge_pollution_zone(page, grid)
        self.limit_y_context = limit_y
        self.grid_lines_per_page[page_num] = grid.vertical_lines
        
        if not is_start_page:
            first_date = self.find_date_beacon(self.purged_words, start_y, limit_y)
            if first_date:
                desc, _ = self.full_overhead_scan_type_b(page, grid, first_date, page_num)
                if desc and self.all_transactions:
                    self.all_transactions[-1]['descripcion'] += " " + desc
        
        slices = self.build_row_slices(start_y, limit_y)
        for i, sl in enumerate(slices):
            is_first = (i==0 and is_start_page)
            tx = self.extract_row_type_b(sl, grid, page_num, is_first)
            self.all_transactions.append(asdict(tx))
        print(f"  Page {page_num}: Extracted {len(slices)} rows (Type B)")

    # ==================== MAIN EXECUTION ====================

    def extract_document(self, pdf_path):
        """V84 TypeA专用提取方法"""
        doc = fitz.open(pdf_path)
        self.original_source_path = pdf_path
        self.page_width = doc[0].rect.width
        stem = Path(pdf_path).stem
        num_pages = len(doc)
        
        print(f"\n{'='*60}\nFinal Grid Extractor V84 - TypeA Engine\n{'='*60}")
        print(f"Document: {stem}")
        print(f"Pages: {num_pages}")
        
        # V84固定处理TypeA文档
        self.doc_type = "A"
        
        # 直接调用TypeA引擎
        self.run_engine_type_a(doc)
        
        # 输出路径
        output_base = Path(r"D:\GEMINI_PDF_TO_JSON_BBVA\output\20260112BBVA_GEMINI_验证结果")
        output_folder = output_base / f"{stem}_TypeA"
        output_folder.mkdir(parents=True, exist_ok=True)
        output_path = output_folder / f"{stem}_v84_extracted.json"
        
        # 调试可视化（仅TypeA）
        if self.DEBUG_VISUAL:
            self.generate_debug_centroids_image(doc, output_path)
        
        # Grid可视化（与TypeB保持一致）
        try:
            from final_grid_visualizer_v37 import FinalGridVisualizerV37
            visualizer = FinalGridVisualizerV37()
            visualizer.process_document(pdf_path, str(output_folder), forced_type="A")
            print(f"  [GRID] Saved grid visualizations to {output_folder}")
        except Exception as e:
            print(f"  [GRID WARNING] Failed to generate grid visualization: {e}")
        
        doc.close()
        
        # 统一输出格式：所有交易放到page 0中
        final_pages = [{
            "page": 0,
            "rows": [
                {k: v for k, v in tx.items() if not k.startswith('_')}
                for tx in self.all_transactions
            ]
        }]
        
        # 构建JSON结果
        final_json = {
            "source_file": stem,
            "document_type": "A",
            "total_pages": num_pages,
            "total_rows": len(self.all_transactions),
            "sessions": self.session_count,
            "pages": final_pages
        }
        
        # 保存JSON
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(final_json, f, ensure_ascii=False, indent=2)
        
        print(f"\n[OK] Extracted {len(self.all_transactions)} transactions. JSON: {output_path}")
        return final_json, str(output_path)

    # ... (Visualization methods kept for compatibility but not core logic) ...
    def generate_debug_centroids_image(self, doc, output_path):
        if not self.cell_boxes_per_page: return
        for page_num, boxes in self.cell_boxes_per_page.items():
            if page_num > len(doc): continue
            page = doc[page_num - 1]
            page_width = page.rect.width
            shape = page.new_shape()
            
            # 1. 画红色横线(行分隔线,位于每行垂直中央 - V82风格)
            # CRITICAL: 只为数值列画红线,确保每行只有一条穿过数值y轴中心的红线
            drawn_y_lines = set()  # 避免重复画线
            for box in boxes:
                # 只为数值列画红线,跳过日期列和描述列
                if box.get('type') == 'num' and 'row_center_y' in box:
                    y_line = box['row_center_y']
                    # 四舍五入到0.5px精度,避免浮点数导致的重复
                    y_line = round(y_line * 2) / 2
                    if y_line not in drawn_y_lines:
                        shape.draw_line(fitz.Point(0, y_line), fitz.Point(page_width, y_line))
                        shape.finish(color=(1, 0, 0), width=0.5)  # 红色线
                        drawn_y_lines.add(y_line)
            
            
            # 2. 画灰色矩形框（单元格边界）
            for box in boxes:
                shape.draw_rect(fitz.Rect(box['x0'], box['y0'], box['x1'], box['y1']))
                shape.finish(color=(0.5, 0.5, 0.5), fill=None, width=0.5)
                
                # 3. 画绿色质心点（仅用于数值列）
                if box.get('type') == 'num' and box.get('centroids'):
                    centroids = box['centroids']
                    for centroid in centroids:
                        cx, cy = centroid['x'], centroid['y']
                        # 画小圆点
                        shape.draw_circle(fitz.Point(cx, cy), 2)
                        shape.finish(color=(0, 1, 0), fill=(0, 1, 0))  # 绿色填充点
            
            shape.commit()
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img_path = output_path.parent / f"debug_centroids_page{page_num}.png"
            pix.save(str(img_path))

    def generate_referencia_debug_image(self, doc, output_path):
        if not self.referencia_debug_per_page: return
        for page_num, words in self.referencia_debug_per_page.items():
            if page_num > len(doc): continue
            page = doc[page_num - 1]
            shape = page.new_shape()
            for word in words:
                shape.draw_rect(fitz.Rect(word['x0'], word['y0'], word['x1'], word['y1']))
                shape.finish(color=(0, 0, 0.8), fill=(0.3, 0.3, 1), fill_opacity=0.3, width=1.5)
            shape.commit()
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img_path = output_path.parent / f"debug_ref_fill_page{page_num}.png"
            pix.save(str(img_path))

def main():
    if len(sys.argv) < 2:
        print("Usage: python final_grid_extractor_v84.py <pdf_path>")
        sys.exit(1)
    try:
        FinalGridExtractorV84().extract_document(sys.argv[1])
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
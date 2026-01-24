"""
增强的data_extractor方法 - 提取BBVA额外业务字段

这些方法将被添加到DataExtractor类中
"""
from typing import Any, Dict, List, Optional
from decimal import Decimal
import re


def _extract_total_movimientos(
    self,
    ocr_data: Dict[str, Any],
    parsed_tables: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    提取Total de Movimientos信息。
    
    从文档中查找:
    - TOTAL IMPORTE CARGOS
    - TOTAL MOVIMIENTOS CARGOS  
    - TOTAL IMPORTE ABONOS
    - TOTAL MOVIMIENTOS ABONOS
    
    Returns:
        包含总计信息的字典，如果未找到返回None
    """
    total_mov = {}
    
    # 从OCR数据中搜索Total de Movimientos相关文本
    for page_idx, page in enumerate(ocr_data.get("pages", [])):
        text_content = page.get("text", "")
        
        # 查找TOTAL IMPORTE CARGOS和数量
        cargos_importe_match = re.search(
            r"TOTAL\s+IMPORTE\s+CARGOS\s*[:\s]*([0-9,]+\.?\d*)",
            text_content,
            re.IGNORECASE
        )
        if cargos_importe_match:
            total_mov["total_importe_cargos"] = cargos_importe_match.group(1)
        
        cargos_count_match = re.search(
            r"TOTAL\s+MOVIMIENTOS\s+CARGOS\s*[:\s]*(\d+)",
            text_content,
            re.IGNORECASE
        )
        if cargos_count_match:
            total_mov["total_movimientos_cargos"] = int(cargos_count_match.group(1))
        
        # 查找TOTAL IMPORTE ABONOS和数量
        abonos_importe_match = re.search(
            r"TOTAL\s+IMPORTE\s+ABONOS\s*[:\s]*([0-9,]+\.?\d*)",
            text_content,
            re.IGNORECASE
        )
        if abonos_importe_match:
            total_mov["total_importe_abonos"] = abonos_importe_match.group(1)
        
        abonos_count_match = re.search(
            r"TOTAL\s+MOVIMIENTOS\s+ABONOS\s*[:\s]*(\d+)",
            text_content,
            re.IGNORECASE
        )
        if abonos_count_match:
            total_mov["total_movimientos_abonos"] = int(abonos_count_match.group(1))
    
    return total_mov if total_mov else None


def _extract_apartados_vigentes(
    self,
    parsed_tables: List[Dict[str, Any]]
) -> Optional[List[Dict[str, Any]]]:
    """
    提取Estado de cuenta de Apartados Vigentes。
    
    查找标题包含"Apartados Vigentes"的表格。
    
    Returns:
        apartados列表，如果未找到返回None
    """
    apartados = []
    
    for table in parsed_tables:
        table_title = str(table.get("title", "")).lower()
        
        if "apartados" in table_title and "vigentes" in table_title:
            # 找到了apartados表格
            data_rows = table.get("data", [])
            
            for row in data_rows:
                # 提取每个apartado的信息
                apartado = {}
                
                # 尝试提取常见字段
                if "folio" in row:
                    apartado["folio"] = row["folio"]
                if "nombre" in row or "nombre_apartado" in row:
                    apartado["nombre_apartado"] = row.get("nombre") or row.get("nombre_apartado")
                if "importe" in row or "importe_apartado" in row:
                    apartado["importe_apartado"] = str(row.get("importe") or row.get("importe_apartado"))
                if "total" in row or "importe_total" in row:
                    apartado["importe_total"] = str(row.get("total") or row.get("importe_total"))
                
                if apartado:  # 只添加非空的apartado
                    apartados.append(apartado)
    
    return apartados if apartados else None


def _extract_cuadro_resumen(
    self,
    parsed_tables: List[Dict[str, Any]]
) -> Optional[List[Dict[str, Any]]]:
    """
    提取Cuadro resumen y gráfico de movimientos del período。
    
    包含:
    - Concepto
    - Cantidad
    - Porcentaje
    - Columna
    
    Returns:
        cuadro resumen列表，如果未找到返回None
    """
    cuadro = []
    
    for table in parsed_tables:
        table_title = str(table.get("title", "")).lower()
        
        if "cuadro" in table_title and "resumen" in table_title:
            # 找到了cuadro resumen表格
            data_rows = table.get("data", [])
            
            for row in data_rows:
                item = {}
                
                # 提取字段
                if "concepto" in row:
                    item["concepto"] = row["concepto"]
                if "cantidad" in row:
                    item["cantidad"] = str(row["cantidad"])
                if "porcentaje" in row or "percentage" in row:
                    item["porcentaje"] = row.get("porcentaje") or row.get("percentage")
                if "columna" in row or "column" in row:
                    item["columna"] = row.get("columna") or row.get("column")
                
                if item:
                    cuadro.append(item)
    
    return cuadro if cuadro else None

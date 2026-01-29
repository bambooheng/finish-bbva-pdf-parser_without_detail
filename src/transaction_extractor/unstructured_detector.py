"""
Unstructured PDF Detector

独立模块，用于检测PDF是否为非结构化文档（图片式PDF）。
该模块与现有的Type A/B检测逻辑完全独立。

检测策略：通过计算PDF的文本提取密度来判断是否为图片式PDF。
如果平均每页提取的字符数低于阈值，则判定为非结构化文档。
"""

import fitz  # PyMuPDF


def is_unstructured_pdf(pdf_path: str, threshold: int = 50) -> bool:
    """
    检测PDF是否为非结构化文档（图片式PDF）
    
    参数:
        pdf_path (str): PDF文件的完整路径
        threshold (int): 文本密度阈值（字符数/页），默认50
        
    返回:
        bool: True表示非结构化文档，False表示结构化文档
        
    检测逻辑:
        1. 打开PDF文件
        2. 遍历所有页面，提取文本内容
        3. 计算总字符数和页数
        4. 计算平均每页字符数 = 总字符数 / 总页数
        5. 如果平均字符数 < 阈值，判定为图片式PDF
    """
    try:
        doc = fitz.open(pdf_path)
        total_chars = 0
        total_pages = len(doc)
        
        # 如果PDF为空，判定为非结构化
        if total_pages == 0:
            doc.close()
            return True
        
        # 遍历所有页面，统计文本字符数
        for page_num in range(total_pages):
            page = doc[page_num]
            text = page.get_text("text")
            
            # 统计非空白字符数（排除空格、换行等）
            chars_in_page = len([c for c in text if not c.isspace()])
            total_chars += chars_in_page
        
        doc.close()
        
        # 计算平均每页字符数
        avg_chars_per_page = total_chars / total_pages
        
        # 如果平均字符数低于阈值，判定为非结构化文档
        is_unstructured = avg_chars_per_page < threshold
        
        return is_unstructured
        
    except Exception as e:
        # 如果发生错误，保守起见返回False（不阻止处理）
        print(f"[UNSTRUCTURED DETECTOR ERROR] {e}")
        return False


def get_text_density_info(pdf_path: str) -> dict:
    """
    获取PDF的文本密度详细信息（用于调试和分析）
    
    参数:
        pdf_path (str): PDF文件的完整路径
        
    返回:
        dict: 包含文本密度统计信息的字典
            - total_pages: 总页数
            - total_chars: 总字符数
            - avg_chars_per_page: 平均每页字符数
            - is_unstructured: 是否为非结构化文档
    """
    try:
        doc = fitz.open(pdf_path)
        total_chars = 0
        total_pages = len(doc)
        
        for page_num in range(total_pages):
            page = doc[page_num]
            text = page.get_text("text")
            chars_in_page = len([c for c in text if not c.isspace()])
            total_chars += chars_in_page
        
        doc.close()
        
        avg_chars_per_page = total_chars / total_pages if total_pages > 0 else 0
        
        return {
            "total_pages": total_pages,
            "total_chars": total_chars,
            "avg_chars_per_page": round(avg_chars_per_page, 2),
            "is_unstructured": avg_chars_per_page < 50
        }
        
    except Exception as e:
        return {
            "error": str(e),
            "is_unstructured": False
        }

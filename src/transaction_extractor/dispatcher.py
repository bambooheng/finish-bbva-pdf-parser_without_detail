"""
Transaction Extractor Dispatcher

调度器模块,负责检测PDF类型并路由到对应的提取引擎。
- Type A检测 -> 使用TypeAExtractor (基于V84)
- Type B检测 -> 使用TypeBExtractor (基于V72)
"""

import fitz
from pathlib import Path
import sys
import os
from contextlib import contextmanager
from typing import Dict, Any, Optional, Tuple

# 导入子模块
from .unstructured_detector import is_unstructured_pdf
from .type_a_extractor import FinalGridExtractorV84
from .type_b_extractor import FinalGridExtractorV72


@contextmanager
def suppress_stdout():
    """Context manager to suppress standard output."""
    with open(os.devnull, "w") as devnull:
        old_stdout = sys.stdout
        sys.stdout = devnull
        try:
            yield
        finally:
            sys.stdout = old_stdout


class TransactionExtractorDispatcher:
    """交易明细提取调度器 - 自动检测类型并路由到对应引擎"""
    
    def __init__(self):
        self.doc_type = None
    
    def _detect_document_type(self, doc) -> str:
        """
        文档类型检测逻辑:
        
        Type A:
        - REFERENCIA 列不包含以 "Referencia" 开头的内容
        - 可能有 "******" 模式（可选提示）
        - REFERENCIA 列可能为空或包含 DESCRIPCION 的延伸内容
        
        Type B:
        - REFERENCIA 列(X: 280-380)包含以 "Referencia" 开头的内容
        - Description和Reference明确分离
        - 示例: "Referencia 8129595110"
        """
        try:
            check_limit = min(3, len(doc))
            
            # 计分器
            type_b_signals = 0  # Type B明确信号
            type_a_hints = 0    # Type A可选提示
            
            for page_idx in range(check_limit):
                page = doc[page_idx]
                words = page.get_text("words")
                
                # 扫描Type B特征: "Referencia"前缀在列中
                for w in words:
                    x0 = w[0]
                    text = w[4]
                    if 280 < x0 < 380:
                        if text.lower().startswith("referencia"):
                            type_b_signals += 1
                            print(f"  [DISPATCHER] Page {page_idx+1}: 发现'Referencia'在列中 (x={x0:.1f}) -> Type B信号")
                
                # 扫描Type A提示(可选): "******"模式
                text_content = page.get_text("text")
                if "******" in text_content:
                    type_a_hints += 1
                    print(f"  [DISPATCHER] Page {page_idx+1}: 发现'******'模式 -> Type A提示")
            
            # 决策矩阵
            if type_b_signals > 0:
                print(f"  [DISPATCHER] 决策 -> Type B: {type_b_signals}个信号(已确认)")
                return "B"
            else:
                print(f"  [DISPATCHER] 决策 -> Type A (无Type B信号, Type A提示: {type_a_hints})")
                return "A"
                
        except Exception as e:
            print(f"  [DISPATCHER ERROR] {e}, 默认使用Type A")
            return "A"
    
    def extract(
        self, 
        pdf_path: str, 
        output_dir: Optional[str] = None,
        verbose: bool = True
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        提取PDF中的交易明细数据
        
        Args:
            pdf_path: PDF文件路径
            output_dir: 输出目录(可选,如果提供则保存JSON文件)
            verbose: 是否输出详细日志
            
        Returns:
            (提取结果字典, 输出文件路径) 或 (None, None)如果处理失败
        """
        doc = fitz.open(pdf_path)
        stem = Path(pdf_path).stem
        num_pages = len(doc)
        
        if verbose:
            print(f"\n{'='*70}\n交易明细提取调度器\n{'='*70}\n文档: {stem}\n页数: {num_pages}")
        
        # 0. 预过滤: 检查非结构化PDF(图片式)
        if is_unstructured_pdf(pdf_path):
            if verbose:
                print(f"  [DISPATCHER] 检测到文档为非结构化文档，暂不支持该类型文档处理")
            doc.close()
            return None, None
        
        # 1. 检测类型
        self.doc_type = self._detect_document_type(doc)
        doc.close()
        
        # 2. 调度到对应引擎
        if self.doc_type == "B":
            if verbose:
                print(f"  [ROUTING] Type B检测 -> 委托给TypeBExtractor (V72引擎)")
                print(f"  [STATUS] 处理{num_pages}页... (详细输出已抑制)")
                print(f"{'-'*70}")
            
            try:
                if not verbose:
                    with suppress_stdout():
                        extractor = FinalGridExtractorV72()
                        result = extractor.extract_document(pdf_path)
                else:
                    extractor = FinalGridExtractorV72()
                    result = extractor.extract_document(pdf_path)
                    
                if verbose:
                    print(f"  [COMPLETED] V72提取完成")
                    if result and result[0] and 'total_rows' in result[0]:
                        print(f"  [RESULT] 提取了{result[0]['total_rows']}条交易记录")
                
                return result
            except Exception as e:
                print(f"  [ERROR] V72引擎失败: {e}")
                import traceback
                traceback.print_exc()
                return None, None
        
        else:  # Type A
            if verbose:
                print(f"  [ROUTING] Type A检测 -> 委托给TypeAExtractor (V84引擎)")
                print(f"  [STATUS] 处理{num_pages}页... (详细输出已抑制)")
                print(f"{'-'*70}")
            
            try:
                if not verbose:
                    with suppress_stdout():
                        extractor = FinalGridExtractorV84()
                        result = extractor.extract_document(pdf_path)
                else:
                    extractor = FinalGridExtractorV84()
                    result = extractor.extract_document(pdf_path)
                    
                if verbose:
                    print(f"  [COMPLETED] V84提取完成")
                    if result and result[0] and 'total_rows' in result[0]:
                        print(f"  [RESULT] 提取了{result[0]['total_rows']}条交易记录")
                
                return result
            except Exception as e:
                print(f"  [ERROR] V84引擎失败: {e}")
                import traceback
                traceback.print_exc()
                return None, None

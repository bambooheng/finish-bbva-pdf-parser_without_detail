"""
对比分析模块：生成解析结果与原始文件的全面对比报告。
"""
import json
import sys
import io
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import Counter
import difflib

# Handle numpy types for JSON serialization
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# Fix encoding for Windows console
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

from src.validation.pdf_comparator import PDFComparator


class ComparisonAnalyzer:
    """对比分析器：生成全面的对比报告"""
    
    def __init__(self):
        self.pdf_comparator = PDFComparator() if PYMUPDF_AVAILABLE else None
    
    def generate_comparison_report(
        self,
        original_pdf_path: str,
        structured_json_path: str,
        reconstructed_pdf_path: Optional[str] = None,
        validation_report_path: Optional[str] = None,
        output_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        生成全面的对比分析报告。
        
        Args:
            original_pdf_path: 原始PDF路径（必需）
            structured_json_path: 结构化JSON路径（必需）
            reconstructed_pdf_path: 重建的PDF路径（可选）
            validation_report_path: 验证报告路径（可选）
            output_dir: 输出目录（可选）
            
        Returns:
            对比报告字典
        """
        report = {
            "original_pdf": str(original_pdf_path),
            "structured_json": str(structured_json_path),
            "reconstructed_pdf": str(reconstructed_pdf_path) if reconstructed_pdf_path else None,
            "validation_report": str(validation_report_path) if validation_report_path else None,
        }
        
        print("\n" + "="*80)
        print("生成对比分析报告")
        print("="*80)
        
        # 1. 文本对比
        print("\n[1/5] 文本内容对比分析...")
        print("-" * 80)
        text_comparison = self._compare_text_content(original_pdf_path, structured_json_path)
        if text_comparison:
            print(f"整体文本覆盖率: {text_comparison.get('overall_coverage', 0):.2f}%")
            print(f"平均页面相似度: {text_comparison.get('avg_similarity', 0):.2f}%")
            report["text_comparison"] = text_comparison
        else:
            print("  警告: 无法进行文本对比")
        
        # 2. 交易数据对比
        print("\n\n[2/5] 交易数据对比分析...")
        print("-" * 80)
        transactions_analysis = self._analyze_transactions(structured_json_path)
        if transactions_analysis:
            print(f"总交易数: {transactions_analysis['total_transactions']}")
            print(f"包含日期: {transactions_analysis['with_date']} ({transactions_analysis['date_coverage']:.2f}%)")
            print(f"包含金额: {transactions_analysis['with_amount']} ({transactions_analysis['amount_coverage']:.2f}%)")
            print(f"包含余额: {transactions_analysis['with_balance']} ({transactions_analysis['balance_coverage']:.2f}%)")
            print(f"包含描述: {transactions_analysis['with_description']} ({transactions_analysis['description_coverage']:.2f}%)")
            report["transactions_analysis"] = transactions_analysis
        else:
            print("  警告: 无法分析交易数据")
        
        # 3. 布局元素分析
        print("\n\n[3/5] 布局元素分析...")
        print("-" * 80)
        layout_analysis = self._analyze_layout_elements(structured_json_path)
        if layout_analysis:
            print(f"总元素数: {layout_analysis['total_elements']}")
            print(f"元素类型分布:")
            for elem_type, count in layout_analysis['element_types'].items():
                print(f"  {elem_type}: {count}")
            print(f"包含边界框的元素: {layout_analysis['elements_with_bbox']} ({layout_analysis['bbox_coverage']:.2f}%)")
            report["layout_analysis"] = layout_analysis
        else:
            print("  警告: 无法分析布局元素")
        
        # 4. 像素级对比（如果有重建的PDF）
        if reconstructed_pdf_path and Path(reconstructed_pdf_path).exists():
            print("\n\n[4/5] PDF像素级对比分析...")
            print("-" * 80)
            pixel_comparison = self._compare_pdfs_pixel_level(original_pdf_path, reconstructed_pdf_path)
            if pixel_comparison and "error" not in pixel_comparison:
                print(f"总体像素准确度: {pixel_comparison.get('pixel_accuracy', 0):.2f}%")
                print(f"总页数: {pixel_comparison.get('total_pages', 0)}")
                report["pixel_comparison"] = pixel_comparison
            else:
                print(f"  警告: 无法进行像素级对比")
                report["pixel_comparison"] = pixel_comparison or {"error": "Comparison failed"}
        else:
            print("\n\n[4/5] PDF像素级对比分析...")
            print("-" * 80)
            print("  跳过: 未找到重建的PDF文件")
            report["pixel_comparison"] = {"skipped": True, "reason": "Reconstructed PDF not found"}
        
        # 5. 验证报告分析
        if validation_report_path and Path(validation_report_path).exists():
            print("\n\n[5/5] 验证报告分析...")
            print("-" * 80)
            validation_data = self._analyze_validation_report(validation_report_path)
            if validation_data:
                print(f"像素准确度: {validation_data.get('pixel_accuracy', 0):.2f}%")
                print(f"语义准确度: {validation_data.get('semantic_accuracy', 0):.2f}%")
                print(f"差异数量: {len(validation_data.get('discrepancies', []))}")
                report["validation_report"] = validation_data
        else:
            print("\n\n[5/5] 验证报告分析...")
            print("-" * 80)
            print("  跳过: 未找到验证报告文件")
            report["validation_report"] = {"skipped": True}
        
        # 生成总结
        print("\n\n" + "=" * 80)
        print("对比分析总结")
        print("=" * 80)
        summary_items = []
        
        if report.get("text_comparison") and "overall_coverage" in report["text_comparison"]:
            coverage = report["text_comparison"]["overall_coverage"]
            summary_items.append(f"文本覆盖率: {coverage:.2f}%")
        
        if report.get("transactions_analysis"):
            trans_total = report["transactions_analysis"]["total_transactions"]
            summary_items.append(f"提取交易数: {trans_total}")
            balance_cov = report["transactions_analysis"]["balance_coverage"]
            summary_items.append(f"余额字段完整性: {balance_cov:.2f}%")
        
        if report.get("pixel_comparison") and "pixel_accuracy" in report["pixel_comparison"]:
            pixel_acc = report["pixel_comparison"]["pixel_accuracy"]
            summary_items.append(f"像素准确度: {pixel_acc:.2f}%")
        
        if report.get("validation_report") and "semantic_accuracy" in report["validation_report"]:
            semantic_acc = report["validation_report"]["semantic_accuracy"]
            summary_items.append(f"语义准确度: {semantic_acc:.2f}%")
        
        for item in summary_items:
            print(f"  {item}")
        
        # 保存报告
        if output_dir:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            
            # 保存JSON报告
            json_report_path = output_path / "comparison_report.json"
            try:
                with open(json_report_path, 'w', encoding='utf-8') as f:
                    json.dump(report, f, ensure_ascii=False, indent=2, default=self._json_serializer)
                print(f"\n详细对比报告已保存至: {json_report_path}")
            except Exception as e:
                print(f"Warning: Failed to save JSON report: {e}")
                import traceback
                traceback.print_exc()
            
            # 保存Markdown报告
            md_report_path = output_path / "comparison_report.md"
            try:
                self._save_markdown_report(report, md_report_path)
                if md_report_path.exists():
                    print(f"Markdown报告已保存至: {md_report_path}")
                else:
                    print(f"Warning: Markdown报告保存失败，文件未创建")
            except Exception as e:
                print(f"Warning: Failed to save Markdown report: {e}")
                import traceback
                traceback.print_exc()
        
        print("=" * 80)
        return report
    
    def _compare_text_content(self, original_pdf: str, structured_json: str) -> Optional[Dict[str, Any]]:
        """对比文本内容"""
        try:
            original_texts = self._extract_text_from_pdf(original_pdf)
            extracted_texts = self._extract_text_from_structured_data(structured_json)
            
            if not original_texts or not extracted_texts:
                return None
            
            page_comparisons = []
            total_chars_original = 0
            total_chars_extracted = 0
            total_matching_chars = 0
            
            for page_num in sorted(set(list(original_texts.keys()) + list(extracted_texts.keys()))):
                orig_text = original_texts.get(page_num, "")
                extr_text = extracted_texts.get(page_num, "")
                
                orig_normalized = self._normalize_text(orig_text)
                extr_normalized = self._normalize_text(extr_text)
                
                # 计算相似度
                similarity = difflib.SequenceMatcher(None, orig_normalized, extr_normalized).ratio() * 100
                
                # 计算字符覆盖率
                orig_chars = len(orig_normalized)
                extr_chars = len(extr_normalized)
                matching_chars = sum(1 for c in orig_normalized if c in extr_normalized)
                
                coverage = (matching_chars / orig_chars * 100) if orig_chars > 0 else 0
                
                total_chars_original += orig_chars
                total_chars_extracted += extr_chars
                total_matching_chars += matching_chars
                
                page_comparisons.append({
                    "page": page_num,
                    "original_chars": orig_chars,
                    "extracted_chars": extr_chars,
                    "similarity": similarity,
                    "coverage": coverage
                })
            
            overall_coverage = (total_matching_chars / total_chars_original * 100) if total_chars_original > 0 else 0
            avg_similarity = sum(p["similarity"] for p in page_comparisons) / len(page_comparisons) if page_comparisons else 0
            
            return {
                "overall_coverage": overall_coverage,
                "avg_similarity": avg_similarity,
                "total_chars_original": total_chars_original,
                "total_chars_extracted": total_chars_extracted,
                "page_comparisons": page_comparisons
            }
        except Exception as e:
            print(f"  错误: {e}")
            return None
    
    def _analyze_transactions(self, structured_json: str) -> Optional[Dict[str, Any]]:
        """分析交易数据"""
        try:
            with open(structured_json, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            transactions = data.get("structured_data", {}).get("account_summary", {}).get("transactions", [])
            
            if not transactions:
                return None
            
            total = len(transactions)
            with_date = sum(1 for t in transactions if t.get("date"))
            with_amount = sum(1 for t in transactions if t.get("amount") is not None)
            with_balance = sum(1 for t in transactions if t.get("balance") is not None)
            with_description = sum(1 for t in transactions if t.get("description"))
            
            return {
                "total_transactions": total,
                "with_date": with_date,
                "date_coverage": (with_date / total * 100) if total > 0 else 0,
                "with_amount": with_amount,
                "amount_coverage": (with_amount / total * 100) if total > 0 else 0,
                "with_balance": with_balance,
                "balance_coverage": (with_balance / total * 100) if total > 0 else 0,
                "with_description": with_description,
                "description_coverage": (with_description / total * 100) if total > 0 else 0,
            }
        except Exception as e:
            print(f"  错误: {e}")
            return None
    
    def _analyze_layout_elements(self, structured_json: str) -> Optional[Dict[str, Any]]:
        """分析布局元素"""
        try:
            with open(structured_json, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            total_elements = 0
            elements_with_bbox = 0
            element_types = Counter()
            
            for page_data in data.get("pages", []):
                for element in page_data.get("layout_elements", []):
                    total_elements += 1
                    elem_type = element.get("type", "unknown")
                    element_types[elem_type] += 1
                    
                    bbox = element.get("bbox")
                    if bbox and isinstance(bbox, dict):
                        if bbox.get("width", 0) > 0 and bbox.get("height", 0) > 0:
                            elements_with_bbox += 1
            
            bbox_coverage = (elements_with_bbox / total_elements * 100) if total_elements > 0 else 0
            
            return {
                "total_elements": total_elements,
                "elements_with_bbox": elements_with_bbox,
                "bbox_coverage": bbox_coverage,
                "element_types": dict(element_types)
            }
        except Exception as e:
            print(f"  错误: {e}")
            return None
    
    def _compare_pdfs_pixel_level(self, original_pdf: str, reconstructed_pdf: str) -> Optional[Dict[str, Any]]:
        """像素级对比"""
        if not self.pdf_comparator:
            return {"error": "PDFComparator not available"}
        
        try:
            result = self.pdf_comparator.compare_pdfs(original_pdf, reconstructed_pdf)
            # Convert numpy types to Python types for JSON serialization
            if isinstance(result, dict):
                if "is_valid" in result:
                    result["is_valid"] = bool(result["is_valid"])
                # Convert any numpy types in nested structures
                result = self._convert_numpy_types(result)
            return result
        except Exception as e:
            return {"error": str(e)}
    
    def _convert_numpy_types(self, obj):
        """递归转换字典/列表中的numpy类型为Python原生类型"""
        if HAS_NUMPY:
            if isinstance(obj, np.bool_):
                return bool(obj)
            elif isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
        
        if isinstance(obj, dict):
            return {k: self._convert_numpy_types(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_numpy_types(item) for item in obj]
        else:
            return obj
    
    def _analyze_validation_report(self, validation_report_path: str) -> Optional[Dict[str, Any]]:
        """分析验证报告"""
        try:
            with open(validation_report_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"  错误: {e}")
            return None
    
    def _extract_text_from_pdf(self, pdf_path: str) -> Dict[int, str]:
        """从PDF提取文本"""
        if not PYMUPDF_AVAILABLE:
            return {}
        
        try:
            doc = fitz.open(str(pdf_path))
            pages_text = {}
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text("text")
                pages_text[page_num + 1] = text
            doc.close()
            return pages_text
        except Exception as e:
            print(f"  错误提取PDF文本: {e}")
            return {}
    
    def _extract_text_from_structured_data(self, json_path: str) -> Dict[int, str]:
        """从结构化数据提取文本"""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            pages_text = {}
            for page_data in data.get("pages", []):
                page_num = page_data.get("page_number", 1)
                text_parts = []
                
                for element in page_data.get("layout_elements", []):
                    if element.get("type") == "text":
                        content = element.get("content", "")
                        if content:
                            text_parts.append(str(content))
                    elif element.get("type") == "table":
                        table_content = element.get("content", {})
                        if isinstance(table_content, dict):
                            rows = table_content.get("rows", [])
                            for row in rows:
                                if isinstance(row, list):
                                    text_parts.append(" | ".join(str(cell) for cell in row))
                                elif isinstance(row, dict):
                                    text_parts.append(" | ".join(str(v) for v in row.values()))
                
                pages_text[page_num] = "\n".join(text_parts)
            return pages_text
        except Exception as e:
            print(f"  错误提取结构化数据文本: {e}")
            return {}
    
    def _normalize_text(self, text: str) -> str:
        """标准化文本"""
        if not text:
            return ""
        lines = text.split('\n')
        normalized_lines = [line.strip() for line in lines if line.strip()]
        return ' '.join(normalized_lines)
    
    def _json_serializer(self, obj):
        """JSON序列化辅助函数，处理numpy类型和其他不可序列化的对象"""
        if HAS_NUMPY:
            if isinstance(obj, (np.integer, np.int64, np.int32)):
                return int(obj)
            elif isinstance(obj, (np.floating, np.float64, np.float32)):
                return float(obj)
            elif isinstance(obj, np.bool_):
                return bool(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
        # Handle other types
        if isinstance(obj, (set, frozenset)):
            return list(obj)
        # Default: convert to string
        return str(obj)
    
    def _save_markdown_report(self, report: Dict[str, Any], output_path: Path):
        """保存Markdown格式的报告"""
        md_content = ["# 解析结果对比分析报告\n"]
        
        # 基本信息
        md_content.append("## 📋 基本信息\n")
        md_content.append(f"- **原始PDF**: {report['original_pdf']}\n")
        md_content.append(f"- **结构化JSON**: {report['structured_json']}\n")
        if report.get('reconstructed_pdf'):
            md_content.append(f"- **重建PDF**: {report['reconstructed_pdf']}\n")
        md_content.append("\n")
        
        # 文本对比
        if report.get("text_comparison"):
            tc = report["text_comparison"]
            md_content.append("## 📄 文本内容对比\n")
            md_content.append(f"- **整体文本覆盖率**: {tc.get('overall_coverage', 0):.2f}%\n")
            md_content.append(f"- **平均页面相似度**: {tc.get('avg_similarity', 0):.2f}%\n")
            md_content.append("\n")
        
        # 交易数据
        if report.get("transactions_analysis"):
            ta = report["transactions_analysis"]
            md_content.append("## 💰 交易数据对比\n")
            md_content.append(f"- **总交易数**: {ta['total_transactions']}\n")
            md_content.append(f"- **日期字段完整性**: {ta['date_coverage']:.2f}%\n")
            md_content.append(f"- **金额字段完整性**: {ta['amount_coverage']:.2f}%\n")
            md_content.append(f"- **余额字段完整性**: {ta['balance_coverage']:.2f}%\n")
            md_content.append(f"- **描述字段完整性**: {ta['description_coverage']:.2f}%\n")
            md_content.append("\n")
        
        # 布局元素
        if report.get("layout_analysis"):
            la = report["layout_analysis"]
            md_content.append("## 🎨 布局元素分析\n")
            md_content.append(f"- **总元素数**: {la['total_elements']}\n")
            md_content.append(f"- **边界框覆盖率**: {la['bbox_coverage']:.2f}%\n")
            md_content.append("\n**元素类型分布**:\n")
            for elem_type, count in la['element_types'].items():
                md_content.append(f"- {elem_type}: {count}\n")
            md_content.append("\n")
        
        # 像素对比
        if report.get("pixel_comparison") and "pixel_accuracy" in report["pixel_comparison"]:
            pc = report["pixel_comparison"]
            md_content.append("## 🖼️ 像素级对比\n")
            md_content.append(f"- **总体像素准确度**: {pc.get('pixel_accuracy', 0):.2f}%\n")
            md_content.append("\n")
        
        # 验证报告
        if report.get("validation_report") and "semantic_accuracy" in report["validation_report"]:
            vr = report["validation_report"]
            md_content.append("## ✅ 验证报告\n")
            md_content.append(f"- **语义准确度**: {vr.get('semantic_accuracy', 0):.2f}%\n")
            md_content.append(f"- **差异数量**: {len(vr.get('discrepancies', []))}\n")
            md_content.append("\n")
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(''.join(md_content))


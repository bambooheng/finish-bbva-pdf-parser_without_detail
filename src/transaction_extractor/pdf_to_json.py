#!/usr/bin/env python
"""
PDF to JSON Converter - 一体化转换器
将任意PDF文件直接转换为结构化JSON，使用Gemini API进行OCR和解析

用法:
    python pdf_to_json.py <pdf_path> [-o output.json]
"""

import sys
import argparse
from pathlib import Path

from config import config
from pdf_converter import PDFConverter
from gemini_client import GeminiClient
from json_generator import JsonGenerator


def print_banner():
    """Print application banner"""
    print("=" * 70)
    print("  PDF to JSON Converter")
    print("  一键将PDF转换为结构化JSON")
    print("=" * 70)
    print()


def convert_pdf_to_json(
    pdf_path: str,
    output_path: str = None,
    include_raw: bool = False,
    save_markdown: bool = False
) -> bool:
    """
    Convert a PDF file to structured JSON
    
    Args:
        pdf_path: Path to input PDF file
        output_path: Path to output JSON file
        include_raw: Whether to include raw markdown in output
        save_markdown: Whether to save intermediate markdown file
        
    Returns:
        True if successful
    """
    try:
        pdf_file = Path(pdf_path)
        if not pdf_file.exists():
            raise FileNotFoundError(f"PDF文件不存在: {pdf_path}")
        
        # Determine output path - use fixed output folder
        if output_path is None:
            output_dir = Path(r"D:\GEMINI_PDF_TO_JSON_BBVA\output")
            output_dir.mkdir(exist_ok=True)
            output_path = str(output_dir / f"{pdf_file.stem}.json")
        
        # Step 0: Document Type Detection and Preprocessing
        doc_type = "TYPE_A"  # Default
        try:
            from pdf_preprocessor import PDFPreprocessor
            import fitz
            
            print(f"[0/4] 文档类型检测与预处理...")
            preprocessor = PDFPreprocessor()
            doc_type_info = preprocessor.detect_document_type(pdf_path)
            doc_type = doc_type_info.doc_type
            
            print(f"      📋 文档类型: {doc_type}")
            print(f"      📊 置信度: {doc_type_info.confidence:.2%}")
            print(f"      📝 模式: {doc_type_info.referencia_pattern}")
            
            # Apply preprocessing
            if doc_type == "TYPE_B":
                print(f"      🔧 Type B: 应用 REFERENCIA 干扰抑制...")
                preprocessed_path, _ = preprocessor.preprocess_for_extraction(pdf_path)
            else:
                print(f"      ✓ Type A: 标准处理流程")
                preprocessed_path = pdf_path
            print()
        except ImportError as e:
            print(f"      (跳过预处理: {e})")
            preprocessed_path = pdf_path
        except Exception as e:
            print(f"      (预处理错误: {e})")
            preprocessed_path = pdf_path
        
        # Step 1: PDF to Markdown
        print(f"[1/4] 将PDF转换为Markdown...")
        pdf_converter = PDFConverter()
        markdown_content = pdf_converter.convert(pdf_path)  # Use original for OCR
        print(f"      Markdown长度: {len(markdown_content):,} 字符")
        
        # Optionally save markdown
        if save_markdown:
            md_path = Path(output_path).with_suffix('.md')
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            print(f"      中间Markdown已保存: {md_path}")
        print()
        
        # Step 2: Markdown to JSON
        print(f"[2/4] 使用Gemini解析为JSON...")
        gemini_client = GeminiClient()
        gemini_result = gemini_client.parse_markdown_to_json(
            markdown_content,
            pdf_file.name
        )
        print()
        
        # Step 2.5: Coordinate-based validation with type awareness
        try:
            from coordinate_validator import CoordinateValidator
            from coordinate_extractor import CoordinateBasedTableExtractor
            import fitz
            
            print(f"[2.5/4] 坐标验证层校正 ({doc_type})...")
            validator = CoordinateValidator()
            doc = fitz.open(pdf_path)
            
            # Extract transactions from gemini_result and validate
            if "content" in gemini_result and "sections" in gemini_result["content"]:
                corrections_total = 0
                for section in gemini_result["content"]["sections"]:
                    data = section.get("data")
                    if isinstance(data, list) and data:
                        # Check if this looks like transaction data
                        if isinstance(data[0], dict) and any(k in data[0] for k in ["CARGOS", "ABONOS", "DESCRIPCIÓN"]):
                            # Validate across all pages (simplified: use first page with table headers)
                            for page_num in range(min(len(doc), 5)):  # Check first 5 pages
                                page = doc[page_num]
                                corrected = validator.validate_and_correct(page, data)
                                data = corrected
                            
                            # For Type B: also validate numeric purity
                            if doc_type == "TYPE_B":
                                data = validator.validate_numeric_purity(data, doc_type)
                            
                            # Semantic validation: check CARGOS/ABONOS based on transaction type
                            data = validator.validate_by_transaction_type(data, verbose=True)
                            
                            section["data"] = data
                
                print(f"      坐标验证完成 ({doc_type})")
            
            doc.close()
        except ImportError:
            print(f"      (跳过坐标验证: 模块未找到)")
        except Exception as e:
            print(f"      (坐标验证跳过: {str(e)})")
        print()
        
        # Step 3: Generate final JSON
        print(f"[3/4] 生成结构化JSON...")
        generator = JsonGenerator(
            include_raw_text=include_raw or config.include_raw_text,
            indent=config.json_indent
        )
        final_json = generator.generate(
            gemini_result,
            source_file=str(pdf_file),
            raw_markdown=markdown_content if include_raw else None
        )
        
        # Get statistics
        stats = generator.get_stats(final_json)
        print(f"      JSON大小: {stats['total_size_kb']:.2f} KB")
        print(f"      总行数: {stats['total_lines']:,}")
        if 'section_count' in stats:
            print(f"      分区数量: {stats['section_count']}")
        print()
        
        # Save JSON
        generator.save(final_json, output_path)
        print()
        
        print("✓" * 35)
        print("转换成功完成!")
        print(f"输入文件: {pdf_path}")
        print(f"输出文件: {output_path}")
        print("✓" * 35)
        
        return True
        
    except FileNotFoundError as e:
        print(f"\n✗ 错误: 文件未找到 - {str(e)}")
        return False
    except ValueError as e:
        print(f"\n✗ 错误: {str(e)}")
        return False
    except Exception as e:
        print(f"\n✗ 未预期的错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main entry point"""
    print_banner()
    
    parser = argparse.ArgumentParser(
        description='将PDF文件转换为结构化JSON',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python pdf_to_json.py document.pdf
  python pdf_to_json.py document.pdf -o output.json
  python pdf_to_json.py document.pdf --include-raw --save-md
  
环境变量:
  需要设置 GEMINI_API_KEY 环境变量（可通过 .env 文件配置）
        """
    )
    
    parser.add_argument(
        'pdf_path',
        help='输入PDF文件路径'
    )
    
    parser.add_argument(
        '-o', '--output',
        help='输出JSON文件路径（可选，默认在PDF同目录的output文件夹下）'
    )
    
    parser.add_argument(
        '--include-raw',
        action='store_true',
        help='在输出JSON中包含原始Markdown文本'
    )
    
    parser.add_argument(
        '--save-md',
        action='store_true',
        help='保存中间生成的Markdown文件'
    )
    
    args = parser.parse_args()
    
    success = convert_pdf_to_json(
        args.pdf_path,
        args.output,
        args.include_raw,
        args.save_md
    )
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python
"""Main CLI interface for BBVA PDF parser."""
import argparse
import sys
import io
from pathlib import Path

# Fix Unicode encoding issues on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from src.pipeline import BankDocumentPipeline
# Backward compatibility
BBVAPipeline = BankDocumentPipeline


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="BBVA PDF Document Parser - High precision extraction with validation"
    )
    
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        type=str,
        help="Path to input PDF file"
    )
    
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="output",
        help="Output directory for results (default: output)"
    )
    
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip validation step (faster but less reliable)"
    )
    
    parser.add_argument(
        "--full-output",
        action="store_true",
        help="输出完整元数据（包含bbox/confidence等，默认使用简化输出）"
    )
    
    parser.add_argument(
        "--config",
        "-c",
        type=str,
        help="Path to config file (default: config.yaml)"
    )
    
    parser.add_argument(
        "--external-transactions",
        type=str,
        help="外部流水明细JSON文件路径（可选，如提供则跳过内部解析）"
    )
    
    args = parser.parse_args()
    
    # Validate input
    if not Path(args.input).exists():
        print(f"Error: Input file not found: {args.input}")
        sys.exit(1)
    
    # Initialize pipeline
    try:
        pipeline = BankDocumentPipeline(config_path=args.config)
    except Exception as e:
        print(f"Error initializing pipeline: {e}")
        sys.exit(1)
    
    # Process PDF
    try:
        # 加载外部交易数据（如果提供）
        external_data = None
        if args.external_transactions:
            import json
            print(f"Loading external transaction data from: {args.external_transactions}")
            with open(args.external_transactions, 'r', encoding='utf-8') as f:
                external_data = json.load(f)
            print(f"✓ Loaded external transaction data")
        
        document = pipeline.process_pdf(
            pdf_path=args.input,
            output_dir=args.output,
            validate=not args.no_validate,
            simplified_output=not args.full_output,  # 默认简化输出
            external_transactions_data=external_data  # 外部交易数据
        )
        
        # Print summary
        print("\n" + "="*50)
        print("Processing Summary")
        print("="*50)
        print(f"Document Type: {document.metadata.document_type}")
        print(f"Bank: {document.metadata.bank}")
        print(f"Account Number: {document.metadata.account_number or 'Not found'}")
        print(f"Language: {document.metadata.language or 'Not detected'}")
        print(f"Total Pages: {document.metadata.total_pages}")
        print(f"Transactions Found: {len(document.structured_data.account_summary.transactions)}")
        print(f"Extraction Completeness: {document.validation_metrics.extraction_completeness:.2f}%")
        print(f"Content Accuracy: {document.validation_metrics.content_accuracy:.2f}%")
        print("="*50)
        
        # Check validation status
        if not args.no_validate and document.validation_metrics.discrepancy_report:
            print(f"\nWarning: {len(document.validation_metrics.discrepancy_report)} discrepancies found.")
            print("See validation_report.json for details.")
        
        sys.exit(0)
    
    except Exception as e:
        print(f"Error processing PDF: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()


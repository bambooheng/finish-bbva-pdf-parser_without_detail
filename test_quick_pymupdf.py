"""Quick test to verify multi-statement PDF splitting with PyMuPDF."""
import sys
import os
import json

from src.pipeline import BankDocumentPipeline

def main():
    pdf_path = r"D:\Mstar\4.MSN20251028359银行流水1_20251231问题单\MSN20251103038银行流水1\MSN20251103038银行流水1.pdf"
    output_dir = r"d:\完成版_finish\bbva-pdf-parser_除流水明细外其他部分\output\test_3038_pymupdf"
    external_transactions_path = r"d:\完成版_finish\bbva-pdf-parser_除流水明细外其他部分\external_data\MSN20251103038银行流水1_v72_extracted.json"
    
    # Load external transactions
    with open(external_transactions_path, 'r', encoding='utf-8') as f:
        external_data = json.load(f)
    
    print("Loaded external transactions data")
    print(f"Total pages in external data: {len(external_data.get('pages', []))}")
    print(f"Total rows: {external_data.get('total_rows', 'N/A')}")
    
    # Initialize pipeline
    pipeline = BankDocumentPipeline()
    
    # Monkey-patch to force PyMuPDF
    pipeline.ocr_handler.process_pdf = pipeline.ocr_handler._fallback_extraction
    
    print("\nProcessing PDF using PyMuPDF (fast mode)")
    print("=" * 60)
    
    # Process PDF
    document = pipeline.process_pdf(
        pdf_path=pdf_path,
        output_dir=output_dir,
        validate=False,
        simplified_output=True,
        external_transactions_data=external_data
    )
    
    print("\n" + "=" * 60)
    print("VERIFICATION RESULTS")
    print("=" * 60)
    
    # Check output files
    import glob
    json_files = sorted(glob.glob(os.path.join(output_dir, "*_structured.json")))
    
    print(f"\n✓ Generated {len(json_files)} output files\n")
    
    for json_file in json_files:
        basename = os.path.basename(json_file)
        print(f"File: {basename}")
        
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Check period
        period = data.get('metadata', {}).get('period', {})
        period_start = period.get('start', 'N/A')
        period_end = period.get('end', 'N/A')
        print(f"  Period: {period_start} to {period_end}")
        
        # Check transaction details
        tx_details = data.get('structured_data', {}).get('account_summary', {}).get('transaction_details', {})
        if tx_details:
            total_rows = tx_details.get('total_rows', 0)
            pages = tx_details.get('pages', [])
            print(f"  Transactions: {total_rows} rows across {len(pages)} pages")
            
            # Sample a few transaction dates to verify period filtering
            if pages and len(pages) > 0:
                first_page_rows = pages[0].get('rows', [])
                if first_page_rows:
                    sample_dates = [row.get('fecha_oper_complete', 'N/A') for row in first_page_rows[:3]]
                    print(f"  Sample dates: {', '.join(sample_dates)}")
        print()
    
    print("\n✓ Test complete! Check the output files above.")
    
if __name__ == "__main__":
    main()

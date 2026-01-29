"""
Debug script to test transaction extraction independently
"""
import sys
sys.path.insert(0, 'GEMINI_PDF_TO_JSON_BBVA_流水明细部分_20260120')

from final_grid_extractor_v72 import FinalGridExtractorV72
import json

pdf_path = r"D:\Mstar\银行审核要点\BBVA流水测试-真实样例1022\BBVA AGO-SEP 真实3-MSN20251016154.pdf"

print("Testing direct grid extractor call...")
extractor = FinalGridExtractorV72()
result, output_path = extractor.extract_document(pdf_path)

print(f"\nResult type: {type(result)}")
print(f"Result keys: {result.keys() if isinstance(result, dict) else 'N/A'}")
print(f"Total rows: {result.get('total_rows') if result else 'N/A'}")

if result and 'pages' in result:
    print(f"\nNumber of pages in result: {len(result['pages'])}")
    for i, page in enumerate(result['pages']):
        print(f"  Page {i}: {len(page.get('rows', []))} rows")
        if page.get('rows'):
            print(f"    First row keys: {page['rows'][0].keys()}")
            print(f"    First row: {json.dumps(page['rows'][0], indent=2, ensure_ascii=False)}")
            break
else:
    print("\nNo pages in result!")

print(f"\nOutput path: {output_path}")

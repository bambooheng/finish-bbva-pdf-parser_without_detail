"""Debug: Check external transaction data format and dates."""
import json

# Load external transactions file
external_path = r"d:\完成版_finish\bbva-pdf-parser_除流水明细外其他部分\external_data\MSN20251103038银行流水1_v72_extracted.json"

with open(external_path, 'r', encoding='utf-8') as f:
    external_data = json.load(f)

print(f"Total pages: {len(external_data.get('pages', []))}")
print(f"Total rows: {external_data.get('total_rows', 'N/A')}")

# Sample first few rows to check date format
if external_data.get('pages'):
    first_page = external_data['pages'][0]
    rows = first_page.get('rows', [])
    
    print(f"\nFirst page has {len(rows)} rows")
    print("\nSample of first 5 rows:")
    for i, row in enumerate(rows[:5]):
        fecha_oper = row.get('fecha_oper', 'N/A')
        fecha_oper_complete = row.get('fecha_oper_complete', 'N/A')
        print(f"  Row {i+1}: fecha_oper={fecha_oper}, fecha_oper_complete={fecha_oper_complete}")
    
    # Count how many rows have fecha_oper_complete
    with_complete = sum(1 for page in external_data['pages'] for row in page.get('rows', []) if row.get('fecha_oper_complete'))
    total_rows = sum(len(page.get('rows', [])) for page in external_data['pages'])
    print(f"\nRows with fecha_oper_complete: {with_complete}/{total_rows}")

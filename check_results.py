"""Quick check of period extraction results."""
import json
import os

output_dir = r"d:\完成版_finish\bbva-pdf-parser_除流水明细外其他部分\output\test_3038_pymupdf"

for i in range(1, 4):
    filename = f"MSN20251103038银行流水1_part{i}_structured.json"
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    period = data.get('metadata', {}).get('period')
    tx_details = data.get('structured_data', {}).get('account_summary', {}).get('transaction_details', {})
    total_rows = tx_details.get('total_rows', 0)
    
    print(f"Doc {i}: Period={period}, Transactions={total_rows}")

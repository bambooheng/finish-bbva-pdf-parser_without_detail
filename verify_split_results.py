"""Quick verification script to check transaction splitting results"""
import json
from pathlib import Path

output_dir = Path(r"D:\完成版_finish\bbva-pdf-parser_除流水明细外其他部分\output\test_split_fix")

# Find all _structured.json files
json_files = sorted(output_dir.glob("*_structured.json"))

print(f"\n{'='*70}")
print(f"Transaction Split Verification Results")
print(f"{'='*70}\n")

total_transactions = 0

for json_file in json_files:
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    raw_tx = data.get("structured_data", {}).get("account_summary", {}).get("raw_transaction_data")
    
    if raw_tx:
        total_rows = raw_tx.get("total_rows", 0)
        total_pages = raw_tx.get("total_pages", 0)
        
        # Get page range
        pages = raw_tx.get("pages", [])
        if pages:
            page_nums = [p.get("page", 0) + 1 for p in pages]  # Convert to 1-indexed
            page_range = f"{min(page_nums)}-{max(page_nums)}"
        else:
            page_range = "N/A"
        
        print(f"File: {json_file.name}")
        print(f"  Transactions: {total_rows}")
        print(f"  Pages Covered: {page_range} ({total_pages} pages)")
        print()
        
        total_transactions += total_rows
    else:
        print(f"File: {json_file.name}")
        print(f"  ⚠ NO TRANSACTION DATA")
        print()

print(f"{'='*70}")
print(f"Total Transactions Across All Documents: {total_transactions}")
print(f"Number of Documents: {len(json_files)}")
print(f"{'='*70}\n")

# Check if transactions are unique (not duplicated)
if len(json_files) > 1:
    print("Checking for duplication...")
    tx_counts = []
    for json_file in json_files:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        raw_tx = data.get("structured_data", {}).get("account_summary", {}).get("raw_transaction_data")
        if raw_tx:
            tx_counts.append(raw_tx.get("total_rows", 0))
    
    if len(set(tx_counts)) == 1 and tx_counts[0] == total_transactions:
        print("❌ DUPLICATION DETECTED: All documents have identical transaction counts!")
    else:
        print("✅ NO DUPLICATION: Transaction counts differ across documents")

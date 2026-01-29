"""Quick check of transaction filtering results"""
import json
from pathlib import Path

# Check if output files exist
output_dir = Path(r"D:\完成版_finish\bbva-pdf-parser_除流水明细外其他部分\output\final_fix_test")

if not output_dir.exists():
    print(f"Output directory doesn't exist yet: {output_dir}")
    print("Test may still be running...")
    exit(1)

# Find JSON files
json_files = sorted(output_dir.glob("MSN20251103038*_structured.json"))

if not json_files:
    print(f"No JSON files found in {output_dir}")
    print("Test may still be running or failed...")
    exit(1)

print(f"\n{'='*70}")
print(f"Transaction Filtering Verification")
print(f"{'='*70}\n")

total = 0
for f in json_files:
    with open(f, 'r', encoding='utf-8') as file:
        data = json.load(file)
    
    metadata = data.get("metadata", {})
    period = metadata.get("period", {})
    
    raw_tx = data.get("structured_data", {}).get("account_summary", {}).get("raw_transaction_data")
    
    if raw_tx:
        tx_count = raw_tx.get("total_rows", 0)
        total += tx_count
        print(f"{f.name}")
        print(f"  Period: {period.get('start')} to {period.get('end')}")
        print(f"  Transactions: {tx_count}")
        print()
    else:
        print(f"{f.name}")
        print(f"  Period: {period.get('start')} to {period.get('end')}")
        print(f"  ⚠️ NO TRANSACTION DATA")
        print()

print(f"{'='*70}")
print(f"Total: {total} transactions across {len(json_files)} files")
print(f"{'='*70}\n")

if len(json_files) == 3 and total == 161:
    print("✅ SUCCESS: 3 files generated with total of 161 transactions")
    print("   Now verify each file has DIFFERENT counts...")
else:
    print(f"⚠️ Expected 3 files with 161 total transactions")

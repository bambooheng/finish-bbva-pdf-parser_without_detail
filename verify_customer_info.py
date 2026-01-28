"""Verify customer_info extraction in all 3 output files (CORRECTED)."""
import json
import os

output_dir = r"d:\完成版_finish\bbva-pdf-parser_除流水明细外其他部分\output\test_3038_pymupdf"

print("=" * 60)
print("CUSTOMER INFO VERIFICATION (FIXED)")
print("=" * 60)

for i in range(1, 4):
    filename = f"MSN20251103038银行流水1_part{i}_structured.json"
    filepath = os.path.join(output_dir, filename)
    
    print(f"\n{'='*60}")
    print(f"Document {i}: {filename}")
    print(f"{'='*60}")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # CORRECTED: customer_info is in structured_data.account_summary, not metadata
    customer_info = data.get('structured_data', {}).get('account_summary', {}).get('customer_info')
    
    if customer_info:
        print(f"✅ customer_info FOUND ({len(customer_info)} fields):")
        for key, value in customer_info.items():
            # Truncate long addresses for display
            if key == "Client Address":
                lines = value.split('\n')
                print(f"  - {key}:")
                for line in lines[:3]:  # Show first 3 lines
                    print(f"      {line}")
                if len(lines) > 3:
                    print(f"      ... ({len(lines)-3} more lines)")
            else:
                print(f"  - {key}: {value}")
    else:
        print("❌ customer_info MISSING")
    
    # Also check period and transactions
    period = data.get('metadata', {}).get('period', {})
    tx_count = data.get('structured_data', {}).get('account_summary', {}).get('transaction_details', {}).get('total_rows', 0)
    
    print(f"\nPeriod: {period.get('start')} to {period.get('end')}")
    print(f"Transactions: {tx_count} rows")

print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)

# Quick summary
all_pass = True
for i in range(1, 4):
    filename = f"MSN20251103038银行流水1_part{i}_structured.json"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    customer_info = data.get('structured_data', {}).get('account_summary', {}).get('customer_info')
    status = "✅ PASS" if customer_info and len(customer_info) >= 6 else "❌ FAIL"
    field_count = len(customer_info) if customer_info else 0
    print(f"Part {i}: {status} - {field_count} fields extracted")
    if not (customer_info and len(customer_info) >= 6):
        all_pass = False

print("\n" + "=" * 60)
if all_pass:
    print("🎉 ALL TESTS PASSED! Customer info extracted in all 3 files!")
else:
    print("⚠️ Some tests failed. Check the details above.")
print("=" * 60)

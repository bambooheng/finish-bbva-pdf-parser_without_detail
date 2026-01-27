
from src.utils.external_data_adapter import inject_external_transactions_to_output
import json

def test_adapter_order():
    print("Testing External Data Adapter Ordering...")
    
    # Mock Output Data (Simulating what main.py produces before injection)
    # The order here is what likely comes from to_simplified_dict
    output_data = {
        "structured_data": {
            "account_summary": {
                "customer_info": {},
                "branch_info": {},
                "transactions": [], # Internal transactions (to be removed)
                "total_movimientos": {"header": "Total Moves"},
                "apartados_vigentes": [{"header": "Investments"}]
            }
        }
    }
    
    # Mock External Data
    external_data = {
        "source_file": "test",
        "document_type": "B",
        "total_pages": 1,
        "total_rows": 10,
        "sessions": 1,
        "pages": []
    }
    
    # Injection
    result = inject_external_transactions_to_output(output_data, external_data)
    summary = result["structured_data"]["account_summary"]
    keys = list(summary.keys())
    print("Result Keys:", keys)
    
    # Verify Order
    # Expected: transactions should be gone. transaction_details added. 
    # Order: transaction_details -> total_movimientos -> apartados_vigentes
    
    assert "transactions" not in keys, "Internal transactions should be removed"
    assert "transaction_details" in keys, "Transaction details should be present"
    
    idx_details = keys.index("transaction_details")
    idx_total = keys.index("total_movimientos")
    idx_apartados = keys.index("apartados_vigentes")
    
    print(f"Indices: Details={idx_details}, Total={idx_total}, Apartados={idx_apartados}")
    
    assert idx_details < idx_total, "Transaction Details MUST be before Total Movimientos"
    assert idx_total < idx_apartados, "Total Movimientos MUST be before Apartados"
    
    print("PASSED: Ordering correct.")

if __name__ == "__main__":
    test_adapter_order()

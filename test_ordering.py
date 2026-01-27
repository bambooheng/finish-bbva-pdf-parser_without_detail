
from src.models.schemas import BankDocument, Metadata, PageData, StructuredData, AccountSummary, Transaction
from decimal import Decimal
import json

def test_ordering():
    # Mock Data
    doc = BankDocument(
        metadata=Metadata(total_pages=1),
        pages=[PageData(page_number=1)],
        structured_data=StructuredData(
            account_summary=AccountSummary(
                customer_info={"Name": "Test"},
                branch_info={"Branch": "Test"},
                transactions=[Transaction(
                    date="2023-01-01", description="T1", amount=Decimal("10.00"), 
                    raw_text="T1", bbox={"x":0,"y":0,"width":0,"height":0,"page":1}
                )],
                total_movimientos={"Total": "100"},
                apartados_vigentes=[{"A": "B"}]
            )
        ),
        validation_metrics={"extraction_completeness": 100.0, "position_accuracy": 1.0, "content_accuracy": 100.0, "is_valid": True}
    )
    
    # Serialize
    simplified = doc.to_simplified_dict()
    summary = simplified["structured_data"]["account_summary"]
    keys = list(summary.keys())
    
    print("Keys Order:", keys)
    
    # Expected Order Indices
    try:
        idx_cust = keys.index("customer_info")
        idx_branch = keys.index("branch_info")
        idx_trans = keys.index("transactions")
        idx_total = keys.index("total_movimientos")
        idx_apartados = keys.index("apartados_vigentes")
        
        # Verify
        assert idx_cust < idx_branch, "Customer Info BEFORE Branch"
        assert idx_branch < idx_trans, "Branch BEFORE Transactions"
        assert idx_trans < idx_total, "Transactions BEFORE Total Movimientos"
        assert idx_total < idx_apartados, "Total Movimientos BEFORE Apartados"
        
        print("PASSED: Order check success")
    except ValueError as e:
        print(f"FAILED: Missing key {e}")
    except AssertionError as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    test_ordering()

"""Table semantic validation."""
from typing import Any, Dict, List


class TableValidator:
    """Validate table semantics."""
    
    def validate_transaction_table(
        self, 
        table_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Validate transaction table data.
        
        Args:
            table_data: Table data to validate
            
        Returns:
            Validation report
        """
        issues = []
        
        # Check required fields
        required_fields = ["date", "description", "amount"]
        for idx, row in enumerate(table_data):
            missing = [field for field in required_fields if field not in row]
            if missing:
                issues.append({
                    "row": idx,
                    "type": "missing_fields",
                    "fields": missing
                })
        
        # Check date format consistency
        date_format_consistent = True
        for row in table_data:
            if "date" in row and row["date"]:
                # Basic date format check
                if not isinstance(row["date"], str) or len(row["date"]) < 8:
                    date_format_consistent = False
        
        if not date_format_consistent:
            issues.append({
                "type": "date_format_inconsistency"
            })
        
        return {
            "is_valid": len(issues) == 0,
            "issues": issues
        }
    
    def validate_summary_table(
        self, 
        table_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Validate summary table data.
        
        Args:
            table_data: Summary table data
            
        Returns:
            Validation report
        """
        issues = []
        
        # Check balance consistency if both initial and final are present
        initial_balance = None
        final_balance = None
        
        for row in table_data:
            if "saldo inicial" in str(row.get("description", "")).lower():
                initial_balance = row.get("amount")
            if "saldo final" in str(row.get("description", "")).lower():
                final_balance = row.get("amount")
        
        # Could add balance calculation validation here
        # if initial_balance and final_balance and transactions:
        #     calculated_final = initial_balance + sum(t.amount for t in transactions)
        #     if abs(calculated_final - final_balance) > 0.01:
        #         issues.append({"type": "balance_mismatch"})
        
        return {
            "is_valid": len(issues) == 0,
            "issues": issues
        }


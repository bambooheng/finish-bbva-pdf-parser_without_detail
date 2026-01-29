            print("Step 6b: Extracting transaction details...")
            from src.transaction_extractor import TransactionExtractorDispatcher
            from src.models.schemas import Transaction
            from datetime import datetime, date
            from decimal import Decimal
            
            tx_extractor = TransactionExtractorDispatcher()
            transaction_result, _ = tx_extractor.extract(
                pdf_path=pdf_path,
                output_dir=None,  # Don't save intermediate files
                verbose=True
            )
            
            # Convert grid extractor format to Transaction objects
            if transaction_result and isinstance(transaction_result, dict):
                transaction_objects = []
                
                # Grid extractor returns dict with 'pages' containing transaction data
                for page_data in transaction_result.get("pages", []):
                    for tx_row in page_data.get("rows", []):
                        try:
                            # Parse date - grid extractor might use different formats
                            date_str = tx_row.get("FECHA", "")
                            tx_date = None
                            if date_str:
                                try:
                                    # Try parsing common formats
                                    if "/" in date_str:
                                        parts = date_str.split("/")
                                        if len(parts) == 2:  # DD/MMM format
                                            # Assume current year if only month/day
                                            tx_date = datetime.strptime(f"{date_str}/{datetime.now().year}", "%d/%b/%Y").date()
                                        else:
                                            tx_date = datetime.strptime(date_str, "%d/%m/%Y").date()
                                except:
                                    tx_date = None  # Keep as None if parsing fails
                            
                            # Convert to Transaction object
                            transaction_objects.append(Transaction(
                                date=tx_date or datetime.now().date(),  # Fallback to today
                                description=tx_row.get("DESCRIPCIÓN", "") or "",
                                reference=tx_row.get("REFERENCIA", ""),
                                amount=Decimal(str(tx_row.get("CARGOS", 0) or tx_row.get("ABONOS", 0) or 0)),
                                balance=Decimal(str(tx_row.get("SALDO", 0) or 0)),
                                raw_text="",  # Grid extractor doesn't provide raw text
                                bbox=[0, 0, 0, 0],  # Placeholder bbox
                                # BBVA specific fields
                                DESCRIPCION=tx_row.get("DESCRIPCIÓN"),
                                REFERENCIA=tx_row.get("REFERENCIA"),
                                CARGOS=tx_row.get("CARGOS"),
                                ABONOS=tx_row.get("ABONOS"),
                                cargos=Decimal(str(tx_row.get("CARGOS", 0) or 0)),
                                abonos=Decimal(str(tx_row.get("ABONOS", 0) or 0))
                            ))
                        except Exception as e:
                            print(f"Warning: Failed to convert transaction row: {e}")
                            continue
                
                # Assign to account_summary
                structured_data.account_summary.transactions = transaction_objects
                print(f"✓ Loaded transaction details: {len(transaction_objects)} rows")
            else:
                print("⚠ Transaction extraction returned no results")
                structured_data.account_summary.transactions = []


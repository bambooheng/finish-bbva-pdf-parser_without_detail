import json
import os

file_path = r"D:\完成版_finish\bbva-pdf-parser_除流水明细外其他部分\output\test_with_real_pdf\BBVA JUN-JUL真实1-MSN20251016154_structured.json"

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    summary = data.get("structured_data", {}).get("account_summary", {})
    
    print("--- Verification Results ---")
    
    # 1. Customer Info (Client Address)
    cust_info = summary.get("customer_info", {})
    print(f"Customer Info present: {bool(cust_info)}")
    if cust_info:
        print(f"  Keys: {list(cust_info.keys())}")
        print(f"  Client Address present: {'Client Address' in cust_info}")
        if 'Client Address' in cust_info:
            print(f"  Client Address (first 50 chars): {cust_info['Client Address'][:50]}...")

    # 2. Branch Info
    branch_info = summary.get("branch_info")
    print(f"Branch Info present: {bool(branch_info)}")
    if branch_info:
        print(f"  Keys: {list(branch_info.keys())}")

    # 3. Total de Movimientos
    total_mov = summary.get("total_movimientos")
    print(f"Total de Movimientos present: {bool(total_mov)}")
    if total_mov:
        print(f"  Keys: {list(total_mov.keys())}")

    # 4. Apartados Vigentes
    apartados = summary.get("apartados_vigentes")
    print(f"Apartados Vigentes present: {bool(apartados)}")
    if apartados:
        print(f"  Count: {len(apartados)}")

    # 5. Cuadro Resumen
    cuadro = summary.get("cuadro_resumen")
    print(f"Cuadro Resumen present: {bool(cuadro)}")
    if cuadro:
        print(f"  Count: {len(cuadro)}")
        print(f"  First item: {cuadro[0]}")

    # 6. Informacion Financiera
    info_fin = summary.get("informacion_financiera")
    print(f"Informacion Financiera present: {bool(info_fin)}")
    
    # 7. Comportamiento
    comp = summary.get("comportamiento")
    print(f"Comportamiento present: {bool(comp)}")

    # 8. Otros Productos
    otros = summary.get("otros_productos")
    print(f"Otros Productos present: {bool(otros)}")

except Exception as e:
    print(f"Error: {e}")

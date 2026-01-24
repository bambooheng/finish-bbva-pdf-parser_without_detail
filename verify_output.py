import json

with open(r'D:\完成版_finish\bbva-pdf-parser_除流水明细外其他部分\output\test_final\BBVA JUN-JUL真实1-MSN20251016154_structured.json', encoding='utf-8') as f:
    data = json.load(f)

s = data['structured_data']['account_summary']

print("=" * 80)
print("问题1检查: customer_info")
print("=" * 80)
if 'customer_info' in s:
    print("✓ customer_info存在")
    print(json.dumps(s['customer_info'], indent=2, ensure_ascii=False))
else:
    print("✗ customer_info不存在 - 问题1未解决")

print("\n" + "=" * 80)
print("问题2检查: total_movimientos")
print("=" * 80)
if 'total_movimientos' in s:
    print("✗ total_movimientos仍然存在 - 问题2未解决")
    print(json.dumps(s['total_movimientos'], indent=2, ensure_ascii=False))
else:
    print("✓ total_movimientos不存在 - 问题2已解决")

print("\n" + "=" * 80)
print("问题3检查: informacion_financiera结构")
print("=" * 80)
if 'informacion_financiera' in s:
    print("✓ informacion_financiera存在")
    print(json.dumps(s['informacion_financiera'], indent=2, ensure_ascii=False))
    if 'Rendimiento' in s['informacion_financiera']:
        print("\n✓ 包含Rendimiento模块")
    if 'Comisiones' in s['informacion_financiera']:
        print("✓ 包含Comisiones模块")
    if 'Total Comisiones' in s['informacion_financiera']:
        print("✓ 包含Total Comisiones模块")
else:
    print("✗ informacion_financiera不存在")

print("\n" + "=" * 80)
print("问题4检查: otros_productos")
print("=" * 80)
if 'otros_productos' in s:
    print("✓ otros_productos存在")
    print(json.dumps(s['otros_productos'], indent=2, ensure_ascii=False))
else:
    print("✗ otros_productos不存在 - 问题4未解决")

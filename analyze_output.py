import json
import sys

# 读取输出文件
with open(r'D:\完成版_finish\bbva-pdf-parser_除流水明细外其他部分\output\test_with_real_pdf\BBVA JUN-JUL真实1-MSN20251016154_structured.json', encoding='utf-8') as f:
    data = json.load(f)

summary = data.get('structured_data', {}).get('account_summary', {})

print("=" * 80)
print("问题1检查: customer_info是否存在")
print("=" * 80)
if 'customer_info' in summary:
    print("✓ customer_info存在")
    print(json.dumps(summary['customer_info'], indent=2, ensure_ascii=False))
else:
    print("✗ customer_info不存在 - 问题1未解决")

print("\n" + "=" * 80)
print("问题2检查: total_movimientos")
print("=" * 80)
if 'total_movimientos' in summary:
    print("存在 total_movimientos（用户认为是冗余）")
    print(json.dumps(summary['total_movimientos'], indent=2, ensure_ascii=False))
else:
    print("不存在 total_movimientos")

print("\n" + "=" * 80)
print("问题3检查: informacion_financiera结构")
print("=" * 80)
if 'informacion_financiera' in summary:
    print("存在 informacion_financiera")
    print(json.dumps(summary['informacion_financiera'], indent=2, ensure_ascii=False))
else:
    print("不存在 informacion_financiera")

print("\n" + "=" * 80)
print("问题4检查: otros_productos（截图3）")
print("=" * 80)
if 'otros_productos' in summary:
    print("✓ otros_productos存在")
    print(json.dumps(summary['otros_productos'], indent=2, ensure_ascii=False))
else:
    print("✗ otros_productos不存在 - 问题4未解决")

print("\n" + "=" * 80)
print("comportamiento检查")
print("=" * 80)
if 'comportamiento' in summary:
    print("存在 comportamiento")
    print(json.dumps(summary['comportamiento'], indent=2, ensure_ascii=False))
else:
    print("不存在 comportamiento")

print("\n" + "=" * 80)
print("所有顶层keys")
print("=" * 80)
print(list(summary.keys()))

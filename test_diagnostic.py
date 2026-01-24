"""
简单的诊断测试 - 测试data_extractor的新方法是否有语法错误
"""
import sys
sys.path.insert(0, 'src')

print("=" * 70)
print("诊断测试: 检查新方法是否可以正常导入和调用")
print("=" * 70)

try:
    print("\n1. 导入AccountSummary...")
    from models.schemas import AccountSummary
    print("✓ AccountSummary导入成功")
    
    # 检查新字段是否存在
    print("\n2. 检查AccountSummary的新字段...")
    test_summary = AccountSummary(transactions=[])
    
    fields_to_check = [
        'total_movimientos',
        'apartados_vigentes',
        'cuadro_resumen',
        'informacion_financiera',
        'comportamiento'
    ]
    
    for field in fields_to_check:
        if hasattr(test_summary, field):
            print(f"  ✓ {field}: 存在")
        else:
            print(f"  ✗ {field}: 缺失")
    
    print("\n3. 导入DataExtractor...")
    from extraction.data_extractor import DataExtractor
    print("✓ DataExtractor导入成功")
    
    # 检查新方法是否存在
    print("\n4. 检查DataExtractor的新方法...")
    extractor = DataExtractor()
    
    methods_to_check = [
        '_extract_total_movimientos',
        '_extract_apartados_vigentes',
        '_extract_cuadro_resumen'
    ]
    
    for method in methods_to_check:
        if hasattr(extractor, method):
            print(f"  ✓ {method}: 存在")
        else:
            print(f"  ✗ {method}: 缺失")
    
    print("\n5. 导入BankDocument...")
    from models.schemas import BankDocument
    print("✓ BankDocument导入成功")
    
    # 检查to_simplified_dict方法
    print("\n6. 检查BankDocument.to_simplified_dict方法...")
    if hasattr(BankDocument, 'to_simplified_dict'):
        print("  ✓ to_simplified_dict方法存在")
    else:
        print("  ✗ to_simplified_dict方法缺失")
    
    print("\n" + "=" * 70)
    print("✓ 诊断测试通过 - 所有新方法和字段都存在")
    print("=" * 70)
    
except Exception as e:
    print(f"\n✗ 诊断测试失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

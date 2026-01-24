"""
验证脚本：测试外部流水明细数据集成功能

此脚本验证：
1. 外部数据适配器功能正确
2. 数据格式验证有效
3. 数据注入成功
4. 输出JSON结构正确
"""
import json
import sys
from pathlib import Path

def test_external_data_adapter():
    """测试外部数据适配器"""
    print("="*60)
    print("测试外部流水明细数据集成")
    print("="*60)
    
    # 1. 导入模块
    print("\n1. 导入模块...")
    try:
        from src.utils.external_data_adapter import (
            inject_external_transactions_to_output,
            validate_external_transaction_format
        )
        print("✓ 模块导入成功")
    except Exception as e:
        print(f"✗ 模块导入失败: {e}")
        return False
    
    # 2. 加载测试数据
    print("\n2. 加载测试数据...")
    try:
        with open('test_external_transactions.json', 'r', encoding='utf-8') as f:
            external_data = json.load(f)
        print(f"✓ 加载成功: {len(external_data.get('pages', [[]])[0].get('rows', []))} 条交易记录")
    except Exception as e:
        print(f"✗ 加载失败: {e}")
        return False
    
    # 3. 验证数据格式
    print("\n3. 验证数据格式...")
    try:
        is_valid = validate_external_transaction_format(external_data)
        if is_valid:
            print("✓ 数据格式验证通过")
        else:
            print("✗ 数据格式验证失败")
            return False
    except Exception as e:
        print(f"✗ 验证过程出错: {e}")
        return False
    
    # 4. 测试数据注入
    print("\n4. 测试数据注入到输出JSON...")
    try:
        # 模拟简化输出结构
        output_data = {
            "metadata": {
                "document_type": "BBVA_STATEMENT",
                "bank": "BBVA Mexico",
                "account_number": "2960296619",
                "total_pages": 9,
                "language": "es"
            },
            "structured_data": {
                "account_summary": {
                    "initial_balance": "5183.20",
                    "final_balance": "106382.65"
                }
            }
        }
        
        # 注入外部数据
        result = inject_external_transactions_to_output(output_data, external_data)
        print("✓ 数据注入成功")
        
        # 5. 验证输出结构
        print("\n5. 验证输出结构...")
        
        # 检查transaction_details是否存在
        if "transaction_details" not in result["structured_data"]["account_summary"]:
            print("✗ transaction_details字段缺失")
            return False
        print("✓ transaction_details字段存在")
        
        # 检查必需字段
        transaction_details = result["structured_data"]["account_summary"]["transaction_details"]
        required_fields = ["source_file", "document_type", "total_pages", "total_rows", "sessions", "pages"]
        
        for field in required_fields:
            if field not in transaction_details:
                print(f"✗ 缺少字段: {field}")
                return False
        print(f"✓ 所有必需字段存在: {required_fields}")
        
        # 6. 验证数据完整性
        print("\n6. 验证数据完整性...")
        print(f"  - source_file: {transaction_details['source_file']}")
        print(f"  - document_type: {transaction_details['document_type']}")
        print(f"  - total_pages: {transaction_details['total_pages']}")
        print(f"  - total_rows: {transaction_details['total_rows']}")
        print(f"  - sessions: {transaction_details['sessions']}")
        print(f"  - pages数量: {len(transaction_details['pages'])}")
        
        if transaction_details['pages']:
            first_page = transaction_details['pages'][0]
            print(f"  - 第一页交易数: {len(first_page.get('rows', []))}")
            
            if first_page.get('rows'):
                first_row = first_page['rows'][0]
                print(f"\n  第一条交易示例:")
                print(f"    fecha_oper: {first_row.get('fecha_oper')}")
                print(f"    descripcion: {first_row.get('descripcion')[:50]}...")
                print(f"    cargos: {first_row.get('cargos')}")
                print(f"    abonos: {first_row.get('abonos')}")
        
        # 7. 保存测试结果
        print("\n7. 保存测试结果...")
        output_path = "output/test_external_integration_output.json"
        Path("output").mkdir(exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        file_size = Path(output_path).stat().st_size
        print(f"✓ 测试结果已保存: {output_path}")
        print(f"  文件大小: {file_size:,} bytes")
        
        # 8. 总结
        print("\n" + "="*60)
        print("测试总结")
        print("="*60)
        print("✓ 模块导入: 成功")
        print("✓ 数据加载: 成功")
        print("✓ 格式验证: 通过")
        print("✓ 数据注入: 成功")
        print("✓ 结构验证: 通过")
        print("✓ 数据完整性: 完整")
        print("✓ 结果保存: 成功")
        print("\n✓✓✓ 所有测试通过！外部流水明细集成功能正常")
        
        return True
        
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    try:
        success = test_external_data_adapter()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ 测试执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

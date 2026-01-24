"""
测试脚本：验证简化输出功能

此脚本测试简化输出是否正确工作：
1. 加载现有的完整JSON文件
2. 创建BankDocument对象
3. 调用to_simplified_dict()方法
4. 验证输出中是否删除了冗余字段
5. 验证输出中是否保留了业务字段
"""
import json
import sys
from pathlib import Path

# 添加src到path
sys.path.insert(0, str(Path(__file__).parent))

from src.models.schemas import BankDocument

def test_simplified_output():
    """测试简化输出功能"""
    
    # 1. 加载现有的完整JSON文件
    json_path = "output/BBVA JUN-JUL真实1-MSN20251016154_structured.json"
    print(f"Loading: {json_path}")
    
    with open(json_path, 'r', encoding='utf-8') as f:
        full_data = json.load(f)
    
    full_size = Path(json_path).stat().st_size
    print(f"✓ Full JSON size: {full_size:,} bytes")
    print(f"✓ Transaction count: {len(full_data['structured_data']['account_summary']['transactions'])}")
    
    # 2. 创建BankDocument对象
    print("\nCreating BankDocument object...")
    try:
        document = BankDocument(**full_data)
        print("✓ BankDocument created successfully")
    except Exception as e:
        print(f"✗ Failed to create BankDocument: {e}")
        return False
    
    # 3. 调用to_simplified_dict()方法
    print("\nGenerating simplified output...")
    try:
        simplified_data = document.to_simplified_dict()
        print("✓ Simplified dict generated successfully")
    except Exception as e:
        print(f"✗ Failed to generate simplified dict: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 4. 保存简化后的JSON用于对比
    simplified_path = "output/test_simplified_output.json"
    with open(simplified_path, 'w', encoding='utf-8') as f:
        json.dump(simplified_data, f, indent=2, ensure_ascii=False)
    
    simplified_size = Path(simplified_path).stat().st_size
    reduction = (1 - simplified_size / full_size) * 100
    
    print(f"\n✓ Simplified JSON saved to: {simplified_path}")
    print(f"✓ Simplified JSON size: {simplified_size:,} bytes")
    print(f"✓ Size reduction: {reduction:.1f}%")
    
    # 5. 验证输出字段
    print("\n=== Field Verification ===")
    
    # 检查顶级键
    print("\nTop-level keys in simplified output:")
    top_keys = list(simplified_data.keys())
    print(f"  {top_keys}")
    
    # 验证删除的字段
    print("\n✓ Checking removed fields:")
    assert 'pages' not in simplified_data, "ERROR: 'pages' should be removed"
    print("  - 'pages' array removed")
    
    assert 'validation_metrics' not in simplified_data, "ERROR: 'validation_metrics' should be removed"
    print("  - 'validation_metrics' removed")
    
    # 验证保留的元数据字段
    print("\n✓ Checking preserved metadata fields:")
    metadata = simplified_data['metadata']
    required_metadata = ['document_type', 'bank', 'account_number', 'total_pages']
    for field in required_metadata:
        assert field in metadata, f"ERROR: '{field}' missing from metadata"
        print(f"  - '{field}': {metadata[field]}")
    
    # 验证第一条交易记录
    print("\n✓ Checking first transaction fields:")
    first_trans = simplified_data['structured_data']['account_summary']['transactions'][0]
    trans_keys = list(first_trans.keys())
    print(f"  Transaction has {len(trans_keys)} fields")
    print(f"  Keys: {trans_keys}")
    
    # 验证删除的交易字段
    removed_fields = ['bbox', 'confidence', 'raw_text']
    for field in removed_fields:
        assert field not in first_trans, f"ERROR: '{field}' should be removed from transaction"
    print(f"  - Removed fields: {removed_fields}")
    
    # 验证保留的业务字段
    business_fields = ['date', 'description', 'OPER', 'LIQ', 'DESCRIPCION', 'page']
    found_fields = [f for f in business_fields if f in first_trans]
    print(f"  - Business fields present: {found_fields}")
    
    # 特别验证page字段
    if 'page' in first_trans:
        print(f"  - Page number: {first_trans['page']} (should be 1-based)")
        assert isinstance(first_trans['page'], int), "ERROR: page should be integer"
        assert first_trans['page'] > 0, "ERROR: page should be 1-based (> 0)"
    else:
        print("  ⚠ WARNING: 'page' field not found in transaction")
    
    # 统计
    print(f"\n=== Summary ===")
    print(f"Full output size:       {full_size:,} bytes")
    print(f"Simplified output size: {simplified_size:,} bytes")
    print(f"Reduction:              {reduction:.1f}%")
    print(f"Transactions:           {len(simplified_data['structured_data']['account_summary']['transactions'])}")
    
    if reduction >= 60:
        print(f"\n✓✓✓ SUCCESS: Achieved {reduction:.1f}% size reduction (target: >60%)")
    else:
        print(f"\n⚠ WARNING: Only achieved {reduction:.1f}% reduction (target: >60%)")
    
    return True

if __name__ == "__main__":
    try:
        success = test_simplified_output()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

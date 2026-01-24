"""
测试修正后的简化输出 - 验证是否保留了所有业务数据

此脚本测试：
1. 使用真实PDF运行解析
2. 验证pages数组是否存在
3. 验证pages中是否包含业务内容
4. 验证technical metadata是否被删除
5. 对比修改前后的输出
"""
import json
import sys
from pathlib import Path

def test_corrected_simplified_output():
    """测试修正后的简化输出"""
    print("="*70)
    print("测试修正后的简化输出")
    print("="*70)
    
    # 查找最新的输出文件
    output_dir = Path("output/test_with_real_pdf")
    if not output_dir.exists():
        print("错误: output/test_with_real_pdf 目录不存在")
        print("请先运行: python main.py --input <PDF> --output output/test_with_real_pdf")
        return False
    
    json_files = list(output_dir.glob("*_structured.json"))
    if not json_files:
        print("错误: 未找到输出JSON文件")
        return False
    
    json_file = json_files[0]
    print(f"\n加载文件: {json_file.name}")
    
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"文件大小: {json_file.stat().st_size:,} bytes")
    
    # 1. 检查顶层字段
    print("\n" + "="*70)
    print("1. 检查顶层字段")
    print("="*70)
    
    top_keys = list(data.keys())
    print(f"顶层字段: {top_keys}")
    
    expected_keys = ["metadata", "pages", "structured_data"]
    for key in expected_keys:
        if key in data:
            print(f"  ✅ {key}: 存在")
        else:
            print(f"  ❌ {key}: 缺失")
            return False
    
    # 2. 检查pages数组
    print("\n" + "="*70)
    print("2. 检查pages数组")
    print("="*70)
    
    pages = data.get("pages", [])
    print(f"总页数: {len(pages)}")
    
    if not pages:
        print("  ❌ pages数组为空")
        return False
    
    # 检查第一页结构
    first_page = pages[0]
    print(f"\n第一页结构:")
    print(f"  - page_number: {first_page.get('page_number')}")
    print(f"  - content数量: {len(first_page.get('content', []))}")
    
    if first_page.get("content"):
        first_content = first_page["content"][0]
        print(f"\n第一个content元素:")
        print(f"  - type: {first_content.get('type')}")
        print(f"  - semantic_type: {first_content.get('semantic_type')}")
        print(f"  - content (前100字符): {str(first_content.get('content', ''))[:100]}")
        
        # 3. 验证technical metadata已删除
        print("\n" + "="*70)
        print("3. 验证technical metadata已删除")
        print("="*70)
        
        technical_fields = ['bbox', 'confidence', 'font_size', 'font_name', 
                           'font_flags', 'color', 'raw_text']
        
        has_technical = False
        for field in technical_fields:
            if field in first_content:
                print(f"  ❌ {field}: 存在（应该被删除）")
                has_technical = True
            else:
                print(f"  ✅ {field}: 已删除")
        
        if has_technical:
            print("\n警告: 仍有technical metadata未删除")
    
    # 4. 检查业务内容
    print("\n" + "="*70)
    print("4. 统计业务内容")
    print("="*70)
    
    total_content_elements = sum(len(page.get("content", [])) for page in pages)
    print(f"所有页面的content元素总数: {total_content_elements}")
    
    # 5. 检查structured_data
    print("\n" + "="*70)
    print("5. 检查structured_data")
    print("="*70)
    
    if "structured_data" in data:
        sd = data["structured_data"]
        if "account_summary" in sd:
            as_keys = list(sd["account_summary"].keys())
            print(f"account_summary字段: {as_keys}")
    
    # 6. 保存分析报告
    print("\n" + "="*70)
    print("6. 保存分析报告")
    print("="*70)
    
    report = {
        "file": str(json_file),
        "file_size_bytes": json_file.stat().st_size,
        "top_level_keys": top_keys,
        "total_pages": len(pages),
        "total_content_elements": total_content_elements,
        "has_pages_array": "pages" in data,
        "has_content_in_pages": total_content_elements > 0,
        "sample_page_structure": {
            "page_number": first_page.get("page_number"),
            "content_count": len(first_page.get("content", [])),
            "sample_fields": list(first_page.get("content", [{}])[0].keys()) if first_page.get("content") else []
        }
    }
    
    report_path = output_dir / "verification_report_corrected.json"
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"分析报告已保存: {report_path}")
    
    # 总结
    print("\n" + "="*70)
    print("测试总结")
    print("="*70)
    
    success = (
        "pages" in data and
        len(pages) > 0 and
        total_content_elements > 0 and
        not has_technical
    )
    
    if success:
        print("✅ 测试通过: pages数组存在且包含业务内容，technical metadata已删除")
        return True
    else:
        print("❌ 测试失败: 请检查上述问题")
        return False

if __name__ == "__main__":
    try:
        success = test_corrected_simplified_output()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ 测试执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

# 重要说明

## 测试数据 vs 实际运行

### 测试中的情况

`test_external_integration.py`是一个**单元测试**，用于验证外部数据注入功能是否正常工作。

**测试中硬编码的数据**：
```python
# 这是模拟数据，不是真实解析结果
output_data = {
    "metadata": {...},
    "structured_data": {
        "account_summary": {
            "initial_balance": "5183.20",  # 硬编码
            "final_balance": "106382.65"   # 硬编码
        }
    }
}
```

**测试数据只有3条记录**: 这是为了快速测试而故意简化的。

### 实际运行时的情况

当使用真实PDF文档和完整外部数据时：

```bash
python main.py \
  --input "real_document.pdf" \
  --output "output" \
  --external-transactions "full_35_records.json"
```

**数据来源**：
1. **metadata** → 从PDF文档解析
2. **initial_balance, final_balance** → 从PDF文档解析（不计算）
3. **transaction_details** → 从外部JSON文件（完整35条）

## 关键原则

✅ 从原文档客观解析  
✅ 不做任何汇总计算  
✅ 外部流水明细使用完整数据  
✅ 如果文档中没有某个字段，返回null而不是计算值  

## 下一步

建议使用真实PDF + 完整35条外部数据进行实际测试，验证程序行为。

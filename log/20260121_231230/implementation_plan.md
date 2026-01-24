# 输出格式优化实施计划

## 目标概述

简化当前JSON输出，删除在实际业务中不需要的冗余元数据信息，只保留：
1. **原始业务数据**：交易信息（日期、描述、金额等）
2. **页码信息**：每条记录来自PDF的哪一页

## User Review Required

> [!IMPORTANT]
> **已确认的优化方案**
> 
> 用户已批准以下优化方案：
> 
> ### 将被删除的字段：
> 1. **坐标信息** (`bbox`): x, y, width, height 
> 2. **类型信息** (`type`, `semantic_type`): 元素类型标记
> 3. **置信度** (`confidence`): OCR识别置信度
> 4. **字体元数据** (`font_size`, `font_name`, `font_flags`, `color`, `alignment`, `line_spacing`)
> 5. **原始文本** (`raw_text`): 用于调试的原始OCR文本
> 6. **布局元素详情** (`layout_elements`): 页面级别的详细布局信息
> 7. **验证指标** (`validation_metrics`): 提取完整性等验证数据
> 
> ### 将被保留的字段：
> 1. ✅ **元数据基本信息**: `document_type`, `bank`, `account_number`, `period`, `total_pages`, `language`
> 2. ✅ **交易业务数据**: 所有BBVA字段 (OPER, LIQ, DESCRIPCION, REFERENCIA, CARGOS, ABONOS等)
> 3. ✅ **页面编号**: 在每条transaction中添加简单的`page`字段（页码）
> 4. ✅ **账户汇总**: `initial_balance`, `deposits`, `withdrawals`, `final_balance`

## 实施步骤

### 步骤1: 修改schemas.py - 添加简化输出方法

在`Transaction`类和`BankDocument`类中添加`to_simplified_dict()`方法。

### 步骤2: 修改pipeline.py - 更新保存逻辑

更新`_save_results()`和`process_pdf()`方法，添加`simplified_output`参数。

### 步骤3: 修改main.py - 添加命令行参数

添加`--full-output`参数，默认使用简化输出。

### 步骤4: 修改api_server.py - 添加API参数

在API接口中添加简化输出选项。

### 步骤5: 验证

运行测试确保输出正确且核心功能未受影响。

## 状态

- ✅ 计划已批准
- 🔄 正在实施中

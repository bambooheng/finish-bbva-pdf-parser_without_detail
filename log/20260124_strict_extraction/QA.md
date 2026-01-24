# QA记录 - 2026-01-24 - 严格提取模式优化

## 1. 问题描述

用户在查看 `BBVA JUN-JUL真实1-MSN20251016154_structured.json` 的输出结果后，指出了以下关键问题：

1.  **语言本地化问题**：部分字段被翻译成了英文，不符合"原文档语言返回"的要求。
2.  **信息缺失**：头部关键信息（如 Periodo, R.F.C, No. de Cuenta 等，参考截图1）未被提取。
3.  **非原文数据干扰**：`account_summary` 中出现了 `initial_balance`, `deposits` 等原文档中不存在的推断/计算字段。用户强调必须严格遵循"所见即所得"，不做任何加工。
4.  **外部数据兼容性**：在使用外部流水明细时，输出结构未严格保持外部数据的原始格式，可能混入了内部解析的字段。

## 2. 根本原因分析

1.  **解析逻辑过度设计**：原有的 `AccountSummary` 逻辑为了方便通用处理，自动计算了期初/期末余额和存取款总额，这违反了 BBVA 项目"严格原文提取"的特殊要求。
2.  **OCR 覆盖不全**：原提取逻辑主要关注表格区域，忽略了文档顶部 Header 区域的非结构化文本（Screenshot 1 内容）。
3.  **Schema 定义宽松**：Pydantic 模型允许这些计算字段存在，且默认输出。
4.  **适配器逻辑缺陷**：`external_data_adapter` 虽然注入了数据，但未清理原有的 `transactions` 列表，导致输出不纯净。

## 3. 解决方案与实施

### 3.1 严格"所见即所得" (Schema & Extractor)
-   **修改**: 在 `DataExtractor._extract_account_summary` 中移除了所有关于 `initial_balance`, `deposits`, `withdrawals`, `final_balance` 的计算逻辑。
-   **修改**: 更新 `BankDocument.to_simplified_dict`，仅当这些字段被显式提取（非计算）时才输出。实际上对于 BBVA 账单，这些字段不再出现。

### 3.2 补全缺失头部信息 (DataExtractor)
-   **新增**: 实现了 `_extract_customer_info(ocr_data)` 方法。
-   **逻辑**: 使用针对性的正则表达式对页面顶部的 OCR 文本进行匹配。
-   **提取字段**:
    -   `Periodo` (期间)
    -   `Fecha de Corte` (截止日期)
    -   `No. de Cuenta` (账号)
    -   `No. de Cliente` (客户号)
    -   `R.F.C` (税号)
    -   `No. Cuenta CLABE` (CLABE账号)
-   **优化**: 使用 `[\d\s/]+` 等更鲁棒的正则模式以应对 OCR 空格干扰。

### 3.3 外部数据严格兼容 (Pipeline & Adapter)
-   **修改**: 在 `src/utils/external_data_adapter.py` 中增加逻辑：当注入外部数据时，**强制删除**原有的 `transactions` 键。
-   **结果**: 输出的 JSON 在 `account_summary` 下仅包含 `transaction_details`，且其结构完全由外部 JSON 决定，不含任何额外字段。

### 3.4 语言修正
-   确保新增的 `customer_info` 和已有的 `comportamiento` 等字段的 Key 和 Value 均使用文档原文（西班牙语），不做英文映射。

## 4. 验证结果

-   **测试文件**: `output_strict/BBVA JUN-JUL真实1-MSN20251016154_structured.json`
-   **验证点**:
    -   [x] `customer_info` 包含头部所有关键信息。
    -   [x] `initial_balance` 等推断字段已消失。
    -   [x] 当使用 `--external-transactions` 时，`transactions` 列表被移除，仅保留符合格式的 `transaction_details`。
    -   [x] 所有字段均为西班牙语原文或原始数值。

## 5. 结论

代码已完成重构，完全满足"严格原文提取"和"外部数据严格兼容"的要求。所有非原文的智能推断逻辑已被剥离。

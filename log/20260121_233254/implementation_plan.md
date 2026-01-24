# 流水明细外部数据集成 - 实施方案

## 目标

将当前项目中的流水明细（transactions）解析逻辑替换为外部数据注入接口，保留其他所有解析功能（元数据、账户汇总等）。

## 当前架构分析

### Transaction解析流程

```
PDF → OCR (MinerU) → Table Parser → Data Extractor → Transaction Objects
```

**关键代码位置**:

1. **`src/pipeline.py`** (Line 121-135)
   - Step 4: `table_parser.parse_bank_tables()` - 解析表格
   - Step 5: `data_extractor.extract_structured_data()` - 提取交易数据

2. **`src/extraction/data_extractor.py`**
   - `_extract_transactions()` - 从解析的表格提取交易
   - `_extract_transactions_from_ocr()` - 直接从OCR提取交易（fallback）

3. **`src/tables/table_parser.py`**
   - `parse_bank_tables()` - 识别并解析交易表格

---

## 外部数据格式分析

### 外部格式
```json
{
  "source_file": "文件名",
  "pages": [
    {
      "page": 0,  // 0-based
      "rows": [
        {
          "fecha_oper": "21/JUN",
          "fecha_liq": "23/JUN", 
          "descripcion": "...",
          "referencia": "Referencia ******6929",
          "cargos": 7200.0,  // float
          "abonos": 0.0,
          "saldo_operacion": 5183.2,
          "saldo_liquidacion": 12383.2
        }
      ]
    }
  ]
}
```

### 当前简化格式（对比）
```json
{
  "transactions": [
    {
      "date": "2025-06-21",  // ISO format
      "description": "...",
      "reference": "******6929",  // without "Referencia" prefix
      "page": 3,  // 1-based
      "OPER": "21/JUN",  // Original format
      "LIQ": "23/JUN",
      "DESCRIPCION": "...",
      "REFERENCIA": "Referencia ******6929",  // with prefix
      "CARGOS": "7,200.00",  // formatted string
      "ABONOS": "",
      "OPERACION": "5,183.20",
      "LIQUIDACION": "12,383.20"
    }
  ]
}
```

### 格式差异

| 字段 | 外部格式 | 当前格式 | 需要转换 |
|-----|---------|---------|---------|
| page | 0-based |  1-based | ✅ +1 |
| fecha_oper | "21/JUN" | OPER:"21/JUN" | ✅ 重命名 |
| fecha_liq | "23/JUN" | LIQ:"23/JUN" | ✅ 重命名 |
| descripcion | text | DESCRIPCION:text | ✅ 重命名 |
| referencia | with "Referencia" prefix | REFERENCIA: with prefix | ✅ 保持 |
| cargos | 7200.0 (float) | CARGOS:"7,200.00" (str) | ✅ 格式化 |
| abonos | 0.0 (float) | ABONOS:"" (str) | ✅ 格式化 |
| saldo_operacion | 5183.2 | OPERACION:"5,183.20" | ✅ 格式化 |
| saldo_liquidacion | 12383.2 | LIQUIDACION:"12,383.20" | ✅ 格式化 |

---

## 实施方案

### 策略：适配器模式 + 可选注入

**核心思路**:
1. 在`pipeline.process_pdf()`添加`external_transactions_data`参数
2. 如果提供外部数据，跳过内部transaction解析
3. 转换外部格式为内部Transaction对象
4. 合并到AccountSummary中

### 修改文件清单

#### 1. `src/pipeline.py`

**修改点A**: 添加external_transactions_data参数

```python
def process_pdf(
    self,
    pdf_path: str,
    output_dir: Optional[str] = None,
    validate: bool = True,
    simplified_output: bool = True,
    external_transactions_data: Optional[Dict[str, Any]] = None  # 新参数
) -> BankDocument:
```

**修改点B**: 条件跳过Step 4和Step 5的transaction解析

```python
# Step 4: Table Parsing (条件执行)
if external_transactions_data is None:
    print("Step 4: Parsing tables...")
    tables_data = self.ocr_handler.process_tables(ocr_data)
    parsed_tables = self.table_parser.parse_bank_tables(tables_data)
else:
    print("Step 4: Skipping table parsing (using external transaction data)")
    parsed_tables = []  # 空列表

# Step 5: Data Extraction (条件执行)  
if external_transactions_data is None:
    print("Step 5: Extracting structured data...")
    structured_data = self.data_extractor.extract_structured_data(
        layout_structure,
        parsed_tables,
        ocr_data
    )
else:
    print("Step 5: Using external transaction data...")
    from src.utils.external_data_adapter import convert_external_transactions
    transactions = convert_external_transactions(external_transactions_data)
    
    # 仍然提取metadata和account_summary（不含transactions）
    structured_data = self.data_extractor.extract_metadata_and_summary(
        layout_structure,
        ocr_data,
        transactions  # 传入外部转换的transactions
    )
```

#### 2. `src/extraction/data_extractor.py`

**新增方法**:

```python
def extract_metadata_and_summary(
    self,
    layout_structure: Any,
    ocr_data: Dict[str, Any],
    external_transactions: List[Transaction]
) -> StructuredData:
    """
    提取元数据和账户汇总信息，使用外部transactions。
    
    不解析transactions，仅提取：
    - account_number
    - period  
    - initial_balance
    - final_balance
    - deposits
    - withdrawals
    """
    # 提取汇总信息（从文档本身，不从transactions计算）
    account_summary = self._extract_account_summary_from_doc(layout_structure, ocr_data)
    
    # 使用外部transactions
    account_summary.transactions = external_transactions
    
    return StructuredData(account_summary=account_summary)
```

#### 3. `src/utils/external_data_adapter.py` (新文件)

```python
"""外部流水明细数据适配器"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List
from src.models.schemas import Transaction, BBox

def convert_external_transactions(external_data: Dict[str, Any]) -> List[Transaction]:
    """
    转换外部流水明细数据为Transaction对象列表。
    
    Args:
        external_data: 外部格式的流水明细数据
        
    Returns:
        Transaction对象列表
    """
    transactions = []
    
    for page_data in external_data.get("pages", []):
        page_num = page_data.get("page", 0)  # 0-based
        
        for row in page_data.get("rows", []):
            # 格式转换
            transaction = _convert_row_to_transaction(row, page_num)
            if transaction:
                transactions.append(transaction)
    
    return transactions

def _convert_row_to_transaction(row: Dict[str, Any], page_num: int) -> Transaction:
    """转换单条row为Transaction对象"""
    
    # 格式化金额
    cargos_str = _format_amount(row.get("cargos", 0))
    abonos_str = _format_amount(row.get("abonos", 0))
    saldo_op_str = _format_amount(row.get("saldo_operacion", 0))
    saldo_liq_str = _format_amount(row.get("saldo_liquidacion", 0))
    
    # 解析日期（简单实现，实际需要year context）
    fecha_oper = row.get("fecha_oper", "")
    fecha_liq = row.get("fecha_liq", "")
    
    # 创建Transaction对象
    transaction = Transaction(
        # 向后兼容字段
        date=_parse_oper_date(fecha_oper),  # 使用oper date作为main date
        description=row.get("descripcion", ""),
        amount=Decimal(str(row.get("cargos", 0) or row.get("abonos", 0))),
        balance=Decimal(str(row.get("saldo_liquidacion", 0))),
        reference=_extract_reference_number(row.get("referencia", "")),
        raw_text="",  # 外部数据无raw_text
        bbox=BBox(x=0, y=0, width=0, height=0, page=page_num),  # 假的bbox
        
        # BBVA原始格式字段
        OPER=fecha_oper,
        LIQ=fecha_liq,
        DESCRIPCION=row.get("descripcion", ""),
        REFERENCIA=row.get("referencia", ""),
        CARGOS=cargos_str if row.get("cargos", 0) > 0 else None,
        ABONOS=abonos_str if row.get("abonos", 0) > 0 else "",
        OPERACION=saldo_op_str,
        LIQUIDACION=saldo_liq_str,
        
        # 解析后的值
        oper_date=_parse_oper_date(fecha_oper),
        liq_date=_parse_liq_date(fecha_liq),
        cargos=Decimal(str(row.get("cargos", 0))),
        abonos=Decimal(str(row.get("abonos", 0))),
        operacion=Decimal(str(row.get("saldo_operacion", 0))),
        liquidacion=Decimal(str(row.get("saldo_liquidacion", 0))),
        
        confidence=1.0  # 外部数据假设100%准确
    )
    
    return transaction

def _format_amount(amount: float) -> str:
    """格式化金额为字符串 (e.g., 7200.0 -> "7,200.00")"""
    if amount == 0:
        return ""
    # 格式化为千位分隔符
    return f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def _extract_reference_number(referencia: str) -> str:
    """提取参考号（去掉"Referencia"前缀）"""
    if referencia.startswith("Referencia "):
        return referencia[11:]  # Remove "Referencia "
    return referencia

def _parse_oper_date(fecha_str: str) -> date:
    """解析操作日期（简化版，需要year context）"""
    # TODO: 实际需要从文档获取year
    # 临时使用2025年
    try:
        from datetime import datetime
        # 假设格式 "21/JUN"
        parts = fecha_str.split("/")
        if len(parts) == 2:
            day = int(parts[0])
            month_str = parts[1].upper()
            month_map = {
                "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4,
                "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8,
                "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12
            }
            month = month_map.get(month_str[:3], 1)
            return date(2025, month, day)
    except:
        return date.today()
    return date.today()

def _parse_liq_date(fecha_str: str) -> date:
    """解析清算日期"""
    return _parse_oper_date(fecha_str)
```

#### 4. `main.py`

添加CLI参数支持外部数据：

```python
parser.add_argument(
    '--external-transactions',
    type=str,
    help='外部流水明细JSON文件路径'
)

# 在process_pdf调用中
external_data = None
if args.external_transactions:
    with open(args.external_transactions, 'r', encoding='utf-8') as f:
        external_data = json.load(f)

document = pipeline.process_pdf(
    pdf_path=args.input,
    output_dir=args.output,
    validate=not args.no_validate,
    simplified_output=not args.full_output,
    external_transactions_data=external_data  # 新参数
)
```

#### 5. `api_server.py`

添加API参数支持：

```python
class ParseRequest(BaseModel):
    pdf_path: str
    validate: bool = True
    output_dir: Optional[str] = None
    simplified_output: bool = True
    external_transactions: Optional[Dict[str, Any]] = None  # 新字段
```

---

## 验证策略

### 测试步骤

1. **准备测试数据**
   - 保存外部流水明细JSON到文件

2. **运行测试**
   ```bash
   python main.py \
     --input "file.pdf" \
     --output "output/test_external" \
     --external-transactions "external_transactions.json"
   ```

3. **验证输出**
   - ✅ JSON格式正确
   - ✅ transactions字段包含外部数据
   - ✅ metadata正常解析
   - ✅ account_summary基本信息存在
   - ✅ 简化输出模式兼容

---

## 实施顺序

1. ✅ 创建`src/utils/external_data_adapter.py`
2. ✅ 修改`src/extraction/data_extractor.py`添加新方法
3. ✅ 修改`src/pipeline.py`添加条件逻辑
4. ✅ 修改`main.py`添加CLI参数
5. ✅ 修改`api_server.py`添加API支持
6. ✅ 测试验证
7. ✅ 更新文档

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|-----|------|---------|
| 格式转换错误 | 数据不一致 | 详细的单元测试 |
| 日期解析问题 | 日期错误 | 从文档提取year context |
| 破坏现有功能 | 兼容性问题 | 保持默认行为不变，仅在提供外部数据时启用 |

---

## 状态

- 📝 计划完成
- 🔄 待实施

# Q&A日志 - 2026-01-22 (第4次提问)

## 问题4：修正简化输出策略 - 保留所有业务数据

**时间**: 2026-01-22 00:19:50

### 用户反馈的问题

用户查看输出结果后发现以下严重问题：

**核心问题**: 之前的"简化输出"删除了很多**必要的业务信息**，这是不对的。

### 必须保留的信息（用户明确要求）

根据用户提供的5张截图，以下信息**必须全部保留并结构化输出**：

#### 1. 账户基本信息页（截图1）

**位置**: 通常在第2页（或无封皮时在第1页），需基于内容判断，不硬编码

**必须保留的内容**（除了BBVA logo、页脚、流水明细外的所有内容）：
- 客户信息：ALMA RUTH CORONA HUERTA, No. de Cliente, R.F.C等
- 账户信息：No. de Cuenta, SUCURSAL, DIRECCIÓN, PLAZA, TELÉFONO
- Información Financiera表格（所有字段和值）
- Comportamiento表格（所有字段和值）
- 其他所有文本内容

#### 2. 页眉信息（截图2 - 每页都有）

**必须保留**：
- 页码：PÁGINA X/Y
- No. de Cuenta: 296029619
- No. de Cliente: 25527031

**特殊要求**: 这部分可以单独解析到一起，便于验证每页的账户号和客户号是否一致

#### 3. Total de Movimientos（截图3）

**必须保留**：
```
TOTAL IMPORTE CARGOS: 139,768.27    TOTAL MOVIMIENTOS CARGOS: 30
TOTAL IMPORTE ABONOS: 233,768.72    TOTAL MOVIMIENTOS ABONOS: 5
```

#### 4. Estado de cuenta de Apartados Vigentes（截图4）

**必须保留**：
- Folio
- Nombre Apartado
- Importe Apartado  
- Importe Total

示例数据：
```
Folio: 
Nombre Apartado: Emilio, Emilio 2
Importe Apartado: $4,500.00, $500.00
Importe Total: $5,000.00
```

#### 5. Cuadro resumen y gráfico de movimientos del período（截图5）

**必须保留**：
```
Concepto          Cantidad      Porcentaje  Columna
Saldo Inicial     12,383.20     5.29%       A
Depósitos/Abonos  213,768.72    100.00%     B
Devoluciones(-)   0.00          0.00%       C
Intereses a favor 0.00          0.00%       D
Comisión efectivo -67,300.00    -28.78%     E
Otros cargos(-)   -72,469.27    -31.00%     F
Saldo Final       106,382.65    45.50%      G
```

### 不需要解析的内容

❌ 所有注释说明  
❌ 页脚信息  
❌ BBVA logo  
❌ 图片/图表（只解析表格数据，不解析图）

### 核心原则（用户强调）

1. ✅ **只对原文内容做事实解析**
2. ❌ **不做任何衍生加工和汇总**
3. ✅ **保持最简单原则**
4. ❌ **不删除任何业务信息**

---

## 当前实现的问题分析

### 错误的简化策略

在`schemas.py`的`to_simplified_dict()`方法中：

```python
def to_simplified_dict(self) -> Dict[str, Any]:
    simplified = {
        "metadata": {...},  # 只保留了基本metadata
        "structured_data": {
            "account_summary": {
                "transactions": [...]  # 只保留了transactions
            }
        }
    }
    # ❌ 删除了：
    # - pages数组（包含了所有页面的详细内容！）
    # - validation_metrics
    # - 很多业务字段
```

**问题**: `pages`数组中包含了大量业务信息，不应该完全删除！

### 应该删除的vs应该保留的

#### ❌ 应该删除的（技术元数据）
- `bbox`: {x, y, width, height, page}
- `confidence`: 0.95
- `type`: "text"
- `semantic_type`: "paragraph"
- `font_size`, `font_name`, `font_flags`, `color`等字体信息
- `raw_text`: 原始OCR文本（重复）
- `validation_metrics`: 验证指标

#### ✅ 应该保留的（业务内容）
- 所有文档中的实际文本内容
- 所有表格数据
- 账户信息、客户信息
- 各种汇总数据（Total de Movimientos等）
- 页码、账户号、客户号
- 所有业务相关的字段和值

---

## 修正方案

### 新的简化策略

**简化的真正含义**应该是：
- ✅ 保留**所有业务内容**（文本、数据、表格）
- ❌ 删除**技术元数据**（bbox、confidence、font信息等）

### 实施步骤

#### 1. 修改`BankDocument.to_simplified_dict()`

需要保留`pages`数组中的业务内容，但简化每个元素：

```python
def to_simplified_dict(self) -> Dict[str, Any]:
    simplified = {
        "metadata": {...},
        "pages": [
            # 保留pages，但简化每个page的内容
            self._simplify_page(page) for page in self.pages
        ],
        "structured_data": {...}
    }
    # 不删除pages！
    return simplified

def _simplify_page(self, page: PageData) -> Dict[str, Any]:
    """简化单个页面 - 保留业务内容，删除技术元数据"""
    return {
        "page_number": page.page_number,
        "content": [
            {
                "text": elem.text,
                # 不包含bbox, font_size等
            }
            for elem in page.layout_elements
        ],
        "tables": page.tables,  # 保留所有表格
        # 不包含layout_elements的完整bbox等信息
    }
```

#### 2. 确保所有业务字段都被解析和保留

检查`data_extractor.py`是否提取了：
- Total de Movimientos
- Estado de cuenta de Apartados Vigentes
- Cuadro resumen
- 页眉信息（账户号、客户号、页码）

#### 3. 结构化输出格式设计

```json
{
  "metadata": {
    "document_type": "BBVA_STATEMENT",
    "bank": "BBVA Mexico",
    "account_number": "296029619",
    "client_number": "25527031",
    "period": {...},
    "total_pages": 9
  },
  "pages": [
    {
      "page_number": 1,
      "header": {
        "account_number": "296029619",
        "client_number": "25527031"
      },
      "sections": [
        {
          "title": "Información Financiera",
          "type": "table",
          "data": {...}
        },
        {
          "title": "Total de Movimientos",
          "type": "summary",
          "data": {...}
        }
      ]
    }
  ],
  "structured_data": {
    "total_movimientos": {
      "total_importe_cargos": "139,768.27",
      "total_movimientos_cargos": 30,
      "total_importe_abonos": "233,768.72",
      "total_movimientos_abonos": 5
    },
    "apartados_vigentes": [...],
    "cuadro_resumen": [...],
    "transaction_details": {
      // 外部流水明细数据
    }
  }
}
```

---

## 下一步行动

1. 重新审视当前的`to_simplified_dict()`实现
2. 设计新的简化策略（保留业务，删除技术）
3. 确保data_extractor提取所有必要的业务字段
4. 修改代码实现
5. 测试验证

**状态**: 已识别问题，待设计详细修正方案

**文档创建时间**: 2026-01-22 00:19:50

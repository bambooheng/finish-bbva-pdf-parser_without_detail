"""
Gemini API client for structured markdown parsing
"""
import json
import time
import requests
from typing import Dict, Any
from config import config


class GeminiClient:
    """Client for interacting with Gemini API for markdown parsing"""
    
    def __init__(self):
        """Initialize Gemini API client"""
        config.validate()
        self.api_key = config.gemini_api_key
        self.model_name = config.gemini_model
        self.base_url = config.base_url
        
        print(f"✓ Gemini客户端已初始化，模型: {self.model_name}")
    
    def parse_markdown_to_json(self, markdown_content: str, source_file: str) -> Dict[str, Any]:
        """
        Parse markdown content to structured JSON using Gemini
        
        Args:
            markdown_content: The markdown content to parse
            source_file: Original source file name
            
        Returns:
            Dictionary containing structured data
        """
        print(f"→ 正在使用Gemini解析Markdown...")
        print(f"  内容长度: {len(markdown_content)} 字符")
        
        # Split by pages for parallel processing
        import re
        page_pattern = r'(---\s*\n\n## Page \d+\s*\n\n)'
        parts = re.split(page_pattern, markdown_content)
        
        # Reconstruct pages
        pages = []
        current_content = ""
        for i, part in enumerate(parts):
            if re.match(r'---\s*\n\n## Page \d+\s*\n\n', part):
                if current_content.strip():
                    pages.append(current_content)
                current_content = part
            else:
                current_content += part
        if current_content.strip():
            pages.append(current_content)
        
        # If document is small or single page, use single request
        if len(pages) <= 1 or len(markdown_content) < 15000:
            return self._parse_single(markdown_content)
        
        print(f"  📄 分页并行处理: {len(pages)} 页")
        
        # Parallel processing
        from concurrent.futures import ThreadPoolExecutor, as_completed
        page_results = [None] * len(pages)
        
        start_time = time.time()
        
        # 使用配置的并发数（默认为5）
        with ThreadPoolExecutor(max_workers=min(config.max_workers, len(pages))) as executor:
            future_to_idx = {
                executor.submit(self._parse_single_page, page, idx): idx 
                for idx, page in enumerate(pages)
            }
            
            completed = 0
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    page_results[idx] = future.result()
                    completed += 1
                    print(f"  ✓ 页面 {idx + 1}/{len(pages)} 解析完成")
                except Exception as e:
                    print(f"  ✗ 页面 {idx + 1} 解析失败: {str(e)}")
                    page_results[idx] = {"error": str(e)}
        
        elapsed = time.time() - start_time
        print(f"✓ 并行解析完成 ({elapsed:.2f}s)")
        
        # Merge results
        return self._merge_page_results(page_results)
    
    def _parse_single(self, markdown_content: str) -> Dict[str, Any]:
        """Parse entire markdown as single request"""
        prompt = self._build_prompt(markdown_content)
        
        try:
            start_time = time.time()
            response_text = self._call_gemini(prompt)
            elapsed = time.time() - start_time
            
            print(f"✓ 收到Gemini响应 ({elapsed:.2f}s)")
            
            result = self._extract_json(response_text)
            return result
            
        except Exception as e:
            print(f"✗ Gemini API调用错误: {str(e)}")
            raise
    
    def _parse_single_page(self, page_content: str, page_idx: int) -> Dict[str, Any]:
        """Parse a single page"""
        # 已移除延迟以提高性能
        prompt = self._build_prompt(page_content)
        response_text = self._call_gemini(prompt)
        return self._extract_json(response_text)
    
    def _merge_page_results(self, page_results: list) -> Dict[str, Any]:
        """Merge results from multiple pages into single document"""
        merged = {
            "document_type": "unknown",
            "page_metadata": [],
            "content": {
                "sections": []
            }
        }
        
        for idx, result in enumerate(page_results):
            if result is None or "error" in result:
                continue
            
            # Get document type from first valid result
            if merged["document_type"] == "unknown" and result.get("document_type"):
                merged["document_type"] = result["document_type"]
            
            # Merge page metadata
            if "page_metadata" in result:
                merged["page_metadata"].extend(result["page_metadata"])
            
            # Merge sections
            if "content" in result and "sections" in result["content"]:
                sections = result["content"]["sections"]
                # Standardize keys for transaction sections
                # Process sections for standardization
                for section in sections:
                    data = section.get("data")
                    if isinstance(data, list):
                        # Heuristic: If list contains dicts with transaction-like keys, apply standardization
                        if data and isinstance(data[0], dict):
                            keys = set(k.upper() for k in data[0].keys())
                            if any(k in keys for k in ["DESCRIPCIÓN", "DESCRIPCION", "OPER", "FECHA OPER"]):
                                section["data"] = self._standardize_transaction_keys(data)
                    elif isinstance(data, dict):
                        # Clean summary keys (e.g. "Label 8": "Amount" -> "Label": "8 Amount")
                        section["data"] = self._clean_summary_keys(data)
                        
                merged["content"]["sections"].extend(sections)
        
        return merged

    def _standardize_transaction_keys(self, data: list) -> list:
        """Standardize keys in transaction records"""
        if not isinstance(data, list):
            return data
            
        standardized_data = []
        # Key mapping (Synonym -> Standard)
        key_map = {
            "FECHA OPER": "OPER",
            "FECHA LIQ": "LIQ",
            "DESCRIPCION": "DESCRIPCIÓN",
            "REF.": "REFERENCIA",
            "SALDO OPERACION": "OPERACIÓN",
            "SALDO LIQUIDACION": "LIQUIDACIÓN",
            "OPERACION": "OPERACIÓN",
            "LIQUIDACION": "LIQUIDACIÓN",
            "SALDO": "OPERACIÓN" # Map generic SALDO to OPERACIÓN as default balance
        }
        
        # Required keys that must exist (value will be null if missing)
        required_keys = ["OPERACIÓN", "LIQUIDACIÓN", "REFERENCIA"]
        
        for record in data:
            if not isinstance(record, dict):
                standardized_data.append(record)
                continue
                
            new_record = {}
            for k, v in record.items():
                upper_k = k.upper().strip()
                # Apply mapping or use original key
                standard_k = key_map.get(upper_k, k)
                new_record[standard_k] = v
            
            # Ensure required keys exist and apply fallback logic
            if new_record.get("LIQUIDACIÓN") is None:
                if new_record.get("OPERACIÓN") is not None:
                    new_record["LIQUIDACIÓN"] = new_record["OPERACIÓN"]
                else:
                    new_record["LIQUIDACIÓN"] = None
            
            if new_record.get("OPERACIÓN") is None:
                new_record["OPERACIÓN"] = None

            # STRICT PARSING: Remove any keys that are not allowed
            # This prevents hallucinated fields like "SALDO DIARIO"
            allowed_keys = {
                "OPER", "LIQ", "DESCRIPCIÓN", "REFERENCIA", 
                "CARGOS", "ABONOS", "OPERACIÓN", "LIQUIDACIÓN"
            }
            final_record = {k: v for k, v in new_record.items() if k in allowed_keys}
            
            # HEURISTIC CORRECTION: Fix swapped columns based on keywords
            final_record = self._apply_heuristic_correction(final_record)
            
            standardized_data.append(final_record)
            
        return standardized_data

    def _apply_heuristic_correction(self, record: dict) -> dict:
        """
        Apply heuristic rules to correct column swaps (Cargos vs Abonos)
        based on description keywords.
        """
        desc = record.get("DESCRIPCIÓN", "").upper()
        
        # Keywords that strongly imply CARGOS (Withdrawals/Payments)
        # Removed broad "PAGO" to avoid false positives like "PAGO DE NOMINA"
        cargo_keywords = [
            "COMPRA", "RETIRO", "ENVIADO", "COMISION", 
            "CGO", "CARGO", "INTERES", "PAGO DE SERVICIOS",
            "PAGO CUENTA DE TERCERO", "TRASPASO A TERCEROS",
            "CHEQUE PAGADO", "MEMBRESIA", "SUSCRIPCION"
        ]
        
        # Keywords that strongly imply ABONOS (Deposits/Credits)
        abono_keywords = [
            "ABONO", "DEPOSITO", "RECIBIDO", "NOMINA", "DEVOLUCION", 
            "REEMBOLSO", "TRASPASO DE TERCEROS", "PAGO DE NOMINA",
            "TRANSFERENCIA RECIBIDA"
        ]
        
        cargos = record.get("CARGOS")
        abonos = record.get("ABONOS")
        
        # Logic 1: Implicit CARGO found in ABONOS
        if any(kw in desc for kw in cargo_keywords):
            # Special Case: "PAGO DE NOMINA" contains "PAGO" but is an ABONO
            if "NOMINA" in desc:
                pass # Do not swap if it's payroll
            elif not cargos and abonos:
                # print(f"  🔧 Auto-Correcting: Moved '{abonos}' from ABONOS to CARGOS based on '{desc[:20]}...'")
                record["CARGOS"] = abonos
                record["ABONOS"] = None
                
        # Logic 2: Implicit ABONO found in CARGOS
        elif any(kw in desc for kw in abono_keywords):
            if not abonos and cargos:
                # print(f"  🔧 Auto-Correcting: Moved '{cargos}' from CARGOS to ABONOS based on '{desc[:20]}...'")
                record["ABONOS"] = cargos
                record["CARGOS"] = None
        
        return record
            
        return standardized_data

    def _clean_summary_keys(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Clean summary keys where count is merged into the key.
        Example: "Depósitos / Abonos (+) 8": "22,400.01" -> "Depósitos / Abonos (+)": "8 22,400.01"
        """
        if not isinstance(data, dict):
            return data
            
        cleaned_data = {}
        import re
        
        for k, v in data.items():
            # Match keys ending with space + number (e.g. "Label 123")
            match = re.search(r'^(.*?)\s+(\d+)$', k)
            if match:
                clean_key = match.group(1).strip()
                count = match.group(2)
                
                # Combine count and value in the value string
                if isinstance(v, str):
                    new_value = f"{count} {v}"
                else:
                    new_value = v # Fallback if value is not string
                
                cleaned_data[clean_key] = new_value
            else:
                cleaned_data[k] = v
                
        return cleaned_data
    
    def _call_gemini(self, prompt: str, retry_count: int = 0) -> str:
        """Call Gemini API using HTTP requests with retry logic"""
        import time
        
        url = f"{self.base_url}/{self.model_name}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        
        data = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": config.temperature,
                "maxOutputTokens": config.max_output_tokens
            }
        }
        
        max_retries = 3
        
        try:
            # Increase timeout for large documents
            response = requests.post(url, headers=headers, json=data, timeout=600)
            
            if response.status_code == 200:
                res_json = response.json()
                candidate = res_json["candidates"][0]
                parts = candidate.get("content", {}).get("parts", [])
                
                # Check for truncation
                finish_reason = candidate.get("finishReason", "")
                if finish_reason == "MAX_TOKENS" and retry_count < 2:
                    print(f"  ⚠ 响应被截断，正在重试 ({retry_count + 1}/2)...")
                    return self._call_gemini(prompt, retry_count + 1)
                
                full_response = ""
                for part in parts:
                    if "text" in part:
                        full_response += part["text"]
                    elif "thought" in part:
                        print(f"  💭 Gemini思考过程已检测")
                
                return full_response
            else:
                error_msg = f"{response.status_code} - {response.text}"
                raise Exception(error_msg)
                
        except requests.exceptions.Timeout:
            if retry_count < max_retries:
                wait_time = (retry_count + 1) * 10
                print(f"  ⚠ 请求超时，{wait_time}秒后重试 ({retry_count + 1}/{max_retries})...")
                time.sleep(wait_time)
                return self._call_gemini(prompt, retry_count + 1)
            raise Exception("请求超时（600秒），已重试3次")
        except (requests.exceptions.ConnectionError, requests.exceptions.RequestException) as e:
            if retry_count < max_retries:
                wait_time = (retry_count + 1) * 10
                print(f"  ⚠ 连接错误，{wait_time}秒后重试 ({retry_count + 1}/{max_retries})...")
                time.sleep(wait_time)
                return self._call_gemini(prompt, retry_count + 1)
            raise Exception(f"请求失败（已重试{max_retries}次）: {str(e)}")
    
    def _build_prompt(self, markdown_content: str) -> str:
        """Build the prompt for Gemini to parse markdown"""
        prompt = f"""STRICT JSON OUTPUT ONLY. DO NOT START WITH "Here is the JSON" OR ANY OTHER TEXT. START DIRECTLY WITH "{{".
DO NOT USE MARKDOWN FORMATTING like ```json. JUST RAW JSON.

CRITICAL: Output ONLY valid JSON. No explanations, no thinking, no markdown formatting.
Start your response with {{ and end with }}. Nothing else.

ABSOLUTE PROHIBITION - READ CAREFULLY:
1. Do NOT add fields that don't exist in the original document
2. Do NOT split values into sub-objects
3. Keep values EXACTLY as they appear

WRONG (adding non-existent fields like Cantidad/Importe):
"Depósitos / Abonos (+)": {{"Cantidad": "5", "Importe": "233,768.72"}}

CORRECT (keeping original format):
"Depósitos / Abonos (+)": "5 233,768.72"

你是一个专业的文档结构化专家。你的任务是将Markdown文档转换为结构化JSON，确保绝对的零信息丢失。

# 核心原则（必须严格遵守）

## 1. 完整性原则（最高优先级）
**绝对禁止截断、省略、简化任何信息**

- ✅ 提取每一个字符、每一个空格、每一个符号
- ✅ 多行内容必须完整合并（用空格连接）
- ✅ 表格的每一个单元格都要完整提取
- ✅ 跨页内容必须完整合并
- ❌ 绝对不能因为内容长就截断
- ❌ 绝对不能省略任何信息

## 2. 字段名精确复制原则（关键！）
**字段名必须100%精确复制原文档中的文字**

❌ 禁止的操作：
- 不要将"Saldo Promedio"改成"saldo_promedio"
- 不要将"Días del Periodo"改成"dias_del_periodo"  
- 不要移除空格、特殊字符（+、-、%、/等）
- 不要改变大小写

✅ 正确做法：
- "Depósitos / Abonos (+)" → 使用 "Depósitos / Abonos (+)" 作为字段名
- "ISR Retenido (-)" → 使用 "ISR Retenido (-)" 作为字段名
- "Tasa Bruta Anual %" → 使用 "Tasa Bruta Anual %" 作为字段名

## 3. 禁止数据重构原则（关键！）
**值必须保持原样，不能添加子字段或解释**

❌ 禁止的操作：
- 不要将 "5 233,768.72" 拆分成 {{"Cantidad": "5", "Importe": "233,768.72"}}
- 不要添加原文档中不存在的字段名（如Cantidad、Importe）
- 不要对数据进行任何解释、总结或重新组织

✅ 正确做法：
- 原文显示 "Depósitos / Abonos (+): 5 233,768.72"
- 输出应为: "Depósitos / Abonos (+)": "5 233,768.72"
- 保持值的原始格式，不做任何拆分

**示例对比：**
原文：Depósitos / Abonos (+)  5  233,768.72

❌ 错误输出（添加了不存在的子字段）：
"Depósitos / Abonos (+)": {{"Cantidad": "5", "Importe": "233,768.72"}}

✅ 正确输出（保持原样）：
"Depósitos / Abonos (+)": "5 233,768.72"

## 4. 通用性原则
**系统必须能处理任意类型的文档**

- 根据实际内容动态识别文档类型（document_type）
- 根据表格的实际列名/行标题创建字段
- 不要假设固定的表格结构
- 自动适应不同的文档格式
- **保持原始语言，不要翻译任何内容**

## 5. 表格和摘要区域处理
**保持原始结构和标签**

- 使用文档中实际显示的文字作为JSON字段名
- 保持原始语言和格式
- 对于键值对形式的摘要信息，使用原始标签作为字段名
- 值必须保持原始格式，不做拆分或重构
- 如"Saldo Anterior: 12,383.20" → {{"Saldo Anterior": "12,383.20"}}

## 6. 页面元数据提取
**如果文档包含页面信息，进行提取**

提取可能存在的：
- 账号、客户号、文档编号等标识符
- 页码信息
- 日期范围等

# JSON输出格式

```json
{{
  "document_type": "根据内容自动识别：bank_statement, invoice, report, contract, form等",
  "page_metadata": [
    {{"page": 1, ...其他页面级信息...}}
  ],
  "content": {{
    "sections": [
      {{
        "section_type": "根据内容识别：header, summary, transactions, table_data等",
        "title": "该分区的标题（如果有）",
        "data": {{
          // 使用原始字段名，保持原始语言
        }}
      }}
    ]
  }}
}}
```

# 银行对账单特殊处理（如果检测到）

如果文档是银行对账单，且表格有这些列：
- OPER, LIQ, DESCRIPCION, REFERENCIA, CARGOS, ABONOS, OPERACION, LIQUIDACION

则：
- 保持这些原始列名作为JSON字段名
- **DESCRIPCIÓN列规则**（重要！观察PDF表格的视觉排列）：
  - DESCRIPCIÓN列只包含交易描述/商户名称
  - 例如：`"GASOL SERV COLIMA2"`, `"AUTOZONE 7740"`, `"RETIRO CAJERO AUTOMATICO"`
  - 不要在DESCRIPCIÓN中包含星号(******)或RFC信息
- **REFERENCIA列规则**（关键！动态识别，不要硬编码）：
  - REFERENCIA列包含卡号后几位（以星号******开头）和参考信息
  - 典型格式：`"******6275 RFC: SCO 7312133D6 10:14 AUT: 202329"`
  - 可能包含的内容：
    - 卡号后几位：`******6275`
    - 税号：`RFC: xxx`
    - 授权码：`AUT: xxx`
    - 时间：`10:14`
    - 流水号：`FOLIO:xxx`
    - 账号/参考号
  - 如果单元格以星号（******）开头，该内容属于REFERENCIA列
  - REFERENCIA可能为空（如SPEI转账等无卡交易）
- **不要将DESCRIPCIÓN的内容放入REFERENCIA**
- **严格禁止添加不存在的字段（ABSOLUTELY FORBIDDEN）**:
  - **严禁**经过计算、推导或总结添加任何原始文档中不存在的列。
  - **严禁**添加 "SALDO DIARIO"、"TOTAL"、"SUBTOTAL" 等原始表格中没有的字段。
  - 如果原始表格只有 "SALDO" 一列，就只输出 "SALDO"，绝对不要自己拆分成 "SALDO DIARIO"。
  - **原则**：原文档有什么字段就输出什么字段，不做任何逻辑判断，不做纠正，不做已存在的总结。
  - 即使发现数据不平衡或看起来有错，也必须**按原样提取**。

# 跨页表格行合并规则（最高优先级！）

文档中包含多个页面（用 "---" 和 "## Page X" 分隔）。当表格跨页时，必须正确合并。

**如何识别需要合并的行：**

方法1：检查标记
- 如果看到 `<!-- ROW_CONTINUES_NEXT_PAGE -->` 和 `<!-- ROW_CONTINUED_FROM_PREV_PAGE -->`
- 这两个标记之间的内容需要合并为一条记录

方法2：检查数据完整性
- 页面末尾的表格行：如果所有金额列（CARGOS/ABONOS/OPERACION/LIQUIDACION）都为空，该行不完整
- 下一页开头的表格行：如果日期列（OPER/LIQ）为空，该行是前一行的延续

**合并规则（必须严格执行）：**
1. 找到页面N末尾的不完整行（缺少金额）
2. 找到页面N+1开头的延续行（缺少日期）
3. 将两者合并为一条完整记录：
   - 日期取自不完整行
   - DESCRIPCION合并两行的内容（用空格连接）
   - 金额取自延续行

**示例场景：**
```
页面2末尾（不完整行 - 无金额）：
OPER: 26/Jun, LIQ: 26/Jun, DESCRIPCION: SPEI RECIBIDOSANTANDER 5292262...

页面3开头（延续行 - 无日期）：
OPER: 空, LIQ: 空, DESCRIPCION: 20250626400140BET0000452922620 AS INTERMODAL..., ABONOS: 15,000.00

页面3第二行（新记录 - 有日期）：
OPER: 26/Jun, LIQ: 26/Jun, DESCRIPCION: PAGO TARJETA DE CREDITO..., CARGOS: 5,000.00
```

**正确结果：**
记录1: SPEI RECIBIDOSANTANDER... + 20250626400140BET... = 合并为一条 (ABONOS: 15,000.00)
记录2: PAGO TARJETA DE CREDITO... = 单独一条 (CARGOS: 5,000.00)

**错误结果（必须避免）：**
将 "20250626400140BET..." 归入 "PAGO TARJETA DE CREDITO" 记录

**检测关键点：**
- 延续行的第一列（日期）通常为空或仅含空白
- 如果下一页的第一条记录没有日期，它一定是上一页记录的延续
**错误处理（必须避免）：**
不要将延续内容归入下一条记录。如果下一页开头的内容缺少日期，它一定是上一条记录的延续。

# 验证检查清单

生成JSON前验证：
1. ☑ 是否有任何内容被截断？
2. ☑ 表格列名是否使用原始名称？
3. ☑ 跨页内容是否完整合并？
4. ☑ 每页元数据是否提取？

# 源文档

{markdown_content}

# 输出要求

1. **只返回JSON**，不要任何解释文字
2. **确保JSON格式正确**且可解析
3. **绝对零信息丢失**
4. **保持原始字段名和语言**

开始转换：
"""
        return prompt
    
    def _sanitize_json_text(self, text: str) -> str:
        """Remove invalid control characters from JSON text"""
        import re
        # Remove control characters except for \t, \n, \r which are valid in some contexts
        # In JSON strings, these should be escaped. Remove unescaped ones.
        
        # First, find all string literals and sanitize them
        def clean_string_content(match):
            content = match.group(0)
            # Replace unescaped control characters within strings
            # Keep \n, \r, \t if they appear as escaped sequences
            cleaned = ""
            i = 0
            while i < len(content):
                char = content[i]
                if char == '\\' and i + 1 < len(content):
                    # Keep escaped sequences
                    cleaned += content[i:i+2]
                    i += 2
                elif ord(char) < 32 and char not in '\t':
                    # Replace control characters with space
                    cleaned += ' '
                    i += 1
                else:
                    cleaned += char
                    i += 1
            return cleaned
        
        # Simple approach: replace all control characters except those in valid escape sequences
        result = []
        in_string = False
        escape_next = False
        
        for char in text:
            if escape_next:
                result.append(char)
                escape_next = False
            elif char == '\\' and in_string:
                result.append(char)
                escape_next = True
            elif char == '"' and not escape_next:
                result.append(char)
                in_string = not in_string
            elif in_string and ord(char) < 32 and char not in '\t':
                # Replace control characters with space inside strings
                result.append(' ')
            else:
                result.append(char)
        
        return ''.join(result)
    
    def _extract_json(self, response_text: str) -> Dict[str, Any]:
        """Extract and parse JSON from Gemini response"""
        text = response_text.strip()
        import re
        
        # Strategy 1: Find Markdown Code Block (Highest Confidence)
        # Check for ```json or just ``` blocks
        code_block_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
        matches = re.findall(code_block_pattern, text, re.DOTALL)
        if matches:
            # Try matches, preferring the largest one or the last one
            for match in reversed(matches):
                try:
                    json_text = self._sanitize_json_text(match)
                    result = json.loads(json_text)
                    print(f"✓ JSON解析成功 (从代码块提取)")
                    return result
                except:
                    continue

        # Strategy 2: Find last } and matching { (Good for "thinking first, json last")
        brace_end = text.rfind('}')
        if brace_end != -1:
            brace_count = 0
            for i in range(brace_end, -1, -1):
                if text[i] == '}':
                    brace_count += 1
                elif text[i] == '{':
                    brace_count -= 1
                    if brace_count == 0:
                        try:
                            json_text = text[i:brace_end+1]
                            json_text = self._sanitize_json_text(json_text)
                            result = json.loads(json_text)
                            print(f"✓ JSON解析成功 (从末尾提取)")
                            return result
                        except:
                            pass # Continue to Strategy 3
                        break # Found the matching brace but failed to parse, stop this strategy

        # Strategy 3: Find first { and matching } (Original/Common case)
        brace_start = text.find('{')
        if brace_start != -1:
            brace_count = 0
            json_end = -1
            for i in range(brace_start, len(text)):
                if text[i] == '{':
                    brace_count += 1
                elif text[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        json_end = i
                        break
            
            if json_end != -1:
                json_text = text[brace_start:json_end+1]
                json_text = self._sanitize_json_text(json_text)
                try:
                    result = json.loads(json_text)
                    print(f"✓ JSON解析成功 (直接提取)")
                    return result
                except json.JSONDecodeError:
                    pass  # Try other methods
        
        # If direct extraction failed, try to find JSON code block
        json_start = text.find('```json')
        if json_start != -1:
            json_content = text[json_start + 7:]
            json_end = json_content.find('```')
            if json_end != -1:
                text = json_content[:json_end].strip()
            else:
                text = json_content.strip()
        elif text.find('```') != -1:
            first_block = text.find('```')
            json_content = text[first_block + 3:]
            json_end = json_content.find('```')
            if json_end != -1:
                text = json_content[:json_end].strip()
        
        # Try to parse again with sanitization
        text = text.strip()
        if text.startswith('{'):
            text = self._sanitize_json_text(text)
            try:
                result = json.loads(text)
                print(f"✓ JSON解析成功")
                return result
            except json.JSONDecodeError as e:
                print(f"✗ JSON解析失败: {str(e)}")
                # Show more context for debugging
                print(f"提取的JSON文本（前500字符）:\n{text[:500]}")
                print(f"原始响应（前500字符）:\n{response_text[:500]}")
                raise ValueError(f"Gemini返回的JSON无效: {str(e)}")
        
        raise ValueError(f"无法从响应中提取JSON。响应开头: {response_text[:200]}")

"""
PDF to Markdown Converter using Gemini API
将PDF文件转换为Markdown格式，使用Gemini API进行OCR识别
"""

import os
import sys
import base64
import re
import requests
from pathlib import Path
from typing import List, Optional
import io
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import fitz  # PyMuPDF
except ImportError:
    print("错误: 需要安装 PyMuPDF 库")
    print("请运行: pip install pymupdf")
    sys.exit(1)

from config import config


class PDFConverter:
    """使用Gemini API将PDF转换为Markdown"""
    
    def __init__(self):
        """初始化转换器"""
        config.validate()
        self.api_key = config.gemini_api_key
        self.model_name = config.gemini_model
        self.base_url = config.base_url
        
        # OCR提示词 - 通用版本，适用于任意PDF
        self.ocr_prompt = """Convert the following document to markdown.
Return only the markdown with no explanation text. Do not include delimiters like ```markdown or ```html.

CORE RULES:
  - You must include ALL information on the page. Do not exclude headers, footers, or subtext.
  - Return tables in HTML format with CLEAR COLUMN SEPARATION.
  - Each column MUST be in its own <td> cell - preserve the exact column structure from the PDF.
  - Charts & infographics must be interpreted to a markdown format. Prefer table format when applicable.
  - Prefer using ☐ and ☑ for check boxes.
  - DO NOT translate any text. Keep all content in its original language.
  - Preserve original field names exactly as shown in the document.

TABLE HANDLING:
  - Identify ALL columns in the table header
  - Keep each column's content in its own <td> cell
  - Multi-line content within a cell should use <br> tags
  - If content continues on multiple lines, merge ALL lines into ONE cell
  - Never merge different columns together

CRITICAL: INCOMPLETE ROW DETECTION
For tables with transaction data:
  - If a table row at the END of the page is missing numeric values in the last columns (like amounts/balances), it is INCOMPLETE
  - Add marker: <!-- ROW_CONTINUES_NEXT_PAGE --> after such incomplete rows
  - If a table row at the START of the page has no date in the first column, it is a CONTINUATION from previous page
  - Add marker: <!-- ROW_CONTINUED_FROM_PREV_PAGE --> before such continuation rows

Example:
<tr><td>26/Jun</td><td>SPEI RECIBIDO SANTANDER<br>Description text</td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
<!-- ROW_CONTINUES_NEXT_PAGE -->

<!-- ROW_CONTINUED_FROM_PREV_PAGE -->
<tr><td></td><td>Continuation of description<br>More text</td><td>RFC XXX</td><td></td><td>15,000.00</td><td>50,000.00</td><td>50,000.00</td></tr>

PAGE METADATA (if available):
  - Extract any account numbers, document numbers, or identifiers at the top of each page
  - Extract page numbers if shown
  - Format as HTML comment: <!-- PAGE_META: key1: value1 | key2: value2 -->

SPECIAL HANDLING FOR BANK STATEMENTS (if detected):
  - If you see a table with columns like OPER, LIQ, DESCRIPCION, REFERENCIA, CARGOS, ABONOS, etc.
  - REFERENCIA column typically contains RFC codes or reference numbers
  - **CRITICAL COLUMNS SEPARATION**: You MUST separate "DESCRIPCION" and "REFERENCIA" columns.
  - "REFERENCIA" column content ALWAYS starts with specific patterns:
      * Masked card numbers: `******1234`
      * The word `Referencia` or `Ref.`
      * RFC codes: `RFC:`
  - **NEVER** merge these into the Description column.
  - If you see `******` inside a description cell, you MUST split it into the next column.
  - **MANDATORY**: The REFERENCIA column MUST exist. If it is empty for a row, output an empty `<td></td>`. Do NOT skip the column.
  - **CRITICAL**: If there are two balance columns (e.g. SALDO OPERACION and SALDO LIQUIDACION), MUST separate them into TWO columns. Do NOT merge them.
  - **MANDATORY**: CAPTURE BALANCE COLUMNS (`SALDO OPERACION`, `SALDO LIQUIDACION`) for EVERY row if a value is present.
      * Look for numbers in the far right columns.
      * Even if the column header is not repeated, the data is likely there.
      * If a cell seems empty but is part of a transaction row, explicitly output `<td></td>`.
  - **VERTICAL ALIGNMENT**: Ensure amounts (`CARGOS`/`ABONOS`) are aligned with the correct description line.
      * Do NOT assign an amount to a header line or a text-only description line if the amount visually belongs to the row below.
      * If a Description spans 2 lines and the Amount is centered or on the 2nd line, treat it as ONE merged row (use `<br>` in Description).
  - **NUMERIC COLUMN ACCURACY (CARGOS vs ABONOS)**:
      * You must distinguish between the `CARGOS` (Charges/Withdrawals) and `ABONOS` (Deposits/Credits) columns.
      * Look at the header positions. `CARGOS` is the 5th column, `ABONOS` is the 6th column (typically).
      * **Rule**: If a number appears in the left numeric column of the pair, it is `CARGOS`. If it appears in the right numeric column, it is `ABONOS`.
      * **CRITICAL**: Do NOT shift numbers horizontally. If a value is clearly under the `CARGOS` header, do not put it in `ABONOS`.
      * Verify the position relative to the column headers on every page, especially after page breaks.
  - If headers are stacked (e.g., "SALDO" over "OPERACION"), treat it as "SALDO OPERACION"."""
        
    
        # 需要过滤的思考过程关键词模式
        self._thinking_patterns = [
            r'\*\*(?:Processing|Structuring|Finalizing|Constructing|Drafting|Assembling|Analyzing|Reviewing|Generating|Reflecting|Re-evaluating|Synthesizing|Formatting|Revising|Refining|Summarizing|Summary|Analysis|Beginning|Complete|Converting|Extracting|Identifying|Understanding|Planning|Preparing|Considering|Checking|Verifying|Translating|Interpreting|Outputting|Rendering|Building|Creating|Composing|Arranging|Organizing|Parsing|Reading|Scanning|Examining|Inspecting|Evaluating|Assessing|Determining|Calculating|Computing|Transforming|Mapping|Matching|Aligning|Adjusting|Correcting|Fixing|Updating|Modifying|Editing|Handling|Managing|Executing|Implementing|Applying|Using|Utilizing|Employing|Following|Adhering|Ensuring|Maintaining|Preserving|Capturing|Recording|Documenting|Noting|Observing|Recognizing|Detecting|Finding|Locating|Searching|Looking|Seeking|Exploring|Investigating|Researching|Studying|Learning|Discovering|Uncovering|Revealing|Exposing|Displaying|Showing|Presenting|Demonstrating|Illustrating|Depicting|Describing|Explaining|Clarifying|Elaborating|Detailing|Specifying|Defining|Stating|Expressing|Conveying|Communicating|Transmitting|Delivering|Providing|Supplying|Offering|Giving|Sending|Passing|Transferring|Moving|Shifting|Transitioning|Changing|Switching|Alternating|Varying|Differing|Comparing|Contrasting|Distinguishing|Differentiating|Separating|Dividing|Splitting|Breaking|Cutting|Slicing|Segmenting|Partitioning|Grouping|Clustering|Categorizing|Classifying|Sorting|Ordering|Ranking|Prioritizing|Sequencing|Listing|Enumerating|Counting|Numbering|Indexing|Labeling|Tagging|Naming|Titling|Heading|Captioning)[^*]*\*\*\s*\n+.*?(?=\n\n(?:[#<\|]|\*\*[A-Z])|\Z)',
            r"(?:^|\n\n)(?:I |I'm |I've |I'll |I'd |I was |I am |I have |I had |I will |I would |I could |I should |I need |I want |I think |I believe |I understand |I recognize |I notice |I see |I found |I received |I analyzed |I converted |I extracted |I identified |I processed |I handled |I ensured |I captured |I followed |I used |I applied |I generated |I created |I built |I formed |I constructed |I assembled |I arranged |I organized |I structured |I formatted |I styled |I designed |I developed |I implemented |I executed |I performed |I completed |I finished |I concluded |I summarized |I reviewed |My |Throughout |The process |This process |This approach |In this |For this )[^\n]*(?:\n(?![#<\|\-\*]|$).*)*",
            r'^\*\*[^*]+\*\*\s*$',
        ]
        
        print(f"✓ PDF转换器已初始化，模型: {self.model_name}")
    
    def _clean_thinking_content(self, text: str) -> str:
        """清除返回内容中的思考过程文本"""
        cleaned = text
        
        for _ in range(3):
            prev_len = len(cleaned)
            for pattern in self._thinking_patterns:
                cleaned = re.sub(pattern, '', cleaned, flags=re.MULTILINE | re.DOTALL | re.IGNORECASE)
            if len(cleaned) == prev_len:
                break
        
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        cleaned = re.sub(r'\n---\s*\n(?=\n---|\Z)', '\n', cleaned)
        cleaned = re.sub(r'^[\s\-]*\n*', '', cleaned)
        
        return cleaned.strip()
    
    def pdf_to_images(self, pdf_path: str, dpi: int = None) -> List[bytes]:
        """将PDF转换为图片列表"""
        dpi = dpi or config.dpi
        print(f"正在读取PDF文件: {pdf_path}")
        doc = fitz.open(pdf_path)
        images = []
        
        for page_num in range(len(doc)):
            print(f"处理第 {page_num + 1}/{len(doc)} 页...")
            page = doc[page_num]
            zoom = dpi / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")
            images.append(img_bytes)
        
        doc.close()
        print(f"PDF转换完成，共 {len(images)} 页")
        return images
    
    def image_to_base64(self, image_bytes: bytes) -> str:
        """将图片字节转换为base64编码"""
        return base64.b64encode(image_bytes).decode('utf-8')
    
    def call_gemini_with_image(self, image_base64: str, page_num: int) -> str:
        """调用Gemini API处理单页图片"""
        url = f"{self.base_url}/{self.model_name}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        
        enhanced_prompt = self.ocr_prompt + """

IMPORTANT: Start your response IMMEDIATELY with the document content. 
Do NOT include any thinking process, analysis, summaries, or meta-commentary.
Do NOT start with phrases like "Processing", "Analyzing", "Summary", etc.
Output ONLY the actual text and tables from the document image."""
        
        data = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": enhanced_prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/png",
                                "data": image_base64
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "maxOutputTokens": 16384,
                "temperature": 0.2
            }
        }
        
        try:
            print(f"正在调用Gemini API处理第 {page_num} 页...")
            response = requests.post(url, headers=headers, json=data, timeout=180)
            
            if response.status_code == 200:
                res_json = response.json()
                parts = res_json.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                
                full_response = ""
                for part in parts:
                    if "text" in part:
                        full_response += part["text"]
                
                cleaned_response = self._clean_thinking_content(full_response)
                print(f"第 {page_num} 页处理完成")
                return cleaned_response
            else:
                error_msg = f"API调用失败 (页 {page_num}): {response.status_code} - {response.text}"
                print(error_msg)
                return f"\n\n---\n**错误**: {error_msg}\n---\n\n"
                
        except Exception as e:
            error_msg = f"请求失败 (页 {page_num}): {str(e)}"
            print(error_msg)
            return f"\n\n---\n**错误**: {error_msg}\n---\n\n"
    
    def _detect_blue_cover(self, image_bytes: bytes, threshold: float = 0.4) -> bool:
        """检测图片是否为蓝色封面"""
        try:
            from PIL import Image
            image = Image.open(io.BytesIO(image_bytes))
            
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            width, height = image.size
            step = max(1, min(width, height) // 50)
            
            blue_count = 0
            total_sampled = 0
            
            for i in range(0, width, step):
                for j in range(0, height, step):
                    r, g, b = image.getpixel((i, j))
                    if b > r + 30 and b > g + 30 and b > 100:
                        blue_count += 1
                    total_sampled += 1
            
            return total_sampled > 0 and (blue_count / total_sampled) > threshold
            
        except Exception as e:
            print(f"⚠ 封面检测失败: {str(e)}")
            return False
    
    def convert(self, pdf_path: str, dpi: int = None, max_workers: int = None,
                skip_blue_cover: bool = None) -> str:
        """
        将PDF文件转换为Markdown
        
        Args:
            pdf_path: PDF文件路径
            dpi: 图片分辨率
            max_workers: 并行处理的最大线程数
            skip_blue_cover: 是否跳过蓝色封面页
            
        Returns:
            Markdown内容
        """
        dpi = dpi or config.dpi
        max_workers = max_workers or config.max_workers
        skip_blue_cover = skip_blue_cover if skip_blue_cover is not None else config.skip_blue_cover
        
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF文件不存在: {pdf_path}")
        
        print(f"\n{'='*60}")
        print(f"开始转换PDF到Markdown")
        print(f"输入文件: {pdf_path}")
        print(f"并行线程数: {max_workers}")
        print(f"{'='*60}\n")
        
        # 将PDF转换为图片
        images = self.pdf_to_images(pdf_path, dpi=dpi)
        total_pages = len(images)
        
        # 并行调用Gemini API处理每一页
        print(f"\n开始并行处理 {total_pages} 页...")
        markdown_pages = [None] * total_pages
        
        # 检测首页是否为蓝色封面
        skip_first_page = False
        if skip_blue_cover and total_pages > 0:
            if self._detect_blue_cover(images[0]):
                skip_first_page = True
                print(f"✓ 检测到首页为蓝色封面，将跳过解析")
                markdown_pages[0] = ""
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_page = {}
            start_index = 1 if skip_first_page else 0
            
            for i in range(start_index, len(images)):
                image_base64 = self.image_to_base64(images[i])
                future = executor.submit(self.call_gemini_with_image, image_base64, i + 1)
                future_to_page[future] = i
            
            completed = start_index
            for future in as_completed(future_to_page):
                page_index = future_to_page[future]
                try:
                    markdown_content = future.result()
                    markdown_pages[page_index] = markdown_content
                    completed += 1
                    print(f"✓ 已完成: {completed}/{total_pages} 页")
                except Exception as e:
                    print(f"✗ 第 {page_index + 1} 页处理失败: {str(e)}")
                    markdown_pages[page_index] = f"\n\n---\n**错误**: 第 {page_index + 1} 页处理失败: {str(e)}\n---\n\n"
        
        # 合并所有页面的Markdown
        print("\n正在合并所有页面...")
        full_markdown = ""
        actual_page_count = 0
        
        for i, page_content in enumerate(markdown_pages, 1):
            if not page_content or page_content.strip() == "":
                continue
                
            actual_page_count += 1
            if actual_page_count > 1:
                full_markdown += "\n\n---\n\n"
                full_markdown += f"## Page {actual_page_count}\n\n"
            
            full_markdown += page_content
        
        # 后处理：修复跨页表格行
        full_markdown = self._fix_cross_page_table_rows(full_markdown)
        
        print(f"\n{'='*60}")
        print(f"✓ PDF转换完成！共 {total_pages} 页")
        print(f"{'='*60}\n")
        
        return full_markdown
    
    def _fix_cross_page_table_rows(self, markdown: str) -> str:
        """
        修复跨页表格行问题
        
        通用检测模式（无硬编码）：
        1. 页面末尾的表格行：后半部分单元格全为空
        2. 下一页开头的表格行：前半部分单元格全为空
        将两者合并为一条完整记录
        """
        import re
        
        # 按页面分隔符拆分
        page_separator = r'\n\n---\n\n## Page \d+\n\n'
        pages = re.split(page_separator, markdown)
        
        if len(pages) <= 1:
            return markdown
        
        fixed_pages = [pages[0]]
        
        for i in range(1, len(pages)):
            prev_page = fixed_pages[-1]
            curr_page = pages[i]
            
            # 查找前一页最后一个表格行
            prev_rows = re.findall(r'<tr>.*?</tr>', prev_page, re.DOTALL)
            curr_rows = re.findall(r'<tr>.*?</tr>', curr_page, re.DOTALL)
            
            if prev_rows and curr_rows:
                last_row = prev_rows[-1]
                first_row = curr_rows[0]
                
                # 提取单元格内容
                last_row_cells = re.findall(r'<td[^>]*>(.*?)</td>', last_row, re.DOTALL)
                first_row_cells = re.findall(r'<td[^>]*>(.*?)</td>', first_row, re.DOTALL)
                
                if len(last_row_cells) >= 4 and len(first_row_cells) >= 4:
                    num_cells = len(last_row_cells)
                    
                    # 判断条件优化：
                    # 只要当前页第一行看起来是延续行（第一列为空，且不是全空），就合并
                    # 银行流水通常第一列是日期。如果日期为空，说明是上一条记录的描述/备注延续
                    first_cell_empty = not first_row_cells[0].strip()
                    has_content = any(c.strip() for c in first_row_cells)
                    
                    if first_cell_empty and has_content:
                        print(f"  ✓ 检测到跨页表格行（延续行），正在合并...")
                        
                        # 合并单元格：非空优先
                        merged_cells = []
                        for j in range(max(len(last_row_cells), len(first_row_cells))):
                            cell1 = last_row_cells[j].strip() if j < len(last_row_cells) else ''
                            cell2 = first_row_cells[j].strip() if j < len(first_row_cells) else ''
                            
                            if cell1 and cell2:
                                # 两者都有内容，合并（用空格连接）
                                combined = f"{cell1} {cell2}".replace('<br>', ' ').replace('  ', ' ').strip()
                                merged_cells.append(combined)
                            elif cell1:
                                merged_cells.append(cell1)
                            else:
                                merged_cells.append(cell2)
                        
                        # 构建合并后的行
                        merged_row = '<tr>' + ''.join(f'<td>{cell}</td>' for cell in merged_cells) + '</tr>'
                        
                        # 替换前一页的最后一行
                        fixed_pages[-1] = prev_page.replace(last_row, merged_row)
                        
                        # 从当前页移除第一行
                        curr_page = curr_page.replace(first_row, '', 1)
            
            fixed_pages.append(curr_page)
        
        # 重新组合页面
        result = fixed_pages[0]
        for i, page in enumerate(fixed_pages[1:], 2):
            result += f"\n\n---\n\n## Page {i}\n\n" + page
        
        return result

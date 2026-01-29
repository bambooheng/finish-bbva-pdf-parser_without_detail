Role (角色设定): 你是一名资深的文档智能处理专家，精通 PDF 布局分析、OCR 坐标矫正及非结构化数据清洗。

Task (任务目标): 针对无框线（Borderless）的银行流水 PDF 文档，执行高精度的表格还原与数据提取。重点解决由于“文本换行”和“列间距过窄”导致的 OCR 串行（Row shift）和串列（Column shift）问题。

Workflow & Constraints (执行流程与约束):

1. 预处理：文档清洗 (Preprocessing)

页眉/页脚剔除： 在处理任何数据前，根据 Y 轴坐标识别并剔除页眉（如 Bank Logo, Address）和页脚（如 Page Number, Disclaimer）。这些区域的信息严禁进入流水列表。

锚定有效区域： 仅在 "Detalle de Movimientos Realizados" 标题下方的区域进行数据提取。

2. 布局策略：虚拟栅格化 (Virtual Grid Injection) 你需根据文档类型（Type A 或 Type B）采用不同的栅格构建策略。请先根据视觉特征对文档进行分类：

Type A (特征：类似附件 8359.pdf):

视觉特征： REFERENCIA 字段通常以 **** 开头，位于 DESCRIPCIÓN 下方，且垂直方向上未侵入右侧数值列。

处理策略： 标准栅格法。直接根据 FECHA, DESCRIPCIÓN, CARGOS, ABONOS, SALDO 的表头坐标，绘制垂直分割线。将每一个坐标块内的内容严格映射到对应的 JSON 字段中。

Type B (特征：类似附件 3038.pdf - 高难度):

视觉特征： REFERENCIA 字段以 "Referencia" 开头，内容较长，且在水平方向上可能延伸至 CARGOS 列的视觉范围内，极易导致 OCR 将引用号误读为金额，或挤占金额列空间。

处理策略： 干扰抑制与骨架优先法。

第一步（逻辑屏蔽）： 在构建坐标系时，暂时忽略/清空所有以 "Referencia" 开头的文本行。将它们视为“透明背景”。

第二步（锚定骨架）： 在清除了长文本干扰后，优先锁定右侧四个核心数值列：CARGOS (借), ABONOS (贷), OPERACION (操作余额), LIQUIDACION (清算余额)。为这四列绘制严格的垂直边界线（Bounding Box），确保数值绝对归位。

第三步（回填描述）： 提取完数值列后，将剩余左侧区域的所有文本（包括之前忽略的 DESCRIPCIÓN 和 REFERENCIA）作为一个整体文本块提取，按 Y 轴坐标归并到对应的交易行中。

3. 数据提取与校验 (Extraction & Validation)

坐标强制绑定： OCR 识别结果必须严格落入上述定义的“虚拟单元格”中。如果某行只有 DESCRIPCIÓN 但没有数值，则视为上一行的附加描述，禁止将其错位对齐到数值列。

逻辑纠错： 针对 Type B，如果发现 CARGOS 或 ABONOS 列中出现了非数值字符（如字母或长串数字 ID），必须将其强制移动到 REFERENCIA 字段，保持数值列的纯净。

Output Format (输出格式): 请返回标准的 JSON 格式列表，确保每一条交易包含完整字段。对于被拆分的 REFERENCIA，请将其合并回所属的交易对象中。


针对 Type 3038 (REFERENCIA 干扰) 这种情况，我在代码层面给你一个具体的 “Masking（掩膜）” 实现思路，这比纯依靠 Prompt 更稳定：

核心思路：利用 PyMuPDF (fitz) 进行“手术式”预处理

在把图片/PDF 喂给 OCR 或大模型之前，先用 Python 修改 PDF 内容。
import fitz  # PyMuPDF
import re

def preprocess_pdf_masking(pdf_path, output_path):
    doc = fitz.open(pdf_path)
    
    for page in doc:
        # 1. 定义页眉页脚区域 (根据你的实际文档调整坐标)
        # 假设顶部 150 和底部 100 是非流水区域
        header_rect = fitz.Rect(0, 0, page.rect.width, 150)
        footer_rect = fitz.Rect(0, page.rect.height - 100, page.rect.width, page.rect.height)
        
        # 绘制白色矩形覆盖页眉页脚 (相当于剔除)
        page.draw_rect(header_rect, color=(1, 1, 1), fill=(1, 1, 1))
        page.draw_rect(footer_rect, color=(1, 1, 1), fill=(1, 1, 1))

        # 2. 针对 Type 3038 的“Referencia”进行各种处理
        # 查找以 "Referencia" 开头的文本块
        text_instances = page.search_for("Referencia")
        
        # 方案 A: 如果你想彻底清除干扰，让 OCR 专心识别数字
        # 直接把 Referencia 画白块盖住 (仅用于提取数字列的步骤)
        # for rect in text_instances:
        #     # 向右扩展 rect 的宽度，因为 "Referencia" 后面跟着长数字
        #     expanded_rect = fitz.Rect(rect.x0, rect.y0, page.rect.width/2, rect.y1) 
        #     page.draw_rect(expanded_rect, color=(1, 1, 1), fill=(1, 1, 1))
        
        # 方案 B (推荐): 获取 REFERENCIA 的 Y 坐标，但不删除。
        # 在生成 Grid 时，告诉算法：在这个 Y 坐标范围内，禁止生成 竖直线 (Vertical Separator)
        # 或者标记这些 Y 坐标为 "Multi-line Description Zone"

    doc.save(output_path)
"""Main processing pipeline."""
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from src.bank_detector import BankDetector
from src.extraction.data_extractor import DataExtractor
from src.layout.deduplicator import ElementDeduplicator
from src.layout.layout_analyzer import LayoutAnalyzer
from src.llm_client import LLMClient
from src.models.schemas import (
    BankDocument,
    BBox,
    ElementType,
    LayoutElement,
    Metadata,
    PageData,
    SemanticType,
    ValidationMetrics,
)
from src.ocr.mineru_handler import MinerUHandler
from src.ocr.ocr_verifier import OCRVerifier
from src.tables.table_parser import TableParser
from src.validation.validator import Validator
from src.validation.comparison_analyzer import ComparisonAnalyzer
from src.export.excel_exporter import ExcelExporter


class BankDocumentPipeline:
    """
    Main pipeline for bank document PDF parsing.
    
    Generic pipeline that can handle documents from different banks.
    Bank-specific settings are loaded from configuration.
    
    Following prompt requirement: absolute avoidance of hardcoding,
    dynamic adaptation to document variations.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize pipeline.
        
        Args:
            config_path: Optional path to configuration file
        """
        # Reload config if custom path provided
        if config_path:
            from src.config import Config
            import os
            os.environ['CONFIG_PATH'] = config_path
        
        # Initialize components
        self.ocr_handler = MinerUHandler()
        self.ocr_verifier = OCRVerifier()
        self.llm_client = LLMClient()
        # LayoutAnalyzer will get bank_config after detection
        self.layout_analyzer = LayoutAnalyzer(llm_client=self.llm_client)
        self.table_parser = TableParser(llm_client=self.llm_client)
        self.data_extractor = DataExtractor()
        self.validator = Validator()
        self.bank_detector = BankDetector()
        self.comparison_analyzer = ComparisonAnalyzer()
        self.excel_exporter = ExcelExporter()
        
        # Bank configuration (will be set after detection)
        self.bank_config = None
    
    def process_pdf(
        self,
        pdf_path: str,
        output_dir: Optional[str] = None,
        validate: bool = True,
        simplified_output: bool = True,
        external_transactions_data: Optional[Dict[str, Any]] = None  # 外部流水明细数据
    ) -> BankDocument:
        """
        Process a bank PDF document (generic, supports multiple banks).
        
        Args:
            pdf_path: Path to input PDF
            output_dir: Optional output directory for results
            validate: Whether to perform validation
            simplified_output: 是否使用简化输出（默认True，仅输出业务数据+页码）
            external_transactions_data: 外部流水明细数据（可选，如提供则跳过内部解析）
            
        Returns:
            Complete BankDocument structure
        """
        print(f"Processing PDF: {pdf_path}")
        
        # Step 1: OCR Processing
        print("Step 1: Performing OCR...")
        ocr_data = self.ocr_handler.process_pdf(pdf_path)
        
        # Display OCR engine and language information
        ocr_engine = ocr_data.get("engine", "unknown")
        ocr_language = ocr_data.get("language", "unknown")
        print(f"OCR 引擎信息: {ocr_engine}")
        print(f"OCR 检测到的文档语言: {ocr_language}")
        
        # Extract critical fields for dual verification
        critical_fields = self.ocr_handler.extract_critical_fields(ocr_data)
        validated_fields = self.ocr_verifier.validate_critical_fields(
            critical_fields,
            self.llm_client
        )
        
        # Step 2: Bank Detection (before layout analysis to get bank-specific config)
        print("Step 2: Detecting bank...")
        bank_profile = self.bank_detector.detect_bank(ocr_data)
        self.bank_config = self.bank_detector.get_bank_config(bank_profile)
        print(f"Detected bank: {self.bank_config.get('name', bank_profile)}")
        
        # Update components with bank config (following prompt: dynamic adaptation)
        self.layout_analyzer.bank_config = self.bank_config
        self.table_parser.bank_config = self.bank_config
        
        # Step 3: Layout Analysis
        print("Step 3: Analyzing document layout...")
        layout_structure = self.layout_analyzer.analyze_document_layout(ocr_data)
        
        # Initialize data extractor with bank config
        self.data_extractor = DataExtractor(bank_config=self.bank_config)
        
        # Step 4 & 5: 条件执行 - 根据是否提供外部交易数据
        if external_transactions_data is None:
            # 使用内部解析流程
            print("Step 4: Parsing tables...")
            tables_data = self.ocr_handler.process_tables(ocr_data)
            parsed_tables = self.table_parser.parse_bank_tables(tables_data)
            
            print("Step 5: Extracting structured data...")
            structured_data = self.data_extractor.extract_structured_data(
                layout_structure,
                parsed_tables,
                ocr_data
            )
        else:
            # 使用外部交易数据，跳过交易解析
            print("Step 4: Skipping table parsing (using external transaction data)")
            print("Step 5: Extracting metadata only (transactions from external source)")
            
            # 仍然需要解析表格以获取account summary信息
            tables_data = self.ocr_handler.process_tables(ocr_data)
            parsed_tables = self.table_parser.parse_bank_tables(tables_data)
            
            # 提取元数据，不解析交易
            structured_data = self.data_extractor.extract_metadata_only(
                layout_structure,
                parsed_tables,
                ocr_data
            )
        
        metadata = self.data_extractor._extract_metadata(ocr_data, self.bank_config)
        
        # Step 6: Build Pages
        print("Step 6: Building page structure...")
        pages = self._build_pages(ocr_data, layout_structure)
        
        # Step 7: Validation
        validation_metrics = ValidationMetrics(
            extraction_completeness=0.0,
            position_accuracy=0.0,
            content_accuracy=0.0,
            discrepancy_report=[]
        )
        
        # Build initial document for validation
        initial_document = BankDocument(
            metadata=metadata,
            pages=pages,
            structured_data=structured_data,
            validation_metrics=ValidationMetrics(
                extraction_completeness=0.0,
                position_accuracy=0.0,
                content_accuracy=0.0,
                discrepancy_report=[]
            )
        )
        
        if validate:
            print("Step 7: Validating extraction...")
            # Initial validation can use the document we just built
            try:
                validation_report = self.validator.validate_extraction(
                    pdf_path,
                    initial_document,
                    output_dir
                )
                # Calculate extraction completeness from document (following prompt: 100% completeness)
                extraction_completeness = self.validator._calculate_completeness(initial_document)
                validation_metrics = ValidationMetrics(
                    extraction_completeness=extraction_completeness,
                    position_accuracy=0.0,  # Would need detailed position comparison
                    content_accuracy=validation_report.semantic_accuracy,
                    discrepancy_report=[d.dict() for d in validation_report.discrepancies]
                )
            except Exception as e:
                print(f"Warning: Initial validation failed: {e}")
                validation_metrics = ValidationMetrics(
                    extraction_completeness=0.0,
                    position_accuracy=0.0,
                    content_accuracy=0.0,
                    discrepancy_report=[{"error": str(e)}]
                )
        else:
            validation_metrics = ValidationMetrics(
                extraction_completeness=0.0,
                position_accuracy=0.0,
                content_accuracy=0.0,
                discrepancy_report=[]
            )
        
        # Build complete document (update with validation if available)
        document = BankDocument(
            metadata=metadata,
            pages=pages,
            structured_data=structured_data,
            validation_metrics=validation_metrics
        )
        
        # Step 7: Save output
        if output_dir:
            print(f"Step 7: Saving results to {output_dir}...")
            self._save_results(document, output_dir, pdf_path, simplified_output, external_transactions_data)
        
        # Perform final validation with complete document
        if validate:
            print("Step 8: Final validation...")
            final_report = self.validator.validate_extraction(
                pdf_path,
                document,
                output_dir
            )
            # Recalculate extraction completeness (must be based on actual extraction, not pixel accuracy)
            # Following prompt: 100% information capture verification
            final_completeness = self.validator._calculate_completeness(document)
            document.validation_metrics = ValidationMetrics(
                extraction_completeness=final_completeness,
                position_accuracy=0.0,  # Would need detailed position comparison
                content_accuracy=final_report.semantic_accuracy,
                discrepancy_report=[d.dict() for d in final_report.discrepancies]
            )
            
            if output_dir:
                self._save_validation_report(final_report, output_dir)
        
        # Generate comparison report (automatically after parsing)
        if output_dir:
            print("\nStep 9: Generating comparison report...")
            try:
                pdf_name = Path(pdf_path).stem
                structured_json_path = Path(output_dir) / f"{pdf_name}_structured.json"
                reconstructed_pdf_path = Path(output_dir) / f"{pdf_name}_reconstructed.pdf"
                validation_report_path = Path(output_dir) / "validation_report.json"
                
                # Only generate comparison if structured JSON exists
                if structured_json_path.exists():
                    self.comparison_analyzer.generate_comparison_report(
                        original_pdf_path=pdf_path,
                        structured_json_path=str(structured_json_path),
                        reconstructed_pdf_path=str(reconstructed_pdf_path) if reconstructed_pdf_path.exists() else None,
                        validation_report_path=str(validation_report_path) if validation_report_path.exists() else None,
                        output_dir=output_dir
                    )
                else:
                    print("Warning: Structured JSON not found, skipping comparison report")
            except Exception as e:
                print(f"Warning: Comparison report generation failed: {e}")
                import traceback
                traceback.print_exc()
        
        print("Processing complete!")
        return document
    
    def _build_pages(
        self,
        ocr_data: Dict[str, Any],
        layout_structure: Any
    ) -> list[PageData]:
        """
        Build page structure from OCR data.
        
        Following prompt requirement: 100% information capture - must include
        all visible elements (text, tables, images, headers, footers, watermarks).
        """
        pages = []
        
        for page_data in ocr_data.get("pages", []):
            page_num = page_data.get("page_number", 1)
            layout_elements = []
            
            # Convert text blocks to layout elements with complete format information
            # IMPORTANT: Extract every text block, even if empty, to ensure 100% capture
            for block in page_data.get("text_blocks", []):
                bbox_list = block.get("bbox", [0, 0, 0, 0])
                if len(bbox_list) >= 4:
                    bbox = BBox(
                        x=bbox_list[0],
                        y=bbox_list[1],
                        width=bbox_list[2] - bbox_list[0],
                        height=bbox_list[3] - bbox_list[1],
                        page=page_num - 1
                    )
                else:
                    bbox = BBox(x=0, y=0, width=0, height=0, page=page_num - 1)
                
                # Extract format information from block
                format_info = block.get("format", {})
                font_size = format_info.get("size")
                font_name = format_info.get("font", "")
                font_flags = format_info.get("flags", 0)
                
                # Convert PyMuPDF color to RGB (0-1)
                color = None
                color_val = format_info.get("color", 0)
                if color_val != 0:
                    # PyMuPDF color is packed as 0xRRGGBB
                    r = ((color_val >> 16) & 0xFF) / 255.0
                    g = ((color_val >> 8) & 0xFF) / 255.0
                    b = (color_val & 0xFF) / 255.0
                    color = [r, g, b]
                
                # Estimate alignment from x position (simple heuristic)
                alignment = None
                if bbox.width > 0:
                    page_width = page_data.get("width", 612)
                    left_margin = bbox.x / page_width
                    if left_margin < 0.1:
                        alignment = "left"
                    elif left_margin > 0.9:
                        alignment = "right"
                    else:
                        alignment = "center"
                
                # Calculate line spacing
                line_spacing = None
                if font_size and format_info.get("ascender"):
                    line_spacing = (format_info.get("ascender", 0) - format_info.get("descender", 0)) / font_size if font_size > 0 else None
                
                # Extract text - preserve all text including empty lines for 100% capture
                block_text = block.get("text", "")
                
                # Extract line-level information if available (for precise rendering)
                lines_info = block.get("lines", None)
                
                layout_element = LayoutElement(
                    type=ElementType.TEXT,
                    content=block_text,  # Include even empty text to preserve structure
                    bbox=bbox,
                    confidence=block.get("confidence", 0.8),
                    semantic_type=SemanticType.UNKNOWN,
                    raw_text=block_text,  # Preserve original text exactly
                    font_size=font_size,
                    font_name=font_name,
                    font_flags=font_flags,
                    color=color,
                    alignment=alignment,
                    line_spacing=line_spacing,
                    lines=lines_info  # Line-level info for precise rendering
                )
                layout_elements.append(layout_element)
            
            # Convert images to layout elements (following prompt: 100% capture)
            for img_data in page_data.get("images", []):
                img_bbox = img_data.get("bbox")
                if img_bbox:
                    if isinstance(img_bbox, list) and len(img_bbox) >= 4:
                        bbox = BBox(
                            x=img_bbox[0],
                            y=img_bbox[1],
                            width=img_bbox[2] - img_bbox[0] if len(img_bbox) > 2 else img_data.get("width", 0),
                            height=img_bbox[3] - img_bbox[1] if len(img_bbox) > 3 else img_data.get("height", 0),
                            page=page_num - 1
                        )
                    else:
                        bbox = BBox(
                            x=0, y=0,
                            width=img_data.get("width", 0),
                            height=img_data.get("height", 0),
                            page=page_num - 1
                        )
                else:
                    bbox = BBox(
                        x=0, y=0,
                        width=img_data.get("width", 0),
                        height=img_data.get("height", 0),
                        page=page_num - 1
                    )
                
                # Create image layout element
                image_element = LayoutElement(
                    type=ElementType.IMAGE,
                    content={
                        "index": img_data.get("index", 0),
                        "xref": img_data.get("xref"),
                        "ext": img_data.get("ext", ""),
                        "width": img_data.get("width", 0),
                        "height": img_data.get("height", 0)
                    },
                    bbox=bbox,
                    confidence=1.0,  # Images are typically 100% confidence
                    semantic_type=SemanticType.UNKNOWN,
                    raw_text=None
                )
                layout_elements.append(image_element)
            
            # CRITICAL: Convert drawings to layout elements (charts, graphics, paths)
            # Following prompt: 100% information capture - must include all visual elements
            # Drawings represent vector graphics, charts, logos drawn as paths
            # Note: Full reconstruction of complex drawings is difficult, but we should
            # at least capture their bounding boxes and basic info
            drawings_data = page_data.get("drawings", [])
            for drawing in drawings_data:
                drawing_rect = drawing.get("rect")
                if drawing_rect and len(drawing_rect) >= 4:
                    # Create a placeholder element for the drawing
                    # Actual rendering would require complex path reconstruction
                    bbox = BBox(
                        x=drawing_rect[0],
                        y=drawing_rect[1],
                        width=drawing_rect[2] - drawing_rect[0] if len(drawing_rect) > 2 else 0,
                        height=drawing_rect[3] - drawing_rect[1] if len(drawing_rect) > 3 else 0,
                        page=page_num - 1
                    )
                    
                    # Store drawing info in content
                    drawing_element = LayoutElement(
                        type=ElementType.IMAGE,  # Use IMAGE type as placeholder (drawings are visual)
                        content={
                            "type": "drawing",
                            "items_count": len(drawing.get("items", [])),
                            "drawing_data": drawing  # Store full drawing data for potential future use
                        },
                        bbox=bbox,
                        confidence=1.0,
                        semantic_type=SemanticType.UNKNOWN,
                        raw_text=None
                    )
                    layout_elements.append(drawing_element)
            
            # CRITICAL: Deduplicate overlapping elements before finalizing page
            # Following prompt requirement: preserve table form, remove duplicates, keep upper layer
            # This ensures tables are not rendered multiple times
            # Use ElementDeduplicator to intelligently remove duplicates while preserving table structure
            if layout_elements:
                # Use bank config for more intelligent table detection
                deduplicator = ElementDeduplicator(
                    position_tolerance=10.0,  # More lenient for table position differences
                    content_similarity_threshold=0.9  # High threshold for exact duplicates
                )
                # Adjust thresholds based on bank config if available
                if self.bank_config:
                    # Lower threshold for table content if bank config has table keywords
                    # Extract keywords from dict structure (transaction_keywords is a dict with deposit/withdrawal/balance keys)
                    transaction_kw = self.bank_config.get('transaction_keywords', {})
                    if isinstance(transaction_kw, dict):
                        # Flatten dict values into a single list
                        transaction_keywords_list = []
                        for key, value_list in transaction_kw.items():
                            if isinstance(value_list, list):
                                transaction_keywords_list.extend(value_list)
                    else:
                        transaction_keywords_list = transaction_kw if isinstance(transaction_kw, list) else []
                    
                    header_keywords = self.bank_config.get('header_keywords', [])
                    summary_keywords = self.bank_config.get('summary_keywords', [])
                    
                    table_keywords = transaction_keywords_list + \
                                    (header_keywords if isinstance(header_keywords, list) else []) + \
                                    (summary_keywords if isinstance(summary_keywords, list) else [])
                    if table_keywords:
                        deduplicator.table_content_similarity_threshold = 0.4  # Lower threshold for tables
                
                layout_elements = deduplicator.deduplicate_elements(layout_elements)
            
            # Extract page dimensions from OCR data
            page_width = page_data.get("width")
            page_height = page_data.get("height")
            
            pages.append(PageData(
                page_number=page_num,
                layout_elements=layout_elements,
                # Store page dimensions for reference
                page_width=page_width,
                page_height=page_height
            ))
        
        return pages
    
    def _save_results(
        self,
        document: BankDocument,
        output_dir: str,
        pdf_path: str,
        simplified_output: bool = True,
        external_transactions_data: Optional[Dict[str, Any]] = None  # 外部交易数据
    ):
        """Save processing results.
        
        Following prompt requirements:
        - Save structured JSON (required)
        - Export transactions to Excel (user requirement)
        - Ensure 100% information completeness in all outputs
        
        Args:
            simplified_output: 是否使用简化输出（默认True，仅输出业务数据+页码）
                              如果为False，输出完整版JSON（包含所有元数据）
        """
        os.makedirs(output_dir, exist_ok=True)
        
        # Save JSON output
        json_path = os.path.join(
            output_dir,
            f"{Path(pdf_path).stem}_structured.json"
        )
        
        # 根据配置选择输出格式
        if simplified_output:
            output_data = document.to_simplified_dict()
            print("✓ 使用简化输出模式（仅业务数据+页码，无bbox/confidence/raw_text等元数据）")
        else:
            output_data = document.dict()
            print("使用完整输出模式（包含所有元数据）")
        
        # 如果提供了外部交易数据，注入到输出JSON
        if external_transactions_data is not None:
            print("✓ 注入外部流水明细数据到输出JSON")
            from src.utils.external_data_adapter import inject_external_transactions_to_output
            output_data = inject_external_transactions_to_output(output_data, external_transactions_data)
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"Saved structured data to: {json_path}")
        
        # Export transactions to Excel
        # Following prompt: Export transaction data separately while maintaining all requirements
        transactions = document.structured_data.account_summary.transactions
        if transactions:
            excel_path = os.path.join(
                output_dir,
                f"{Path(pdf_path).stem}_transactions.xlsx"
            )
            try:
                self.excel_exporter.export_transactions_to_excel(
                    transactions=transactions,
                    output_path=excel_path,
                    document=document
                )
                print(f"Exported {len(transactions)} transactions to Excel: {excel_path}")
            except Exception as e:
                print(f"Warning: Failed to export transactions to Excel: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("No transactions found to export to Excel")
    
    def _save_validation_report(
        self,
        report: Any,
        output_dir: str
    ):
        """Save validation report."""
        report_path = os.path.join(output_dir, "validation_report.json")
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report.dict(), f, indent=2, ensure_ascii=False, default=str)
        
        print(f"Saved validation report to: {report_path}")


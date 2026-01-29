"""Pydantic models for structured bank document PDF data."""
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class ElementType(str, Enum):
    """Types of layout elements."""
    TEXT = "text"
    TABLE = "table"
    IMAGE = "image"
    HEADER = "header"
    FOOTER = "footer"


class SemanticType(str, Enum):
    """Semantic types of elements."""
    TRANSACTION = "transaction"
    BALANCE = "balance"
    HEADER = "header"
    FOOTER = "footer"
    SUMMARY = "summary"
    UNKNOWN = "unknown"


class BBox(BaseModel):
    """Bounding box coordinates."""
    x: float
    y: float
    width: float
    height: float
    page: int

    def to_list(self) -> List[float]:
        """Convert to list format [x, y, width, height]."""
        return [self.x, self.y, self.width, self.height]


class LayoutElement(BaseModel):
    """A single layout element from the document."""
    type: ElementType
    content: Union[str, Dict[str, Any]]
    bbox: BBox
    confidence: float = Field(ge=0.0, le=1.0)
    semantic_type: SemanticType
    raw_text: Optional[str] = None
    # Format information for precise PDF reconstruction
    font_size: Optional[float] = None
    font_name: Optional[str] = None
    font_flags: Optional[int] = None  # Bold, italic, etc.
    color: Optional[List[float]] = None  # RGB color [r, g, b] (0-1)
    alignment: Optional[str] = None  # left, center, right, justify
    line_spacing: Optional[float] = None
    char_spacing: Optional[float] = None
    # Line-level information for precise rendering (list of lines with individual bbox/format)
    lines: Optional[List[Dict[str, Any]]] = None  # Each line: {"text": str, "bbox": [x,y,w,h], "format": {...}}


class PageData(BaseModel):
    """Data for a single page."""
    page_number: int
    layout_elements: List[LayoutElement] = []
    page_width: Optional[float] = None  # Page width in points
    page_height: Optional[float] = None  # Page height in points


class Transaction(BaseModel):
    """A single transaction.
    
    Following prompt requirements:
    - 100% information completeness: All fields from BBVA tables included
    - Position information: BBox coordinates preserved
    - Traceability: Raw text and reference fields included
    - Strictly parse according to document structure without inference
    - Preserve original language and format
    """
    date: date  # Main date (FECHA) - kept for backward compatibility
    description: str  # DESCRIPCION - description without Referencia
    amount: Decimal  # Kept for backward compatibility
    balance: Optional[Decimal] = None  # Kept for backward compatibility
    reference: Optional[str] = None  # Kept for backward compatibility (without "Referencia" prefix)
    raw_text: str
    bbox: BBox
    # BBVA-specific fields (following prompt: dynamic adaptation, no hardcoding)
    # These fields are extracted dynamically from table headers
    oper_date: Optional[date] = None  # OPER - Operation date (ISO format, kept for backward compatibility)
    liq_date: Optional[date] = None  # LIQ - Liquidation date (ISO format, kept for backward compatibility)
    cargos: Optional[Decimal] = None  # CARGOS - Debits/charges (Decimal format, kept for backward compatibility)
    abonos: Optional[Decimal] = None  # ABONOS - Credits/deposits (Decimal format, kept for backward compatibility)
    operacion: Optional[Decimal] = None  # OPERACION - Operation amount (Decimal format, kept for backward compatibility)
    liquidacion: Optional[Decimal] = None  # LIQUIDACION - Liquidation amount (Decimal format, kept for backward compatibility)
    
    # BBVA fields in original format (following prompt: strictly parse according to document structure)
    # These fields preserve the original format from the document (strings with original formatting)
    OPER: Optional[str] = None  # OPER - Operation date in original format (e.g., "21/JUN")
    LIQ: Optional[str] = None  # LIQ - Liquidation date in original format (e.g., "23/JUN")
    DESCRIPCION: Optional[str] = None  # DESCRIPCION - Description without Referencia
    REFERENCIA: Optional[str] = None  # REFERENCIA - Reference with "Referencia" prefix (e.g., "Referencia ******6929")
    CARGOS: Optional[str] = None  # CARGOS - Debits/charges in original format (e.g., "7,200.00")
    ABONOS: Optional[str] = None  # ABONOS - Credits/deposits in original format (e.g., "" or "24,360.00")
    OPERACION: Optional[str] = None  # OPERACION - Operation amount in original format (e.g., "5,183.20")
    LIQUIDACION: Optional[str] = None  # LIQUIDACION - Liquidation amount in original format (e.g., "12,383.20")
    
    # Confidence score (following prompt: mark uncertain data with low confidence)
    # Range: 0.0 (uncertain) to 1.0 (high confidence)
    # Based on field completeness, format correctness, and extraction method
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Confidence score for transaction extraction accuracy")
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            date: lambda v: v.isoformat() if v else None,
            Decimal: lambda v: str(v) if v else None,
        }

    def to_simplified_dict(self) -> Dict[str, Any]:
        """
        生成简化的交易记录。
        保留所有业务字段，移除raw_text, bbox, confidence等技术字段。
        """
        from datetime import date
        
        simple = {}
        
        # 基础字段
        if self.date:
            simple["date"] = self.date.isoformat() if isinstance(self.date, date) else self.date
        if self.description:
            simple["description"] = self.description
        if self.amount is not None:
            simple["amount"] = str(self.amount)
        if self.balance is not None:
            simple["balance"] = str(self.balance)
        if self.reference:
            simple["reference"] = self.reference
            
        # BBVA特定字段
        if self.oper_date:
            simple["oper_date"] = self.oper_date.isoformat() if isinstance(self.oper_date, date) else self.oper_date
        if self.liq_date:
            simple["liq_date"] = self.liq_date.isoformat() if isinstance(self.liq_date, date) else self.liq_date
        
        if self.cargos is not None: simple["cargos"] = str(self.cargos)
        if self.abonos is not None: simple["abonos"] = str(self.abonos)
        
        # 原始解析字段 - 保持原样字符串
        if self.DESCRIPCION: simple["DESCRIPCION"] = self.DESCRIPCION
        if self.REFERENCIA: simple["REFERENCIA"] = self.REFERENCIA
        if self.CARGOS: simple["CARGOS"] = self.CARGOS
        if self.ABONOS: simple["ABONOS"] = self.ABONOS
        if self.OPERACION: simple["OPERACION"] = self.OPERACION
        if self.LIQUIDACION: simple["LIQUIDACION"] = self.LIQUIDACION
        
        # 页码 (如果有)
        if hasattr(self.bbox, 'page') and self.bbox.page is not None:
            simple["page"] = self.bbox.page + 1  # 转换为1-based
            
        return simple


class AccountSummary(BaseModel):
    """Account summary information."""
    initial_balance: Optional[Decimal] = None
    deposits: Optional[Decimal] = None
    withdrawals: Optional[Decimal] = None
    final_balance: Optional[Decimal] = None
    transactions: List[Transaction] = []
    # Raw transaction data from grid extractor (preserves original format)
    raw_transaction_data: Optional[Dict[str, Any]] = None
    # Store original table headers for dynamic Excel export (following prompt: no hardcoding)
    transaction_table_headers: Optional[List[str]] = None  # Original column headers from transaction table
    
    # 新增业务字段 - 从BBVA文档提取的额外信息
    total_movimientos: Optional[Dict[str, Any]] = None  # (用户反馈重要，已恢复)
    apartados_vigentes: Optional[List[Dict[str, Any]]] = None  # (用户反馈重要，已恢复)
    branch_info: Optional[Dict[str, str]] = None  # 分支机构信息 (Screenshot 2)
    pages_info: Optional[List[Dict[str, str]]] = None # 每页的头部信息
    cuadro_resumen: Optional[List[Dict[str, Any]]] = None  # Cuadro resumen y gráfico (改为List以适应多行)
    informacion_financiera: Optional[Dict[str, Any]] = None  # Información Financiera表格
    comportamiento: Optional[Dict[str, Any]] = None  # Comportamiento表格
    customer_info: Optional[Dict[str, str]] = None  # Header info (Screenshot 1)
    otros_productos: Optional[Dict[str, Any]] = None  # Otros productos + Total de Apartados (Screenshot 2)


class StructuredData(BaseModel):
    """Structured data extracted from the document."""
    account_summary: AccountSummary


class ValidationMetrics(BaseModel):
    """Validation metrics."""
    extraction_completeness: float = Field(ge=0.0, le=100.0)
    position_accuracy: float
    content_accuracy: float = Field(ge=0.0, le=100.0)
    discrepancy_report: List[Dict[str, Any]] = []


class Metadata(BaseModel):
    """Document metadata."""
    document_type: Optional[str] = None  # No hardcoded default - detect from document
    bank: Optional[str] = None  # No hardcoded default - detect from document
    account_number: Optional[str] = None
    period: Optional[Dict[str, Optional[date]]] = None
    total_pages: int
    language: Optional[str] = None  # Detected document language


class BankDocument(BaseModel):
    """Complete bank document structure (generic, not bank-specific)."""
    metadata: Metadata
    pages: List[PageData]
    structured_data: StructuredData
    validation_metrics: ValidationMetrics
    
    def to_simplified_dict(self) -> Dict[str, Any]:
        """
        生成简化的文档输出。
        
        保留: 所有业务内容（结构化数据）
        删除: pages数组, validation_metrics, 所有bbox/confidence信息等技术元数据
        
        Returns:
            简化的字典，包含所有业务数据但无技术元数据
        """
        from datetime import date
        
        simplified = {
            "metadata": {
                "document_type": self.metadata.document_type,
                "bank": self.metadata.bank,
                "account_number": self.metadata.account_number,
                "total_pages": self.metadata.total_pages,
            }
        }
        
        # 添加language字段（如果存在）
        if hasattr(self.metadata, 'language') and self.metadata.language:
            simplified["metadata"]["language"] = self.metadata.language
        
        # 添加period信息（如果存在）
        if self.metadata.period:
            period_dict = {}
            if self.metadata.period.get("start"):
                start = self.metadata.period["start"]
                period_dict["start"] = start.isoformat() if isinstance(start, date) else start
            if self.metadata.period.get("end"):
                end = self.metadata.period["end"]
                period_dict["end"] = end.isoformat() if isinstance(end, date) else end
            if period_dict:
                simplified["metadata"]["period"] = period_dict
        
        # 构建简化的structured_data
        simplified["structured_data"] = {
            "account_summary": {}
        }
        
        account_summary = self.structured_data.account_summary
        
        # 1. Customer Info (Top of JSON)
        if account_summary.customer_info:
            simplified["structured_data"]["account_summary"]["customer_info"] = account_summary.customer_info
            
        # 2. Pages Info (Headers per page)
        if account_summary.pages_info:
            simplified["structured_data"]["account_summary"]["pages_info"] = account_summary.pages_info
            
        # 3. Branch Info
        if account_summary.branch_info:
            simplified["structured_data"]["account_summary"]["branch_info"] = account_summary.branch_info

        # 4. Standard Balances
        if account_summary.initial_balance is not None:
             simplified["structured_data"]["account_summary"]["initial_balance"] = str(account_summary.initial_balance)
        if account_summary.deposits is not None:
            simplified["structured_data"]["account_summary"]["deposits"] = str(account_summary.deposits)
        if account_summary.withdrawals is not None:
            simplified["structured_data"]["account_summary"]["withdrawals"] = str(account_summary.withdrawals)
        if account_summary.final_balance is not None:
            simplified["structured_data"]["account_summary"]["final_balance"] = str(account_summary.final_balance)
            
        # 5. Financial Info & Behavior (Summary Tables)
        # User feedback: "Cuadro resumen... location wrong, should be at end"
        # However, checking schemas.py current logic:
        # Standard Balances -> Cuadro Resumen -> Informacion Financiera -> Comportamiento -> Otros Productos
        # This seems to match the document flow (Body -> Bottom).
        # We will keep it here but ensure fields inside are ordered.
        
        if account_summary.informacion_financiera:
            simplified["structured_data"]["account_summary"]["informacion_financiera"] = account_summary.informacion_financiera
        
        if account_summary.comportamiento:
            simplified["structured_data"]["account_summary"]["comportamiento"] = account_summary.comportamiento
            
        # 6. Other Products
        if account_summary.otros_productos:
            simplified["structured_data"]["account_summary"]["otros_productos"] = account_summary.otros_productos
        
        # 7. Transactions Header (skip - not needed for raw format)
        # if account_summary.transaction_table_headers:
        #     simplified["structured_data"]["account_summary"]["transaction_table_headers"] = \
        #         account_summary.transaction_table_headers
        
        # 8. Transactions (Body) - REMOVED to avoid duplication with raw_transaction_data
        # User wants only raw_transaction_data format
        # simplified["structured_data"]["account_summary"]["transactions"] = [
        #     t.to_simplified_dict() for t in account_summary.transactions
        # ]
        
        # 8b. Raw Transaction Data (Grid extractor original format - preserves JSON structure)
        if account_summary.raw_transaction_data:
            simplified["structured_data"]["account_summary"]["raw_transaction_data"] = account_summary.raw_transaction_data
            
        # 9. Total Movimientos (Footer - AFTER transactions per User Request)
        if account_summary.total_movimientos:
             simplified["structured_data"]["account_summary"]["total_movimientos"] = account_summary.total_movimientos
        
        # 10. Apartados (Footer - AFTER Total Movimientos)
        if account_summary.apartados_vigentes:
             simplified["structured_data"]["account_summary"]["apartados_vigentes"] = account_summary.apartados_vigentes
        
        # 11. Cuadro Resumen (Moved to end per user request)
        if account_summary.cuadro_resumen:
            simplified["structured_data"]["account_summary"]["cuadro_resumen"] = account_summary.cuadro_resumen
        
        return simplified

# Backward compatibility alias (will be deprecated)
BBVADocument = BankDocument


class Discrepancy(BaseModel):
    """A single discrepancy found during validation."""
    type: str
    location: Optional[BBox] = None
    original_value: Optional[str] = None
    extracted_value: Optional[str] = None
    severity: str
    description: str


class ValidationReport(BaseModel):
    """Complete validation report."""
    pixel_accuracy: float = Field(ge=0.0, le=100.0)
    semantic_accuracy: float = Field(ge=0.0, le=100.0)
    discrepancies: List[Discrepancy] = []
    is_valid: bool
    critical_checks: Dict[str, bool] = {}

"""Data models for bank document PDF parsing system."""
from .schemas import (
    BBox,
    LayoutElement,
    PageData,
    Transaction,
    AccountSummary,
    StructuredData,
    ValidationMetrics,
    BankDocument,
    BBVADocument,  # Backward compatibility alias
    ValidationReport,
    Discrepancy,
)

__all__ = [
    "BBox",
    "LayoutElement",
    "PageData",
    "Transaction",
    "AccountSummary",
    "StructuredData",
    "ValidationMetrics",
    "BankDocument",
    "BBVADocument",  # Backward compatibility
    "ValidationReport",
    "Discrepancy",
]


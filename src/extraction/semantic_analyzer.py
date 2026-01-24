"""Semantic analysis using LLM."""
from typing import Any, Dict, List, Optional


class SemanticAnalyzer:
    """Perform semantic analysis using LLM."""
    
    def __init__(self, llm_client: Optional[Any] = None):
        """Initialize semantic analyzer."""
        self.llm_client = llm_client
    
    def analyze_semantics(
        self,
        ocr_data: Dict[str, Any],
        extracted_data: Any
    ) -> Dict[str, Any]:
        """
        Perform semantic analysis on extracted data.
        
        Args:
            ocr_data: OCR output
            extracted_data: Extracted structured data
            
        Returns:
            Semantic analysis results
        """
        if not self.llm_client:
            return {"semantic_analysis": "LLM not available", "status": "skipped"}
        
        # Build analysis prompt
        prompt = self._build_analysis_prompt(ocr_data, extracted_data)
        
        try:
            # Extract structured data summary for LLM
            data_summary = self._extract_data_summary(extracted_data)
            
            # Call LLM for semantic validation
            if hasattr(self.llm_client, 'validate_fields'):
                enhanced_prompt = prompt + f"\n\n提取的数据摘要：\n{data_summary}\n\n请以JSON格式返回分析结果。"
                result = self.llm_client.validate_fields(enhanced_prompt, {"analysis": {}})
                return {
                    "status": "completed",
                    "analysis": result.get("analysis", {}),
                    "issues": result.get("issues", []),
                    "recommendations": result.get("recommendations", [])
                }
            else:
                return {"status": "completed", "note": "LLM client does not support validation"}
        except Exception as e:
            print(f"Semantic analysis failed: {e}")
            return {"semantic_analysis": "failed", "error": str(e)}
    
    def _extract_data_summary(self, extracted_data: Any) -> str:
        """Extract summary of structured data for LLM analysis."""
        try:
            summary_parts = []
            
            # Extract metadata if available
            if hasattr(extracted_data, 'metadata'):
                metadata = extracted_data.metadata
                summary_parts.append(f"账户号: {getattr(metadata, 'account_number', '未找到')}")
                summary_parts.append(f"文档类型: {getattr(metadata, 'document_type', '未知')}")
            
            # Extract transaction summary
            if hasattr(extracted_data, 'structured_data'):
                structured = extracted_data.structured_data
                if hasattr(structured, 'account_summary'):
                    account_summary = structured.account_summary
                    summary_parts.append(f"初始余额: {getattr(account_summary, 'initial_balance', '未找到')}")
                    summary_parts.append(f"最终余额: {getattr(account_summary, 'final_balance', '未找到')}")
                    summary_parts.append(f"交易数量: {len(getattr(account_summary, 'transactions', []))}")
            
            return "\n".join(summary_parts) if summary_parts else "无数据摘要"
        except Exception as e:
            return f"提取摘要时出错: {str(e)}"
    
    def _build_analysis_prompt(
        self,
        ocr_data: Dict[str, Any],
        extracted_data: Any
    ) -> str:
        """Build prompt for semantic analysis."""
        prompt = """作为银行文档专家，请分析以下银行对账单的提取数据：

请验证：
1. 数据完整性
2. 逻辑一致性（如余额计算）
3. 格式正确性
4. 可能的错误或缺失

返回分析结果。
"""
        return prompt


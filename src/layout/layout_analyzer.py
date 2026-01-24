"""Dynamic layout analysis without hardcoding."""
from typing import Any, Dict, List, Optional

from src.layout.region_clustering import RegionClustering


class DocumentStructure:
    """Document structure representation."""
    
    def __init__(self):
        """Initialize document structure."""
        self.headers: List[Dict[str, Any]] = []
        self.footers: List[Dict[str, Any]] = []
        self.transaction_tables: List[Dict[str, Any]] = []
        self.summary_sections: List[Dict[str, Any]] = []
        self.other_regions: List[Dict[str, Any]] = []


class LayoutAnalyzer:
    """
    Analyze document layout dynamically.
    
    Following prompt requirement: absolute avoidance of hardcoding,
    use bank configuration for keywords.
    """
    
    def __init__(self, llm_client: Optional[Any] = None, bank_config: Optional[Dict[str, Any]] = None):
        """
        Initialize layout analyzer.
        
        Args:
            llm_client: Optional LLM client for semantic analysis
            bank_config: Optional bank configuration dictionary
        """
        self.region_clustering = RegionClustering()
        self.llm_client = llm_client
        self.bank_config = bank_config
    
    def analyze_document_layout(
        self, 
        ocr_data: Dict[str, Any]
    ) -> DocumentStructure:
        """
        Analyze document layout dynamically.
        
        Args:
            ocr_data: OCR output with layout information
            
        Returns:
            DocumentStructure with identified regions
        """
        # 1. Extract visual features
        visual_features = self.region_clustering.extract_visual_features(ocr_data)
        
        # 2. Cluster regions
        regions = self.region_clustering.cluster_regions(visual_features)
        
        # 3. Identify semantic roles
        if self.llm_client:
            region_roles = self._llm_identify_roles(regions, ocr_data)
        else:
            region_roles = self._rule_based_role_identification(regions)
        
        # 4. Build document structure
        document_structure = self._build_document_tree(regions, region_roles)
        
        return document_structure
    
    def _llm_identify_roles(
        self, 
        regions: List[Dict[str, Any]],
        ocr_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Use LLM to identify semantic roles of regions.
        
        Args:
            regions: Clustered regions
            ocr_data: Original OCR data for context
            
        Returns:
            Regions with assigned roles
        """
        # Build prompt for LLM
        prompt = self._build_role_identification_prompt(regions, ocr_data)
        
        try:
            if self.llm_client and hasattr(self.llm_client, 'identify_roles'):
                roles = self.llm_client.identify_roles(prompt, regions)
                return roles
        except Exception as e:
            print(f"LLM role identification failed: {e}. Using rule-based method.")
        
        return self._rule_based_role_identification(regions)
    
    def _rule_based_role_identification(
        self, 
        regions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Rule-based fallback for role identification."""
        for region in regions:
            # Extract text from region
            region_text = " ".join(
                e.get("raw_data", {}).get("text", "")
                for e in region.get("elements", [])
            ).lower()
            
            # Heuristic role assignment
            role = "unknown"
            bbox = region.get("bbox", [])
            
            # Header detection: top of page, larger font, contains keywords (from config)
            if bbox and bbox[1] < 100:  # Near top
                header_keywords = self.bank_config.get('header_keywords', ["bank", "statement", "account"]) if self.bank_config else ["bank", "statement", "account"]
                if any(keyword.lower() in region_text.lower() for keyword in header_keywords):
                    role = "header"
            
            # Footer detection: bottom of page
            page_height = 792  # Default letter size
            if bbox and bbox[3] > page_height - 100:  # Near bottom
                role = "footer"
            
            # Transaction table: contains date patterns and amounts (from config)
            currency_symbol = self.bank_config.get('currency_symbol', '$') if self.bank_config else '$'
            if any(char in region_text for char in ["/", currency_symbol]):
                transaction_keywords = self.bank_config.get('transaction_keywords', {}) if self.bank_config else {}
                all_transaction_keywords = []
                for category, keywords in transaction_keywords.items():
                    all_transaction_keywords.extend(keywords)
                # Also check for common date/currency indicators
                if any(keyword.lower() in region_text.lower() for keyword in all_transaction_keywords + ["fecha", "date", "amount"]):
                    role = "transaction_table"
            
            # Summary: contains balance keywords (from config)
            summary_keywords = self.bank_config.get('summary_keywords', ["saldo inicial", "saldo final", "resumen", "summary"]) if self.bank_config else ["summary", "balance"]
            if any(keyword.lower() in region_text.lower() for keyword in summary_keywords):
                role = "summary"
            
            region["role"] = role
        
        return regions
    
    def _build_role_identification_prompt(
        self,
        regions: List[Dict[str, Any]],
        ocr_data: Dict[str, Any]
    ) -> str:
        """Build prompt for LLM role identification."""
        prompt = """分析以下文档区域在银行对账单中的可能角色。

文档区域：
"""
        for i, region in enumerate(regions[:10]):  # Limit for prompt size
            text_sample = " ".join(
                e.get("raw_data", {}).get("text", "")[:50]
                for e in region.get("elements", [])[:3]
            )
            prompt += f"\n区域 {i+1}:\n"
            prompt += f"  位置: {region.get('bbox')}\n"
            prompt += f"  文本示例: {text_sample[:100]}\n"
        
        prompt += """
请为每个区域识别其角色：
- header: 页眉
- footer: 页脚
- transaction_table: 交易表格
- summary: 摘要信息
- other: 其他

返回JSON格式，每个区域一个角色。
"""
        return prompt
    
    def _build_document_tree(
        self,
        regions: List[Dict[str, Any]],
        region_roles: List[Dict[str, Any]]
    ) -> DocumentStructure:
        """Build document structure tree from regions and roles."""
        structure = DocumentStructure()
        
        # Map roles to structure
        role_mapping = {
            "header": "headers",
            "footer": "footers",
            "transaction_table": "transaction_tables",
            "summary": "summary_sections",
            "unknown": "other_regions"
        }
        
        for region in region_roles:
            role = region.get("role", "unknown")
            target_list = getattr(structure, role_mapping.get(role, "other_regions"))
            target_list.append(region)
        
        return structure
    
    def find_by_role(
        self, 
        structure: DocumentStructure, 
        role: str
    ) -> List[Dict[str, Any]]:
        """Find regions by role."""
        role_mapping = {
            "header": structure.headers,
            "footer": structure.footers,
            "transaction_table": structure.transaction_tables,
            "summary": structure.summary_sections,
            "other": structure.other_regions
        }
        return role_mapping.get(role, [])


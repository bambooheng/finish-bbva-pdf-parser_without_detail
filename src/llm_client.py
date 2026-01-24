"""LLM client wrapper for semantic analysis."""
from typing import Any, Dict, List, Optional

from src.config import config


class LLMClient:
    """Unified LLM client interface."""
    
    def __init__(self):
        """Initialize LLM client."""
        self.provider = config.get('llm.provider', 'anthropic')
        self.model = config.get('llm.model', 'claude-3-opus-20240229')
        self.api_key = config.get_llm_api_key()
        self.client = None
        
        if self.api_key:
            self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the appropriate LLM client."""
        if self.provider == 'anthropic':
            try:
                from anthropic import Anthropic
                self.client = Anthropic(api_key=self.api_key)
            except ImportError:
                print("Anthropic library not installed. LLM features disabled.")
        
        elif self.provider == 'openai':
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=self.api_key)
            except ImportError:
                print("OpenAI library not installed. LLM features disabled.")
    
    def validate_fields(
        self,
        prompt: str,
        fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate fields using LLM."""
        if not self.client:
            return fields  # Return unchanged if no LLM
        
        try:
            if self.provider == 'anthropic':
                message = self.client.messages.create(
                    model=self.model,
                    max_tokens=config.get('llm.max_tokens', 4096),
                    temperature=config.get('llm.temperature', 0.1),
                    messages=[{
                        "role": "user",
                        "content": prompt + "\n\n请以JSON格式返回验证结果，包含校正后的字段值和置信度。"
                    }]
                )
                # Parse Claude response
                response_text = message.content[0].text if hasattr(message.content[0], 'text') else str(message.content)
                validated = self._parse_llm_json_response(response_text, fields)
                return validated
            
            elif self.provider == 'openai':
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{
                        "role": "user",
                        "content": prompt + "\n\nPlease return validation results in JSON format with corrected field values and confidence scores."
                    }],
                    temperature=config.get('llm.temperature', 0.1),
                    response_format={"type": "json_object"} if hasattr(self.client.chat.completions, 'create') else None
                )
                # Parse OpenAI response
                response_text = response.choices[0].message.content
                validated = self._parse_llm_json_response(response_text, fields)
                return validated
        
        except Exception as e:
            print(f"LLM validation error: {e}")
            return fields
    
    def _parse_llm_json_response(
        self,
        response_text: str,
        original_fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Parse JSON response from LLM and update fields."""
        import json
        import re
        
        # Try to extract JSON from response (might be wrapped in markdown code blocks)
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find JSON object directly
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                # If no JSON found, return original fields
                print(f"Warning: Could not extract JSON from LLM response")
                return original_fields
        
        try:
            validated_data = json.loads(json_str)
            
            # Merge validated data back into original fields structure
            # This preserves the structure while updating validated values
            validated_fields = original_fields.copy()
            
            # Update fields based on LLM response
            for field_type in validated_fields.keys():
                if field_type in validated_data:
                    # LLM might return a list of validated fields
                    if isinstance(validated_data[field_type], list):
                        validated_fields[field_type] = validated_data[field_type]
                    elif isinstance(validated_data[field_type], dict):
                        # Update individual fields
                        for idx, field in enumerate(validated_fields.get(field_type, [])):
                            if str(idx) in validated_data[field_type]:
                                validated_fields[field_type][idx].update(
                                    validated_data[field_type][str(idx)]
                                )
            
            return validated_fields
        except json.JSONDecodeError as e:
            print(f"Error parsing LLM JSON response: {e}")
            return original_fields
    
    def identify_roles(
        self,
        prompt: str,
        regions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Identify semantic roles using LLM."""
        if not self.client:
            return regions  # Return unchanged
        
        try:
            enhanced_prompt = prompt + "\n\n请以JSON格式返回，格式为：{\"regions\": [{\"index\": 0, \"role\": \"header\"}, ...]}"
            
            if self.provider == 'anthropic':
                message = self.client.messages.create(
                    model=self.model,
                    max_tokens=config.get('llm.max_tokens', 4096),
                    temperature=config.get('llm.temperature', 0.1),
                    messages=[{"role": "user", "content": enhanced_prompt}]
                )
                response_text = message.content[0].text if hasattr(message.content[0], 'text') else str(message.content)
            
            elif self.provider == 'openai':
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": enhanced_prompt}],
                    temperature=config.get('llm.temperature', 0.1)
                )
                response_text = response.choices[0].message.content
            
            # Parse response and update regions
            roles_data = self._parse_llm_json_response(response_text, {"regions": regions})
            
            if "regions" in roles_data:
                role_list = roles_data["regions"]
                # Update regions with identified roles
                for idx, region in enumerate(regions):
                    if idx < len(role_list) and "role" in role_list[idx]:
                        region["role"] = role_list[idx]["role"]
            
            return regions
        except Exception as e:
            print(f"LLM role identification error: {e}")
            return regions


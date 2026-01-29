"""
统一配置管理模块
Configuration management for PDF to JSON converter
"""
import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Configuration class for managing API keys and settings"""
    
    def __init__(self):
        # API Configuration
        self.gemini_api_key: str = os.getenv('GEMINI_API_KEY', '')
        self.gemini_model: str = os.getenv('GEMINI_MODEL', 'gemini-3-flash-preview')
        self.base_url: str = "https://api.vectorengine.ai/v1beta/models"
        
        # PDF Processing Configuration
        self.dpi: int = int(os.getenv('DPI', '300'))
        self.max_workers: int = int(os.getenv('MAX_WORKERS', '5'))
        self.skip_blue_cover: bool = os.getenv('SKIP_BLUE_COVER', 'true').lower() == 'true'
        
        # JSON Output Configuration
        self.json_indent: int = int(os.getenv('JSON_INDENT', '2'))
        self.include_raw_text: bool = os.getenv('INCLUDE_RAW_TEXT', 'false').lower() == 'true'
        
        # Model Parameters
        self.temperature: float = float(os.getenv('TEMPERATURE', '0.1'))
        self.max_output_tokens: int = int(os.getenv('MAX_OUTPUT_TOKENS', '65536'))
        
    def validate(self) -> bool:
        """Validate configuration settings"""
        if not self.gemini_api_key:
            raise ValueError(
                "GEMINI_API_KEY environment variable is not set. "
                "Please create a .env file based on .env.example"
            )
        return True
    
    def __repr__(self) -> str:
        return (
            f"Config(model={self.gemini_model}, "
            f"dpi={self.dpi}, max_workers={self.max_workers}, "
            f"json_indent={self.json_indent})"
        )


# Global config instance
config = Config()

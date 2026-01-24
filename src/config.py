"""Configuration management."""
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Config:
    """Configuration manager."""
    
    _instance = None
    
    def __new__(cls, config_path: str = None):
        """Singleton pattern to ensure single config instance."""
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, config_path: str = None):
        """Initialize configuration."""
        import os
        if config_path is None:
            config_path = os.getenv('CONFIG_PATH', 'config.yaml')
        self.config_path = config_path
        self.config = self._load_config()
        self._load_env_vars()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        if not os.path.exists(self.config_path):
            return self._default_config()
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    
    def _default_config(self) -> Dict[str, Any]:
        """Return default configuration."""
        return {
            'mineru': {
                'python_path': r"D:\Computer\Anaconda\envs\mineru\python.exe",
                'timeout': 300
            },
            'ocr': {
                'primary_engine': 'mineru',
                'confidence_threshold': 0.7,
                'dual_verification_enabled': True
            },
            'llm': {
                'provider': 'anthropic',
                'model': 'claude-3-opus-20240229',
                'api_key_env': 'ANTHROPIC_API_KEY',
                'temperature': 0.1,
                'max_tokens': 4096
            },
            'validation': {
                'pixel_tolerance': 1,
                'enable_pdf_rebuild': True,
                'enable_pixel_comparison': True,
                'enable_semantic_validation': True,
                'min_confidence': 0.8
            },
            'output': {
                'save_intermediate_results': True,
                'output_directory': 'output',
                'detailed_reports': True
            }
        }
    
    def _load_env_vars(self):
        """Load environment variables."""
        # LLM API keys are loaded via dotenv
        pass
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """Get configuration value by dot-separated path."""
        keys = key_path.split('.')
        value = self.config
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return default
            else:
                return default
        return value
    
    def get_mineru_python(self) -> str:
        """Get MinerU Python executable path."""
        return self.get('mineru.python_path', 
                       r"D:\Computer\Anaconda\envs\mineru\python.exe")
    
    def get_llm_api_key(self) -> Optional[str]:
        """Get LLM API key from environment."""
        provider = self.get('llm.provider', 'anthropic')
        env_key = self.get('llm.api_key_env', 'ANTHROPIC_API_KEY')
        return os.getenv(env_key)
    
    @property
    def mineru_timeout(self) -> int:
        """Get MinerU timeout in seconds."""
        return self.get('mineru.timeout', 300)
    
    @property
    def ocr_confidence_threshold(self) -> float:
        """Get OCR confidence threshold."""
        return self.get('ocr.confidence_threshold', 0.7)
    
    @property
    def pixel_tolerance(self) -> int:
        """Get pixel tolerance for validation."""
        return self.get('validation.pixel_tolerance', 1)
    
    @property
    def output_directory(self) -> str:
        """Get output directory."""
        return self.get('output.output_directory', 'output')


# Global config instance
config = Config()


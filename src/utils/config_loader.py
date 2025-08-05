"""
Configuration loader
"""

import json
import os
from typing import Dict
from pathlib import Path

def load_config(config_path: str = None) -> Dict:
    """Load configuration from JSON file"""
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "config" / "config.json"
        
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
    with open(config_path, 'r') as f:
        config = json.load(f)
        
    # Validate required sections
    required = ['alerts', 'risk_management', 'ibkr', 'logging', 'system', 'state']
    for section in required:
        if section not in config:
            raise ValueError(f"Missing required config section: {section}")
            
    return config

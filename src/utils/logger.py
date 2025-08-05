"""
Logging setup
"""

import logging
import os
from datetime import datetime
from pathlib import Path

def setup_logging(config: dict):
    """Setup logging configuration"""
    # Create logs directory
    log_dir = Path(__file__).parent.parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    
    # Get config values
    level = config.get('level', 'INFO')
    format_str = config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Create filename with date
    filename = log_dir / f'holly_ibkr_{datetime.now().strftime("%Y%m%d")}.log'
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, level),
        format=format_str,
        handlers=[
            logging.FileHandler(filename),
            logging.StreamHandler()
        ]
    )
    
    # Set third-party loggers to WARNING
    logging.getLogger('ib_insync').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)

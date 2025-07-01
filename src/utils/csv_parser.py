"""Holly AI CSV Alert Parser"""
import pandas as pd
import os
from datetime import datetime
from typing import Dict, List, Optional
from loguru import logger
import json

class HollyAlertParser:
    def __init__(self, config_path: str = "config/config.json"):
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        self.csv_path = self.config['alerts']['csv_path']
        self.processed_alerts = set()
        self.columns = self.config['alerts']['columns']
        
    def parse_alerts(self) -> List[Dict]:
        """Parse new alerts from CSV file"""
        try:
            if not os.path.exists(self.csv_path):
                logger.warning(f"CSV file not found: {self.csv_path}")
                return []
                
            # Read CSV with proper parsing
            df = pd.read_csv(self.csv_path, parse_dates=[self.columns['timestamp']])
            
            # Filter new alerts
            new_alerts = []
            for idx, row in df.iterrows():
                alert_id = f"{row[self.columns['timestamp']]}_{row[self.columns['symbol']]}"
                
                if alert_id not in self.processed_alerts:
                    alert = self._process_alert(row)
                    if alert:
                        new_alerts.append(alert)
                        self.processed_alerts.add(alert_id)
                        
            if new_alerts:
                logger.info(f"Found {len(new_alerts)} new alerts")
                
            return new_alerts
            
        except Exception as e:
            logger.error(f"Error parsing CSV: {e}")
            return []
    
    def _process_alert(self, row) -> Optional[Dict]:
        """Process individual alert row"""
        try:
            # Parse description for trading signals
            description = row[self.columns['description']]
            
            # Extract resistance level from description
            resistance = None
            if "Next resistance" in description:
                parts = description.split("Next resistance")
                if len(parts) > 1:
                    resistance = float(parts[1].split()[0])
            
            alert = {
                'timestamp': row[self.columns['timestamp']],
                'symbol': row[self.columns['symbol']],
                'type': row[self.columns['type']],
                'description': description,
                'price': float(row[self.columns['price']]),
                'volume': float(row[self.columns['volume']]),
                'resistance': resistance,
                'signal': 'BUY' if 'New High' in description else None
            }
            
            return alert
            
        except Exception as e:
            logger.error(f"Error processing alert: {e}")
            return None

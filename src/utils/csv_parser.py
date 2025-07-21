"""Holly AI CSV Alert Parser - Updated for daily file format"""
import pandas as pd
import os
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path
from loguru import logger
import json
import time

class HollyAlertParser:
    def __init__(self, config_path: str = "config/config.json"):
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        # Get base path and strategy name from config
        self.base_path = self.config['alerts']['csv_path']
        self.strategy_name = self.config['alerts'].get('strategy_name', 'Breaking out on Volume')
        self.file_prefix = self.config['alerts'].get('file_prefix', 'alertlogging')
        
        self.processed_alerts = set()
        self.columns = self.config['alerts']['columns']
        self.current_file = None
        self.last_file_check = None
        
    def get_todays_csv_file(self) -> Optional[str]:
        """Get today's CSV file path"""
        # Format: alertlogging.Breaking out on Volume.20250715.csv
        today = datetime.now().strftime("%Y%m%d")
        filename = f"{self.file_prefix}.{self.strategy_name}.{today}.csv"
        
        # Get directory from base_path
        if os.path.isdir(self.base_path):
            file_path = os.path.join(self.base_path, filename)
        else:
            # If base_path is a file, use its directory
            directory = os.path.dirname(self.base_path)
            file_path = os.path.join(directory, filename)
        
        return file_path
    
    def wait_for_todays_file(self, timeout: int = 300) -> Optional[str]:
        """Wait for today's file to be created (useful at market open)"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            file_path = self.get_todays_csv_file()
            if os.path.exists(file_path):
                logger.info(f"Found today's CSV file: {file_path}")
                return file_path
            
            logger.debug(f"Waiting for file: {file_path}")
            time.sleep(5)  # Check every 5 seconds
        
        logger.warning(f"Timeout waiting for today's CSV file")
        return None
        
    def parse_alerts(self) -> List[Dict]:
        """Parse new alerts from CSV file"""
        try:
            # Get today's file
            csv_path = self.get_todays_csv_file()
            
            # Check if we need to switch to a new file (new trading day)
            if csv_path != self.current_file:
                logger.info(f"Switching to new file: {csv_path}")
                self.current_file = csv_path
                # Reset processed alerts for new day
                self.processed_alerts = set()
            
            if not os.path.exists(csv_path):
                # Try to wait for file if it's early in the trading day
                current_time = datetime.now()
                market_open = current_time.replace(hour=9, minute=30, second=0)
                
                # If it's near market open, wait for file
                if market_open <= current_time <= market_open.replace(hour=10):
                    logger.info("Near market open, waiting for CSV file...")
                    csv_path = self.wait_for_todays_file()
                    if not csv_path:
                        return []
                else:
                    logger.debug(f"CSV file not found: {csv_path}")
                    return []
            
            # Read CSV with proper parsing
            df = pd.read_csv(csv_path)
            
            # Filter new alerts
            new_alerts = []
            for idx, row in df.iterrows():
                # Create unique alert ID
                alert_id = f"{row[self.columns['timestamp']]}_{row[self.columns['symbol']]}"
                
                if alert_id not in self.processed_alerts:
                    alert = self._process_alert(row)
                    if alert:
                        new_alerts.append(alert)
                        self.processed_alerts.add(alert_id)
            
            if new_alerts:
                logger.info(f"Found {len(new_alerts)} new alerts from {os.path.basename(csv_path)}")
                
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
                    # Extract number after "Next resistance"
                    resistance_text = parts[1].strip()
                    # Get first number (could be formatted as $X.XX or just X.XX)
                    resistance_value = resistance_text.split()[0].replace('$', '').replace(',', '')
                    try:
                        resistance = float(resistance_value)
                    except:
                        logger.debug(f"Could not parse resistance: {resistance_text}")
            
            alert = {
                'timestamp': row[self.columns['timestamp']],
                'symbol': row[self.columns['symbol']],
                'type': row[self.columns['type']],
                'description': description,
                'price': float(row[self.columns['price']]),
                'volume': float(row[self.columns['volume']]) if 'volume' in row else 0,
                'resistance': resistance,
                'signal': 'BUY',  # Breaking out on Volume is a bullish signal
                'strategy': self.strategy_name
            }
            
            return alert
            
        except Exception as e:
            logger.error(f"Error processing alert row: {e}")
            logger.debug(f"Row data: {row.to_dict()}")
            return None
    
    def get_historical_files(self, days_back: int = 7) -> List[str]:
        """Get list of historical CSV files for backtesting"""
        files = []
        base_dir = os.path.dirname(self.base_path) if os.path.isfile(self.base_path) else self.base_path
        
        for i in range(days_back):
            date = datetime.now() - pd.Timedelta(days=i)
            date_str = date.strftime("%Y%m%d")
            filename = f"{self.file_prefix}.{self.strategy_name}.{date_str}.csv"
            file_path = os.path.join(base_dir, filename)
            
            if os.path.exists(file_path):
                files.append(file_path)
        
        return sorted(files)
    
    def parse_historical_file(self, file_path: str) -> List[Dict]:
        """Parse a specific historical file"""
        try:
            if not os.path.exists(file_path):
                logger.warning(f"Historical file not found: {file_path}")
                return []
            
            df = pd.read_csv(file_path)
            alerts = []
            
            for idx, row in df.iterrows():
                alert = self._process_alert(row)
                if alert:
                    alerts.append(alert)
            
            logger.info(f"Parsed {len(alerts)} alerts from {os.path.basename(file_path)}")
            return alerts
            
        except Exception as e:
            logger.error(f"Error parsing historical file {file_path}: {e}")
            return []
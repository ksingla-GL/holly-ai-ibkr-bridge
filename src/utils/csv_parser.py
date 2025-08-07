"""
Fixed Holly AI CSV Alert Parser - Compatible Version
Handles daily file format without state_manager dependency
"""
import pandas as pd
import os
from typing import Dict, List, Optional, Union
from datetime import datetime
from pathlib import Path
import json
import time
import logging

class HollyAlertParser:
    def __init__(self, config: Union[str, dict] = "config/config.json", *_, **__):
        """Initialize parser with config object or path and persistent state"""
        self.logger = logging.getLogger(__name__)

        if isinstance(config, str):
            with open(config, 'r') as f:
                self.config = json.load(f)
        else:
            self.config = config

        # Get base path and strategy name from config
        self.base_path = self.config['alerts']['csv_path']
        self.strategy_name = self.config['alerts'].get('strategy_name', 'Breaking out on Volume')
        self.file_prefix = self.config['alerts'].get('file_prefix', 'alertlogging')

        # Persistent processed alerts
        self.state_file = Path("data/processed_alerts.json")
        self.processed_alerts = self._load_processed_alerts()
        self._cleanup_old_alerts()

        self.columns = self.config['alerts']['columns']
        self.current_file = None
        self.last_file_check = None

        self.logger.info(f"CSV Parser initialized for strategy: {self.strategy_name}")
        self.logger.info(f"Loaded {sum(len(v) for v in self.processed_alerts.values())} previously processed alerts")

    def _load_processed_alerts(self) -> Dict[str, list]:
        """Load processed alerts from disk"""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                return {k: set(v) for k, v in data.items()}
        except Exception as e:
            self.logger.warning(f"Could not load processed alerts: {e}")
        return {}

    def _save_processed_alerts(self):
        """Persist processed alerts to disk"""
        try:
            os.makedirs(self.state_file.parent, exist_ok=True)
            serializable = {k: list(v) for k, v in self.processed_alerts.items()}
            with open(self.state_file, 'w') as f:
                json.dump(serializable, f, indent=2)
        except Exception as e:
            self.logger.warning(f"Could not save processed alerts: {e}")

    def _get_today_key(self) -> str:
        return datetime.now().strftime('%Y-%m-%d')

    def _is_alert_processed(self, alert_id: str) -> bool:
        today = self._get_today_key()
        return alert_id in self.processed_alerts.get(today, set())

    def _mark_alert_processed(self, alert_id: str):
        today = self._get_today_key()
        if today not in self.processed_alerts:
            self.processed_alerts[today] = set()
        if alert_id not in self.processed_alerts[today]:
            self.processed_alerts[today].add(alert_id)
            self._save_processed_alerts()

    def _cleanup_old_alerts(self, days_to_keep: int = 7):
        """Remove processed alerts older than specified days"""
        try:
            today = datetime.now().date()
            cutoff = today - pd.Timedelta(days=days_to_keep)
            removed = False
            for date_str in list(self.processed_alerts.keys()):
                try:
                    alert_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    if alert_date < cutoff:
                        del self.processed_alerts[date_str]
                        removed = True
                except Exception:
                    continue
            if removed:
                self._save_processed_alerts()
        except Exception as e:
            self.logger.debug(f"Cleanup failed: {e}")

    def get_processed_alerts_stats(self) -> Dict[str, int]:
        stats = {date: len(alerts) for date, alerts in self.processed_alerts.items()}
        stats['total'] = sum(stats.values())
        return stats

    def clear_old_processed_alerts(self, days_to_keep: int = 7):
        """Manually clear processed alerts older than specified days"""
        today = datetime.now().date()
        cleaned = {}
        for date_str, alerts in self.processed_alerts.items():
            try:
                alert_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                if (today - alert_date).days <= days_to_keep:
                    cleaned[date_str] = alerts
                else:
                    self.logger.info(f"Cleared {len(alerts)} old alerts from {date_str}")
            except Exception:
                continue
        original = len(self.processed_alerts)
        self.processed_alerts = cleaned
        self._save_processed_alerts()
        self.logger.info(f"Cleanup complete: {original} -> {len(cleaned)} date entries")
    
    def get_todays_csv_file(self) -> Optional[str]:
        """Get today's CSV file path"""
        # Format: alertlogging.Breaking out on Volume.20250804.csv
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
                self.logger.info(f"Found today's CSV file: {file_path}")
                return file_path
            
            self.logger.debug(f"Waiting for file: {file_path}")
            time.sleep(5)  # Check every 5 seconds
        
        self.logger.warning(f"Timeout waiting for today's CSV file")
        return None
        
    def parse_alerts(self) -> List[Dict]:
        """Parse new alerts from CSV file"""
        try:
            # Get today's file
            csv_path = self.get_todays_csv_file()
            
            # Check if we need to switch to a new file (new trading day)
            if csv_path != self.current_file:
                self.logger.info(f"Switching to new file: {csv_path}")
                self.current_file = csv_path
                self._cleanup_old_alerts()
            
            if not os.path.exists(csv_path):
                # Try to wait for file if it's early in the trading day
                current_time = datetime.now()
                market_open = current_time.replace(hour=9, minute=30, second=0)
                
                # If it's near market open, wait for file
                if market_open <= current_time <= market_open.replace(hour=10):
                    self.logger.info("Near market open, waiting for CSV file...")
                    csv_path = self.wait_for_todays_file()
                    if not csv_path:
                        return []
                else:
                    self.logger.debug(f"CSV file not found: {csv_path}")
                    return []
            
            # Read CSV with proper parsing
            df = pd.read_csv(csv_path)

            # Filter new alerts
            new_alerts = []
            for idx, row in df.iterrows():
                alert_id = f"{row[self.columns['timestamp']]}_{row[self.columns['symbol']]}"

                if not self._is_alert_processed(alert_id):
                    alert = self._process_alert(row)
                    if alert:
                        new_alerts.append(alert)
                        self._mark_alert_processed(alert_id)

            if new_alerts:
                self.logger.info(
                    f"Found {len(new_alerts)} new alerts from {os.path.basename(csv_path)}"
                )

            return new_alerts
            
        except Exception as e:
            self.logger.error(f"Error parsing CSV: {e}")
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
                        self.logger.debug(f"Could not parse resistance: {resistance_text}")
            
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
            self.logger.error(f"Error processing alert row: {e}")
            self.logger.debug(f"Row data: {row.to_dict()}")
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
                self.logger.warning(f"Historical file not found: {file_path}")
                return []
            
            df = pd.read_csv(file_path)
            alerts = []
            
            for idx, row in df.iterrows():
                alert = self._process_alert(row)
                if alert:
                    alerts.append(alert)
            
            self.logger.info(f"Parsed {len(alerts)} alerts from {os.path.basename(file_path)}")
            return alerts
            
        except Exception as e:
            self.logger.error(f"Error parsing historical file {file_path}: {e}")
            return []
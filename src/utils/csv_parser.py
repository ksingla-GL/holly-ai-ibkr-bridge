"""Holly AI CSV Alert Parser with Dynamic Date-based File Handling"""
import pandas as pd
import os
import glob
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from loguru import logger
import json

class HollyAlertParser:
    def __init__(self, config_path: str = "config/config.json"):
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        # Base path from config (directory where CSV files are stored)
        self.base_path = self.config['alerts']['csv_path']
        
        # Extract directory and base filename pattern
        if os.path.isdir(self.base_path):
            self.csv_directory = self.base_path
            self.base_pattern = "alertlogging.Breaking out on Volume"
        else:
            # If config points to a file, extract directory
            self.csv_directory = os.path.dirname(self.base_path)
            self.base_pattern = "alertlogging.Breaking out on Volume"
            
        self.processed_alerts = set()
        self.columns = self.config['alerts']['columns']
        self.current_csv_file = None
        
        logger.info(f"CSV Parser initialized. Looking for files in: {self.csv_directory}")
        
    def get_today_csv_file(self) -> Optional[str]:
        """Get today's CSV file path"""
        today = datetime.now().strftime("%Y%m%d")
        filename = f"{self.base_pattern}.{today}.csv"
        filepath = os.path.join(self.csv_directory, filename)
        
        if os.path.exists(filepath):
            logger.info(f"Found today's CSV file: {filename}")
            return filepath
        else:
            logger.warning(f"Today's CSV file not found: {filename}")
            return None
    
    def get_latest_csv_file(self) -> Optional[str]:
        """Get the most recent CSV file if today's doesn't exist"""
        pattern = os.path.join(self.csv_directory, f"{self.base_pattern}.*.csv")
        csv_files = glob.glob(pattern)
        
        if not csv_files:
            logger.error(f"No CSV files found matching pattern: {pattern}")
            return None
            
        # Sort by date in filename
        csv_files_with_dates = []
        for file in csv_files:
            try:
                # Extract date from filename
                date_str = file.split('.')[-2]  # Get YYYYMMDD part
                date_obj = datetime.strptime(date_str, "%Y%m%d")
                csv_files_with_dates.append((file, date_obj))
            except:
                logger.warning(f"Could not parse date from filename: {file}")
                continue
                
        if not csv_files_with_dates:
            return None
            
        # Sort by date and get the most recent
        csv_files_with_dates.sort(key=lambda x: x[1], reverse=True)
        latest_file = csv_files_with_dates[0][0]
        
        logger.info(f"Using most recent CSV file: {os.path.basename(latest_file)}")
        return latest_file
    
    def get_active_csv_file(self) -> Optional[str]:
        """Get the CSV file to read - today's or most recent"""
        # First try today's file
        today_file = self.get_today_csv_file()
        if today_file:
            return today_file
            
        # If not found, get the most recent
        return self.get_latest_csv_file()
        
    def parse_alerts(self) -> List[Dict]:
        """Parse new alerts from CSV file"""
        try:
            # Get the current CSV file
            csv_file = self.get_active_csv_file()
            
            if not csv_file:
                logger.error("No valid CSV file found")
                return []
            
            # Check if we've switched to a new file (new trading day)
            if self.current_csv_file != csv_file:
                logger.info(f"Switching to new CSV file: {os.path.basename(csv_file)}")
                self.current_csv_file = csv_file
                # Optionally clear processed alerts for new day
                # self.processed_alerts.clear()
                
            # Read CSV with proper parsing
            df = pd.read_csv(csv_file)
            
            # Log the number of total rows
            logger.debug(f"CSV contains {len(df)} total rows")
            
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
                logger.info(f"Found {len(new_alerts)} new alerts")
                for alert in new_alerts[:3]:  # Log first 3 alerts
                    logger.debug(f"New alert: {alert['symbol']} @ ${alert['price']}")
                    
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
                    try:
                        # Extract number after "Next resistance"
                        resistance_text = parts[1].strip()
                        # Get first word/number
                        resistance = float(resistance_text.split()[0])
                    except:
                        logger.debug(f"Could not parse resistance from: {description}")
            
            alert = {
                'timestamp': row[self.columns['timestamp']],
                'symbol': row[self.columns['symbol']],
                'type': row[self.columns['type']],
                'description': description,
                'price': float(row[self.columns['price']]),
                'volume': float(row[self.columns['volume']]),
                'resistance': resistance,
                'signal': 'BUY' if 'New High' in description else None,
                'source_file': os.path.basename(self.current_csv_file) if self.current_csv_file else None
            }
            
            return alert
            
        except Exception as e:
            logger.error(f"Error processing alert row: {e}")
            logger.debug(f"Row data: {row}")
            return None
    
    def cleanup_old_processed_alerts(self, days_to_keep: int = 7):
        """Optional: Clean up processed alerts older than specified days"""
        # This prevents the processed_alerts set from growing indefinitely
        if len(self.processed_alerts) > 10000:  # Arbitrary threshold
            logger.info("Cleaning up old processed alerts...")
            self.processed_alerts.clear()


# For testing
if __name__ == "__main__":
    # Test the parser
    from loguru import logger
    logger.add("test_parser.log", rotation="1 day")
    
    parser = HollyAlertParser()
    
    # Check for files
    csv_file = parser.get_active_csv_file()
    if csv_file:
        print(f"Found CSV file: {csv_file}")
        
        # Parse alerts
        alerts = parser.parse_alerts()
        print(f"Found {len(alerts)} new alerts")
        
        if alerts:
            print("\nFirst alert:")
            print(json.dumps(alerts[0], indent=2))
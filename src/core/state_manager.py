"""
State Manager - Handles persistent state across restarts
"""

import json
import logging
import os
from datetime import datetime, date, timedelta
from typing import Dict, Set, Any
from pathlib import Path
import pytz
import time

class StateManager:
    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.state_file = Path(config['state']['state_file'])
        self.backup_file = Path(config['state']['backup_file'])
        
        # Timezone for proper date handling
        self.market_tz = pytz.timezone(config['system']['market_timezone'])
        
        # Initialize state structure
        self.state = {
            'version': '2.0.0',
            'last_save': None,
            'processed_alerts': {},  # date -> set of alert IDs
            'open_positions': {},    # symbol -> position data
            'pending_exits': {},     # symbol -> exit time
            'daily_stats': {},       # date -> stats
            'system_state': {
                'last_startup': None,
                'last_shutdown': None,
                'total_runtime_seconds': 0
            }
        }
        
    def load_state(self) -> bool:
        """Load state from file"""
        try:
            if self.state_file.exists():
                # Windows-compatible file reading with retry logic
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        with open(self.state_file, 'r') as f:
                            loaded_state = json.load(f)
                        break
                    except (IOError, OSError) as e:
                        if attempt < max_retries - 1:
                            time.sleep(0.1)  # Brief pause before retry
                        else:
                            raise
                            
                # Merge loaded state
                self._merge_state(loaded_state)
                
                self.logger.info(f"State loaded from {self.state_file}")
                return True
            else:
                self.logger.info("No previous state found, starting fresh")
                return False
                
        except Exception as e:
            self.logger.error(f"Error loading state: {e}")
            
            # Try backup
            if self.backup_file.exists():
                try:
                    with open(self.backup_file, 'r') as f:
                        loaded_state = json.load(f)
                    self._merge_state(loaded_state)
                    self.logger.info("State loaded from backup")
                    return True
                except:
                    pass
                    
            return False
            
    def save_state(self):
        """Save state to file with atomic write"""
        try:
            # Update timestamp
            self.state['last_save'] = datetime.now().isoformat()
            
            # Create backup of existing state
            if self.state_file.exists():
                import shutil
                try:
                    shutil.copy2(self.state_file, self.backup_file)
                except:
                    pass  # Backup is optional
                    
            # Prepare state for JSON serialization
            json_state = self._prepare_for_json(self.state)
            
            # Windows-compatible atomic write
            temp_file = self.state_file.with_suffix('.tmp')
            
            # Write to temp file
            with open(temp_file, 'w') as f:
                json.dump(json_state, f, indent=2)
                
            # Atomic rename on Windows
            if os.path.exists(self.state_file):
                os.remove(self.state_file)
            os.rename(temp_file, self.state_file)
            
            self.logger.debug("State saved successfully")
            
        except Exception as e:
            self.logger.error(f"Error saving state: {e}")
            
    def _merge_state(self, loaded_state: dict):
        """Merge loaded state with current state"""
        # Convert sets from lists
        if 'processed_alerts' in loaded_state:
            for date_str, alerts in loaded_state['processed_alerts'].items():
                self.state['processed_alerts'][date_str] = set(alerts)
                
        # Merge other fields
        for key in ['open_positions', 'pending_exits', 'daily_stats', 'system_state']:
            if key in loaded_state:
                self.state[key] = loaded_state[key]
                
    def _prepare_for_json(self, obj: Any) -> Any:
        """Prepare state for JSON serialization"""
        if isinstance(obj, dict):
            return {k: self._prepare_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, set):
            return list(obj)
        elif isinstance(obj, (datetime, date)):
            return obj.isoformat()
        else:
            return obj
            
    def get_market_date(self) -> str:
        """Get current market date in ET"""
        now_et = datetime.now(self.market_tz)
        # If before 4 PM ET, use today; otherwise use next trading day
        if now_et.hour < 16:
            return now_et.date().isoformat()
        else:
            # Simple next day - could be enhanced to skip weekends
            return (now_et.date() + timedelta(days=1)).isoformat()
            
    def is_alert_processed(self, alert_id: str) -> bool:
        """Check if alert has been processed"""
        market_date = self.get_market_date()
        processed_today = self.state['processed_alerts'].get(market_date, set())
        return alert_id in processed_today
        
    def mark_alert_processed(self, alert_id: str):
        """Mark alert as processed"""
        market_date = self.get_market_date()
        if market_date not in self.state['processed_alerts']:
            self.state['processed_alerts'][market_date] = set()
        self.state['processed_alerts'][market_date].add(alert_id)
        
    def add_open_position(self, symbol: str, position_data: dict):
        """Add open position"""
        self.state['open_positions'][symbol] = position_data
        
    def remove_open_position(self, symbol: str):
        """Remove open position"""
        if symbol in self.state['open_positions']:
            del self.state['open_positions'][symbol]
            
    def get_open_positions(self) -> Dict:
        """Get all open positions"""
        return self.state['open_positions'].copy()
        
    def add_pending_exit(self, symbol: str, exit_data: dict):
        """Add pending exit"""
        self.state['pending_exits'][symbol] = exit_data
        
    def remove_pending_exit(self, symbol: str):
        """Remove pending exit"""
        if symbol in self.state['pending_exits']:
            del self.state['pending_exits'][symbol]
            
    def get_pending_exits(self) -> Dict:
        """Get all pending exits"""
        return self.state['pending_exits'].copy()
        
    def update_daily_stats(self, stats: dict):
        """Update daily statistics"""
        market_date = self.get_market_date()
        self.state['daily_stats'][market_date] = stats
        
    def get_daily_stats(self) -> Dict:
        """Get daily statistics for current market date"""
        market_date = self.get_market_date()
        return self.state['daily_stats'].get(market_date, {
            'trades_taken': 0,
            'trades_closed': 0,
            'pnl': 0.0,
            'win_rate': 0.0
        })
        
    def cleanup_old_data(self, days_to_keep: int = 30):
        """Clean up old data to prevent file bloat"""
        cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).date()
        
        # Clean processed alerts
        dates_to_remove = []
        for date_str in self.state['processed_alerts']:
            if datetime.fromisoformat(date_str).date() < cutoff_date:
                dates_to_remove.append(date_str)
                
        for date_str in dates_to_remove:
            del self.state['processed_alerts'][date_str]
            
        # Clean daily stats
        dates_to_remove = []
        for date_str in self.state['daily_stats']:
            if datetime.fromisoformat(date_str).date() < cutoff_date:
                dates_to_remove.append(date_str)
                
        for date_str in dates_to_remove:
            del self.state['daily_stats'][date_str]
            
        if dates_to_remove:
            self.logger.info(f"Cleaned up data older than {days_to_keep} days")

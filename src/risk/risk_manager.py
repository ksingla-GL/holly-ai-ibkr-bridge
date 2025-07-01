"""Risk Management Module"""
from typing import Dict, List
from datetime import datetime, timedelta
from loguru import logger
import json

class RiskManager:
    def __init__(self, config_path: str = "config/config.json"):
        with open(config_path, 'r') as f:
            self.config = json.load(f)['risk']
        self.daily_trades = []
        self.daily_pnl = 0
        self.active_positions = {}
        
    def check_trade_allowed(self, alert: Dict) -> bool:
        """Check if new trade is allowed based on risk rules"""
        # Check daily trade limit
        today_trades = [t for t in self.daily_trades 
                       if t['timestamp'].date() == datetime.now().date()]
        if len(today_trades) >= self.config['max_trades_per_day']:
            logger.warning("Daily trade limit reached")
            return False
        
        # Check daily loss limit
        if self.daily_pnl <= -self.config['max_daily_loss']:
            logger.warning("Daily loss limit reached")
            return False
        
        # Check if symbol already has position
        if alert['symbol'] in self.active_positions:
            logger.warning(f"Already have position in {alert['symbol']}")
            return False
        
        return True
    
    def calculate_stop_loss(self, entry_price: float) -> float:
        """Calculate stop loss price"""
        stop_pct = self.config['stop_loss_pct'] / 100
        return round(entry_price * (1 - stop_pct), 2)
    
    def calculate_take_profit(self, entry_price: float) -> float:
        """Calculate take profit price"""
        tp_pct = self.config['take_profit_pct'] / 100
        return round(entry_price * (1 + tp_pct), 2)
    
    def should_exit_time_based(self, entry_time: datetime) -> bool:
        """Check if position should be exited based on time"""
        exit_minutes = self.config['time_based_exit_minutes']
        return datetime.now() > entry_time + timedelta(minutes=exit_minutes)
    
    def update_position(self, symbol: str, trade_data: Dict):
        """Update position tracking"""
        self.active_positions[symbol] = trade_data
        self.daily_trades.append(trade_data)
        logger.info(f"Updated position for {symbol}")
    
    def remove_position(self, symbol: str, exit_price: float):
        """Remove position and update P&L"""
        if symbol in self.active_positions:
            position = self.active_positions[symbol]
            pnl = (exit_price - position['entry_price']) * position['quantity']
            self.daily_pnl += pnl
            del self.active_positions[symbol]
            logger.info(f"Closed {symbol} position, P&L: ${pnl:.2f}")
    
    def reset_daily_counters(self):
        """Reset daily counters"""
        self.daily_trades = []
        self.daily_pnl = 0
        logger.info("Reset daily risk counters")

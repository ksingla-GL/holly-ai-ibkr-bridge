"""
Fixed Order Manager - Compatible with original interface
Removes async complexity and threading issues
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
import time

class OrderManager:
    def __init__(self, ib_connector, config: dict):
        """
        Initialize with ib_connector and config only
        """
        self.ib_connector = ib_connector
        self.ib = ib_connector.ib  # Access the IB instance for compatibility
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.pending_exits = {}  # symbol: exit_time
        self.active_orders = {}  # For compatibility
        
    def place_entry_order(self, symbol: str, shares: int, entry_price: float = None) -> Optional[int]:
        """Place entry order with stop loss"""
        try:
            # Calculate stop price
            stop_price = entry_price * (1 - self.config['risk_management']['stop_loss_pct'] / 100)
            
            self.logger.info(f"Placing order: {symbol} - {shares} shares @ ${entry_price}, stop @ ${stop_price}")
            
            # Place order using connector
            trade = self.ib_connector.place_market_order_with_stop(
                symbol=symbol,
                quantity=shares,
                stop_price=round(stop_price, 2)
            )
            
            if trade:
                # Schedule time exit
                exit_time = datetime.now() + timedelta(minutes=self.config['risk_management']['time_exit_minutes'])
                self.pending_exits[symbol] = {
                    'exit_time': exit_time,
                    'shares': shares,
                    'entry_price': entry_price,
                    'order_id': trade.order.orderId
                }
                
                self.logger.info(f"Order placed successfully: {symbol}, exit scheduled for {exit_time.strftime('%H:%M:%S')}")
                return trade.order.orderId
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error placing order for {symbol}: {e}")
            return None

    def schedule_time_exit(self, symbol: str, shares: int, entry_price: float):
        """Schedule a time-based exit for an existing position"""
        exit_time = datetime.now() + timedelta(
            minutes=self.config['risk_management']['time_exit_minutes']
        )
        self.pending_exits[symbol] = {
            'exit_time': exit_time,
            'shares': shares,
            'entry_price': entry_price,
            'order_id': None
        }
        self.logger.info(
            f"Scheduled time exit for {symbol} at {exit_time.strftime('%H:%M:%S')}"
        )
    
    def check_time_exits(self) -> list:
        """Check for positions that need time-based exit"""
        current_time = datetime.now()
        symbols_to_exit = []
        
        for symbol, exit_data in list(self.pending_exits.items()):
            if current_time >= exit_data['exit_time']:
                symbols_to_exit.append(symbol)
                self.logger.info(f"Time exit due for {symbol}")
        
        return symbols_to_exit
    
    def execute_time_exit(self, symbol: str) -> bool:
        """Execute time-based exit - IMPROVED POSITION DETECTION"""
        try:
            if symbol not in self.pending_exits:
                self.logger.warning(f"No pending exit for {symbol}")
                return False
            
            exit_data = self.pending_exits[symbol]
            
            # Always get fresh positions from IBKR instead of relying on internal tracking
            self.logger.info(f"Checking IBKR for {symbol} position...")
            
            # Use the improved close_position method which will find actual quantities
            success = self.ib_connector.close_position(symbol, exit_data['shares'])
            
            if success:
                self.logger.info(f"Time exit executed successfully for {symbol}")
                del self.pending_exits[symbol]
                return True
            else:
                # If close failed, it might mean position was already closed by stop loss
                self.logger.info(f"Position close failed for {symbol} - may have been closed by stop loss")
                # Still remove from pending exits since we tried
                del self.pending_exits[symbol]
                return False
                
        except Exception as e:
            self.logger.error(f"Error executing time exit for {symbol}: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    def get_pending_exits(self) -> Dict:
        """Get all pending exits for monitoring"""
        return self.pending_exits.copy()
    
    def cancel_pending_exit(self, symbol: str):
        """Cancel a pending exit (if position closed by stop loss)"""
        if symbol in self.pending_exits:
            del self.pending_exits[symbol]
            self.logger.info(f"Cancelled pending exit for {symbol}")
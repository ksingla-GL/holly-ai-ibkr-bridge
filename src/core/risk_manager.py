"""
Fixed Risk Manager - Compatible with original interface
Implements 3% position sizing, max 3 concurrent, 30 daily trades
"""

import logging
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

class RiskManager:
    def __init__(self, config: dict, account_value: float = None):
        self.config = config['risk_management']
        self.logger = logging.getLogger(__name__)
        
        # Core parameters from optimal config
        self.max_daily_trades = self.config['max_daily_trades']  # 30
        self.max_concurrent = self.config['max_concurrent_positions']  # 3
        self.position_size_pct = self.config['position_size_pct']  # 3.0%
        self.stop_loss_pct = self.config['stop_loss_pct']  # 1.0%
        self.time_exit_minutes = self.config['time_exit_minutes']  # 10
        
        # Tracking variables
        self.daily_trades = 0
        self.current_positions = {}  # symbol: position_data
        self.trade_history = []
        self.last_reset_date = datetime.now().date()
        self.account_value = account_value or 50000  # Default for paper

        # Persistent state
        self.state_file = self.config.get('state_file', 'data/state/risk_state.json')
        self._load_state()

        self.logger.info(
            f"Risk Manager initialized: {self.position_size_pct}% positions, max {self.max_concurrent} concurrent"
        )

    def _load_state(self):
        """Load risk state from disk"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    data = json.load(f)

                self.daily_trades = data.get('daily_trades', 0)
                last_date = data.get('last_reset_date')
                if last_date:
                    self.last_reset_date = datetime.fromisoformat(last_date).date()

                positions = {}
                for sym, pos in data.get('current_positions', {}).items():
                    pos['entry_time'] = datetime.fromisoformat(pos['entry_time'])
                    pos['exit_time'] = datetime.fromisoformat(pos['exit_time'])
                    positions[sym] = pos
                self.current_positions = positions
                self.logger.info("Risk state loaded")
        except Exception as e:
            self.logger.warning(f"Could not load risk state: {e}")

    def _save_state(self):
        """Persist risk state to disk"""
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            positions = {
                sym: {
                    **pos,
                    'entry_time': pos['entry_time'].isoformat(),
                    'exit_time': pos['exit_time'].isoformat(),
                }
                for sym, pos in self.current_positions.items()
            }
            data = {
                'daily_trades': self.daily_trades,
                'last_reset_date': self.last_reset_date.isoformat(),
                'current_positions': positions,
            }
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.logger.warning(f"Could not save risk state: {e}")
    
    def check_pre_trade(self, signal: Dict) -> bool:
        """Check if we can take a new trade"""
        # Reset daily counter if new day
        if datetime.now().date() != self.last_reset_date:
            self.daily_trades = 0
            self.last_reset_date = datetime.now().date()
            self.logger.info("New trading day - reset daily counters")
            self._save_state()
        
        # Check daily trade limit
        if self.daily_trades >= self.max_daily_trades:
            self.logger.warning(f"Daily trade limit reached ({self.max_daily_trades})")
            return False
        
        # Check concurrent positions
        if len(self.current_positions) >= self.max_concurrent:
            self.logger.info(f"Max concurrent positions reached ({self.max_concurrent})")
            return False
        
        # Check if already in position
        symbol = signal['symbol']
        if symbol in self.current_positions:
            self.logger.info(f"Already in position for {symbol}")
            return False
        
        return True
    
    def calculate_position_size(self) -> int:
        """Calculate position size based on 3% of account"""
        position_value = self.account_value * (self.position_size_pct / 100)
        self.logger.info(f"Position size: ${position_value:.2f} ({self.position_size_pct}% of ${self.account_value})")
        return position_value
    
    def calculate_shares(self, price: float) -> int:
        """Calculate number of shares to buy"""
        position_value = self.calculate_position_size()
        shares = int(position_value / price)
        self.logger.info(f"Shares to buy: {shares} at ${price}")
        return shares
    
    def add_position(self, symbol: str, entry_price: float, shares: int, order_id: int):
        """Track new position with time-based exit"""
        entry_time = datetime.now()
        exit_time = entry_time + timedelta(minutes=self.time_exit_minutes)
        
        self.current_positions[symbol] = {
            'entry_time': entry_time,
            'exit_time': exit_time,
            'entry_price': entry_price,
            'shares': shares,
            'order_id': order_id,
            'stop_price': entry_price * (1 - self.stop_loss_pct / 100)
        }
        
        self.daily_trades += 1
        self.logger.info(
            f"Added position: {symbol} - {shares} shares @ ${entry_price}, exit at {exit_time.strftime('%H:%M:%S')}"
        )
        self._save_state()

    def track_existing_position(self, symbol: str, entry_price: float, shares: int):
        """Track an existing position without counting as new trade"""
        entry_time = datetime.now()
        exit_time = entry_time + timedelta(minutes=self.time_exit_minutes)
        self.current_positions[symbol] = {
            'entry_time': entry_time,
            'exit_time': exit_time,
            'entry_price': entry_price,
            'shares': shares,
            'order_id': None,
            'stop_price': entry_price * (1 - self.stop_loss_pct / 100)
        }
        self.logger.info(
            f"Tracking existing position: {symbol} - {shares} shares @ ${entry_price}, exit at {exit_time.strftime('%H:%M:%S')}"
        )
        self._save_state()

    def sync_with_ibkr(self, ibkr_positions):
        """Reconcile tracked positions with actual IBKR positions"""
        try:
            ibkr_map = {
                pos.contract.symbol: pos
                for pos in ibkr_positions
                if getattr(pos, 'position', 0) != 0
            }
        except Exception as e:
            self.logger.warning(f"Could not parse IBKR positions: {e}")
            return

        # Remove positions not present in IBKR
        for symbol in list(self.current_positions.keys()):
            if symbol not in ibkr_map:
                self.logger.info(f"Removing stale position from risk manager: {symbol}")
                del self.current_positions[symbol]

        # Track any IBKR positions not currently tracked
        for symbol, pos in ibkr_map.items():
            if symbol not in self.current_positions:
                shares = abs(int(getattr(pos, 'position', 0)))
                entry_price = float(getattr(pos, 'avgCost', 0) or 0)
                self.track_existing_position(symbol, entry_price, shares)

        self._save_state()
    
    def check_exits(self) -> List[str]:
        """Check for positions that need to exit (time-based)"""
        current_time = datetime.now()
        symbols_to_exit = []
        
        for symbol, position in self.current_positions.items():
            if current_time >= position['exit_time']:
                symbols_to_exit.append(symbol)
                self.logger.info(f"Time exit triggered for {symbol}")
        
        return symbols_to_exit
    
    def remove_position(self, symbol: str, exit_price: float, exit_reason: str):
        """Remove position and track results"""
        if symbol not in self.current_positions:
            return
        
        position = self.current_positions[symbol]
        pnl = (exit_price - position['entry_price']) * position['shares']
        pnl_pct = ((exit_price - position['entry_price']) / position['entry_price']) * 100
        
        trade_record = {
            'symbol': symbol,
            'entry_time': position['entry_time'],
            'exit_time': datetime.now(),
            'entry_price': position['entry_price'],
            'exit_price': exit_price,
            'shares': position['shares'],
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'exit_reason': exit_reason
        }
        
        self.trade_history.append(trade_record)
        del self.current_positions[symbol]
        
        self.logger.info(f"Closed {symbol}: {exit_reason} - P&L: ${pnl:.2f} ({pnl_pct:.2f}%)")
        self._save_state()
    
    def update_account_value(self, new_value: float):
        """Update account value for position sizing"""
        self.account_value = new_value
        self.logger.info(f"Account value updated: ${new_value:,.2f}")
    
    def get_daily_stats(self) -> Dict:
        """Get today's trading statistics"""
        # Get closed trades for today
        today_closed = [t for t in self.trade_history 
                       if t['exit_time'].date() == datetime.now().date()]
        
        # Calculate P&L and win rate only from closed trades
        if today_closed:
            total_pnl = sum(t['pnl'] for t in today_closed)
            wins = sum(1 for t in today_closed if t['pnl'] > 0)
            win_rate = (wins / len(today_closed)) * 100
        else:
            total_pnl = 0
            win_rate = 0
        
        # Always return all keys
        return {
            'trades': self.daily_trades,  # Total trades taken today (open + closed)
            'trades_closed': len(today_closed),  # Trades closed today
            'pnl': total_pnl,
            'win_rate': win_rate,
            'positions_open': len(self.current_positions),
            'trades_remaining': self.max_daily_trades - self.daily_trades
        }
"""
Position Tracker - Single source of truth for positions
"""

import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import asyncio
from datetime import datetime, timedelta

class PositionTracker:
    def __init__(self, ib_connector, state_manager):
        self.ib = ib_connector
        self.state_manager = state_manager
        self.logger = logging.getLogger(__name__)
        
        # Position data from state
        self.positions = {}
        self.pending_exits = {}
        
        # Load from state
        self._load_from_state()
        
    def _load_from_state(self):
        """Load positions from state manager"""
        self.positions = self.state_manager.get_open_positions()
        self.pending_exits = self.state_manager.get_pending_exits()
        
    def sync_positions(self) -> List[str]:
        """Sync with IBKR positions and properly track them"""
        discrepancies = []
        
        try:
            # Get positions from IBKR
            ibkr_positions = self.ib.get_positions()
            portfolio = self.ib.get_portfolio() if hasattr(self.ib, 'get_portfolio') else []
            
            print(f"\n=== POSITION SYNC at {datetime.now().strftime('%H:%M:%S')} ===")
            print(f"Positions found: {len(ibkr_positions)}")
            print(f"Portfolio items: {len(portfolio)}")
            
            ibkr_dict = {}
            
            # Build dict of IBKR positions
            for pos in ibkr_positions:
                if pos.position != 0:
                    symbol = pos.contract.symbol
                    shares = abs(pos.position)
                    print(f"Position: {symbol} - {shares} shares @ {pos.avgCost}")
                    
                    ibkr_dict[symbol] = {
                        'shares': shares,
                        'side': 'LONG' if pos.position > 0 else 'SHORT',
                        'avg_cost': pos.avgCost
                    }
            
            # CRITICAL: Show current internal state
            print(f"\nInternal tracking:")
            print(f"  Tracked positions: {list(self.positions.keys())}")
            print(f"  Pending exits: {list(self.pending_exits.keys())}")
            
            # Check for untracked positions
            for symbol, ibkr_data in ibkr_dict.items():
                if symbol not in self.positions:
                    print(f"\n!!! UNTRACKED POSITION FOUND: {symbol} !!!")
                    self.logger.warning(f"UNTRACKED POSITION: {symbol} - {ibkr_data['shares']} shares")
                    discrepancies.append(f"Untracked: {symbol}")
                    
                    # Add to tracking
                    entry_time = datetime.now()
                    position_data = {
                        'shares': ibkr_data['shares'],
                        'entry_price': ibkr_data['avg_cost'],
                        'entry_time': entry_time.isoformat(),
                        'recovered': True,
                        'order_id': -1,  # Unknown
                        'stop_price': ibkr_data['avg_cost'] * 0.99  # 1% stop
                    }
                    
                    # CRITICAL: Use the add_position method to ensure state is saved
                    self.add_position(symbol, position_data)
                    
                    # Schedule time exit
                    exit_time = entry_time + timedelta(minutes=10)
                    self.schedule_time_exit(symbol, exit_time)
                    
                    print(f"Added to tracking and scheduled exit at {exit_time.strftime('%H:%M:%S')}")
                    
            # Check for phantom positions
            for symbol in list(self.positions.keys()):
                if symbol not in ibkr_dict:
                    print(f"\n!!! PHANTOM POSITION: {symbol} in tracking but not in IBKR !!!")
                    self.logger.warning(f"PHANTOM POSITION: {symbol}")
                    discrepancies.append(f"Phantom: {symbol}")
                    self.remove_position(symbol)
                    
            print("=========================\n")
            
            # Save state if changes made
            if discrepancies:
                self.state_manager.save_state()
                
            return discrepancies
            
        except Exception as e:
            self.logger.error(f"Error syncing: {e}", exc_info=True)
            return discrepancies
            
    def add_position(self, symbol: str, position_data: dict):
        """Add new position"""
        self.positions[symbol] = position_data
        self.state_manager.add_open_position(symbol, position_data)
        self.logger.info(f"Position added: {symbol}")
        
    def remove_position(self, symbol: str):
        """Remove position"""
        if symbol in self.positions:
            del self.positions[symbol]
            self.state_manager.remove_open_position(symbol)
            
        if symbol in self.pending_exits:
            del self.pending_exits[symbol]
            self.state_manager.remove_pending_exit(symbol)
            
        self.logger.info(f"Position removed: {symbol}")
        
    def schedule_time_exit(self, symbol: str, exit_time: datetime):
        """Schedule time-based exit"""
        exit_data = {
            'exit_time': exit_time.isoformat(),
            'scheduled_at': datetime.now().isoformat()
        }
        
        self.pending_exits[symbol] = exit_data
        self.state_manager.add_pending_exit(symbol, exit_data)
        
        self.logger.info(
            f"Exit scheduled for {symbol} at {exit_time.strftime('%H:%M:%S')}"
        )
        
    def get_positions_due_for_exit(self) -> List[Tuple[str, dict]]:
        """Get positions that are due for time-based exit"""
        current_time = datetime.now()
        due_positions = []
        
        for symbol, exit_data in self.pending_exits.items():
            exit_time = datetime.fromisoformat(exit_data['exit_time'])
            
            if current_time >= exit_time and symbol in self.positions:
                position_data = self.positions[symbol].copy()
                position_data['exit_data'] = exit_data
                due_positions.append((symbol, position_data))
                
        return due_positions
        
    def get_open_positions(self) -> Dict[str, dict]:
        """Get all open positions"""
        return self.positions.copy()
        
    def get_position(self, symbol: str) -> Optional[dict]:
        """Get specific position"""
        return self.positions.get(symbol)
        
    def has_position(self, symbol: str) -> bool:
        """Check if position exists"""
        return symbol in self.positions

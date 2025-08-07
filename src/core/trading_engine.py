"""
Trading Engine - Core orchestrator with proper state management
"""

import logging
import threading
import time
from datetime import datetime, timedelta
import pytz
from typing import Dict, List, Optional

from src.core.ibkr_connector import IBKRConnector
from src.core.state_manager import StateManager
from src.core.risk_manager import RiskManager
from src.core.order_manager import OrderManager
from src.core.position_tracker import PositionTracker
from src.utils.csv_parser import HollyAlertParser

class TradingEngine:
    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Timezone setup
        self.market_tz = pytz.timezone(config['system']['market_timezone'])
        self.local_tz = pytz.timezone(config['system']['timezone'])
        
        # Initialize components
        self.state_manager = StateManager(config)
        self.ibkr = None
        self.risk_manager = None
        self.order_manager = None
        self.position_tracker = None
        self.alert_parser = HollyAlertParser(config, self.state_manager)
        
        # Control flags
        self.running = False
        self.connected = False
        
        # Threads
        self.alert_thread = None
        self.exit_monitor_thread = None
        self.sync_thread = None
        
    def _alert_processing_loop(self):
        """Main loop for processing alerts"""
        self.logger.info("Alert processing thread started")  # ADD THIS
        
        while self.running:
            try:
                # Check if within trading hours
                if not self._is_market_hours():
                    self.logger.debug("Outside market hours, waiting...")  # ADD THIS
                    time.sleep(60)  # Check every minute outside market hours
                    continue
                    
                self.logger.debug("Within market hours, checking for alerts...")  # ADD THIS
                
                # Process new alerts
                new_alerts = self.alert_parser.get_new_alerts()
                
                if new_alerts:  # ADD THIS CHECK
                    self.logger.info(f"Found {len(new_alerts)} new alerts")
                else:
                    self.logger.debug("No new alerts found")
                    
                for alert in new_alerts:
                    if not self.running:
                        break
                        
                    self._process_alert(alert)
                    
                # Save state after processing
                if new_alerts:
                    self.state_manager.save_state()
                    
                time.sleep(self.config['alerts']['check_interval'])
                
            except Exception as e:
                self.logger.error(f"Error in alert processing: {e}", exc_info=True)
                time.sleep(5)
        
    def start(self) -> bool:
        """Start the trading engine"""
        try:
            # Load previous state
            self.state_manager.load_state()
            
            # Connect to IBKR
            self.logger.info("Connecting to IBKR...")
            self.ibkr = IBKRConnector(self.config)
            
            if not self.ibkr.connect():
                self.logger.error("Failed to connect to IBKR")
                return False
                
            self.connected = True
            self.logger.info("Connected to IBKR successfully")
            
            # Get account info
            account_info = self.ibkr.get_account_summary()
            account_value = float(account_info.get('NetLiquidation', 50000))
            self.logger.info(f"Account value: ${account_value:,.2f}")
            
            # Initialize managers
            self.risk_manager = RiskManager(self.config, account_value)
            self.position_tracker = PositionTracker(self.ibkr, self.state_manager)
            self.order_manager = OrderManager(self.ibkr, self.config, self.position_tracker)

            # Sync positions with IBKR
            self.logger.info("Syncing positions with IBKR...")
            self.ibkr.refresh_positions()
            self.position_tracker.sync_positions()
            self.risk_manager.sync_with_ibkr(self.ibkr.get_positions())
            
            # Recover any pending time exits
            self._recover_pending_exits()
            
            # Start threads
            self.running = True
            self._start_threads()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error starting engine: {e}", exc_info=True)
            return False
            
    def _start_threads(self):
        """Start all monitoring threads"""
        # Alert processing thread
        self.alert_thread = threading.Thread(
            target=self._alert_processing_loop,
            name="AlertProcessor",
            daemon=True
        )
        self.alert_thread.start()
        
        # Time exit monitor thread
        self.exit_monitor_thread = threading.Thread(
            target=self._exit_monitor_loop,
            name="ExitMonitor",
            daemon=True
        )
        self.exit_monitor_thread.start()
        
        # Position sync thread
        self.sync_thread = threading.Thread(
            target=self._position_sync_loop,
            name="PositionSync",
            daemon=True
        )
        self.sync_thread.start()
        
        self.logger.info("All monitoring threads started")
        
    def _alert_processing_loop(self):
        """Main loop for processing alerts"""
        while self.running:
            try:
                # Check if within trading hours
                if not self._is_market_hours():
                    time.sleep(60)  # Check every minute outside market hours
                    continue
                    
                # Process new alerts
                new_alerts = self.alert_parser.get_new_alerts()
                
                for alert in new_alerts:
                    if not self.running:
                        break
                        
                    self._process_alert(alert)
                    
                # Save state after processing
                if new_alerts:
                    self.state_manager.save_state()
                    
                time.sleep(self.config['alerts']['check_interval'])
                
            except Exception as e:
                self.logger.error(f"Error in alert processing: {e}", exc_info=True)
                time.sleep(5)
                
    def _process_alert(self, alert: dict):
        """Process a single alert"""
        try:
            symbol = alert['symbol']
            if self.position_tracker.has_position(symbol):
                self.logger.debug(f"Already have position in {symbol}, skipping")
                return
            self.logger.info(f"Processing alert for {symbol} at ${alert['price']}")
            
            # Risk checks
            if not self.risk_manager.check_pre_trade(alert):
                self.logger.info(f"Risk check failed for {symbol}")
                return
                
            # Update account value
            account_info = self.ibkr.get_account_summary()
            if account_info:
                self.risk_manager.update_account_value(
                    float(account_info.get('NetLiquidation', 50000))
                )
                
            # Calculate position size
            shares = self.risk_manager.calculate_shares(alert['price'])
            if shares <= 0:
                self.logger.warning(f"Invalid share count for {symbol}: {shares}")
                return
                
            # Place order
            order_result = self.order_manager.place_entry_order(
                symbol=symbol,
                shares=shares,
                entry_price=alert['price']
            )
            
            if order_result and order_result.get('success'):
                # Update state
                self.risk_manager.add_position(
                    symbol=symbol,
                    entry_price=alert['price'],
                    shares=shares,
                    order_id=order_result['order_id']
                )
                
                # Schedule time exit
                exit_time = datetime.now() + timedelta(
                    minutes=self.config['risk_management']['time_exit_minutes']
                )
                
                self.position_tracker.schedule_time_exit(symbol, exit_time)
                
                self.logger.info(
                    f"Order placed: {symbol} - {shares} shares @ ${alert['price']:.2f}, "
                    f"exit scheduled for {exit_time.strftime('%H:%M:%S')}"
                )
                
                # Log stats
                stats = self.risk_manager.get_daily_stats()
                self.logger.info(
                    f"Daily stats - Trades: {stats['trades']}/{stats['max_trades']}, "
                    f"Open: {stats['positions_open']}/{stats['max_positions']}"
                )
                
        except Exception as e:
            self.logger.error(f"Error processing alert: {e}", exc_info=True)
            
    def _exit_monitor_loop(self):
        """Monitor and execute time-based exits"""
        self.logger.info("Time exit monitor started")
        
        # Track symbols we're currently exiting to prevent duplicates
        exiting_symbols = set()
        
        while self.running:
            try:
                # Get positions due for exit
                positions_to_exit = self.position_tracker.get_positions_due_for_exit()
                
                if positions_to_exit:
                    self.logger.info(f"Found {len(positions_to_exit)} positions due for exit")
                    
                for symbol, position_data in positions_to_exit:
                    if not self.running:
                        break
                        
                    # Skip if already processing this symbol
                    if symbol in exiting_symbols:
                        self.logger.debug(f"Already processing exit for {symbol}")
                        continue
                        
                    self.logger.info(f"Executing time-based exit for {symbol}")
                    exiting_symbols.add(symbol)
                    
                    try:
                        # Execute exit
                        if self.order_manager.place_time_exit_order(symbol, position_data):
                            # Update risk manager
                            current_price = self._get_current_price(symbol)
                            if current_price:
                                self.risk_manager.remove_position(
                                    symbol=symbol,
                                    exit_price=current_price,
                                    exit_reason="TIME_EXIT_10MIN"
                                )
                    finally:
                        # Remove from exiting set
                        exiting_symbols.discard(symbol)
                        
                    # Save state after exit
                    self.state_manager.save_state()
                    
                time.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                self.logger.error(f"Error in exit monitor: {e}", exc_info=True)
                time.sleep(10)
                
    def _position_sync_loop(self):
        """Periodically sync positions with IBKR"""
        while self.running:
            try:
                time.sleep(300)  # Sync every 5 minutes
                
                if self.connected and self.position_tracker:
                    self.logger.info("Running position sync...")
                    self.ibkr.refresh_positions()
                    discrepancies = self.position_tracker.sync_positions()
                    if self.risk_manager:
                        self.risk_manager.sync_with_ibkr(self.ibkr.get_positions())

                    if discrepancies:
                        self.logger.warning(f"Found {len(discrepancies)} position discrepancies")
                        
            except Exception as e:
                self.logger.error(f"Error in position sync: {e}", exc_info=True)
                
    def _recover_pending_exits(self):
        """Recover pending exits from saved state"""
        pending_exits = self.state_manager.get_pending_exits()
        
        for symbol, exit_data in pending_exits.items():
            exit_time = datetime.fromisoformat(exit_data['exit_time'])
            
            if datetime.now() >= exit_time:
                self.logger.info(f"Executing overdue exit for {symbol}")
                self.order_manager.place_time_exit_order(symbol, exit_data)
            else:
                self.logger.info(f"Rescheduling exit for {symbol} at {exit_time}")
                self.position_tracker.schedule_time_exit(symbol, exit_time)
                
    def _is_market_hours(self) -> bool:
        """Check if market is open (US Eastern Time)"""
        now_et = datetime.now(self.market_tz)
        
        # Check if weekend
        if now_et.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return False
            
        # Market hours: 9:30 AM - 4:00 PM ET
        market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
        
        return True #market_open <= now_et <= market_close
        
    def _get_current_price(self, symbol: str) -> Optional[float]:
        """Get current market price"""
        try:
            ticker = self.ibkr.get_market_data(symbol)
            if ticker and hasattr(ticker, 'last'):
                return ticker.last
            elif ticker and hasattr(ticker, 'close'):
                return ticker.close
            return None
        except Exception as e:
            self.logger.error(f"Error getting price for {symbol}: {e}")
            return None
            
    def stop(self):
        """Stop the trading engine gracefully"""
    
        self.logger.info("Stopping trading engine...")
        self.running = False
        
        # Close all open positions - BUT CHECK THEY EXIST FIRST
        if self.position_tracker:
            # Get ACTUAL positions from IBKR
            actual_positions = {}
            if self.ibkr and self.ibkr.connected:
                ibkr_positions = self.ibkr.get_positions()
                for pos in ibkr_positions:
                    if pos.position > 0:
                        actual_positions[pos.contract.symbol] = pos.position
                        
            # Only close positions that actually exist
            tracked_positions = self.position_tracker.get_open_positions()
            for symbol in tracked_positions:
                if symbol in actual_positions:
                    self.logger.info(f"Closing position: {symbol}")
                    self.order_manager.place_time_exit_order(symbol, tracked_positions[symbol])
                else:
                    self.logger.info(f"Position {symbol} already closed, removing from tracking")
                    self.position_tracker.remove_position(symbol)
                
        # Save final state
        if self.state_manager:
            self.state_manager.save_state()
            
        # Disconnect from IBKR
        if self.ibkr:
            self.ibkr.disconnect()
            
        # Wait for threads to finish
        threads = [self.alert_thread, self.exit_monitor_thread, self.sync_thread]
        for thread in threads:
            if thread and thread.is_alive():
                thread.join(timeout=5)
                
        self.logger.info("Trading engine stopped")
        
    def is_running(self) -> bool:
        """Check if engine is running"""
        return self.running

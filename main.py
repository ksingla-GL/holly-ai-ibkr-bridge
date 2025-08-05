"""
Fixed Main Application - NO UNICODE CHARACTERS ANYWHERE
Single-threaded approach with proper error handling
"""

import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from src.core.ibkr_connector import IBKRConnector
from src.core.risk_manager import RiskManager  
from src.core.order_manager import OrderManager
from src.utils.logger import setup_logging
from src.utils.config_loader import load_config
from src.utils.csv_parser import HollyAlertParser

class TradingSystem:
    """Main trading system - simplified single-threaded approach"""
    
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.running = True
        
        # Initialize components
        self.ib_connector = None
        self.risk_manager = None
        self.order_manager = None
        self.parser = None
        
    def initialize(self) -> bool:
        """Initialize all components"""
        try:
            # Connect to IBKR
            self.logger.info("Initializing IBKR connector...")
            self.ib_connector = IBKRConnector(self.config)
            if not self.ib_connector.connect():
                self.logger.error("Failed to connect to IBKR")
                return False
            
            # Get initial account value
            self.logger.info("Getting account information...")
            account_info = self.ib_connector.get_account_summary()
            account_value = account_info.get('NetLiquidation', 50000)
            self.logger.info(f"Account value: ${account_value:,.2f}")
            
            # Initialize risk manager
            self.logger.info("Initializing risk manager...")
            self.risk_manager = RiskManager(self.config, account_value=account_value)
            
            # Initialize order manager
            self.logger.info("Initializing order manager...")
            self.order_manager = OrderManager(self.ib_connector, self.config)
            
            # Initialize CSV parser
            self.logger.info("Initializing CSV parser...")
            self.parser = HollyAlertParser("config/config.json")
            
            # Show processed alerts stats
            stats = self.parser.get_processed_alerts_stats()
            if stats['total'] > 0:
                self.logger.info(f"Processed alerts by date: {stats}")
            
            self.logger.info("All components initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Initialization failed: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    def run(self):
        """Main trading loop"""
        self.logger.info("Starting trading system...")
        
        last_exit_check = time.time()
        
        while self.running:
            try:
                if not self.ib_connector.ensure_connection():
                    self.logger.warning("IBKR disconnected, retrying...")
                    time.sleep(5)
                    continue

                # Check market hours
                if not self.ib_connector.is_market_hours():
                    self.logger.info("Market closed, waiting...")
                    time.sleep(60)  # Check every minute
                    continue
                
                # Process new alerts
                self._process_alerts()
                
                # Check time exits every 10 seconds
                if time.time() - last_exit_check >= 10:
                    self._check_time_exits()
                    last_exit_check = time.time()
                
                # Wait before next iteration
                time.sleep(self.config['alerts']['check_interval'])
                
            except KeyboardInterrupt:
                self.logger.info("Shutdown requested")
                break
            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")
                time.sleep(5)
    
    def _process_alerts(self):
        """Process new alerts from CSV"""
        try:
            new_alerts = self.parser.parse_alerts()
            
            # Parser already handles duplicate detection, so process all returned alerts
            for alert in new_alerts:
                self._handle_alert(alert)
                    
        except Exception as e:
            self.logger.error(f"Error processing alerts: {e}")
    
    def _handle_alert(self, alert):
        """Handle individual alert"""
        try:
            symbol = alert['symbol']
            
            # Risk checks
            if not self.risk_manager.check_pre_trade(alert):
                self.logger.info(f"Risk check failed for {symbol}")
                return
            
            # Update account value
            account_info = self.ib_connector.get_account_summary()
            if account_info:
                self.risk_manager.update_account_value(
                    account_info.get('NetLiquidation', 50000)
                )
            
            # Calculate position size
            shares = self.risk_manager.calculate_shares(alert['price'])
            if shares <= 0:
                self.logger.warning(f"Invalid share count for {symbol}: {shares}")
                return
            
            # Place order
            order_id = self.order_manager.place_entry_order(
                symbol=symbol,
                shares=shares,
                entry_price=alert['price']
            )
            
            if order_id:
                # Track position
                self.risk_manager.add_position(
                    symbol=symbol,
                    entry_price=alert['price'],
                    shares=shares,
                    order_id=order_id
                )
                
                # Log stats
                stats = self.risk_manager.get_daily_stats()
                self.logger.info(f"Daily stats - Trades: {stats['trades']}, "
                               f"Open: {stats['positions_open']}, "
                               f"Remaining: {stats['trades_remaining']}")
                
        except Exception as e:
            self.logger.error(f"Error handling alert: {e}")
    
    def _check_time_exits(self):
        """Check and execute time-based exits"""
        try:
            # Refresh position data first
            self.ib_connector.refresh_positions()
            
            # Get symbols that need exit
            symbols_to_exit = self.order_manager.check_time_exits()
            
            for symbol in symbols_to_exit:
                self.logger.info(f"Executing time exit for {symbol}")
                
                if self.order_manager.execute_time_exit(symbol):
                    # Get current price for P&L calculation (approximate)
                    current_price = self._get_current_price(symbol)
                    
                    # Remove from risk manager tracking
                    self.risk_manager.remove_position(
                        symbol=symbol,
                        exit_price=current_price or 0,  # Use 0 if can't get price
                        exit_reason="TIME_EXIT_10MIN"
                    )
                    
                    self.logger.info(f"Time exit completed for {symbol}")
                        
        except Exception as e:
            self.logger.error(f"Error checking time exits: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
    
    def _get_current_price(self, symbol: str) -> float:
        """Get current price for a symbol"""
        try:
            # For time exits, use the last known price or a reasonable estimate
            # In paper trading, this doesn't need to be perfect
            positions = self.ib_connector.get_positions()
            
            for pos in positions:
                if pos.contract.symbol == symbol:
                    return pos.marketPrice if hasattr(pos, 'marketPrice') else pos.avgCost
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting price for {symbol}: {e}")
            return None
    
    def shutdown(self):
        """Graceful shutdown"""
        self.logger.info("Initiating graceful shutdown...")
        self.running = False
        
        try:
            if self.order_manager:
                # Get fresh position data
                self.ib_connector.refresh_positions()
                
                # Close all pending exits
                pending_exits = self.order_manager.get_pending_exits()
                
                if pending_exits:
                    self.logger.info(f"Closing {len(pending_exits)} open positions...")
                    
                    for symbol in pending_exits:
                        self.logger.info(f"Closing position on shutdown: {symbol}")
                        success = self.order_manager.execute_time_exit(symbol)
                        if success:
                            self.logger.info(f"Successfully closed {symbol}")
                        else:
                            self.logger.warning(f"Failed to close {symbol}")
                else:
                    self.logger.info("No open positions to close")
            
            # Final position check
            if self.ib_connector:
                positions = self.ib_connector.get_positions()
                remaining_positions = [(p.contract.symbol, p.position) for p in positions if p.position != 0]
                
                if remaining_positions:
                    self.logger.warning(f"Remaining positions after shutdown: {remaining_positions}")
                else:
                    self.logger.info("All positions successfully closed")
                
                self.ib_connector.disconnect()
                
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            
        self.logger.info("Shutdown complete")

def main():
    """Main entry point"""
    try:
        # Load configuration
        config = load_config('config/config.json')
        
        # Setup logging
        setup_logging(config.get('logging', {}))
        logger = logging.getLogger(__name__)
        
        logger.info("============================================================")
        logger.info("Holly AI to IBKR Bridge Starting")
        logger.info("============================================================")
        
        # Create and initialize system
        system = TradingSystem(config)
        
        if not system.initialize():
            logger.error("System initialization failed")
            return
        
        # Run the system
        system.run()
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        if 'system' in locals():
            system.shutdown()

if __name__ == "__main__":
    main()
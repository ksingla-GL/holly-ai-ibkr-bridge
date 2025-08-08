"""
Simplified IBKR Connector - Fixed Version
Removes async/sync mixing issues
"""

from ib_insync import *
import logging
import json
from typing import Optional, Dict, List, Union
import time
from datetime import datetime, time as dt_time
import pytz

util.startLoop()
logger = logging.getLogger(__name__)

class IBKRConnector:
    def __init__(self, config: Union[Dict, str] = "config/config.json"):
        """Initialize IBKR Connector with configuration support"""
        if isinstance(config, str):
            with open(config, 'r') as f:
                full_config = json.load(f)
        else:
            full_config = config

        # Split full configuration for convenience
        self.full_config = full_config
        self.ib_config = full_config.get('ibkr', full_config)
        self.system_config = full_config.get('system', {})

        self.ib = IB()
        self.connected = False
        self.account = None
        self.contracts_cache = {}
        self.active_orders = {}  # Track active orders for each symbol
        
    def is_market_hours(self) -> bool:
        """Check if market is open based on configured hours"""
        hours_cfg = self.system_config.get('market_hours', {})
        if not hours_cfg.get('enabled', True):
            return True

        now = datetime.now()
        if now.weekday() >= 5:  # Weekend
            logger.info("Weekend - market closed")
            return False

        try:
            tz_name = self.system_config.get('market_timezone', 'US/Eastern')
            tz = pytz.timezone(tz_name)
            current_time = now.astimezone(tz).time()
            start_str = hours_cfg.get('start', '09:30')
            end_str = hours_cfg.get('end', '16:00')
            start = dt_time.fromisoformat(start_str)
            end = dt_time.fromisoformat(end_str)
            return start <= current_time <= end
        except Exception as e:
            logger.warning(f"Market hours check failed: {e}")
            return True

    def ensure_connection(self) -> bool:
        """Ensure IBKR connection is alive, attempt reconnection if needed"""
        try:
            if self.ib.isConnected():
                # Heartbeat check
                self.ib.reqCurrentTime()
                return True
        except Exception:
            logger.warning("IBKR connection appears lost")

        # Attempt reconnection with basic backoff
        for delay in [1, 2, 4, 8]:
            logger.info("Attempting to reconnect to IBKR...")
            if self.connect():
                return True
            time.sleep(delay)
        return False
    
    def refresh_positions(self):
        """Force refresh of position data"""
        try:
            self.ib.reqPositions()
            time.sleep(1)  # Wait for update
            logger.info("Position data refreshed")
        except Exception as e:
            logger.error(f"Error refreshing positions: {e}")
    
    def connect(self) -> bool:
        """Simplified synchronous connection"""
        try:
            if self.ib.isConnected():
                self.ib.disconnect()
                time.sleep(1)
            
            logger.info("Connecting to IBKR...")
            self.ib.connect(
                self.ib_config['host'],
                self.ib_config['port'],
                clientId=self.ib_config.get('client_id', 1),
                timeout=20
            )
            
            # Wait for connection to stabilize
            time.sleep(3)
            
            # Get account
            accounts = self.ib.managedAccounts()
            if accounts:
                self.account = accounts[0]
                logger.info(f"Connected with account: {self.account}")
            else:
                # Fallback for paper accounts
                self.account = "DU1234567"  # Default paper account
                logger.warning(f"Using default account: {self.account}")
            
            self.connected = True
            
            # Setup error handler
            self.ib.errorEvent += self._on_error
            
            return True
            
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False
    
    def place_market_order_with_stop(self, symbol: str, quantity: int, stop_price: float):
        """Place market order with stop - SIMPLIFIED RELIABLE APPROACH"""
        try:
            if not self.is_market_hours():
                logger.warning("Market is closed, skipping order")
                return None
                
            # Get contract
            contract = self._get_contract(symbol)
            if not contract:
                return None
            
            # SIMPLIFIED APPROACH: Just place market order first, then stop separately
            logger.info(f"Placing market order for {symbol}: {quantity} shares")
            
            # Create simple market order
            market_order = MarketOrder('BUY', quantity)
            market_order.account = self.account
            market_order.transmit = True  # Transmit immediately
            
            # Place the market order
            trade = self.ib.placeOrder(contract, market_order)
            
            # Wait a moment for order to be processed
            import time
            time.sleep(2)
            
            # Check if order was filled
            filled = False
            for i in range(30):  # Wait up to 3 seconds
                self.ib.sleep(0.1)
                if trade.orderStatus.status == 'Filled':
                    filled = True
                    break
                elif trade.orderStatus.status in ['Cancelled', 'Rejected']:
                    logger.error(f"Market order rejected: {trade.orderStatus.status}")
                    return None
            
            if filled:
                fill_price = trade.orderStatus.avgFillPrice
                logger.info(f"Market order filled at ${fill_price}")
                
                # Now place stop order separately
                logger.info(f"Placing stop order at ${stop_price}")
                
                stop_order = StopOrder('SELL', quantity, stop_price)
                stop_order.account = self.account
                stop_order.transmit = True
                
                stop_trade = self.ib.placeOrder(contract, stop_order)
                logger.info(f"Stop order placed successfully")
                
                # Store both trades for tracking
                self.active_orders[symbol] = {
                    'entry_trade': trade,
                    'stop_trade': stop_trade,
                    'quantity': quantity
                }
                
                return trade
            else:
                logger.error(f"Market order failed to fill: {trade.orderStatus.status}")
                return None
                
        except Exception as e:
            logger.error(f"Order placement failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def close_position(self, symbol: str, quantity: int) -> Optional[float]:
        """Close position with market order and return fill price if successful."""
        try:
            # First, let's refresh positions to make sure we have latest data
            self.ib.reqPositions()
            time.sleep(1)  # Give it time to update
            
            # Get actual current positions
            positions = self.get_positions()
            actual_quantity = 0
            position_found = False
            
            logger.info(f"Looking for position: {symbol}")
            logger.info(f"Current positions: {[(p.contract.symbol, p.position) for p in positions]}")
            
            for pos in positions:
                if pos.contract.symbol == symbol and pos.position != 0:
                    actual_quantity = abs(int(pos.position))  # Use absolute value and convert to int
                    position_found = True
                    logger.info(f"Found position: {symbol} - {actual_quantity} shares")
                    break
            
            if not position_found:
                logger.warning(f"No actual position found for {symbol} in IBKR")
                # Check if we have any orders for this symbol that might be filled
                orders = self.ib.orders()
                for order in orders:
                    if hasattr(order, 'contract') and order.contract.symbol == symbol:
                        logger.info(f"Found order for {symbol}: {order.orderStatus.status}")

                return None
            
            # Cancel any existing orders for this symbol first
            self._cancel_orders_for_symbol(symbol)
            time.sleep(0.5)  # Wait for cancellation
            
            # Get contract
            contract = self._get_contract(symbol)
            if not contract:
                return None
            
            # Place market sell order
            order = MarketOrder('SELL', actual_quantity)
            order.account = self.account
            order.transmit = True  # Make sure it transmits immediately
            
            trade = self.ib.placeOrder(contract, order)
            logger.info(f"Placed close order for {symbol}: {actual_quantity} shares")
            
            # Wait for fill (up to 15 seconds for market orders)
            for i in range(150):  # 15 seconds
                self.ib.sleep(0.1)
                if trade.orderStatus.status == 'Filled':
                    fill_price = trade.orderStatus.avgFillPrice or 0
                    logger.info(f"Position closed: {symbol} at ${fill_price}")
                    return fill_price
                elif trade.orderStatus.status in ['Cancelled', 'Rejected']:
                    logger.error(f"Close order failed: {trade.orderStatus.status}")
                    return None

            logger.warning(f"Close order timeout for {symbol}, status: {trade.orderStatus.status}")
            return None

        except Exception as e:
            logger.error(f"Error closing position for {symbol}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def _get_contract(self, symbol: str):
        """Get contract for symbol"""
        if symbol in self.contracts_cache:
            return self.contracts_cache[symbol]
        
        try:
            contract = Stock(symbol, 'SMART', 'USD')
            qualified = self.ib.qualifyContracts(contract)
            
            if qualified:
                self.contracts_cache[symbol] = qualified[0]
                return qualified[0]
            else:
                logger.error(f"Could not qualify contract for {symbol}")
                return None
                
        except Exception as e:
            logger.error(f"Contract error: {e}")
            return None
    
    def _cancel_orders_for_symbol(self, symbol: str):
        """Cancel all orders for a symbol"""
        try:
            # Cancel from active orders tracking
            if symbol in self.active_orders:
                orders_data = self.active_orders[symbol]
                
                # Cancel stop order
                if 'stop_trade' in orders_data:
                    self.ib.cancelOrder(orders_data['stop_trade'].order)
                    logger.info(f"Cancelled stop order for {symbol}")
                
                # Remove from tracking
                del self.active_orders[symbol]
            
            # Also cancel any other orders for this symbol
            orders = self.ib.orders()
            for order in orders:
                if hasattr(order, 'contract') and order.contract.symbol == symbol:
                    self.ib.cancelOrder(order)
                    logger.info(f"Cancelled order for {symbol}")
                    
        except Exception as e:
            logger.error(f"Error cancelling orders: {e}")
    
    def get_positions(self):
        """Get current positions"""
        try:
            return self.ib.positions()
        except:
            return []
    
    def get_account_summary(self) -> Dict:
        """Get account summary"""
        try:
            if not self.account:
                return {"NetLiquidation": 50000.0}
            
            summary = {}
            values = self.ib.accountValues(self.account)
            
            for value in values:
                if value.tag in ['NetLiquidation', 'BuyingPower']:
                    summary[value.tag] = float(value.value)
            
            return summary if summary else {"NetLiquidation": 50000.0}
            
        except Exception as e:
            logger.error(f"Account summary error: {e}")
            return {"NetLiquidation": 50000.0}
    
    def _on_error(self, reqId, errorCode, errorString, contract):
        """Handle IB errors"""
        # Ignore harmless errors
        if errorCode in [2104, 2106, 2107, 2108, 2158, 10167]:
            return
        logger.error(f"IB Error {errorCode}: {errorString}")
    
    def disconnect(self):
        """Disconnect from IB"""
        if self.connected:
            self.ib.disconnect()
            self.connected = False
            logger.info("Disconnected from IBKR")
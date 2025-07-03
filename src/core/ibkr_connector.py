"""IBKR TWS API Connector - Fixed for Event Loop Issues"""
from ib_insync import *
from loguru import logger
import json
from typing import Optional, Dict, List
import asyncio
from datetime import datetime

# Configure ib_insync to work with existing event loops
util.startLoop()  # This prevents the event loop conflict

class IBKRConnector:
    def __init__(self, config_path: str = "config/config.json"):
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        self.ib = IB()
        self.connected = False
        self.contracts = {}  # Cache for qualified contracts
        self.active_orders = {}  # Track active orders
        
    async def connect(self) -> bool:
        """Connect to IBKR TWS/Gateway"""
        try:
            # SAFETY CHECK
            if self.config['ibkr']['port'] == 7496:
                logger.error("BLOCKED: Port 7496 is for LIVE trading! Use 7497 for paper trading.")
                return False
                
            await self.ib.connectAsync(
                host=self.config['ibkr']['host'],
                port=self.config['ibkr']['port'],
                clientId=self.config['ibkr']['client_id']
            )
            self.connected = True
            logger.info("Connected to IBKR TWS")
            
            # Set up event handlers
            self.ib.orderStatusEvent += self.on_order_status
            self.ib.execDetailsEvent += self.on_exec_details
            self.ib.errorEvent += self.on_error
            
            # Don't wait for account data - just return success
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to IBKR: {e}")
            self.connected = False
            return False
    
    async def place_bracket_order(self, symbol: str, quantity: int, 
                                 entry_price: float, stop_loss: float, 
                                 take_profit: float) -> Optional[Trade]:
        """Place bracket order (entry + stop loss + take profit)"""
        if not self.connected:
            logger.error("Not connected to IBKR")
            return None
            
        try:
            # Get or create contract
            contract = await self.get_contract(symbol)
            if not contract:
                return None
            
            # Create bracket order using ib_insync's bracketOrder method
            bracket = self.ib.bracketOrder(
            action='BUY',
            quantity=quantity,
            limitPrice=entry_price,
            stopLossPrice=round(stop_loss, 2),  # Ensure 2 decimals
            takeProfitPrice=round(take_profit, 2),  # Ensure 2 decimals
            #outsideRth=True
        )
            
            # Place all orders with parent transmitted last
            trades = []
            for i, order in enumerate(bracket):
                if i == 0:  # Parent order
                    order.transmit = False
                elif i == len(bracket) - 1:  # Last order
                    order.transmit = True
                else:
                    order.transmit = False
                    
                trade = self.ib.placeOrder(contract, order)
                trades.append(trade)
                self.active_orders[order.orderId] = {
                    'symbol': symbol,
                    'order': order,
                    'trade': trade
                }
                
            logger.info(f"Placed bracket order for {symbol}: Entry @ market, SL @ ${stop_loss:.2f}, TP @ ${take_profit:.2f}")
            
            # Return the parent trade
            return trades[0] if trades else None
            
        except Exception as e:
            logger.error(f"Error placing bracket order for {symbol}: {e}")
            return None
    
    async def place_order(self, alert: Dict) -> Optional[Trade]:
        """Place simple market order (fallback method)"""
        if not self.connected:
            logger.error("Not connected to IBKR")
            return None
            
        try:
            # Get or create contract
            contract = await self.get_contract(alert['symbol'])
            if not contract:
                return None
            
            # Calculate position size
            quantity = self._calculate_position_size(alert['price'])
            
            # Create market order
            order = MarketOrder('BUY', quantity)
            
            # Place order
            trade = self.ib.placeOrder(contract, order)
            self.active_orders[order.orderId] = {
                'symbol': alert['symbol'],
                'order': order,
                'trade': trade
            }
            
            logger.info(f"Placed market order: {alert['symbol']} x{quantity}")
            
            # Wait for fill
            await asyncio.sleep(1)
            
            return trade
            
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return None
    
    async def close_position(self, symbol: str, quantity: int, 
                           parent_order_id: int = None) -> bool:
        """Close position by cancelling bracket orders and selling"""
        if not self.connected:
            logger.error("Not connected to IBKR")
            return False
            
        try:
            # Cancel any child orders (stop loss and take profit)
            if parent_order_id:
                for order_id, order_info in list(self.active_orders.items()):
                    order = order_info['order']
                    if hasattr(order, 'parentId') and order.parentId == parent_order_id:
                        self.ib.cancelOrder(order)
                        logger.info(f"Cancelled child order {order_id}")
                        del self.active_orders[order_id]
            
            # Get contract
            contract = await self.get_contract(symbol)
            if not contract:
                return False
            
            # Place market sell order
            sell_order = MarketOrder('SELL', quantity)
            trade = self.ib.placeOrder(contract, sell_order)
            
            logger.info(f"Placed closing order for {symbol} x{quantity}")
            
            # Wait for fill
            await asyncio.sleep(2)
            
            return trade.orderStatus.status == 'Filled'
            
        except Exception as e:
            logger.error(f"Error closing position {symbol}: {e}")
            return False
    
    async def get_contract(self, symbol: str) -> Optional[Contract]:
        """Get or create qualified contract"""
        if symbol in self.contracts:
            return self.contracts[symbol]
            
        try:
            contract = Stock(symbol, 'SMART', 'USD')
            qualified = await self.ib.qualifyContractsAsync(contract)
            
            if qualified:
                self.contracts[symbol] = qualified[0]
                return qualified[0]
            else:
                logger.warning(f"Failed to qualify contract for {symbol} (might be demo limitation)")
                return None
                
        except Exception as e:
            logger.warning(f"Error getting contract for {symbol}: {e}")
            return None
    
    async def get_real_time_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Get real-time prices for multiple symbols"""
        prices = {}
        
        if not self.connected:
            return prices
            
        try:
            for symbol in symbols:
                contract = await self.get_contract(symbol)
                if contract:
                    # Request market data
                    ticker = self.ib.reqMktData(contract, '', False, False)
                    
                    # Wait for data with timeout
                    timeout = 5
                    start_time = asyncio.get_event_loop().time()
                    
                    while asyncio.get_event_loop().time() - start_time < timeout:
                        await asyncio.sleep(0.1)
                        
                        # Check if we have valid price data
                        if ticker.last and not util.isNan(ticker.last):
                            prices[symbol] = ticker.last
                            break
                        elif ticker.close and not util.isNan(ticker.close):
                            prices[symbol] = ticker.close
                            break
                        elif ticker.bid and ticker.ask and not util.isNan(ticker.bid) and not util.isNan(ticker.ask):
                            prices[symbol] = (ticker.bid + ticker.ask) / 2
                            break
                    
                    # Cancel market data subscription
                    self.ib.cancelMktData(contract)
                    
            return prices
            
        except Exception as e:
            logger.error(f"Error getting real-time prices: {e}")
            return prices
    
    async def get_order_status(self, order_id: int) -> str:
        """Get status of specific order"""
        if order_id in self.active_orders:
            trade = self.active_orders[order_id]['trade']
            return trade.orderStatus.status
        return 'Unknown'
    
    async def get_account_info(self) -> Dict:
        """Get account summary information"""
        if not self.connected:
            return {}
            
        try:
            account_values = {}
            
            # Wait a bit for account data to populate
            await asyncio.sleep(0.5)
            
            summary = self.ib.accountSummary()
            
            for item in summary:
                if item.tag in ['TotalCashValue', 'BuyingPower', 'NetLiquidation', 
                               'UnrealizedPnL', 'RealizedPnL', 'AvailableFunds']:
                    account_values[item.tag] = item.value
                    
            # If empty, try account values
            if not account_values:
                values = self.ib.accountValues()
                for item in values:
                    if item.tag in ['TotalCashValue', 'BuyingPower', 'NetLiquidationByCurrency']:
                        account_values[item.tag] = item.value
                        
            return account_values
            
        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            return {}
    
    def get_positions(self) -> list:
        """Get current positions"""
        if not self.connected:
            return []
        return self.ib.positions()
    
    def _calculate_position_size(self, price: float) -> int:
        """Calculate position size based on risk parameters"""
        max_capital = self.config['risk']['max_capital_per_trade']
        quantity = int(max_capital / price)
        return max(1, quantity)
    
    # Event handlers
    def on_order_status(self, trade: Trade):
        """Handle order status updates"""
        status = trade.orderStatus.status
        order_id = trade.order.orderId
        
        logger.info(f"Order {order_id} status: {status}")
        
        if status in ['Filled', 'Cancelled', 'ApiCancelled']:
            # Remove from active orders
            if order_id in self.active_orders:
                del self.active_orders[order_id]
    
    def on_exec_details(self, trade: Trade, fill: Fill):
        """Handle execution details"""
        logger.info(f"Execution: {fill.contract.symbol} {fill.execution.side} "
                   f"{fill.execution.shares} @ ${fill.execution.price:.2f}")
    
    def on_error(self, reqId: int, errorCode: int, errorString: str, contract: Contract):
        """Handle errors"""
        # Ignore common non-error codes
        if errorCode in [2104, 2106, 2107, 2108, 2158]:  # Market data farm messages
            return
        logger.error(f"Error {errorCode}: {errorString}")
    
    def disconnect(self):
        """Disconnect from IBKR"""
        if self.connected:
            # Cancel any market data subscriptions
            for contract in self.contracts.values():
                try:
                    self.ib.cancelMktData(contract)
                except:
                    pass
                    
            self.ib.disconnect()
            self.connected = False
            logger.info("Disconnected from IBKR")

    def __del__(self):
        """Cleanup on deletion"""
        try:
            self.disconnect()
        except:
            pass
"""IBKR TWS API Connector"""
from ib_insync import *
from loguru import logger
import json
from typing import Optional, Dict
import asyncio

class IBKRConnector:
    def __init__(self, config_path: str = "config/config.json"):
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        self.ib = IB()
        self.connected = False
        
    async def connect(self) -> bool:
        """Connect to IBKR TWS/Gateway"""
        try:
            await self.ib.connectAsync(
                host=self.config['ibkr']['host'],
                port=self.config['ibkr']['port'],
                clientId=self.config['ibkr']['client_id']
            )
            self.connected = True
            logger.info("Connected to IBKR TWS")
            
            # Request account updates
            self.ib.reqAccountUpdates()
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to IBKR: {e}")
            self.connected = False
            return False
    
    async def place_order(self, alert: Dict) -> Optional[Trade]:
        """Place order based on alert"""
        if not self.connected:
            logger.error("Not connected to IBKR")
            return None
            
        try:
            # Create contract
            contract = Stock(alert['symbol'], 'SMART', 'USD')
            
            # Qualify contract
            await self.ib.qualifyContractsAsync(contract)
            
            # Create order
            quantity = self._calculate_position_size(alert['price'])
            order = MarketOrder('BUY', quantity)
            
            # Place order
            trade = self.ib.placeOrder(contract, order)
            logger.info(f"Placed order: {alert['symbol']} x{quantity} @ market")
            
            return trade
            
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return None
    
    def _calculate_position_size(self, price: float) -> int:
        """Calculate position size based on risk parameters"""
        max_capital = self.config['risk']['max_capital_per_trade']
        quantity = int(max_capital / price)
        return max(1, quantity)
    
    def get_positions(self) -> list:
        """Get current positions"""
        if not self.connected:
            return []
        return self.ib.positions()
    
    def get_account_summary(self) -> Dict:
        """Get account summary"""
        if not self.connected:
            return {}
        return {tag.tag: tag.value for tag in self.ib.accountSummary()}
    
    def disconnect(self):
        """Disconnect from IBKR"""
        if self.connected:
            self.ib.disconnect()
            self.connected = False
            logger.info("Disconnected from IBKR")

"""Main Trading System"""
import asyncio
import json
import threading
from datetime import datetime
from loguru import logger
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Import modules
from utils.csv_parser import HollyAlertParser
from core.ibkr_connector import IBKRConnector
from risk.risk_manager import RiskManager
from dashboard.app import run_dashboard, update_dashboard_data

class CSVWatcher(FileSystemEventHandler):
    """Watch for CSV file changes"""
    def __init__(self, callback):
        self.callback = callback
        
    def on_modified(self, event):
        if event.src_path.endswith('.csv'):
            self.callback()

class TradingSystem:
    def __init__(self):
        # Load config
        with open('config/config.json', 'r') as f:
            self.config = json.load(f)
            
        # Initialize components
        self.parser = HollyAlertParser()
        self.ibkr = IBKRConnector()
        self.risk_manager = RiskManager()
        self.running = False
        
        # Setup logging
        logger.add("logs/trading_{time}.log", rotation="1 day")
        
    async def start(self):
        """Start trading system"""
        logger.info("Starting Holly AI - IBKR Trading System")
        
        # Connect to IBKR
        connected = await self.ibkr.connect()
        if not connected:
            logger.error("Failed to connect to IBKR. Exiting.")
            return
            
        self.running = True
        
        # Start dashboard in separate thread
        dashboard_thread = threading.Thread(
            target=run_dashboard, 
            args=(self.config,)
        )
        dashboard_thread.daemon = True
        dashboard_thread.start()
        
        # Setup file watcher
        observer = Observer()
        observer.schedule(
            CSVWatcher(self.process_alerts),
            path='data/alerts',
            recursive=False
        )
        observer.start()
        
        # Main trading loop
        try:
            while self.running:
                await self.trading_loop()
                await asyncio.sleep(self.config['alerts']['check_interval'])
                
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            observer.stop()
            observer.join()
            self.ibkr.disconnect()
            
    async def trading_loop(self):
        """Main trading loop"""
        # Update dashboard data
        self.update_dashboard()
        
        # Check for exit signals
        await self.check_exit_signals()
        
        # Process new alerts
        self.process_alerts()
        
    def process_alerts(self):
        """Process new alerts from CSV"""
        alerts = self.parser.parse_alerts()
        
        for alert in alerts:
            # Check risk rules
            if not self.risk_manager.check_trade_allowed(alert):
                continue
                
            # Place order
            asyncio.create_task(self.place_trade(alert))
            
    async def place_trade(self, alert):
        """Place trade based on alert"""
        logger.info(f"Processing alert for {alert['symbol']}")
        
        # Place order
        trade = await self.ibkr.place_order(alert)
        
        if trade:
            # Calculate risk levels
            stop_loss = self.risk_manager.calculate_stop_loss(alert['price'])
            take_profit = self.risk_manager.calculate_take_profit(alert['price'])
            
            # Track position
            trade_data = {
                'symbol': alert['symbol'],
                'entry_price': alert['price'],
                'quantity': trade.order.totalQuantity,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'entry_time': datetime.now(),
                'trade': trade,
                'timestamp': datetime.now()
            }
            
            self.risk_manager.update_position(alert['symbol'], trade_data)
            logger.info(f"Opened position: {alert['symbol']} SL: {stop_loss} TP: {take_profit}")
            
    async def check_exit_signals(self):
        """Check for exit conditions"""
        positions = list(self.risk_manager.active_positions.items())
        
        for symbol, position in positions:
            # Get current price (simplified - in production use real-time data)
            current_price = position['entry_price']  # Placeholder
            
            # Check stop loss
            if current_price <= position['stop_loss']:
                await self.close_position(symbol, current_price, "Stop Loss")
                
            # Check take profit
            elif current_price >= position['take_profit']:
                await self.close_position(symbol, current_price, "Take Profit")
                
            # Check time-based exit
            elif self.risk_manager.should_exit_time_based(position['entry_time']):
                await self.close_position(symbol, current_price, "Time Exit")
                
    async def close_position(self, symbol: str, price: float, reason: str):
        """Close position"""
        logger.info(f"Closing {symbol} position - Reason: {reason}")
        
        # Place closing order (simplified)
        # In production, implement proper closing logic
        
        # Update risk manager
        self.risk_manager.remove_position(symbol, price)
        
    def update_dashboard(self):
        """Update dashboard with current data"""
        # Get account info
        account_summary = self.ibkr.get_account_summary()
        update_dashboard_data('account_info', {
            'balance': account_summary.get('TotalCashValue', 0),
            'buying_power': account_summary.get('BuyingPower', 0),
            'daily_pnl': self.risk_manager.daily_pnl
        })
        
        # Update risk metrics
        update_dashboard_data('risk_metrics', {
            'trades_today': len(self.risk_manager.daily_trades),
            'max_trades': self.config['risk']['max_trades_per_day'],
            'daily_loss': abs(min(0, self.risk_manager.daily_pnl)),
            'max_loss': self.config['risk']['max_daily_loss'],
            'active_positions': len(self.risk_manager.active_positions)
        })
        
        # Update active trades
        active_trades = []
        for symbol, position in self.risk_manager.active_positions.items():
            duration = (datetime.now() - position['entry_time']).seconds // 60
            active_trades.append({
                'symbol': symbol,
                'entry_price': position['entry_price'],
                'current_price': position['entry_price'],  # Placeholder
                'pnl': 0,  # Calculate based on current price
                'duration': f"{duration}m"
            })
        update_dashboard_data('active_trades', active_trades)

if __name__ == "__main__":
    system = TradingSystem()
    asyncio.run(system.start())

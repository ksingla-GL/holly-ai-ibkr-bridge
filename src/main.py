"""Main Trading System - Complete Version"""
import os
import asyncio
import json
import threading
from datetime import datetime
from loguru import logger
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import time
import pytz

# Import modules
from utils.csv_parser import HollyAlertParser
from core.ibkr_connector import IBKRConnector

class CSVWatcher(FileSystemEventHandler):
    """Watch for CSV file changes"""
    def __init__(self, callback):
        self.callback = callback
        self.last_modified = 0
        
    def on_modified(self, event):
        if event.src_path.endswith('.csv'):
            # Debounce to avoid multiple calls
            current_time = time.time()
            if current_time - self.last_modified > 1:
                self.last_modified = current_time
                self.callback()

class TradingSystem:
    def __init__(self):
        # Load config
        with open('config/config.json', 'r') as f:
            self.config = json.load(f)
            
        # Initialize components
        self.parser = HollyAlertParser()
        self.ibkr = IBKRConnector()
        # REMOVE: self.risk_manager = RiskManager()
        self.running = False
        self.process_lock = asyncio.Lock()
        self.processed_symbols = set()  # ADD THIS - simple position tracking
        
        logger.info("Starting Holly AI - IBKR Trading System")
        logger.warning(f"Trading Mode: {'PAPER' if self.config['ibkr']['port'] == 7497 else 'LIVE'} (Port {self.config['ibkr']['port']})")
        
        # Setup logging
        logger.add("logs/trading_{time}.log", rotation="1 day")
        
    async def start(self):
        """Start trading system"""
        
        # Connect to IBKR
        connected = await self.ibkr.connect()
        if not connected:
            logger.error("Failed to connect to IBKR. Exiting.")
            return
        
        # Check for account info after connection
        account_info = await self.ibkr.get_account_info()
        if not account_info:
            logger.error("Cannot retrieve account info - check TWS permissions")
            return
        logger.info(f"Connected to account with buying power: ${account_info.get('BuyingPower', 0)}")    
        
        self.running = True
        
        # Process existing alerts on startup
        logger.info("Processing initial alerts...")
        await self.process_alerts()
        
        # Setup file watcher for new alerts
        observer = Observer()
        event_handler = CSVWatcher(lambda: asyncio.create_task(self.process_alerts_async()))
        observer.schedule(
            event_handler,
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
            self.running = False
            # REMOVE price_monitor_task.cancel()
            observer.stop()
            observer.join()
            self.ibkr.disconnect()
            
    async def trading_loop(self):
        """Main trading loop"""
        # Just keep running - file watcher handles new alerts
        pass
        
    async def process_alerts_async(self):
        """Async wrapper for process_alerts"""
        async with self.process_lock:
            await self.process_alerts()
        
    async def process_alerts(self):
        """Process new alerts from CSV"""
        try:
            alerts = self.parser.parse_alerts() 
            for alert in alerts:
                # Check if market is open
                if not self.is_market_open():
                    logger.info("Market closed, skipping alert")
                    continue
                    
                # Place order
                await self.place_trade(alert)
                
        except Exception as e:
            logger.error(f"Error processing alerts: {e}")
            
    async def place_trade(self, alert):
        """Place trade based on alert"""
        logger.info(f"Processing alert for {alert['symbol']}")
        
        # Simple duplicate check
        if alert['symbol'] in self.processed_symbols:
            logger.warning(f"Already processed {alert['symbol']}")
            return
        
        try:
            # Calculate simple position size
            position_size = int(self.config['risk']['max_capital_per_trade'] / alert['price'])
            position_size = max(1, position_size)
            
            # Simple stop/target calculation
            stop_loss = round(alert['price'] * 0.98, 2)  # 2% stop
            take_profit = round(alert['price'] * 1.05, 2)  # 5% target
            
            # Place bracket order
            trade = await self.ibkr.place_bracket_order(
                symbol=alert['symbol'],
                quantity=position_size,
                entry_price=alert['price'],
                stop_loss=stop_loss,
                take_profit=take_profit
            )
            
            if trade:
                self.processed_symbols.add(alert['symbol'])
                logger.info(f"Opened position: {alert['symbol']} x{position_size} @ ${alert['price']:.2f}")
            
        except Exception as e:
            logger.error(f"Error placing trade for {alert['symbol']}: {e}")
            
    def is_market_open(self):
        """Check if US market is open (timezone aware)"""
        
        # Get current time in US Eastern
        eastern = pytz.timezone('US/Eastern')
        now_et = datetime.now(eastern)
        
        # Check if weekday (Mon=0, Fri=4)
        if now_et.weekday() > 4:  # Weekend
            return False
        
        # Market hours: 9:30 AM - 4:00 PM ET
        market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
        
        is_open = market_open <= now_et <= market_close
        
        if not is_open:
            logger.info(f"Market closed. Current ET time: {now_et.strftime('%H:%M:%S')}")
        
        return is_open

if __name__ == "__main__":
    import os
    
    # Ensure required directories exist
    os.makedirs("data/alerts", exist_ok=True)
    os.makedirs("data/trades", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    
    # Run trading system
    system = TradingSystem()
    asyncio.run(system.start())
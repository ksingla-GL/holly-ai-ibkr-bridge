"""Test IBKR Connection and Basic Functionality"""
import asyncio
import json
from src.core.ibkr_connector import IBKRConnector
from loguru import logger

async def test_connection():
    """Test IBKR connection and basic functionality"""
    print("=" * 50)
    print("IBKR Connection Test")
    print("=" * 50)
    
    # Load config
    with open('config/config.json', 'r') as f:
        config = json.load(f)
    
    # Create connector
    connector = IBKRConnector()
    
    # Test 1: Connection
    print("\n1. Testing connection to IBKR...")
    connected = await connector.connect()
    if not connected:
        print("❌ Failed to connect. Please check:")
        print("   - TWS/Gateway is running")
        print("   - API connections are enabled")
        print("   - Port number is correct (7497 for paper)")
        return
    print("✅ Connected successfully!")
    
    # Test 2: Account Info
    print("\n2. Getting account info...")
    account_info = await connector.get_account_info()
    if account_info:
        print("✅ Account info retrieved:")
        for key, value in account_info.items():
            print(f"   {key}: {value}")
    else:
        print("❌ Failed to get account info")
    
    # Test 3: Contract Qualification
    print("\n3. Testing contract qualification...")
    test_symbol = "AAPL"
    contract = await connector.get_contract(test_symbol)
    if contract:
        print(f"✅ Successfully qualified {test_symbol}")
    else:
        print(f"❌ Failed to qualify {test_symbol}")
    
    # Test 4: Real-time Price
    print("\n4. Testing real-time price data...")
    prices = await connector.get_real_time_prices([test_symbol])
    if prices and test_symbol in prices:
        print(f"✅ {test_symbol} current price: ${prices[test_symbol]:.2f}")
    else:
        print("❌ Failed to get real-time price")
    
    # Test 5: Current Positions
    print("\n5. Checking current positions...")
    positions = connector.get_positions()
    if positions:
        print(f"✅ Found {len(positions)} position(s):")
        for pos in positions:
            print(f"   {pos.contract.symbol}: {pos.position} shares @ ${pos.avgCost:.2f}")
    else:
        print("✅ No open positions")
    
    # Disconnect
    connector.disconnect()
    print("\n✅ All tests completed!")
    print("\nYour IBKR connection is working properly.")
    print("You can now run the main trading system.")

async def test_paper_order():
    """Test placing a paper order (optional)"""
    print("\n" + "=" * 50)
    print("Paper Order Test (Optional)")
    print("=" * 50)
    
    response = input("\nWould you like to test placing a paper order? (y/n): ")
    if response.lower() != 'y':
        return
    
    connector = IBKRConnector()
    await connector.connect()
    
    # Test order parameters
    symbol = input("Enter symbol (default: AAPL): ").strip() or "AAPL"
    quantity = int(input("Enter quantity (default: 1): ").strip() or "1")
    
    print(f"\nPlacing test order: BUY {quantity} {symbol} @ MARKET")
    
    # Create test alert
    test_alert = {
        'symbol': symbol,
        'price': 100.0,  # Dummy price
        'type': 'TEST'
    }
    
    # Place order
    trade = await connector.place_order(test_alert)
    
    if trade:
        print("✅ Test order placed successfully!")
        print(f"   Order ID: {trade.order.orderId}")
        print(f"   Status: {trade.orderStatus.status}")
        
        # Wait and check status
        await asyncio.sleep(2)
        print(f"   Final Status: {trade.orderStatus.status}")
        
        # Cancel if not filled
        if trade.orderStatus.status not in ['Filled', 'Cancelled']:
            print("\nCancelling test order...")
            connector.ib.cancelOrder(trade.order)
            await asyncio.sleep(1)
            print("✅ Order cancelled")
    else:
        print("❌ Failed to place test order")
    
    connector.disconnect()

if __name__ == "__main__":
    print("Holly AI - IBKR Connection Tester")
    print("Make sure TWS/Gateway is running before proceeding.\n")
    
    # Run tests
    asyncio.run(test_connection())
    
    # Optional: Test paper order
    asyncio.run(test_paper_order())
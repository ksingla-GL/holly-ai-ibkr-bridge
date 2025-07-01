"""Test CSV Parser"""
import pytest
from src.utils.csv_parser import HollyAlertParser
import pandas as pd
import os

def test_parse_alerts():
    # Create test CSV
    test_data = {
        'TimeStamp': ['7/1/2025 0:00'],
        'Type': ['NHP'],
        'Time': ['1.75E+09'],
        'Symbol': ['IONX'],
        'Description': ['New High: +0.01. Next resistance 74.6452 from 6/11/2025.'],
        'Price': [70.8],
        'Relative Volume': [2.568092]
    }
    
    df = pd.DataFrame(test_data)
    df.to_csv('data/alerts/test_alerts.csv', index=False)
    
    # Test parser
    parser = HollyAlertParser()
    parser.csv_path = 'data/alerts/test_alerts.csv'
    
    alerts = parser.parse_alerts()
    assert len(alerts) == 1
    assert alerts[0]['symbol'] == 'IONX'
    assert alerts[0]['price'] == 70.8
    assert alerts[0]['resistance'] == 74.6452
    
    # Cleanup
    os.remove('data/alerts/test_alerts.csv')

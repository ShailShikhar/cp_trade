#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import pandas as pd
from src.utils import setup_logging
import logging

setup_logging(level=logging.DEBUG)

print("=" * 60)
print(" LOGIN SYSTEM DIAGNOSTIC ".center(60))
print("=" * 60)

# Check if Excel exists
excel_path = Path("MasterFile.xlsx")
print(f"\n📂 Checking for MasterFile.xlsx...")
print(f"   Expected location: {excel_path.absolute()}")
print(f"   File exists: {excel_path.exists()}")

if not excel_path.exists():
    print("\n❌ CRITICAL: MasterFile.xlsx not found!")
    print("   Place it in the SAME directory as menu.py")
    sys.exit(1)

# Try loading Excel
try:
    print("\n📊 Attempting to load Excel...")
    df = pd.read_excel(excel_path, dtype=str)
    print(f"✅ Excel loaded successfully!")
    print(f"   Rows: {len(df)}")
    print(f"   Columns: {list(df.columns)}")
    
    # Normalize columns
    df.columns = df.columns.str.strip().str.upper()
    print(f"\n📊 Normalized columns: {list(df.columns)}")
    
    # Check required columns
    required = ['USER_ID', 'PASSWORRD', 'TOTP', 'TRADE_ENABLED']
    missing = [col for col in required if col not in df.columns]
    if missing:
        print(f"\n❌ Missing required columns: {missing}")
        print(f"   Expected columns: USER_ID, PASSWORRD, TOTP, TRADE_ENABLED")
        sys.exit(1)
    
    # Show first row
    if len(df) > 0:
        print(f"\n🔍 First row sample:")
        row = df.iloc[0]
        for col in required:
            value = str(row.get(col, 'MISSING')).strip()
            # Hide sensitive data
            if col in ['PASSWORRD', 'TOTP']:
                value = value[:3] + "***" if len(value) > 3 else "***"
            print(f"   {col}: {value}")
    
    # Check enabled accounts
    enabled_count = 0
    for idx, row in df.iterrows():
        user_id = str(row.get('USER_ID', '')).strip()
        if pd.isna(user_id) or user_id == '':
            continue
        
        trade_enabled = str(row.get('TRADE_ENABLED', 'FALSE')).lower() in ['true', '1', 'yes']
        print(f"\n   Row {idx + 2}: USER_ID={user_id}, TRADE_ENABLED={trade_enabled}")
        
        if trade_enabled:
            enabled_count += 1
    
    print(f"\n✅ Found {enabled_count} enabled accounts for trading")
    
except Exception as e:
    print(f"\n❌ Excel loading failed: {e}")
    import traceback
    traceback.print_exc()
#!/usr/bin/env python3
import argparse
from pathlib import Path
from src.main import TradingTestSuite

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AliceBlue Trading System")
    parser.add_argument(
        "--multi-account",
        action="store_true",
        help="Execute on multiple accounts concurrently"
    )
    parser.add_argument(
        "--config-dir",
        default="config",
        help="Configuration directory path"
    )
    
    args = parser.parse_args()
    
    # ⚠️ FIX: Convert string to Path object
    suite = TradingTestSuite(config_dir=Path(args.config_dir))
    suite.run(multi_account=args.multi_account)
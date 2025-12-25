#!/usr/bin/env python3
from pathlib import Path
from src.main import TradingTestSuite

if __name__ == "__main__":
    suite = TradingTestSuite(config_dir=Path("config"))
    suite.run(multi_account=False)  # Explicit single account mode
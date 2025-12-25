#!/usr/bin/env python3
"""
Generate instruments.json directly from AliceBlue API.
Bypasses CSV parsing issues by using live search_instruments.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict
import sys

sys.path.insert(0, str(Path(__file__).parent / "src"))
from auth import Authenticator

def setup_logging():
    """Configure logging"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def print_section(title: str):
    print(f"\n{'='*60}")
    print(f" {title}".upper())
    print(f"{'='*60}\n")

class InstrumentGeneratorFromAPI:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.alice = None
        
    def login_and_setup(self):
        """Login to AliceBlue and get API connection"""
        self.logger.info("🔐 Logging into AliceBlue...")
        auth = Authenticator()
        self.alice = auth.login()
        self.logger.info("✅ Login successful")
        return self.alice
    
    def fetch_index_instruments(self, symbol: str) -> List[Dict]:
        """
        Fetch all instruments for a given index (NIFTY/BANKNIFTY)
        Returns list of instrument objects from AliceBlue
        """
        self.logger.info(f"🔍 Fetching all instruments for {symbol}...")
        
        try:
            # Search returns list of instrument objects
            instruments = self.alice.search_instruments("NFO", symbol)
            self.logger.info(f"✅ Found {len(instruments)} total contracts for {symbol}")
            return instruments
        except Exception as e:
            self.logger.error(f"❌ Failed to fetch {symbol}: {e}")
            return []
    
    def extract_options_data(self, instruments: List[Dict], symbol: str) -> Dict:
        """
        Extract options and group by expiry date.
        Returns: { "2025-12-30": {"strikes": [...], "token_map": {...}} }
        """
        # Filter for options only
        options = [inst for inst in instruments if "CE" in inst.symbol or "PE" in inst.symbol]
        self.logger.info(f"📊 Found {len(options)} option contracts")
        
        # Group by expiry
        expiry_data = {}
        
        for opt in options:
            try:
                # Extract expiry date from instrument object
                expiry_str = opt.expiry  # Format: "2025-12-30"
                if not expiry_str or '-' not in expiry_str:
                    continue
                
                # Extract strike price from symbol (e.g., "NIFTY30DEC2515000CE")
                # Parse strike from token or symbol
                strike_price = opt.strike_price
                
                # Initialize expiry group
                if expiry_str not in expiry_data:
                    expiry_data[expiry_str] = {
                        "strikes": set(),
                        "symbol": symbol
                    }
                
                expiry_data[expiry_str]["strikes"].add(float(strike_price))
                
            except Exception as e:
                self.logger.debug(f"⚠️ Skipping invalid option {opt.symbol}: {e}")
                continue
        
        # Convert strike sets to sorted lists
        for expiry in expiry_data:
            strikes = sorted(list(expiry_data[expiry]["strikes"]))
            expiry_data[expiry]["strikes"] = strikes
            
            self.logger.info(
                f"✅ {symbol} {expiry}: {len(strikes)} strikes "
                f"(Range: {min(strikes):.0f} - {max(strikes):.0f})"
            )
        
        return expiry_data
    
    def generate_instruments_dict(self, nifty_expiry_data: Dict, banknifty_expiry_data: Dict) -> Dict:
        """Convert to instruments.json format"""
        instruments = {
            "nse_equity": self.generate_equities(),
            "nfo_derivatives": {},
            "mcx_commodities": {
                "symbols": ["GOLD", "SILVER"],
                "exchange": "MCX"
            }
        }
        
        # Process NIFTY
        for expiry_date, data in nifty_expiry_data.items():
            expiry_key = expiry_date.replace("-", "")[2:].upper()  # "2025-12-30" -> "DEC30"
            
            # Skip past expiries
            if datetime.strptime(expiry_date, '%Y-%m-%d') < datetime.now():
                continue
            
            options = []
            for strike in data["strikes"]:
                options.append({"strike": int(strike), "type": "CE"})
                options.append({"strike": int(strike), "type": "PE"})
            
            config_key = f"NIFTY_{expiry_key}"
            instruments["nfo_derivatives"][config_key] = {
                "symbol": "NIFTY",
                "expiry": expiry_date,
                "futures": True,
                "options": options
            }
            
            self.logger.info(f"✅ {config_key}: {len(options)} options")
        
        # Process BANKNIFTY
        for expiry_date, data in banknifty_expiry_data.items():
            expiry_key = expiry_date.replace("-", "")[2:].upper()
            
            if datetime.strptime(expiry_date, '%Y-%m-%d') < datetime.now():
                continue
            
            options = []
            for strike in data["strikes"]:
                options.append({"strike": int(strike), "type": "CE"})
                options.append({"strike": int(strike), "type": "PE"})
            
            config_key = f"BANKNIFTY_{expiry_key}"
            instruments["nfo_derivatives"][config_key] = {
                "symbol": "BANKNIFTY",
                "expiry": expiry_date,
                "futures": True,
                "options": options
            }
            
            self.logger.info(f"✅ {config_key}: {len(options)} options")
        
        return instruments
    
    def generate_equities(self) -> List[Dict]:
        """Static equity list"""
        return [
            {"symbol": "RELIANCE", "exchange": "NSE"},
            {"symbol": "TCS", "exchange": "NSE"},
            {"symbol": "HDFCBANK", "exchange": "NSE"},
            {"symbol": "INFY", "exchange": "NSE"},
            {"symbol": "KOTAKBANK", "exchange": "NSE"},
            {"symbol": "ICICIBANK", "exchange": "NSE"},
        ]
    
    def generate(self):
        """Main generation pipeline"""
        print_section("GENERATING INSTRUMENTS FROM ALICEBLUE API")
        
        # 1. Login
        self.login_and_setup()
        
        # 2. Fetch NIFTY
        nifty_instruments = self.fetch_index_instruments("NIFTY")
        nifty_expiry_data = self.extract_options_data(nifty_instruments, "NIFTY")
        
        # 3. Fetch BANKNIFTY
        banknifty_instruments = self.fetch_index_instruments("BANKNIFTY")
        banknifty_expiry_data = self.extract_options_data(banknifty_instruments, "BANKNIFTY")
        
        # 4. Generate config
        instruments = self.generate_instruments_dict(nifty_expiry_data, banknifty_expiry_data)
        
        # 5. Save
        output_path = Path("config") / "instruments.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(instruments, f, indent=2)
        
        # Print summary
        total_options = sum(
            len(details.get("options", []))
            for details in instruments["nfo_derivatives"].values()
        )
        
        print_section("GENERATION COMPLETE")
        print(f"📈 F&O Contracts: {len(instruments['nfo_derivatives'])}")
        print(f"🎯 Total Options: {total_options}")
        print(f"📊 NSE Equities: {len(instruments['nse_equity'])}")
        print(f"✅ Saved to: {output_path.absolute()}")


if __name__ == "__main__":
    setup_logging()
    generator = InstrumentGeneratorFromAPI()
    generator.generate()
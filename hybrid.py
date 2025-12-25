#!/usr/bin/env python3
"""
Hybrid Instruments Generator
- Tries AliceBlue API first (real market data)
- Falls back to manual/synthetic data on holidays
- Creates backup copies for future use
"""

import json
import logging
from pathlib import Path
from datetime import datetime
import sys
import calendar

sys.path.insert(0, str(Path(__file__).parent / "src"))
from auth import Authenticator

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def print_section(title: str):
    print(f"\n{'='*60}")
    print(f" {title}".upper())
    print(f"{'='*60}\n")

class HybridInstrumentGenerator:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.alice = None
        self.backup_dir = Path("config/backups")
        self.backup_dir.mkdir(exist_ok=True)
        
        # Market holidays 2025 (update this list annually)
        self.market_holidays = [
            "2025-01-26", "2025-03-07", "2025-03-30", "2025-04-10",
            "2025-04-14", "2025-05-01", "2025-08-15", "2025-08-19",
            "2025-09-15", "2025-10-02", "2025-10-21", "2025-11-05",
            "2025-12-25"  # ✅ Today is a holiday!
        ]
    
    def is_market_holiday(self) -> bool:
        """Check if today is a trading holiday"""
        today = datetime.now().strftime("%Y-%m-%d")
        is_holiday = today in self.market_holidays
        
        if is_holiday:
            self.logger.warning(f"⚠️ Today ({today}) is a market holiday!")
        
        return is_holiday
    
    def is_market_hours(self) -> bool:
        """Check if current time is within market hours"""
        now = datetime.now().time()
        market_start = datetime.strptime("09:15", "%H:%M").time()
        market_end = datetime.strptime("15:30", "%H:%M").time()
        
        is_open = market_start <= now <= market_end
        
        if not is_open:
            self.logger.warning(
                f"⚠️ Outside market hours ({now.strftime('%H:%M')} IST). "
                f"Markets open 09:15-15:30"
            )
        
        return is_open
    
    def login_and_setup(self):
        """Login to AliceBlue"""
        try:
            self.logger.info("🔐 Logging into AliceBlue...")
            auth = Authenticator()
            self.alice = auth.login()
            self.logger.info("✅ Login successful")
            return True
        except Exception as e:
            self.logger.error(f"❌ Login failed: {e}")
            return False
    
    def try_api_fetch(self, symbol: str) -> list:
        """Try to fetch instruments from API"""
        try:
            self.logger.info(f"🌐 Trying API for {symbol}...")
            result = self.alice.search_instruments("NFO", symbol)
            
            # Check if result is list and has data
            if isinstance(result, list) and len(result) > 0:
                self.logger.info(f"✅ API returned {len(result)} instruments")
                
                # Quick validation - check first item
                first = result[0]
                if hasattr(first, 'symbol') and hasattr(first, 'expiry'):
                    return result
            
            self.logger.warning(f"⚠️ API returned empty/invalid data for {symbol}")
            return []
            
        except Exception as e:
            self.logger.error(f"❌ API fetch failed for {symbol}: {e}")
            return []
    
    def load_backup(self) -> dict:
        """Load backup instruments.json if it exists"""
        backup_file = self.backup_dir / "instruments_backup.json"
        
        if backup_file.exists():
            self.logger.info(f"📂 Loading backup from {backup_file}")
            
            with open(backup_file) as f:
                data = json.load(f)
            
            # Verify structure
            if "nfo_derivatives" in data and len(data["nfo_derivatives"]) > 0:
                self.logger.info("✅ Backup loaded successfully")
                return data
        
        self.logger.warning("❌ No valid backup found")
        return None
    
    def save_backup(self, instruments: dict):
        """Save current instruments as backup"""
        backup_file = self.backup_dir / "instruments_backup.json"
        
        with open(backup_file, 'w') as f:
            json.dump(instruments, f, indent=2)
        
        self.logger.info(f"💾 Backup saved to {backup_file}")
    
    def create_synthetic_instruments(self) -> dict:
        """
        Create synthetic but realistic instruments for trading setup.
        Uses last known NIFTY levels (adjust these based on current market)
        """
        print_section("CREATING SYNTHETIC INSTRUMENTS (MARKET CLOSED)")
        
        self.logger.info("📊 Using synthetic data for setup/trading")
        self.logger.info("⚠️  Replace with real data during market hours")
        
        # Current approximate levels (update these!)
        nifty_level = 26000  # Adjust to current market
        banknifty_level = 48000  # Adjust to current market
        
        instruments = {
            "nse_equity": self.generate_equities(),
            "nfo_derivatives": {},
            "mcx_commodities": {
                "symbols": ["GOLD", "SILVER"],
                "exchange": "MCX"
            }
        }
        
        # Generate NIFTY expiries (2 weekly + 2 monthly)
        nifty_expiries = {
            "2025-12-30": f"DEC30",
            "2026-01-06": f"JAN06",
            "2026-01-27": f"JAN27",
        }
        
        for date_str, key in nifty_expiries.items():
            # Generate strikes around ATM
            atm = round(nifty_level / 50) * 50
            strikes = [atm + (i * 50) for i in range(-20, 21)]  # ±1000 points
            
            options = []
            for strike in strikes:
                options.append({"strike": strike, "type": "CE"})
                options.append({"strike": strike, "type": "PE"})
            
            instruments["nfo_derivatives"][f"NIFTY_{key}"] = {
                "symbol": "NIFTY",
                "expiry": date_str,
                "futures": True,
                "options": options
            }
            
            self.logger.info(
                f"✅ NIFTY_{key}: {len(options)} options "
                f"(Range: {min(strikes)}-{max(strikes)})"
            )
        
        # Generate BANKNIFTY expiries (weekly only)
        banknifty_expiries = {
            "2025-12-30": f"DEC30",
            "2026-01-06": f"JAN06",
        }
        
        for date_str, key in banknifty_expiries.items():
            atm = round(banknifty_level / 100) * 100
            strikes = [atm + (i * 100) for i in range(-15, 16)]  # ±1500 points
            
            options = []
            for strike in strikes:
                options.append({"strike": strike, "type": "CE"})
                options.append({"strike": strike, "type": "PE"})
            
            instruments["nfo_derivatives"][f"BANKNIFTY_{key}"] = {
                "symbol": "BANKNIFTY",
                "expiry": date_str,
                "futures": True,
                "options": options
            }
            
            self.logger.info(
                f"✅ BANKNIFTY_{key}: {len(options)} options "
                f"(Range: {min(strikes)}-{max(strikes)})"
            )
        
        return instruments
    
    def generate_equities(self) -> list:
        return [
            {"symbol": "RELIANCE", "exchange": "NSE"},
            {"symbol": "TCS", "exchange": "NSE"},
            {"symbol": "HDFCBANK", "exchange": "NSE"},
            {"symbol": "INFY", "exchange": "NSE"},
            {"symbol": "KOTAKBANK", "exchange": "NSE"},
            {"symbol": "ICICIBANK", "exchange": "NSE"},
            {"symbol": "SBIN", "exchange": "NSE"},
            {"symbol": "AXISBANK", "exchange": "NSE"},
            {"symbol": "TATAMOTORS", "exchange": "NSE"},
        ]
    
    def generate(self):
        """Main generation with intelligent fallback"""
        print_section("HYBRID INSTRUMENT GENERATOR")
        
        # 1. Check conditions
        is_holiday = self.is_market_holiday()
        is_after_hours = not self.is_market_hours()
        
        if is_holiday or is_after_hours:
            self.logger.info("🌙 Running in OFFLINE mode (holiday/after hours)")
            
            # Try backup first
            backup = self.load_backup()
            if backup:
                print_section("✅ USING BACKUP DATA")
                instruments = backup
            else:
                print_section("⚠️  NO BACKUP - CREATING SYNTHETIC DATA")
                instruments = self.create_synthetic_instruments()
        else:
            # Market is open - try API
            print_section("🌞 MARKET IS OPEN - FETCHING LIVE DATA")
            
            if not self.login_and_setup():
                # Login failed, fall back
                instruments = self.create_synthetic_instruments()
            else:
                # Try API fetch
                nifty_all = self.try_api_fetch("NIFTY")
                banknifty_all = self.try_api_fetch("BANKNIFTY")
                
                if nifty_all and banknifty_all:
                    # API succeeded
                    nifty_data = self.extract_api_data(nifty_all, "NIFTY")
                    banknifty_data = self.extract_api_data(banknifty_all, "BANKNIFTY")
                    
                    if nifty_data and banknifty_data:
                        instruments = self.build_from_api_data(nifty_data, banknifty_data)
                        self.save_backup(instruments)  # Save for future
                    else:
                        instruments = self.create_synthetic_instruments()
                else:
                    # API failed
                    instruments = self.create_synthetic_instruments()
        
        # Save to main location
        output_path = Path("config") / "instruments.json"
        with open(output_path, 'w') as f:
            json.dump(instruments, f, indent=2)
        
        # Print summary
        total_fno = len(instruments["nfo_derivatives"])
        total_options = sum(len(v["options"]) for v in instruments["nfo_derivatives"].values())
        
        print_section("GENERATION SUMMARY")
        print(f"📈 F&O Contracts: {total_fno}")
        print(f"🎯 Total Options: {total_options}")
        print(f"📊 NSE Equities: {len(instruments['nse_equity'])}")
        print(f"✅ Saved to: {output_path.absolute()}")
        
        # Show what mode we used
        if is_holiday:
            print(f"\n⚠️  Used synthetic data (today is holiday)")
            print(f"   Run again during market hours for real data")
    
    # Helper methods for API path
    def extract_api_data(self, instruments: list, symbol: str) -> dict:
        """Extract from API response"""
        expiry_data = {}
        for inst in instruments:
            try:
                expiry = getattr(inst, 'expiry', '')
                strike = getattr(inst, 'strike', 0)
                if expiry and strike:
                    if expiry not in expiry_data:
                        expiry_data[expiry] = set()
                    expiry_data[expiry].add(float(strike))
            except:
                continue
        
        return expiry_data
    
    def build_from_api_data(self, nifty_data: dict, banknifty_data: dict) -> dict:
        """Build instruments dict from API data"""
        instruments = {
            "nse_equity": self.generate_equities(),
            "nfo_derivatives": {},
            "mcx_commodities": {"symbols": ["GOLD", "SILVER"], "exchange": "MCX"}
        }
        
        # Add NIFTY
        for expiry, strikes in nifty_data.items():
            expiry_key = expiry.replace("-", "")[2:].upper()
            options = [{"strike": int(s), "type": "CE"} for s in strikes] + \
                     [{"strike": int(s), "type": "PE"} for s in strikes]
            
            instruments["nfo_derivatives"][f"NIFTY_{expiry_key}"] = {
                "symbol": "NIFTY",
                "expiry": expiry,
                "futures": True,
                "options": options
            }
        
        # Add BANKNIFTY
        for expiry, strikes in banknifty_data.items():
            expiry_key = expiry.replace("-", "")[2:].upper()
            options = [{"strike": int(s), "type": "CE"} for s in strikes] + \
                     [{"strike": int(s), "type": "PE"} for s in strikes]
            
            instruments["nfo_derivatives"][f"BANKNIFTY_{expiry_key}"] = {
                "symbol": "BANKNIFTY",
                "expiry": expiry,
                "futures": True,
                "options": options
            }
        
        return instruments

if __name__ == "__main__":
    setup_logging()
    generator = HybridInstrumentGenerator()
    generator.generate()
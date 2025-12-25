#!/usr/bin/env python3
"""
Instant Instrument Resolver - Full compatibility version
Supports: resolve(), resolve_equity(), resolve_fno(), resolve_mcx_gold()
"""

import logging
from typing import Optional, Dict, Any
from collections import namedtuple
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from instruments_cache import resolve as cache_resolve, TOTAL_INSTRUMENTS
except ImportError:
    print("❌ instruments_cache.py not found. Run: python src/generate_python_cache.py")
    sys.exit(1)

Instrument = namedtuple('Instrument', ['exchange', 'token', 'symbol', 'name', 'expiry', 'lot_size'])

class InstantInstrumentResolver:
    def __init__(self, alice):
        self.alice = alice
        self.logger = logging.getLogger(__name__)
        self.resolved_cache: Dict[str, Optional[Instrument]] = {}
        self.logger.info(f"✅ InstantResolver ready: {TOTAL_INSTRUMENTS} instruments")
    
    def resolve(self, instrument_key: str) -> Optional[Instrument]:
        """Main resolve method - O(0) lookup"""
        key = instrument_key.strip().upper()
        
        if key in self.resolved_cache:
            return self.resolved_cache[key]
        
        config = cache_resolve(key)
        
        if not config:
            self.resolved_cache[key] = None
            return None
        
        try:
            instrument = self._resolve_via_api(key, config)
            self.resolved_cache[key] = instrument
            return instrument
            
        except Exception as e:
            self.logger.error(f"❌ Resolution failed for {key}: {e}")
            self.resolved_cache[key] = None
            return None
    
    def resolve_equity(self, exchange: str, symbol: str) -> Optional[Instrument]:
        """Legacy method - called by orchestrator"""
        key = f"{exchange}_{symbol}".upper()
        return self.resolve(key)
    
    def resolve_fno(self, exchange: str, symbol: str, expiry_date: str,
                    is_fut: bool = True, strike: Optional[int] = None,
                    is_ce: bool = True) -> Optional[Instrument]:
        """Legacy method - called by orchestrator"""
        if is_fut:
            key = f"{symbol}_{expiry_date.replace('-', '')[2:].upper()}_FUT"
        else:
            opt_type = "CE" if is_ce else "PE"
            key = f"{symbol}_{expiry_date.replace('-', '')[2:].upper()}_{opt_type}_{strike}"
        
        return self.resolve(key)
    
    def resolve_mcx_gold(self, symbols: list) -> Optional[Instrument]:
        """Legacy method - called by orchestrator"""
        for symbol in symbols:
            key = f"MCX_{symbol}".upper()
            result = self.resolve(key)
            if result:
                return result
        return None
    
    def _resolve_via_api(self, key: str, config: dict) -> Instrument:
        """Internal API resolution"""
        exchange = config.get("exchange", "")
        
        if exchange == "NSE":
            return self._resolve_equity_api(key, config)
        elif exchange == "NFO":
            return self._resolve_fno_api(key, config)
        elif exchange == "MCX":
            return self._resolve_mcx_api(key, config)
        else:
            # Dynamic equity
            return self._resolve_equity_api(key, {"symbol": key, "exchange": "NSE"})
    
    def _resolve_equity_api(self, key: str, config: dict) -> Instrument:
        symbol = config["symbol"]
        result = self.alice.get_instrument_by_symbol("NSE", symbol)
        return self._normalize(result, "NSE", symbol)
    
    def _resolve_fno_api(self, key: str, config: dict) -> Instrument:
        symbol = config["symbol"]
        expiry = config["expiry"]
        
        if config["type"] == "FUT":
            result = self.alice.get_instrument_for_fno(
                exch="NFO", symbol=symbol, expiry_date=expiry, is_fut=True
            )
        else:
            result = self.alice.get_instrument_for_fno(
                exch="NFO", symbol=symbol, expiry_date=expiry,
                is_fut=False, strike=config["strike"], is_CE=(config["option_type"] == "CE")
            )
        
        return self._normalize(result, "NFO", symbol)
    
    def _resolve_mcx_api(self, key: str, config: dict) -> Instrument:
        symbol = config["symbol"]
        result = self.alice.get_instrument_by_symbol("MCX", symbol)
        return self._normalize(result, "MCX", symbol)
    
    def _normalize(self, result, exchange: str, symbol: str) -> Instrument:
        """Normalize API result"""
        try:
            if hasattr(result, 'exchange'):
                return Instrument(
                    exchange=result.exchange,
                    token=result.token,
                    symbol=result.symbol,
                    name=getattr(result, 'name', symbol),
                    expiry=getattr(result, 'expiry', ''),
                    lot_size=getattr(result, 'lot_size', 1)
                )
            else:
                return Instrument(
                    exchange=result.get('exchange', exchange),
                    token=result.get('token', ''),
                    symbol=result.get('symbol', symbol),
                    name=result.get('name', symbol),
                    expiry=result.get('expiry', ''),
                    lot_size=result.get('lot_size', 1)
                )
        except Exception as e:
            self.logger.error(f"❌ Normalization failed: {e}")
            raise

if __name__ == "__main__":
    setup_logging()
    
    class MockAlice:
        def get_instrument_by_symbol(self, exch, sym):
            return type('I', (), {'exchange': exch, 'token': 'TKN', 'symbol': sym, 'name': sym, 'expiry': '', 'lot_size': 1})()
        def get_instrument_for_fno(self, **kw):
            return type('I', (), {'exchange': 'NFO', 'token': 'TKN_FNO', 'symbol': f"{kw['symbol']}_FUT", 'name': kw['symbol'], 'expiry': kw['expiry_date'], 'lot_size': 50})()
    
    import time
    resolver = InstantInstrumentResolver(MockAlice())
    
    # Test legacy methods
    print("Testing legacy methods...")
    result1 = resolver.resolve_equity("NSE", "RELIANCE")
    print(f"✅ resolve_equity: {result1.symbol if result1 else 'Failed'}")
    
    result2 = resolver.resolve_fno("NFO", "NIFTY", "2025-12-30", is_fut=True)
    print(f"✅ resolve_fno: {result2.symbol if result2 else 'Failed'}")
    
    # Benchmark
    keys = ["NSE_RELIANCE"] * 1000
    start = time.time()
    for key in keys:
        resolver.resolve(key)
    elapsed = (time.time() - start) * 1000
    
    print(f"\n📊 1,000 lookups: {elapsed:.3f} ms")
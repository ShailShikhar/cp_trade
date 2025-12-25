import logging
from collections import namedtuple
from typing import Optional, Dict, Any
from pya3 import Aliceblue

Instrument = namedtuple('Instrument', ['exchange', 'token', 'symbol', 'name', 'expiry', 'lot_size'])

class InstrumentResolver:
    def __init__(self, alice: Aliceblue):
        self.alice = alice
        self.logger = logging.getLogger(__name__)
        self.cache: Dict[str, Instrument] = {}

    def resolve_equity(self, exchange: str, symbol: str) -> Optional[Instrument]:
        """Resolve NSE equity instrument"""
        key = f"{exchange}_{symbol}"
        if key in self.cache:
            return self.cache[key]

        try:
            self.logger.info(f"Resolving {symbol} on {exchange}...")
            result = self.alice.get_instrument_by_symbol(exchange, symbol)
            instrument = self._normalize_instrument(result, exchange, symbol)
            self.cache[key] = instrument
            self.logger.info(f"✓ Found: {instrument}")
            return instrument
        except Exception as e:
            self.logger.error(f"Failed to resolve {key}: {e}")
            return None

    def resolve_fno(
        self, 
        exchange: str, 
        symbol: str, 
        expiry_date: str,
        is_fut: bool = True,
        strike: Optional[int] = None,
        is_ce: bool = True
    ) -> Optional[Instrument]:
        """Resolve F&O instrument with aggressive debugging"""
        opt_type = "FUT" if is_fut else f"{'CE' if is_ce else 'PE'}{strike}"
        key = f"{exchange}_{symbol}_{expiry_date}_{opt_type}"
        
        self.logger.debug(f"Resolving: exchange={exchange}, symbol={symbol}, expiry={expiry_date}")
        self.logger.debug(f"  is_fut={is_fut}, strike={strike}, is_ce={is_ce}")
        self.logger.debug(f"  Generated key: {key}")
        
        if key in self.cache:
            self.logger.debug(f"  ✅ Cache hit: {key}")
            return self.cache[key]

        try:
            self.logger.info(f"🔍 API call for {key}...")
            result = self.alice.get_instrument_for_fno(
                exch=exchange,
                symbol=symbol,
                expiry_date=expiry_date,
                is_fut=is_fut,
                strike=strike,
                is_CE=is_ce
            )
            instrument = self._normalize_instrument(result, exchange, symbol)
            self.cache[key] = instrument
            self.logger.info(f"✅ Resolved: {instrument}")
            return instrument
            
        except Exception as e:
            self.logger.error(f"❌ Resolution failed: {e}")
            return None

    def resolve_mcx_gold(self, symbols: list) -> Optional[Instrument]:
        """Resolve MCX GOLD instrument with fallback symbols"""
        for symbol in symbols:
            instrument = self.resolve_equity("MCX", symbol)
            if instrument:
                return instrument
        self.logger.warning("No valid MCX GOLD instrument found")
        return None

    def _normalize_instrument(self, result: Any, exchange: str, symbol: str) -> Instrument:
        """Normalize different return types to Instrument namedtuple"""
        # Create the instrument object
        if hasattr(result, 'exchange'):
            instrument = Instrument(
                exchange=result.exchange,
                token=result.token,
                symbol=result.symbol,
                name=getattr(result, 'name', ''),
                expiry=getattr(result, 'expiry', ''),
                lot_size=getattr(result, 'lot_size', 1)
            )
        elif isinstance(result, dict):
            instrument = Instrument(
                exchange=result.get('exchange', exchange),
                token=result.get('token', ''),
                symbol=result.get('symbol', symbol),
                name=result.get('name', ''),
                expiry=result.get('expiry', ''),
                lot_size=result.get('lot_size', 1)
            )
        else:
            raise ValueError(f"Unsupported instrument format: {type(result)}")
        
        # 🎯 CRITICAL: Validate token is not empty
        # if not instrument.token:
        #     self.logger.error(f"❌ INSTRUMENT HAS EMPTY TOKEN: {instrument}")
        #     self.logger.error(f"   This means the strike/expiry doesn't exist on AliceBlue")
        #     raise ValueError(f"Invalid instrument {instrument.symbol}: token is empty")
        
        return instrument

    def debug_cache(self):
        """Print cache contents"""
        print("=== INSTRUMENT RESOLVER CACHE ===")
        for key, inst in sorted(self.cache.items()):
            print(f"{key:40} → {inst}")
        print("===================================")
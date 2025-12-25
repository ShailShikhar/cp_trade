# Save this as D:\Testorders\order test working\src\main.py

import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from .utils import setup_logging, load_master_config, load_config_file, print_section, load_master_excel
from .account_manager import AccountManager, AccountSession
from .threaded_orchestrator import ThreadedOrchestrator

class TradingTestSuite:
    def __init__(self, config_dir: Path = Path("config")):
        """Initialize with configuration directory"""
        self.config_dir = config_dir
        self.logger = logging.getLogger(__name__)
        self.account_manager = None
        self.orchestrator = None
        self.config_data = {}
        self.multi_account_mode = False
        self.sessions = {}
        self.instruments = {}  # Add this line - it was missing!

    def initialize(self, multi_account: bool = False):
        """Initialize system in single or multi-account mode"""
        self.multi_account_mode = multi_account
        
        print_section("INITIALIZING TRADING SYSTEM")
        setup_logging()
        
        # Load all configurations from master manifest
        try:
            self.config_data = load_master_config(self.config_dir)
            self.logger.info("✓ Configuration loaded successfully")
        except Exception as e:
            self.logger.critical(f"Failed to load configuration: {e}", exc_info=True)
            raise
        
        if multi_account:
            self._initialize_multi_account()
        else:
            self._initialize_single_account()

    def _initialize_single_account(self):
        """Original single-account initialization"""
        from .auth import Authenticator
        from .instrument_resolver import InstrumentResolver
        from .order_executor import OrderExecutor
        from .basket_order_executor import BasketOrderExecutor
        
        auth = Authenticator()
        alice = auth.login()
        auth.download_contracts()
        
        self.resolver = InstrumentResolver(alice)
        self.executor = OrderExecutor(alice)
        self.basket_executor = BasketOrderExecutor(alice, self.resolver)
        
        # Store as single session for compatibility
        self.sessions = {"primary": type('Session', (), {
            'alice': alice,
            'resolver': self.resolver,
            'executor': self.executor,
            'basket_executor': self.basket_executor
        })()}
        
        self.logger.info("✓ Single account mode initialized")

    def _initialize_multi_account(self):
        """Initialize multiple accounts from master config or MasterFile.xlsx"""
        
        # First try loading from master config
        accounts_config = self.config_data.get("accounts", [])
        
        # Fallback to MasterFile.xlsx in root directory
        if not accounts_config:
            try:
                excel_file = Path("MasterFile.xlsx")  # Root level, NOT in config/
                if excel_file.exists():
                    accounts_config = load_master_excel(excel_file)
                else:
                    raise FileNotFoundError("MasterFile.xlsx not found in root directory")
            except Exception as e:
                self.logger.critical(f"Failed to load MasterFile.xlsx: {e}", exc_info=True)
                raise ValueError("No accounts configuration found. Need 'accounts' in _master.yaml or MasterFile.xlsx")
        
        # Filter enabled accounts (safety net)
        enabled_accounts = [acc for acc in accounts_config if acc.get("enabled", True)]
        if not enabled_accounts:
            raise ValueError("No enabled accounts found")
        
        self.account_manager = AccountManager(enabled_accounts)
        self.sessions = self.account_manager.initialize_all()
        
        # Initialize orchestrator with appropriate workers
        self.orchestrator = ThreadedOrchestrator(max_workers=min(5, len(self.sessions)))
        
        self.logger.info(f"✓ Multi-account mode initialized with {len(self.sessions)} accounts")

    def load_and_resolve_instruments(self):
        """Load and resolve instruments (shared across accounts)"""
        print_section("RESOLVING INSTRUMENTS")
        
        config = self.config_data.get("instruments", {})
        
        if not config:
            self.logger.critical("No instrument configuration loaded!")
            raise ValueError("Instrument config is empty")
        
        self.instruments = {}
        
        # NSE Equity
        for equity in config.get("nse_equity", []):
            symbol = equity["symbol"]
            self.instruments[symbol] = self._resolve_instrument(
                "resolve_equity", equity["exchange"], symbol
            )
        
        # NFO Derivatives (multi-expiry support)
        nfo_config = config.get("nfo_derivatives", {})
        for namespace, details in nfo_config.items():
            symbol = details["symbol"]
            expiry = details["expiry"]
            
            if details.get("futures", True):
                key = f"{namespace}_FUT".upper()
                self.instruments[key] = self._resolve_instrument(
                    "resolve_fno", "NFO", symbol, expiry, True
                )
            
            for option in details.get("options", []):
                key = f"{namespace}_{option['type']}_{str(option['strike'])}".upper()
                self.instruments[key] = self._resolve_instrument(
                    "resolve_fno", "NFO", symbol, expiry, False,
                    option["strike"], option["type"] == "CE"
                )
        
        # MCX Commodities
        mcx_config = config.get("mcx_commodities", {})
        for symbol in mcx_config.get("symbols", []):
            self.instruments[symbol] = self._resolve_instrument(
                "resolve_equity", "MCX", symbol
            )
        
        # Distribute to all resolvers in multi-account mode
        if self.multi_account_mode:
            for session in self.sessions.values():
                session.resolver.instruments = self.instruments
        
        resolved_count = sum(1 for inst in self.instruments.values() if inst and inst.token)
        self.logger.info(f"✓ Resolved {resolved_count}/{len(self.instruments)} instruments")

    def _resolve_instrument(self, method: str, *args):
        """Resolve instrument using first available session"""
        if not self.sessions:
            raise RuntimeError("No sessions available for instrument resolution")
        
        first_session = next(iter(self.sessions.values()))
        resolver = first_session.resolver
        
        try:
            return getattr(resolver, method)(*args)
        except Exception as e:
            self.logger.error(f"Failed to resolve {args}: {e}")
            return None

    def execute_test_orders(self):
        """Execute individual orders on all accounts"""
        print_section("EXECUTING INDIVIDUAL ORDERS")
        
        orders_config = self.config_data.get("orders", [])
        enabled_orders = [o for o in orders_config if o.get("enabled", True)]
        
        if not enabled_orders:
            self.logger.warning("No enabled orders found")
            return
        
        if self.multi_account_mode:
            results = self.orchestrator.execute_on_all_accounts(
                self.sessions, self.instruments, 
                lambda session, order: session.executor.place_order, 
                enabled_orders
            )
            self._print_multi_account_results(results)
        else:
            # Single-account logic
            for order_data in enabled_orders:
                instrument = self.instruments.get(order_data["instrument"])
                if not instrument or not instrument.token:
                    # Try dynamic resolution
                    instrument = self._resolve_instrument_dynamic(order_data["instrument"])
                    if not instrument:
                        self.logger.warning(f"Skipping order {order_data['name']}: Invalid instrument")
                        continue
                
                try:
                    self.sessions["primary"].executor.place_order(
                        name=order_data["name"],
                        transaction_type=order_data["transaction_type"],
                        instrument=instrument,
                        quantity=order_data["quantity"],
                        order_type=order_data["order_type"],
                        product_type=order_data["product_type"],
                        price=order_data.get("price", 0.0),
                        trigger_price=order_data.get("trigger_price"),
                        stop_loss=order_data.get("stop_loss"),
                        square_off=order_data.get("square_off"),
                        trailing_sl=order_data.get("trailing_sl"),
                        is_amo=order_data.get("is_amo", False),
                        order_tag=order_data.get("order_tag", "")
                    )
                except Exception as e:
                    self.logger.error(f"Order failed: {e}", exc_info=True)

    def execute_basket_orders(self):
        """Execute basket orders on all accounts"""
        print_section("EXECUTING BASKET ORDERS")
        
        baskets_config = self.config_data.get("basket_orders", [])
        enabled_baskets = [b for b in baskets_config if b.get("enabled", True)]
        
        if not enabled_baskets:
            self.logger.warning("No enabled baskets found")
            return
        
        if self.multi_account_mode:
            results = self.orchestrator.execute_basket_on_all_accounts(
                self.sessions, enabled_baskets
            )
            self._print_basket_results(results)
        else:
            # Single-account logic
            for basket in enabled_baskets:
                try:
                    result = self.sessions["primary"].basket_executor.execute_basket(basket)
                    if result.get("success"):
                        self.logger.info(f"✓ Basket executed: {result['message']}")
                    else:
                        self.logger.error(f"✗ Basket failed: {result.get('message')}")
                except Exception as e:
                    self.logger.error(f"Basket execution failed: {e}", exc_info=True)

    def _print_multi_account_results(self, results: Dict[str, Any]):
        """Display formatted results for multi-account execution"""
        print_section("MULTI-ACCOUNT EXECUTION SUMMARY")
        
        for account_name, account_results in results.items():
            print(f"\n📊 Account: *****")
            orders = account_results.get("individual_orders", [])
            successful = sum(1 for o in orders if o.get("success", False))
            print(f"   Orders: {successful}/{len(orders)} successful")
            
            if account_results.get("error"):
                print(f"   ❌ Error: {account_results['error']}")

    def _print_basket_results(self, results: Dict[str, Any]):
        """Display formatted basket results"""
        print_section("BASKET ORDER SUMMARY")
        
        for account_name, account_data in results.items():
            baskets = account_data.get("basket_orders", [])
            print(f"\n📊 Account: *****")
            for basket_result in baskets:
                if basket_result.get("success"):
                    print(f"   ✅ {basket_result['basket_name']}: {basket_result['message']}")
                else:
                    print(f"   ❌ {basket_result.get('basket_name')}: {basket_result.get('message')}")

    def run(self, multi_account: bool = False):
        """Main execution pipeline (PRODUCTION READY)"""
        try:
            self.initialize(multi_account=multi_account)
            self.load_and_resolve_instruments()
            self.execute_test_orders()
            self.execute_basket_orders()
            print_section("TEST SUITE COMPLETED")
        except Exception as e:
            self.logger.critical(f"Test suite failed: {e}", exc_info=True)
            raise

# Add to TradingTestSuite class in src/main.py

def _resolve_instrument_dynamic(self, instrument_key: str) -> Optional[Any]:
    """
    Dynamically resolve equity instruments not in config.
    For F&O instruments, still requires pre-definition.
    """
    # 1. Check cache first
    if instrument_key in self.instruments:
        return self.instruments[instrument_key]
    
    # 2. Determine if it's likely an equity (simple uppercase symbol)
    # F&O instruments have underscores (_FUT, _CE, _PE)
    if "_" in instrument_key:
        self.logger.warning(
            f"❌ Cannot dynamically resolve F&O instrument: {instrument_key}. "
            f"Must be pre-defined in instruments.json"
        )
        return None
    
    # 3. Try to resolve as NSE equity
    self.logger.info(f"🔄 Dynamic resolution attempt: {instrument_key}")
    
    if not self.sessions:
        raise RuntimeError("No sessions available")
    
    first_session = next(iter(self.sessions.values()))
    resolver = first_session.resolver
    
    try:
        # Try NSE first (most common)
        instrument = resolver.resolve_equity("NSE", instrument_key)
        
        if instrument and instrument.token:
            # Add to cache for future use
            self.instruments[instrument_key] = instrument
            self.logger.info(f"✅ Dynamically resolved: {instrument_key} (Token: {instrument.token})")
            
            # Distribute to all resolvers in multi-account mode
            if self.multi_account_mode:
                for session in self.sessions.values():
                    session.resolver.instruments[instrument_key] = instrument
            
            return instrument
        else:
            self.logger.error(f"❌ Resolution succeeded but token is empty")
            return None
            
    except Exception as e:
        self.logger.error(f"❌ Dynamic resolution failed for {instrument_key}: {e}")
        return None
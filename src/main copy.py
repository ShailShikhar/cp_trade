import logging
from pathlib import Path
from typing import Dict, Any, List
from .utils import setup_logging, load_json_config, print_section
from .account_manager import AccountManager, AccountSession
from .threaded_orchestrator import ThreadedOrchestrator

class TradingTestSuite:
    def __init__(self, config_dir: Path = Path("config")):
        self.config_dir = config_dir
        self.logger = logging.getLogger(__name__)
        self.account_manager = None
        self.orchestrator = None
        self.instruments = {}
        self.multi_account_mode = False
        self.sessions = {}

    def initialize(self, multi_account: bool = False):
        """Initialize system in single or multi-account mode"""
        self.multi_account_mode = multi_account
        
        print_section("INITIALIZING TRADING SYSTEM")
        setup_logging()
        
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
        """Initialize multiple accounts concurrently"""
        accounts_config = load_json_config(self.config_dir / "accounts.json")
        
        if not accounts_config:
            raise ValueError("No accounts found in accounts.json")
        
        self.account_manager = AccountManager(accounts_config)
        self.sessions = self.account_manager.initialize_all()
        
        # Shared instrument cache (read-only after load)
        self.orchestrator = ThreadedOrchestrator(max_workers=len(self.sessions))
        
        self.logger.info(f"✓ Multi-account mode initialized with {len(self.sessions)} accounts")

    def load_and_resolve_instruments(self):
        """Load and resolve instruments (shared across accounts)"""
        print_section("RESOLVING INSTRUMENTS")
        
        config = load_json_config(self.config_dir / "instruments.json")
        
        # NSE Equity
        for equity in config.get("nse_equity", []):
            symbol = equity["symbol"]
            self.instruments[symbol] = self._resolve_instrument(
                "resolve_equity", equity["exchange"], symbol
            )
        
        # NFO Derivatives
        nfo_config = config.get("nfo_derivatives", {})
        for namespace, details in nfo_config.items():
            symbol = details["symbol"]        # Extract underlying symbol
            expiry = details["expiry"]        # Extract expiry date
            
            if details.get("futures", True):
                key = f"{namespace}_FUT"      # Use namespace in cache key
                self.instruments[key] = self._resolve_instrument(
                    "resolve_fno", "NFO", symbol, expiry, True
                )
            
            for option in details.get("options", []):
                key = f"{namespace}_{option['type']}_{option['strike']}"
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
        
        # Distribute instruments to all resolvers in multi-account mode
        if self.multi_account_mode:
            for session in self.sessions.values():
                session.resolver.instruments = self.instruments
        
        self.logger.info(f"✓ Resolved {len(self.instruments)} instruments")

    def _resolve_instrument(self, method: str, *args):
        """Resolve instrument using first available session"""
        first_session = next(iter(self.sessions.values()))
        resolver = first_session.resolver
        
        try:
            return getattr(resolver, method)(*args)
        except Exception as e:
            self.logger.error(f"Failed to resolve {args}: {e}")
            return None

    def execute_test_orders(self):
        """Execute individual orders on all accounts"""
        print_section("CHECKING ENABLED INDIVIDUAL ORDERS")
        
        orders_config = load_json_config(self.config_dir / "orders.json")
        enabled_orders = [o for o in orders_config if o.get("enabled", True)]
        
        if not enabled_orders:
            self.logger.info("No enabled orders found")
            return
        
        if self.multi_account_mode:
            results = self.orchestrator.execute_on_all_accounts(
                self.sessions, self.instruments, 
                lambda session, order: session.executor.place_order, 
                enabled_orders
            )
            self._print_multi_account_results(results)
        else:
            # Original single-account logic
            for order_data in enabled_orders:
                instrument = self.instruments.get(order_data["instrument"])
                if not instrument or not instrument.token:
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
                    self.logger.error(f"Order failed: {e}")

    def execute_basket_orders(self):
        """Execute basket orders on all accounts"""
        print_section("CHECKING ENABLED BASKET ORDERS")
        
        try:
            basket_config = load_json_config(self.config_dir / "basket_orders.json")
            baskets = basket_config.get("basket_orders", [])
            enabled_baskets = [b for b in baskets if b.get("enabled", True)]
            
            if not enabled_baskets:
                self.logger.info("No enabled baskets found")
                return
            
            if self.multi_account_mode:
                results = self.orchestrator.execute_basket_on_all_accounts(
                    self.sessions, enabled_baskets
                )
                self._print_basket_results(results)
            else:
                # Original single-account logic
                for basket in enabled_baskets:
                    result = self.sessions["primary"].basket_executor.execute_basket(basket)
                    # ... existing logic ...
                    
        except FileNotFoundError:
            self.logger.info("No basket_orders.json found")
        except Exception as e:
            self.logger.error(f"Failed to load basket config: {e}")

    def _print_multi_account_results(self, results: Dict[str, Any]):
        """Display formatted results for multi-account execution"""
        print_section("MULTI-ACCOUNT EXECUTION SUMMARY")
        
        for account_name, account_results in results.items():
            print(f"\n📊 Account: {account_name}")
            orders = account_results.get("individual_orders", [])
            successful = sum(1 for o in orders if o.get("success"))
            print(f"   Orders: {successful}/{len(orders)} successful")
            
            if account_results.get("error"):
                print(f"   ❌ Error: {account_results['error']}")

    def _print_basket_results(self, results: Dict[str, Any]):
        """Display formatted basket results"""
        print_section("BASKET ORDER SUMMARY")
        
        for account_name, account_data in results.items():
            baskets = account_data.get("basket_orders", [])
            print(f"\n📊 Account: {account_name}")
            for basket_result in baskets:
                if basket_result.get("success"):
                    print(f"   ✅ {basket_result['basket_name']}: {basket_result['message']}")
                else:
                    print(f"   ❌ {basket_result.get('basket_name')}: {basket_result.get('error')}")

    def run(self, multi_account: bool = False):
        """Main execution pipeline"""
        try:
            self.initialize(multi_account=multi_account)
            self.load_and_resolve_instruments()
            self.execute_test_orders()
            self.execute_basket_orders()
            print_section("App run successfully")
        except Exception as e:
            self.logger.critical(f"Test suite failed: {e}", exc_info=True)
            raise
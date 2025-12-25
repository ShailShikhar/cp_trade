import logging
from typing import Dict, List
from src.auth import Authenticator  # Explicit full path
from src.instrument_resolver import InstrumentResolver
from src.order_executor import OrderExecutor
from src.basket_order_executor import BasketOrderExecutor



import logging
import inspect

# Debug logging
from src import auth
logging.error(f"auth module: {auth}")
# logging.error(f"auth contents: {dir(auth)}")
# logging.error(f"Authenticator type: {type(auth.Authenticator)}")
class AccountSession:
    """Container for per-account trading components"""
    def __init__(self, account_name: str, user_id: str, api_key: str):
        self.account_name = account_name
        self.user_id = user_id
        self.api_key = api_key
        self.alice = None
        self.resolver = None
        self.executor = None
        self.basket_executor = None
        self.logger = logging.getLogger(f"{__name__}.{account_name}")

class AccountManager:
    """Manages multiple AliceBlue account sessions"""
    def __init__(self, accounts_config: List[Dict]):
        self.accounts_config = accounts_config
        self.sessions: Dict[str, AccountSession] = {}
        self.logger = logging.getLogger(__name__)

    def initialize_all(self) -> Dict[str, AccountSession]:
        """Initialize all enabled accounts concurrently"""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        enabled_accounts = [
            acc for acc in self.accounts_config if acc.get("enabled", True)
        ]
        
        self.logger.info(f"Initializing {len(enabled_accounts)} accounts...")
        
        with ThreadPoolExecutor(max_workers=min(5, len(enabled_accounts))) as executor:
            future_to_account = {
                executor.submit(self._initialize_single, acc): acc["account_name"]
                for acc in enabled_accounts
            }
            
            for future in as_completed(future_to_account):
                account_name = future_to_account[future]
                try:
                    session = future.result()
                    self.sessions[account_name] = session
                    self.logger.info(f"✓ {account_name} initialized successfully")
                except Exception as e:
                    self.logger.error(f"✗ Failed to initialize {account_name}: {e}", exc_info=True)
        
        return self.sessions

    def _initialize_single(self, account_config: Dict) -> AccountSession:
        """Initialize a single account (thread-safe)"""
        session = AccountSession(
            account_config["account_name"],
            account_config["user_id"],
            account_config["api_key"]
        )
        
        # Create authenticator - THIS IS THE FIX
        auth = Authenticator()  # Now correctly instantiates the class
        
        # Override credentials
        auth.user_id = session.user_id
        auth.api_key = session.api_key
        
        # Login and setup
        session.alice = auth.login()
        auth.download_contracts()
        
        # Initialize components
        session.resolver = InstrumentResolver(session.alice)
        session.executor = OrderExecutor(session.alice)
        session.basket_executor = BasketOrderExecutor(session.alice, session.resolver)
        
        return session
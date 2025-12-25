import logging
from typing import Dict, List, Any, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from .account_manager import AccountSession

class ThreadedOrchestrator:
    """Orchestrates concurrent order execution across multiple accounts"""
    
    def __init__(self, max_workers: int = 5):
        self.max_workers = max_workers
        self.logger = logging.getLogger(__name__)

    def execute_on_all_accounts(
        self,
        sessions: Dict[str, AccountSession],
        instruments: Dict[str, Any],
        order_func: Callable,
        order_config: List[Dict]
    ) -> Dict[str, Any]:
        """Execute orders on all accounts concurrently"""
        
        results = {}
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_account = {}
            
            for account_name, session in sessions.items():
                future = executor.submit(
                    self._execute_on_single_account,
                    account_name,
                    session,
                    instruments,
                    order_func,
                    order_config
                )
                future_to_account[future] = account_name
            
            for future in as_completed(future_to_account):
                account_name = future_to_account[future]
                try:
                    results[account_name] = future.result()
                except Exception as e:
                    self.logger.error(f"Account {account_name} failed: {e}")
                    results[account_name] = {"success": False, "error": str(e)}
        
        return results

    def _execute_on_single_account(
        self,
        account_name: str,
        session: AccountSession,
        instruments: Dict[str, Any],
        order_func: Callable,
        order_config: List[Dict]
    ) -> Dict[str, Any]:
        """Execute orders on a single account (thread-safe)"""
        
        logger = logging.getLogger(f"{__name__}.{account_name}")
        logger.info(f"Starting execution for {account_name}")
        
        account_results = {"individual_orders": [], "basket_orders": []}
        
        logger.info(f"Processing {len(order_config)} orders for {account_name}")
        
        for order_data in order_config:
            # Double-check enabled flag
            if not order_data.get("enabled", True):
                logger.debug(f"Skipping disabled order: {order_data.get('name')}")
                continue
            
            # In _execute_on_single_account
            instrument_key = str(order_data["instrument"]).strip().upper()
            # ✅ NEW CODE:
            instrument = instruments.get(instrument_key)
            if not instrument or not instrument.token:
                # Try dynamic resolution for simple equity symbols
                if "_" not in instrument_key:  # Equity symbols don't have underscores
                    logger.info(f"🔄 Dynamic resolution attempt: {instrument_key}")
                    instrument = session.resolver.resolve_equity("NSE", instrument_key)
                    
                    if instrument and instrument.token:
                        # Cache in both shared dict and session resolver
                        instruments[instrument_key] = instrument
                        session.resolver.instruments[instrument_key] = instrument
                        logger.info(f"✅ Dynamically resolved: {instrument_key} (Token: {instrument.token})")
                    else:
                        logger.warning(f"❌ Dynamic resolution failed for {instrument_key}, skipping")
                        continue
                else:
                    logger.warning(f"❌ Invalid F&O instrument {instrument_key}, skipping")
                    continue
            
            try:
                logger.info(f"Executing: {order_data['name']} on {account_name}")
                result = session.executor.place_order(
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
                    order_tag=f"{account_name}_{order_data.get('order_tag', '')}"
                )
                account_results["individual_orders"].append(result)
            except Exception as e:
                logger.error(f"Order failed: {e}")
                account_results["individual_orders"].append({
                    "success": False,
                    "error": str(e)
                })
        
        return account_results
    
    def execute_basket_on_all_accounts(
        self,
        sessions: Dict[str, AccountSession],
        baskets_config: List[Dict]
    ) -> Dict[str, Any]:
        """Execute basket orders on all accounts concurrently"""
        
        results = {}
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_account = {}
            
            for account_name, session in sessions.items():
                future = executor.submit(
                    self._execute_baskets_on_single_account,
                    account_name,
                    session,
                    baskets_config
                )
                future_to_account[future] = account_name
            
            for future in as_completed(future_to_account):
                account_name = future_to_account[future]
                try:
                    results[account_name] = future.result()
                except Exception as e:
                    self.logger.error(f"Basket execution failed for {account_name}: {e}")
                    results[account_name] = {"success": False, "error": str(e)}
        
        return results

    def _execute_baskets_on_single_account(
        self,
        account_name: str,
        session: AccountSession,
        baskets_config: List[Dict]
    ) -> Dict[str, Any]:
        """Execute basket orders for a single account"""
        
        logger = logging.getLogger(f"{__name__}.{account_name}")
        results = []
        
        for basket in baskets_config:
            if not basket.get("enabled", True):
                logger.info(f"Skipping disabled basket: {basket.get('name')}")
                continue
            
            try:
                basket_copy = self._tag_basket_orders(basket, account_name)
                result = session.basket_executor.execute_basket(basket_copy)
                results.append(result)
            except Exception as e:
                logger.error(f"Basket failed: {e}")
                results.append({"success": False, "error": str(e)})
        
        return {"basket_orders": results}

    def _tag_basket_orders(self, basket: Dict, account_name: str) -> Dict:
        """Add account name prefix to order tags for tracking"""
        basket_copy = basket.copy()
        for order in basket_copy.get("orders", []):
            original_tag = order.get("order_tag", "")
            order["order_tag"] = f"{account_name}_{original_tag}"
        return basket_copy
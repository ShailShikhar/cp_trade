import logging
from typing import Dict, Any, List, Optional
from pya3 import TransactionType, OrderType, ProductType

class BasketOrderExecutionError(Exception):
    """Custom exception for basket order failures"""
    pass

class BasketOrderExecutor:
    def __init__(self, alice, instrument_resolver):
        self.alice = alice
        self.resolver = instrument_resolver
        self.logger = logging.getLogger(__name__)

    def execute_basket(self, basket_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a basket order with multiple legs
        
        Args:
            basket_config: Configuration dictionary containing basket details
            
        Returns:
            Dict containing execution results
        """
        basket_name = basket_config.get("name", "Unnamed Basket")
        
        if not basket_config.get("enabled", True):
            self.logger.info(f"Skipping disabled basket: {basket_name}")
            return {"success": False, "message": "Basket disabled"}
        
        orders = basket_config.get("orders", [])
        if not orders:
            self.logger.warning(f"No orders found in basket: {basket_name}")
            return {"success": False, "message": "Empty basket"}
        
        self.logger.info(f"Executing basket order: {basket_name} with {len(orders)} legs")
        
        # Build basket orders with resolved instruments
        basket = []
        for order_data in orders:
            try:
                order_dict = self._build_order_dict(order_data)
                basket.append(order_dict)
            except Exception as e:
                self.logger.error(f"Failed to build order: {e}")
                return {"success": False, "message": f"Order build failed: {e}"}
        
        # Execute basket order
        try:
            response = self.alice.place_basket_order(basket)
            return self._process_basket_response(basket_name, response)
        except Exception as e:
            self.logger.error(f"Basket order execution failed: {e}")
            raise BasketOrderExecutionError(f"API Error: {str(e)}")

    def _build_order_dict(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert order config to pya3 basket order format with all parameters"""
        # Resolve instrument
        # NEW CODE:
        instrument_key = str(order_data["instrument"]).strip().upper()
        instrument = self.resolver.instruments.get(instrument_key)

        if not instrument or not instrument.token:
            # Try dynamic resolution for equities
            if "_" not in instrument_key:  # Only for equities
                self.logger.info(f"🔄 {instrument_key} not in cache, attempting dynamic resolution...")
                # Use the resolver to fetch dynamically
                instrument = self.resolver.resolve_equity("NSE", instrument_key)
                
                if instrument and instrument.token:
                    # Cache it
                    self.resolver.instruments[instrument_key] = instrument
                    self.logger.info(f"✅ Dynamically resolved basket instrument: {instrument_key}")
                else:
                    raise ValueError(f"Invalid instrument: {instrument_key} (dynamic resolution failed)")
            else:
                raise ValueError(f"Invalid F&O instrument: {instrument_key}. Must be pre-defined.")

        
        # Map string enums to pya3 objects
        order_dict = {
        "instrument": instrument,
        "order_type": getattr(OrderType, order_data["order_type"]),
        "quantity": order_data["quantity"],
        "transaction_type": getattr(TransactionType, order_data["transaction_type"]),
        "product_type": getattr(ProductType, order_data["product_type"]),
        "order_tag": order_data.get("order_tag", "")
            }
        
        # Add price if present (required for limit orders)
        # Add optional parameters only if they exist and have valid values
        if order_data.get("price", 0.0) > 0:
            order_dict["price"] = order_data["price"]
        
        if order_data.get("trigger_price") is not None:
            order_dict["trigger_price"] = order_data["trigger_price"]
        
        if order_data.get("stop_loss") is not None:
            order_dict["stop_loss"] = order_data["stop_loss"]
        
        if order_data.get("square_off") is not None:
            order_dict["square_off"] = order_data["square_off"]
        
        if order_data.get("trailing_sl") is not None:
            order_dict["trailing_sl"] = order_data["trailing_sl"]
        
        if order_data.get("is_amo", False):
            order_dict["is_amo"] = True
        
        return order_dict

    def _process_basket_response(self, basket_name: str, response: Any) -> Dict[str, Any]:
        """Process and validate basket order response"""
        result = {
            "success": False,
            "basket_name": basket_name,
            "raw_response": response,
            "order_numbers": [],
            "message": ""
        }
        
        self.logger.info(f"Basket response for {basket_name}: {response}")
        
        if isinstance(response, list):
            if len(response) == 0:
                result["message"] = "Empty response from basket order"
                self.logger.warning(f"{basket_name}: {result['message']}")
            else:
                result["success"] = True
                result["message"] = f" Basket executed with {len(response)} responses"
                # Extract order numbers if available
                for idx, resp in enumerate(response):
                    if isinstance(resp, dict) and resp.get('stat') == 'Ok':
                        order_no = resp.get('NOrdNo')
                        if order_no:
                            result["order_numbers"].append(order_no)
                self.logger.info(f"✓ {basket_name}: {len(result['order_numbers'])} orders placed successfully")
                
        elif isinstance(response, dict):
            if response.get('stat') == 'Ok':
                result["success"] = True
                result["order_numbers"] = [response.get('NOrdNo')]
                result["message"] = f"Order placed: NOrdNo={response.get('NOrdNo')}"
                self.logger.info(f"✓ {basket_name}: {result['message']}")
            else:
                result["message"] = f" Basket failed: {response}"
                self.logger.error(f"✗ {basket_name}: {result['message']}")
        else:
            result["message"] = f"Unexpected response type: {type(response)}"
            self.logger.error(f"{basket_name}: {result['message']}")
        
        return result
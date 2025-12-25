import logging
from typing import Dict, Any, Optional
from pya3 import TransactionType, OrderType, ProductType

class OrderExecutionError(Exception):
    """Custom exception for order execution failures"""
    pass

class OrderExecutor:
    def __init__(self, alice):
        self.alice = alice
        self.logger = logging.getLogger(__name__)

    def place_order(
        self,
        name: str,
        transaction_type: str,
        instrument,
        quantity: int,
        order_type: str,
        product_type: str,
        price: float = 0.0,
        trigger_price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        square_off: Optional[float] = None,
        trailing_sl: Optional[float] = None,
        is_amo: bool = False,
        order_tag: str = ""
    ) -> Dict[str, Any]:
        """Enhanced order placement with all pya3 parameters"""
        
        if not instrument or not hasattr(instrument, 'token'):
            raise OrderExecutionError(f"Invalid instrument for {name}")

        # Map string types to pya3 enums
        txn_enum = getattr(TransactionType, transaction_type)
        order_enum = getattr(OrderType, order_type)
        product_enum = getattr(ProductType, product_type)

        self.logger.info(f"Placing order: {name}")
        
        order_params = {
        'transaction_type': txn_enum,
        'instrument': instrument,
        'quantity': quantity,
        'order_type': order_enum,
        'product_type': product_enum,
        'price': price,
        'trigger_price': trigger_price,
        'stop_loss': stop_loss,
        'square_off': square_off,
        'trailing_sl': trailing_sl,
        'is_amo': is_amo,
        'order_tag': order_tag
            }
        # Remove None values to avoid API errors
        order_params = {k: v for k, v in order_params.items() if v is not None}
        try:
            response = self.alice.place_order(**order_params)
            return self._process_response(name, response)
        except Exception as e:
            self.logger.error(f"Order placement failed for {name}: {e}")
            raise OrderExecutionError(f"API Error: {str(e)}")

    def _process_response(self, name: str, response: Any) -> Dict[str, Any]:
        """Process and validate API response"""
        result = {
            'success': False,
            'order_number': None,
            'raw_response': response,
            'message': ''
        }

        if isinstance(response, list):
            if len(response) == 0:
                result['message'] = "Empty response - possible invalid token"
                self.logger.warning(f"{name}: {result['message']}")
            else:
                result['success'] = True
                result['message'] = f"Response: {response}"

        elif isinstance(response, dict):
            if response.get('stat') == 'Ok':
                result['success'] = True
                result['order_number'] = response.get('NOrdNo')
                result['message'] = f"Order placed: NOrdNo={result['order_number']}"
                self.logger.info(f"{name}: {result['message']}")
            else:
                result['message'] = f"Order failed: {response}"
                self.logger.error(f"{name}: {result['message']}")
        else:
            result['message'] = f"Unexpected response type: {type(response)}"
            self.logger.error(f"{name}: {result['message']}")

        return result
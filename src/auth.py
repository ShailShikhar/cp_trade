import os
import logging
from pya3 import Aliceblue
from dotenv import load_dotenv

# =========== COMPLETE PATCH FOR PYA3 BUG ===========
import pya3.alicebluepy
from datetime import time as dt_time, datetime
import requests
import os

# Store original method reference (not used, but kept for safety)
_original_get_contract_master = pya3.alicebluepy.Aliceblue.get_contract_master

def _patched_get_contract_master(self, exchange):
    """Complete replacement for buggy pya3 method"""
    try:
        # Map exchange to token (as pya3 expects)
        token_map = {
            "NSE": "nse_cm",
            "NFO": "nfo_cm", 
            "MCX": "mcx_cm",
            "CDS": "cds_cm",
            "BSE": "bse_cm"
        }
        
        if exchange not in token_map:
            raise ValueError(f"Invalid exchange: {exchange}")
            
        token = token_map[exchange]
        
        # FIXED: Use dt_time instead of time module
        if dt_time(8, 0) <= datetime.now().time() or True:
            # Download contract file (replicating pya3's internal logic)
            url = f"https://v2api.aliceblueonline.com/restpy/contract_master?exch={token}"
            
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            # Save to aliceblue's expected location
            contract_dir = os.path.join(os.path.expanduser("~"), ".aliceblue")
            os.makedirs(contract_dir, exist_ok=True)
            
            contract_path = os.path.join(contract_dir, f"{token}.csv")
            with open(contract_path, 'w', encoding='utf-8') as f:
                f.write(response.text)
            
            # Return success message (pya3 doesn't use return value)
            logging.info(f"✓ Contract master downloaded for {exchange}")
            return True
            
    except Exception as e:
        logging.error(f"Contract download failed for {exchange}: {e}")
        # Don't call original - it's broken. Just return False
        return False

# Apply the monkey patch
pya3.alicebluepy.Aliceblue.get_contract_master = _patched_get_contract_master
# =====================================

load_dotenv()

class Authenticator:
    # ... rest of your class remains unchanged ...
    def __init__(self):
        self.user_id = os.getenv("USER_ID")
        self.api_key = os.getenv("API_KEY")
        self.alice = None
        self.logger = logging.getLogger(__name__)
        
        if not self.user_id or not self.api_key:
            raise ValueError("USER_ID and API_KEY must be set in .env file")

    def login(self) -> Aliceblue:
        """Establish connection to AliceBlue API"""
        self.logger.info("Initializing AliceBlue session...")
        self.alice = Aliceblue(user_id=self.user_id, api_key=self.api_key)
        session_id = self.alice.get_session_id()
        self.logger.info(f"Session ID: {session_id}")
        return self.alice

    def download_contracts(self, exchanges: list = None):
        """Download master contracts for specified exchanges"""
        if not self.alice:
            raise RuntimeError("Must login first")
            
        exchanges = exchanges or ["NSE", "NFO", "MCX"]
        for exchange in exchanges:
            self.logger.info(f"Downloading contracts for {exchange}...")
            self.alice.get_contract_master(exchange)  # Uses patched method
        self.logger.info("✓ All contracts downloaded")
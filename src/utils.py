#!/usr/bin/env python3
import logging
import json
import yaml
import pandas as pd
from pathlib import Path
from typing import Any, Dict, List, Union
import importlib.util
import sys

def setup_logging(level=logging.INFO):
    """Configure logging format for the entire system"""
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

def load_config_file(filepath: Path) -> Union[List, Dict]:
    """
    Load a single config file (JSON or YAML)
    Supports both .json and .yaml/.yml extensions
    """
    if not filepath.exists():
        raise FileNotFoundError(f"Config file not found: {filepath}")
    
    try:

        # ✅ NEW: Handle Python modules
        if filepath.suffix == '.py':
            # Add parent directory to path
            module_dir = str(filepath.parent)
            if module_dir not in sys.path:
                sys.path.insert(0, module_dir)
            
            module_name = filepath.stem
            spec = importlib.util.spec_from_file_location(module_name, filepath)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Return the INSTRUMENTS dict
            if hasattr(module, 'INSTRUMENTS'):
                return module.INSTRUMENTS
            else:
                raise ValueError(f"Python module {filepath} must define 'INSTRUMENTS' variable")
                
        if filepath.suffix in ['.yaml', '.yml']:
            with open(filepath, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        else:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except yaml.YAMLError as e:
        logging.error(f"YAML syntax error in {filepath}: {e}")
        raise
    except json.JSONDecodeError as e:
        logging.error(f"JSON syntax error in {filepath}: {e}")
        raise
    except Exception as e:
        logging.error(f"Failed to load config {filepath}: {e}")
        raise

def load_master_excel(filepath: Path) -> List[Dict]:
    """
    Load account configuration from MasterFile.xlsx in root directory.
    Only 3 columns required: USER_ID, API_KEY, CopyEnabled
    Returns list compatible with existing account configuration.
    """
    if not filepath.exists():
        raise FileNotFoundError(f"MasterFile.xlsx not found at: {filepath}")
    
    try:
        df = pd.read_excel(filepath, dtype=str)  # Read all as strings
        df.columns = df.columns.str.strip()  # Normalize column names
        
        logging.info(f"📊 Loaded MasterFile.xlsx with {len(df)} rows, columns: {list(df.columns)}")
        
    except Exception as e:
        logging.error(f"Failed to parse Excel file: {e}")
        raise
    
    # Check for required columns only
    required_cols = ['USER_ID', 'API_KEY', 'CopyEnabled']
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"MasterFile.xlsx missing required columns: {missing}")
    
    accounts = []
    enabled_count = 0
    disabled_count = 0
    
    for idx, row in df.iterrows():
        # Skip rows with empty credentials
        if pd.isna(row['USER_ID']) or pd.isna(row['API_KEY']):
            logging.warning(f"Skipping row {idx + 2}: Empty USER_ID or API_KEY")
            continue
        
        # Parse CopyEnabled - accept 1/0 or TRUE/FALSE (case-insensitive)
        copy_val = str(row['CopyEnabled']).strip().lower()
        is_enabled = copy_val in ['true', '1', 'yes', 'y']
        
        if not is_enabled:
            logging.debug(f"Skipping {row['USER_ID']}: CopyEnabled={row['CopyEnabled']}")
            disabled_count += 1
            continue
        
        # Create account config
        account = {
            'account_name': str(row.get('Account_Name', row['USER_ID'])).strip(),
            'user_id': str(row['USER_ID']).strip(),
            'api_key': str(row['API_KEY']).strip(),
            'enabled': True,
        }
        
        accounts.append(account)
        enabled_count += 1
        logging.info(f"✓ Loaded account: {account['account_name']} (ID: {account['user_id']})")
    
    logging.info(f"📊 Summary: {enabled_count} enabled, {disabled_count} disabled")
    
    if not accounts:
        logging.warning("No enabled accounts found in MasterFile.xlsx")
    
    return accounts

def load_master_config(config_dir: Path) -> Dict[str, Any]:
    """
    Load entire trading configuration from master manifest (_master.yaml).
    Returns dict with 'orders', 'basket_orders', 'instruments' keys.
    """
    master_file = config_dir / "_master.yaml"
    
    # Fall back to legacy JSON if master.yaml doesn't exist
    if not master_file.exists():
        logging.warning("No _master.yaml found, falling back to legacy JSON files")
        return _load_legacy_configs(config_dir)
    
    # Load master manifest
    manifest = load_config_file(master_file)
    result = {"orders": [], "basket_orders": [], "instruments": {}}
    
    # Load individual orders from YAML/JSON fragments
    for order_file in manifest.get("orders", []):
        path = config_dir / order_file
        if path.exists():
            data = load_config_file(path)
            if isinstance(data, list):
                result["orders"].extend(data)
                logging.info(f"✓ Loaded {len(data)} orders from {order_file}")
            else:
                logging.warning(f"Expected list in {order_file}, got {type(data).__name__}")
        else:
            logging.error(f"Order config file not found: {order_file}")
    
    # Load basket orders
    for basket_file in manifest.get("basket_orders", []):
        path = config_dir / basket_file
        if path.exists():
            data = load_config_file(path)
            if isinstance(data, list):
                result["basket_orders"].extend(data)
                logging.info(f"✓ Loaded {len(data)} baskets from {basket_file}")
            else:
                logging.warning(f"Expected list in {basket_file}, got {type(data).__name__}")
        else:
            logging.error(f"Basket config file not found: {basket_file}")
    
    # Load instruments (keeping JSON format for backward compatibility)
    instruments_file = config_dir / manifest.get("instruments", "instruments.json")
    if instruments_file.exists():
        result["instruments"] = load_config_file(instruments_file)
        logging.info(f"✓ Loaded instruments from {instruments_file}")
    else:
        logging.error(f"Instruments config not found: {instruments_file}")
        raise FileNotFoundError(f"Critical: {instruments_file} is required")
    
    # Summary
    total_orders = len(result["orders"])
    total_baskets = len(result["basket_orders"])
    logging.info(f"🎯 Config load complete: {total_orders} orders, {total_baskets} baskets")
    
    return result

def _load_legacy_configs(config_dir: Path) -> Dict[str, Any]:
    """
    Fallback loader for legacy single-file JSON configs.
    Used when _master.yaml is not present.
    """
    try:
        return {
            "orders": load_config_file(config_dir / "orders.json"),
            "basket_orders": load_config_file(config_dir / "basket_orders.json"),
            "instruments": load_config_file(config_dir / "instruments.json")
        }
    except FileNotFoundError as e:
        logging.critical("Neither _master.yaml nor legacy JSON files found!")
        raise

def print_section(title: str):
    """Print formatted section header to console"""
    print(f"\n{'='*60}")
    print(f" {title:^58}".upper())
    print(f"{'='*60}\n")

def validate_config_structure(config_data: Dict[str, Any]) -> bool:
    """
    Validate that loaded config has required structure.
    Returns True if valid, raises ValueError if critical issues found.
    """
    required_keys = ["orders", "basket_orders", "instruments"]
    missing = [key for key in required_keys if key not in config_data]
    
    if missing:
        raise ValueError(f"Missing required config sections: {missing}")
    
    # Validate instruments has required subsections
    instruments = config_data["instruments"]
    if "nse_equity" not in instruments and "nfo_derivatives" not in instruments:
        logging.warning("instruments.json missing expected NSE/NFO sections")
    
    return True
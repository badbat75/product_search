import logging
from pathlib import Path
from typing import Dict, Any
import sys
from config import SEARCH_CONFIG_PATH

def setup_logging(name: str) -> logging.Logger:
    """Initialize logging configuration"""
    # Ensure var/log directory exists
    log_dir = Path('var/log')
    log_dir.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / f'{name}.log')
        ]
    )
    return logging.getLogger(name)

def read_config(required_keys: list[str] = None) -> Dict[str, Any]:
    """Read configuration from search.cfg file
    
    Args:
        required_keys: List of keys that must be present in config
    
    Returns:
        Dictionary containing configuration values
    """
    config = {}
    try:
        with open(SEARCH_CONFIG_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                    
                try:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"\'')
                    config[key] = value
                except ValueError as e:
                    logging.warning(f"Invalid config line: {line} - {str(e)}")

        if required_keys:
            missing = [key for key in required_keys if key not in config]
            if missing:
                raise ValueError(f"Required config keys not found: {', '.join(missing)}")
                
        return config
        
    except FileNotFoundError:
        raise FileNotFoundError(f"Config file {SEARCH_CONFIG_PATH} not found")
    except Exception as e:
        raise Exception(f"Config file reading error: {str(e)}")

def normalize_product_name(name: str) -> str:
    """Convert product name to filename format
    
    Args:
        name: Product name to normalize
    
    Returns:
        Normalized product name suitable for filenames
    """
    # Remove trailing comma and quantity if present
    if ',' in name:
        name = name.split(',')[0]
    return name.strip().replace(' ', '_')

def read_products(filename: str) -> Dict[str, int]:
    """Read products and their quantities from file
    
    Args:
        filename: Path to products file
        
    Returns:
        Dictionary mapping product names to quantities
    """
    # Ensure var/data directory exists
    data_dir = Path('var/data')
    data_dir.mkdir(parents=True, exist_ok=True)

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            products = {}
            for line in f:
                line = line.strip()
                if ',' in line:
                    product_name, quantity = line.split(',')
                    products[product_name.strip()] = int(quantity)
                else:
                    products[line.strip()] = 1

            # Move any existing CSV files to var/data
            for product_name in products:
                csv_name = f"{normalize_product_name(product_name)}.csv"
                old_path = Path(csv_name)
                new_path = data_dir / csv_name
                
                if old_path.exists() and not new_path.exists():
                    old_path.rename(new_path)
                    
            return products
            
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found")
        sys.exit(1)
    return products

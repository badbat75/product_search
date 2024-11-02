import logging
from pathlib import Path
from typing import Dict, Any
import sys

def setup_logging(name: str) -> logging.Logger:
    """Initialize logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(f'{name}.log')
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
        with open('search.cfg', 'r', encoding='utf-8') as f:
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
        raise FileNotFoundError("Config file search.cfg not found")
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
    products = {}
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if ',' in line:
                    product_name, quantity = line.split(',')
                    products[product_name.strip()] = int(quantity)
                else:
                    products[line.strip()] = 1
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found")
        sys.exit(1)
    return products

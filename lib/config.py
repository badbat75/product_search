"""Common configuration variables for search and optimizer modules"""
from pathlib import Path
import os

# Configuration paths
SEARCH_CONFIG_PATH = Path(os.getenv('SEARCH_CONFIG_PATH', 'conf/search.cfg'))

# Directory paths
VAR_DATA_DIR = Path('var/data')
VAR_LOG_DIR = Path('var/log')
VAR_DEBUG_DIR = Path('var/debug')
VAR_DEBUG_AI_DIR = VAR_DEBUG_DIR / 'ai'
TEMPLATES_DIR = Path('templates')

# Browser configuration
BROWSER_CONFIGS = {
    'edge': ('EdgeOptions', 'Edge'),
    'firefox': ('FirefoxOptions', 'Firefox'),
    'chrome': ('ChromeOptions', 'Chrome')
}

# Browser binary paths - these can be overridden in search.cfg
BROWSER_BINARY_PATHS = {
    'edge': None,
    'firefox': None,
    'chrome': None
}

BROWSER_OPTIONS = [
    '--start-maximized',
    '--disable-popup-blocking',
    '--disable-notifications'
]

# Search configuration
BASE_URL = "https://www.trovaprezzi.it"
CSV_COLUMNS = ['nome_prodotto', 'prezzo', 'spedizione', 'venditore', 'link_venditore']

# Timing configuration
DEFAULT_THROTTLE_DELAY = 2.0
DEFAULT_RETRY_COUNT = 3
DEFAULT_PAGE_LOAD_TIMEOUT = 30
DEFAULT_CAPTCHA_TIMEOUT = 300

# Order configuration
DEFAULT_MINIMUM_ORDER = 50.0  # Default minimum order value in euros
DEFAULT_MAX_VENDOR_COMBINATIONS = 4  # Default maximum number of vendors to combine

# Create necessary directories
VAR_DATA_DIR.mkdir(parents=True, exist_ok=True)
VAR_LOG_DIR.mkdir(parents=True, exist_ok=True)
VAR_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
VAR_DEBUG_AI_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

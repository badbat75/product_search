import time
import urllib.parse
from pathlib import Path
from typing import List, Optional
import csv
import argparse
import sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from datetime import datetime
from lib.utils import setup_logging, read_config, read_products, normalize_product_name
from lib.aisearch import AIProcessor
from lib.browser import configure_browser_options
from lib.config import (
    VAR_DATA_DIR, VAR_DEBUG_DIR, VAR_DEBUG_AI_DIR, TEMPLATES_DIR,
    BROWSER_CONFIGS, BROWSER_OPTIONS, BASE_URL, CSV_COLUMNS,
    DEFAULT_THROTTLE_DELAY, DEFAULT_RETRY_COUNT,
    DEFAULT_PAGE_LOAD_TIMEOUT, DEFAULT_CAPTCHA_TIMEOUT
)

class TrovaprezziProcessor:
    """Processor for scraping Trovaprezzi.it and processing with Claude"""
    
    def __init__(self, 
                 claude_api_key: str, 
                 throttle_delay_sec: float = DEFAULT_THROTTLE_DELAY, 
                 output_dir: str = None, 
                 retry_count: int = DEFAULT_RETRY_COUNT, 
                 browser_type: str = 'edge',
                 debug: bool = False,
                 debug_ai: bool = False,
                 force: bool = False,
                 config: dict = None):
        self.logger = setup_logging(__name__)
        self.throttle_delay_sec = float(throttle_delay_sec)
        self.retry_count = retry_count
        self.debug = debug
        self.debug_ai = debug_ai
        self.force = force
        self.config = config or {}
        
        # Use var/data directory for CSV files
        self.csv_dir = VAR_DATA_DIR
        
        # Initialize AI processor
        self.ai_processor = AIProcessor(
            claude_api_key=claude_api_key,
            throttle_delay_sec=throttle_delay_sec,
            retry_count=retry_count,
            debug_ai=debug_ai,
            ai_responses_dir=VAR_DEBUG_AI_DIR if debug_ai else None
        )
        
        self.browser_type = browser_type.lower()
        self.driver = self._init_browser()

    def _init_browser(self) -> webdriver.Remote:
        """Initialize and configure the selected browser"""
        try:
            if self.browser_type not in BROWSER_CONFIGS:
                raise ValueError(f"Unsupported browser type: {self.browser_type}")
            
            options_name, driver_name = BROWSER_CONFIGS[self.browser_type]
            OptionsClass = getattr(webdriver, options_name)
            DriverClass = getattr(webdriver, driver_name)
            
            options = OptionsClass()
            
            # Set binary location if specified in config
            if hasattr(self, 'config') and 'BROWSER_BINARY_PATHS' in self.config:
                binary_path = self.config['BROWSER_BINARY_PATHS'].get(self.browser_type)
                if binary_path:
                    self.logger.info(f"Using custom binary path for {self.browser_type}: {binary_path}")
                    options.binary_location = binary_path

            # Add common browser options
            for option in BROWSER_OPTIONS:
                options.add_argument(option)

            # Configure browser profile using the browser utility
            options = configure_browser_options(self.browser_type, options, self.config, self.logger)

            driver = DriverClass(options=options)
            driver.set_page_load_timeout(DEFAULT_PAGE_LOAD_TIMEOUT)
            
            self.logger.info(f"Browser {self.browser_type} initialized successfully")
            return driver
            
        except Exception as e:
            self.logger.error(f"Browser initialization error: {str(e)}")
            raise

    def handle_captcha(self) -> bool:
        """Handle CAPTCHA presence"""
        try:
            if "captcha" not in self.driver.current_url.lower():
                return False
                
            self.logger.info("CAPTCHA detected, waiting for human input...")
            WebDriverWait(self.driver, DEFAULT_CAPTCHA_TIMEOUT).until(
                lambda driver: "captcha" not in driver.current_url.lower()
            )
            self.logger.info("CAPTCHA resolved")
            return True
            
        except TimeoutException:
            self.logger.error("CAPTCHA resolution timeout")
            return False
        except Exception as e:
            self.logger.error(f"CAPTCHA handling error: {str(e)}")
            return False

    def save_to_csv(self, data: List[List[str]], product_name: str) -> Optional[Path]:
        """Save extracted data to CSV"""
        try:
            filename = normalize_product_name(product_name)
            csv_path = self.csv_dir / f"{filename}.csv"
            
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, delimiter=',', quoting=csv.QUOTE_NONNUMERIC)
                writer.writerow(CSV_COLUMNS)
                writer.writerows(data)
            
            self.logger.info(f"Data saved to: {csv_path}")
            return csv_path
            
        except Exception as e:
            self.logger.error(f"CSV save error: {str(e)}")
            return None

    def process_product(self, product_name: str) -> bool:
        """Process a single product search"""
        try:
            # Check for existing CSV unless force flag is set
            filename = normalize_product_name(product_name)
            csv_path = self.csv_dir / f"{filename}.csv"
            if csv_path.exists() and not self.force:
                self.logger.info(f"CSV exists, skipping: {csv_path}")
                return True

            # Prepare search
            search_url = f"{BASE_URL}/categoria.aspx?id=-1&libera={urllib.parse.quote(product_name)}"
            self.logger.info(f"Searching: {product_name}")
            
            # Visit homepage first
            self.driver.get(BASE_URL)
            
            # Search page
            self.driver.get(search_url)
            
            # Handle CAPTCHA if needed
            if self.handle_captcha():
                self.driver.get(search_url)
            
            # Wait for page load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Process and save
            html_content = self.driver.page_source
            if self.debug:
                debug_file = VAR_DEBUG_DIR / 'debug_last_page.html'
                debug_file.write_text(html_content, encoding='utf-8')
            
            data = self.ai_processor.process_html(html_content, product_name, BASE_URL)
            
            if data:
                return bool(self.save_to_csv(data, product_name))
            else:
                self.logger.warning(f"No data extracted for {product_name}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error processing {product_name}: {str(e)}")
            return False

    def run(self, products_file: str) -> bool:
        """Main execution flow"""
        try:
            products = read_products(products_file)
            
            if not products:
                self.logger.error("No products to search")
                return False
                
            self.logger.info(f"Found {len(products)} products to process")
            
            success_count = 0
            for product in products:
                if self.process_product(product):
                    success_count += 1
                    
            self.logger.info(f"Processed {success_count}/{len(products)} products successfully")
            return success_count > 0
                
        finally:
            if self.driver:
                self.driver.quit()

def main():
    parser = argparse.ArgumentParser(
        description='Search products on Trovaprezzi and process with Claude'
    )
    parser.add_argument(
        'input_file',
        type=str,
        help='Input file with shopping list (e.g., farmacia.txt, list.csv)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode'
    )
    parser.add_argument(
        '--debug-ai',
        action='store_true',
        help='Enable AI response debugging (saves responses to var/debug/ai)'
    )
    parser.add_argument(
        '-f', '--force',
        action='store_true',
        help='Force overwrite existing CSV files'
    )
    
    try:
        args = parser.parse_args()
        config = read_config(['CLAUDE_API_KEY', 'THROTTLE_DELAY_SEC', 'RETRY_COUNT', 'BROWSER_TYPE'])
        
        # Use file stem (name without extension) for output directory
        output_dir = Path(args.input_file).stem
        
        processor = TrovaprezziProcessor(
            claude_api_key=config['CLAUDE_API_KEY'],
            throttle_delay_sec=float(config.get('THROTTLE_DELAY_SEC', DEFAULT_THROTTLE_DELAY)),
            output_dir=output_dir,
            retry_count=int(config.get('RETRY_COUNT', DEFAULT_RETRY_COUNT)),
            browser_type=config.get('BROWSER_TYPE', 'edge'),
            debug=args.debug,
            debug_ai=args.debug_ai,
            force=args.force,
            config=config  # Pass the entire config dictionary
        )
        
        if not processor.run(args.input_file):
            sys.exit(1)
            
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

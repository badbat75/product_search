import time
from pathlib import Path
from typing import List, Optional
import csv
import argparse
import sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from datetime import datetime
from lib.utils import setup_logging, read_config, read_products, normalize_product_name
from lib.htmlparser import HtmlProcessor
from lib.config import (
    VAR_DATA_DIR, VAR_DEBUG_DIR, VAR_DEBUG_AI_DIR, TEMPLATES_DIR,
    BROWSER_CONFIGS, BROWSER_OPTIONS, BASE_URL, CSV_COLUMNS,
    DEFAULT_THROTTLE_DELAY, DEFAULT_RETRY_COUNT,
    DEFAULT_PAGE_LOAD_TIMEOUT, DEFAULT_CAPTCHA_TIMEOUT
)

class TrovaprezziProcessor:
    """Processor for scraping Trovaprezzi.it and processing with Claude"""
    
    def __init__(self,
                 throttle_delay_sec: float = DEFAULT_THROTTLE_DELAY,
                 output_dir: str = None,
                 retry_count: int = DEFAULT_RETRY_COUNT,
                 browser_type: str = 'edge',
                 debug: bool = False,
                 debug_ai: bool = False,
                 force: bool = False,
                 use_ai: bool = False,
                 claude_api_key: str = None):
        self.logger = setup_logging(__name__)
        self.throttle_delay_sec = float(throttle_delay_sec)
        self.retry_count = retry_count
        self.debug = debug
        self.debug_ai = debug_ai
        self.force = force
        self.use_ai = use_ai

        # Use var/data directory for CSV files
        self.csv_dir = VAR_DATA_DIR

        # Initialize processor
        if use_ai:
            from lib.aisearch import AIProcessor
            self.processor = AIProcessor(
                claude_api_key=claude_api_key,
                throttle_delay_sec=throttle_delay_sec,
                retry_count=retry_count,
                debug_ai=debug_ai,
                ai_responses_dir=VAR_DEBUG_AI_DIR if debug_ai else None
            )
        else:
            self.processor = HtmlProcessor()

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

            # Add common browser options
            for option in BROWSER_OPTIONS:
                options.add_argument(option)

            # Anti-detection: hide Selenium/automation fingerprint
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_experimental_option('excludeSwitches', ['enable-automation'])
            options.add_experimental_option('useAutomationExtension', False)

            driver = DriverClass(options=options)
            driver.set_page_load_timeout(DEFAULT_PAGE_LOAD_TIMEOUT)

            # Remove navigator.webdriver flag
            driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
            })
            
            self.logger.info(f"Browser {self.browser_type} initialized successfully")
            return driver
            
        except Exception as e:
            self.logger.error(f"Browser initialization error: {str(e)}")
            raise

    def _is_captcha_present(self) -> bool:
        """Detect CAPTCHA by checking URL and visible page elements"""
        url = self.driver.current_url.lower()
        if "captcha" in url or "challenge" in url:
            return True

        # Check for visible CAPTCHA elements
        captcha_selectors = [
            "iframe[src*='captcha-delivery.com']",
            "iframe[src*='geo.captcha-delivery.com']",
            "iframe[title*='DataDome']",
            "iframe[src*='recaptcha']",
            "iframe[src*='hcaptcha']",
            ".g-recaptcha",
            ".h-captcha",
            "#cf-challenge-running",
            "iframe[src*='turnstile']",
        ]
        for selector in captcha_selectors:
            try:
                el = self.driver.find_element(By.CSS_SELECTOR, selector)
                if el.is_displayed():
                    return True
            except Exception:
                continue

        # DataDome: full-page captcha with script from captcha-delivery.com
        try:
            page = self.driver.page_source
            if "captcha-delivery.com" in page and "<iframe" in page.lower():
                return True
        except Exception:
            pass

        return False

    def handle_captcha(self) -> bool:
        """Handle CAPTCHA presence - waits for user to solve it manually"""
        try:
            if self.debug:
                debug_file = VAR_DEBUG_DIR / 'debug_captcha_check.html'
                debug_file.write_text(self.driver.page_source, encoding='utf-8')
                self.logger.debug(f"Captcha check - URL: {self.driver.current_url}")

            if not self._is_captcha_present():
                return False

            self.logger.info("CAPTCHA detected! Please solve it in the browser...")

            start = time.time()
            while time.time() - start < DEFAULT_CAPTCHA_TIMEOUT:
                time.sleep(2)
                if not self._is_captcha_present():
                    self.logger.info("CAPTCHA resolved")
                    return True

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

    def _find_search_box(self):
        """Find the search input on the page"""
        selectors = [
            (By.NAME, "libera"),
            (By.ID, "search"),
            (By.CSS_SELECTOR, "input[type='search']"),
            (By.CSS_SELECTOR, "input.search"),
            (By.CSS_SELECTOR, "input[placeholder*='cerca' i]"),
            (By.CSS_SELECTOR, "input[placeholder*='search' i]"),
            (By.CSS_SELECTOR, "form[role='search'] input"),
        ]
        for by, selector in selectors:
            try:
                el = self.driver.find_element(by, selector)
                if el.is_displayed():
                    return el
            except Exception:
                continue
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

            self.logger.info(f"Searching: {product_name}")

            # Navigate to homepage
            self.driver.get(BASE_URL)

            # Handle CAPTCHA if it appears on homepage
            self.handle_captcha()

            # Wait for homepage and find search box
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            search_box = self._find_search_box()
            if not search_box:
                self.logger.error("Could not find search box on homepage")
                return False

            # Type the search query and submit
            search_box.clear()
            search_box.send_keys(product_name)
            search_box.send_keys(Keys.RETURN)

            # Handle CAPTCHA if it appears after search
            self.handle_captcha()

            # Wait for results page
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Process and save
            html_content = self.driver.page_source
            if self.debug:
                debug_file = VAR_DEBUG_DIR / 'debug_last_page.html'
                debug_file.write_text(html_content, encoding='utf-8')
            
            data = self.processor.process_html(html_content, product_name, BASE_URL)
            
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
    parser.add_argument(
        '--ai',
        action='store_true',
        help='Use Claude AI for HTML extraction instead of HTML parser'
    )

    try:
        args = parser.parse_args()

        required_keys = ['THROTTLE_DELAY_SEC', 'RETRY_COUNT', 'BROWSER_TYPE']
        if args.ai:
            required_keys.append('CLAUDE_API_KEY')
        config = read_config(required_keys)

        # Use file stem (name without extension) for output directory
        output_dir = Path(args.input_file).stem

        processor = TrovaprezziProcessor(
            throttle_delay_sec=float(config.get('THROTTLE_DELAY_SEC', DEFAULT_THROTTLE_DELAY)),
            output_dir=output_dir,
            retry_count=int(config.get('RETRY_COUNT', DEFAULT_RETRY_COUNT)),
            browser_type=config.get('BROWSER_TYPE', 'edge'),
            debug=args.debug,
            debug_ai=args.debug_ai,
            force=args.force,
            use_ai=args.ai,
            claude_api_key=config.get('CLAUDE_API_KEY'),
        )
        
        if not processor.run(args.input_file):
            sys.exit(1)
            
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

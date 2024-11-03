import time
import urllib.parse
import anthropic
from pathlib import Path
from typing import List, Optional
import csv
import argparse
import random
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import sys
import json
from datetime import datetime
from utils import setup_logging, read_config, read_products, normalize_product_name

class TrovaprezziProcessor:
    """Processor for scraping Trovaprezzi.it and processing with Claude"""
    
    BASE_URL = "https://www.trovaprezzi.it"
    CSV_COLUMNS = ['nome_prodotto', 'prezzo', 'spedizione', 'venditore', 'link_venditore']
    
    def __init__(self, 
                 claude_api_key: str, 
                 throttle_delay_sec: float, 
                 output_dir: str, 
                 retry_count: int, 
                 browser_type: str = 'edge',
                 debug: bool = False,
                 debug_ai: bool = False):
        self.logger = setup_logging(__name__)
        self.client = anthropic.Anthropic(api_key=claude_api_key, max_retries=0)
        self.throttle_delay_sec = float(throttle_delay_sec)
        self.retry_count = retry_count
        self.last_api_call_time = None
        self.debug = debug
        self.debug_ai = debug_ai
        
        # Use var/data directory for CSV files
        self.csv_dir = Path('var/data')
        self.csv_dir.mkdir(parents=True, exist_ok=True)
        
        # Create AI responses directory if debug_ai is enabled
        if self.debug_ai:
            self.ai_responses_dir = Path('var/debug/ai')
            self.ai_responses_dir.mkdir(parents=True, exist_ok=True)
        
        self.browser_type = browser_type.lower()
        self.driver = self._init_browser()

    def _init_browser(self) -> webdriver.Remote:
        """Initialize and configure the selected browser"""
        browser_configs = {
            'edge': (webdriver.EdgeOptions, webdriver.Edge),
            'firefox': (webdriver.FirefoxOptions, webdriver.Firefox),
            'chrome': (webdriver.ChromeOptions, webdriver.Chrome)
        }
        
        try:
            if self.browser_type not in browser_configs:
                raise ValueError(f"Unsupported browser type: {self.browser_type}")
            
            OptionsClass, DriverClass = browser_configs[self.browser_type]
            options = OptionsClass()
            
            # Common browser options
            options.add_argument('--start-maximized')
            options.add_argument('--disable-popup-blocking')
            options.add_argument('--disable-notifications')
            
            driver = DriverClass(options=options)
            driver.set_page_load_timeout(30)
            
            self.logger.info(f"Browser {self.browser_type} initialized successfully")
            return driver
            
        except Exception as e:
            self.logger.error(f"Browser initialization error: {str(e)}")
            raise

    def _wait_for_throttle(self):
        """Apply throttling between API calls"""
        if self.last_api_call_time:
            time.sleep(self.throttle_delay_sec)
            self.logger.debug(f"Throttled for {self.throttle_delay_sec}s")

    def _random_delay(self, min_sec: float = 2, max_sec: float = 5):
        """Add random delay between requests"""
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)
        self.logger.debug(f"Random delay: {delay:.2f}s")

    def _convert_to_absolute_url(self, url: str) -> str:
        """Convert relative URL to absolute"""
        if not url or url.startswith('http'):
            return url
        return f"{self.BASE_URL}{url}"

    def _parse_price(self, price_str: str) -> Optional[float]:
        """Parse price string to float, handling European number format"""
        try:
            # Remove any whitespace and currency symbols
            price_str = price_str.strip().replace('€', '').strip()
            
            # Handle empty or zero prices
            if not price_str or price_str == '0':
                return 0.0
                
            # Convert European format (1.234,56) to standard float format
            # First remove thousands separators, then replace decimal comma
            price_str = price_str.replace('.', '').replace(',', '.')
            
            return float(price_str)
        except (ValueError, AttributeError):
            return None

    def _save_ai_response(self, product_name: str, response_data: dict):
        """Save AI response data to JSON file"""
        if not self.debug_ai:
            return
            
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{product_name.replace(' ', '_')}_{timestamp}.json"
            filepath = self.ai_responses_dir / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(response_data, f, ensure_ascii=False, indent=2)
                
            self.logger.info(f"AI response saved to: {filepath}")
            
        except Exception as e:
            self.logger.error(f"Error saving AI response: {str(e)}")

    def handle_captcha(self) -> bool:
        """Handle CAPTCHA presence"""
        try:
            if "captcha" not in self.driver.current_url.lower():
                return False
                
            self.logger.info("CAPTCHA detected, waiting for human input...")
            WebDriverWait(self.driver, 300).until(
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

    def process_html_with_claude(self, html_content: str, product_name: str, retry_count: int = 0) -> List[List[str]]:
        """Process HTML content with Claude and get structured data"""
        prompt = """Estrai dati prodotti da TrovaPrezzi.it nel seguente formato:
    nome_prodotto|prezzo|spese|venditore|link

    Regole importanti:
    1. Per nome_prodotto: Estrai il nome completo del prodotto con tutte le specifiche tecniche, NON il nome del venditore
    2. Per prezzo: 
       - Estrai SOLO il numero (es: se vedi "123,45 €" scrivi "123,45")
       - Rimuovi il simbolo € e qualsiasi altro testo
       - Usa la virgola come separatore decimale
    3. Per spese: 
       - Se spedizione gratuita/gratis: scrivi "0"
       - Altrimenti: estrai SOLO il numero come per il prezzo (es: se vedi "5,90 €" scrivi "5,90")
    4. Per venditore: Nome del negozio/venditore
    5. Per link: URL completo del venditore

    Stampa in formato CSV con | come separatore. Non includere intestazioni.
    NON includere il simbolo € o altro testo nei campi numerici.

    HTML:"""
        
        try:
            if retry_count == 0:
                self._wait_for_throttle()
            
            message = self.client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=4096,
                temperature=0,
                system="Estrai dati CSV con | separatore. Per nome_prodotto usa il nome completo del prodotto con specifiche tecniche. Per prezzi e spese, estrai SOLO i numeri senza € o altro testo.",
                messages=[{"role": "user", "content": f"{prompt}\n{html_content}"}]
            )
            
            self.last_api_call_time = time.time()
            response_content = message.content[0].text.strip()
            
            # Save AI response if debug_ai is enabled
            if self.debug_ai:
                response_data = {
                    "timestamp": datetime.now().isoformat(),
                    "product_name": product_name,
                    "prompt": prompt,
                    "html_content": html_content,
                    "response": response_content
                }
                self._save_ai_response(product_name, response_data)
            
            # Process response
            data = []
            for line in response_content.splitlines():
                if not line.strip():
                    continue
                    
                fields = line.split('|')
                if len(fields) == 5:
                    # Parse price and shipping cost
                    price = self._parse_price(fields[1])
                    shipping = self._parse_price(fields[2])
                    
                    if price is not None and shipping is not None:
                        # Format prices with 2 decimal places
                        fields[1] = f"{price:.2f}"
                        fields[2] = f"{shipping:.2f}"
                        
                        # Convert link to absolute URL
                        fields[4] = self._convert_to_absolute_url(fields[4])
                        data.append(fields)
                    else:
                        self.logger.warning(f"Skipping row with invalid price format: {fields}")
            
            return data

        except anthropic.RateLimitError:
            attempt = retry_count + 2
            self.logger.warning(f"Rate limit error (429) - Attempt {attempt}/{self.retry_count + 1}")
            if retry_count < self.retry_count:
                time.sleep(self.throttle_delay_sec * 2)  # Double delay on retry
                return self.process_html_with_claude(html_content, product_name, retry_count + 1)
            self.logger.error("Max retries exceeded for rate limiting")
            raise
                
        except Exception as e:
            self.logger.error(f"Claude processing error: {str(e)}")
            self.last_api_call_time = time.time()
            return []

    def save_to_csv(self, data: List[List[str]], product_name: str) -> Optional[Path]:
        """Save extracted data to CSV"""
        try:
            filename = normalize_product_name(product_name)
            csv_path = self.csv_dir / f"{filename}.csv"
            
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, delimiter=',', quoting=csv.QUOTE_NONNUMERIC)
                writer.writerow(self.CSV_COLUMNS)
                writer.writerows(data)
            
            self.logger.info(f"Data saved to: {csv_path}")
            return csv_path
            
        except Exception as e:
            self.logger.error(f"CSV save error: {str(e)}")
            return None

    def process_product(self, product_name: str) -> bool:
        """Process a single product search"""
        try:
            # Check for existing CSV
            filename = normalize_product_name(product_name)
            csv_path = self.csv_dir / f"{filename}.csv"
            if csv_path.exists():
                self.logger.info(f"CSV exists, skipping: {csv_path}")
                return True

            # Prepare search
            search_url = f"{self.BASE_URL}/categoria.aspx?id=-1&libera={urllib.parse.quote(product_name)}"
            self.logger.info(f"Searching: {product_name}")
            
            # Visit homepage first
            self.driver.get(self.BASE_URL)
            self._random_delay()
            
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
                Path('debug_last_page.html').write_text(html_content, encoding='utf-8')
            
            data = self.process_html_with_claude(html_content, product_name)
            
            if data:
                return bool(self.save_to_csv(data, product_name))
            else:
                self.logger.warning(f"No data extracted for {product_name}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error processing {product_name}: {str(e)}")
            return False
        finally:
            self._random_delay()

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
    
    try:
        args = parser.parse_args()
        config = read_config(['CLAUDE_API_KEY', 'THROTTLE_DELAY_SEC', 'RETRY_COUNT', 'BROWSER_TYPE'])
        
        # Use file stem (name without extension) for output directory
        output_dir = Path(args.input_file).stem
        
        processor = TrovaprezziProcessor(
            claude_api_key=config['CLAUDE_API_KEY'],
            throttle_delay_sec=float(config['THROTTLE_DELAY_SEC']),
            output_dir=output_dir,
            retry_count=int(config['RETRY_COUNT']),
            browser_type=config['BROWSER_TYPE'],
            debug=args.debug,
            debug_ai=args.debug_ai
        )
        
        if not processor.run(args.input_file):
            sys.exit(1)
            
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

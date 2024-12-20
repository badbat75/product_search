import anthropic
from datetime import datetime
import json
from pathlib import Path
import time
from typing import List, Optional
from lib.utils import setup_logging

class AIProcessor:
    """Handles AI processing using Claude API"""
    
    def __init__(self, 
                 claude_api_key: str,
                 throttle_delay_sec: float,
                 retry_count: int,
                 debug_ai: bool = False,
                 ai_responses_dir: Optional[Path] = None):
        self.logger = setup_logging(__name__)
        self.client = anthropic.Anthropic(api_key=claude_api_key, max_retries=0)
        self.throttle_delay_sec = float(throttle_delay_sec)
        self.retry_count = retry_count
        self.last_api_call_time = None
        self.debug_ai = debug_ai
        self.ai_responses_dir = ai_responses_dir

    def _wait_for_throttle(self):
        """Apply throttling between API calls"""
        if self.last_api_call_time:
            time.sleep(self.throttle_delay_sec)
            self.logger.debug(f"Throttled for {self.throttle_delay_sec}s")

    def _save_ai_response(self, product_name: str, response_data: dict):
        """Save AI response data to JSON file"""
        if not self.debug_ai or not self.ai_responses_dir:
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

    def process_html(self, html_content: str, product_name: str, base_url: str, retry_count: int = 0) -> List[List[str]]:
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
                        
                        # Convert link to absolute URL if needed
                        if not fields[4].startswith('http'):
                            fields[4] = f"{base_url}{fields[4]}"
                        
                        data.append(fields)
                    else:
                        self.logger.warning(f"Skipping row with invalid price format: {fields}")
            
            return data

        except anthropic.RateLimitError:
            attempt = retry_count + 2
            self.logger.warning(f"Rate limit error (429) - Attempt {attempt}/{self.retry_count + 1}")
            if retry_count < self.retry_count:
                time.sleep(self.throttle_delay_sec)  # Double delay on retry
                return self.process_html(html_content, product_name, base_url, retry_count + 1)
            self.logger.error("Max retries exceeded for rate limiting")
            raise
                
        except Exception as e:
            self.logger.error(f"Claude processing error: {str(e)}")
            self.last_api_call_time = time.time()
            return []

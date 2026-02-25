import re
from typing import List, Optional
from bs4 import BeautifulSoup
from lib.utils import setup_logging


class HtmlProcessor:
    """Extracts product data directly from Trovaprezzi HTML"""

    def __init__(self):
        self.logger = setup_logging(__name__)

    def _parse_price(self, text: str) -> Optional[float]:
        """Extract price from text like '6,25 €' or '+ Sped. 4,90 €'"""
        match = re.search(r'(\d[\d.]*,\d{2})', text)
        if not match:
            return None
        price_str = match.group(1).replace('.', '').replace(',', '.')
        return float(price_str)

    def process_html(self, html_content: str, product_name: str, base_url: str) -> List[List[str]]:
        """Parse Trovaprezzi listing items from HTML"""
        soup = BeautifulSoup(html_content, 'html.parser')
        items = soup.select('li.listing_item')

        if not items:
            self.logger.warning(f"No listing items found for {product_name}")
            return []

        data = []
        for item in items:
            try:
                name_el = item.select_one('.item_name')
                price_el = item.select_one('.item_basic_price')
                shipping_el = item.select_one('.item_delivery_price')
                merchant_el = item.select_one('.merchant_name')
                link_el = item.select_one('a.listing_item_button')

                if not all([name_el, price_el, merchant_el]):
                    continue

                name = name_el.get_text(strip=True)
                price = self._parse_price(price_el.get_text())
                merchant = merchant_el.get_text(strip=True)

                if price is None:
                    self.logger.warning(f"Skipping item with unparseable price: {name}")
                    continue

                # Shipping: free if class contains 'free_shipping' or text says 'gratuita'
                shipping = 0.0
                if shipping_el:
                    shipping_text = shipping_el.get_text()
                    if 'free_shipping' in shipping_el.get('class', []) or 'gratuit' in shipping_text.lower():
                        shipping = 0.0
                    else:
                        parsed = self._parse_price(shipping_text)
                        if parsed is not None:
                            shipping = parsed

                # Vendor link
                link = ''
                if link_el and link_el.get('href'):
                    href = link_el['href']
                    link = href if href.startswith('http') else f"{base_url}{href}"

                data.append([
                    name,
                    f"{price:.2f}",
                    f"{shipping:.2f}",
                    merchant,
                    link,
                ])

            except Exception as e:
                self.logger.warning(f"Error parsing listing item: {e}")
                continue

        self.logger.info(f"Extracted {len(data)} offers for {product_name}")
        return data

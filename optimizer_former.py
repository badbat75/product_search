import pandas as pd
import os
import argparse
from typing import Dict, List, Tuple, Set, Optional
from dataclasses import dataclass
from pathlib import Path
import time
import sys
import re
import shutil
import itertools
from lib.utils import read_config, normalize_product_name, read_products
from lib.config import VAR_DATA_DIR, TEMPLATES_DIR, DEFAULT_MINIMUM_ORDER, DEFAULT_MAX_VENDOR_COMBINATIONS

@dataclass(frozen=True)
class Product:
    name: str
    price: float
    shipping: float
    vendor: str
    component_type: str
    url: str
    quantity: int = 1

    @property
    def total_price(self) -> float:
        return self.price * self.quantity

    @property
    def total_cost(self) -> float:
        return self.total_price + self.shipping

def get_best_product_for_component(products: List[Product], consider_shipping: bool = True) -> Product:
    """Get the best product from a list of products for the same component"""
    if consider_shipping:
        return min(products, key=lambda p: p.total_cost)
    return min(products, key=lambda p: p.total_price)

def print_order_table(vendor: str, products: Dict[str, Product], shipping_cost: float) -> None:
    col1_width = max(30, max(len(p.component_type) for p in products.values()))
    col2_width = 40
    col3_width = 8
    col4_width = 12

    print(f"\nOrdine da {vendor}")
    print("-" * (col1_width + col2_width + col3_width + col4_width + 6))
    
    header = (f"{'Componente':<{col1_width}} "
             f"{'Prodotto':<{col2_width}} "
             f"{'Qtà':>{col3_width}} "
             f"{'Prezzo':>{col4_width}}")
    print(header)
    print("-" * (col1_width + col2_width + col3_width + col4_width + 6))
    
    order_total = 0
    for component, product in sorted(products.items()):
        truncated_name = product.name[:40] if len(product.name) > 40 else product.name
        row = (f"{product.component_type:<{col1_width}} "
               f"{truncated_name:<{col2_width}} "
               f"{product.quantity:>{col3_width}} "
               f"€{product.total_price:>{10}.2f}")
        print(row)
        order_total += product.total_price
    
    print("-" * (col1_width + col2_width + col3_width + col4_width + 6))
    shipping_row = (f"{'Spese di spedizione':<{col1_width + col2_width + col3_width + 1}}"
                   f"€{shipping_cost:>{10}.2f}")
    print(shipping_row)
    
    print("-" * (col1_width + col2_width + col3_width + col4_width + 6))
    total_row = (f"{'TOTALE':<{col1_width + col2_width + col3_width + 1}}"
                 f"€{(order_total + shipping_cost):>{10}.2f}")
    print(total_row)
    print(f"(Totale prodotti senza spedizione: €{order_total:.2f})")
    print()

class PurchaseOptimizer:
    def __init__(self, input_file: str):
        self.input_file = input_file
        self.csv_folder = VAR_DATA_DIR
        self.products_by_component: Dict[str, List[Product]] = {}
        self.products_by_vendor: Dict[str, List[Product]] = {}
        self.required_components: Set[str] = set()
        self.excluded_components: Set[str] = set()
        self.project_name = Path(input_file).stem
        self.products = read_products(self.input_file)
        self.config = read_config()
        try:
            self.minimum_order = float(self.config['MINIMUM_ORDER'])
        except (KeyError, ValueError):
            self.minimum_order = DEFAULT_MINIMUM_ORDER
        try:
            self.max_vendor_combinations = int(self.config['MAX_VENDOR_COMBINATIONS'])
        except (KeyError, ValueError):
            self.max_vendor_combinations = DEFAULT_MAX_VENDOR_COMBINATIONS

    def _generate_orders_html(self, orders: Dict) -> str:
        """Generate HTML for orders section"""
        orders_html = ""
        for vendor, products in orders.items():
            shipping_cost = max(p.shipping for p in products.values())
            products_total = sum(p.total_price for p in products.values())
            order_total = products_total + shipping_cost
            
            orders_html += f"""
    <div class="order-card">
        <div class="vendor-header">
            <h2>Ordine da {vendor}</h2>
        </div>
        <table>
            <thead>
                <tr>
                    <th>Componente</th>
                    <th>Prodotto</th>
                    <th class="quantity">Qtà</th>
                    <th class="price">Prezzo</th>
                </tr>
            </thead>
            <tbody>"""
            
            for component, product in sorted(products.items()):
                orders_html += f"""
                <tr>
                    <td>{product.component_type}</td>
                    <td><a href="{product.url}" target="_blank">{product.name}</a></td>
                    <td class="quantity">{product.quantity}</td>
                    <td class="price">€{product.total_price:.2f}</td>
                </tr>"""
            
            orders_html += f"""
                <tr>
                    <td colspan="3">Spese di spedizione</td>
                    <td class="price">€{shipping_cost:.2f}</td>
                </tr>
                <tr class="total-row">
                    <td colspan="3">Totale ordine</td>
                    <td class="price">€{order_total:.2f}</td>
                </tr>
            </tbody>
        </table>
        <div class="subtotal">Totale prodotti senza spedizione: €{products_total:.2f}</div>
    </div>"""
        
        return orders_html

    def _read_html_template(self) -> str:
        """Read HTML template from file"""
        template_path = TEMPLATES_DIR / 'purchase_plan.html'
        try:
            return template_path.read_text(encoding='utf-8')
        except Exception as e:
            print(f"Error reading HTML template: {str(e)}")
            sys.exit(1)

    def _read_css_template(self) -> str:
        """Read CSS template from file"""
        css_path = TEMPLATES_DIR / 'style.css'
        try:
            css_content = css_path.read_text(encoding='utf-8')
            return f'<style>\n{css_content}\n</style>'
        except Exception as e:
            print(f"Error reading CSS template: {str(e)}")
            sys.exit(1)

    def _generate_html_content(self, total_cost: float, orders: Dict, execution_time: float) -> str:
        """Generate HTML content using template"""
        template = self._read_html_template()
        css_content = self._read_css_template()
        
        # Generate orders HTML
        orders_html = self._generate_orders_html(orders)
        
        # Fill template with data
        return template.format(
            css_content=css_content,
            num_components=len(self.required_components),
            execution_time=execution_time,
            minimum_order=self.minimum_order,
            excluded_components_count="",
            orders_html=orders_html,
            total_cost=total_cost,
            excluded_components_html=""
        )

    def load_data(self) -> None:
        print(f"Loading data for {len(self.products)} products...")
        
        # Process each product from the input file
        for product_name, quantity in self.products.items():
            try:
                quantity = int(quantity)
            except ValueError:
                print(f"Error: Invalid quantity for product '{product_name}': {quantity}")
                sys.exit(1)
                
            csv_filename = normalize_product_name(product_name) + '.csv'
            csv_path = self.csv_folder / csv_filename
            
            if not csv_path.exists():
                print(f"Error: CSV file not found for product: {product_name}")
                print(f"Expected path: {csv_path}")
                sys.exit(1)
            
            component_type = csv_path.stem
            self.required_components.add(component_type)
            
            try:
                df = pd.read_csv(csv_path)
                required_columns = {'nome_prodotto', 'prezzo', 'spedizione', 'venditore', 'link_venditore'}
                missing_columns = required_columns - set(df.columns)
                if missing_columns:
                    print(f"Error: Missing required columns in {csv_path}: {missing_columns}")
                    sys.exit(1)
                    
            except Exception as e:
                print(f"Error reading CSV file {csv_path}: {str(e)}")
                sys.exit(1)
            
            products = []
            for _, row in df.iterrows():
                try:
                    product = Product(
                        name=str(row['nome_prodotto']),
                        price=float(row['prezzo']),
                        shipping=float(row['spedizione']),
                        vendor=str(row['venditore']),
                        component_type=component_type,
                        url=str(row['link_venditore']),
                        quantity=quantity
                    )
                    products.append(product)
                    
                    if product.vendor not in self.products_by_vendor:
                        self.products_by_vendor[product.vendor] = []
                    self.products_by_vendor[product.vendor].append(product)
                except (ValueError, KeyError) as e:
                    print(f"Error processing row in {csv_path}: {str(e)}")
                    sys.exit(1)
            
            if not products:
                print(f"Warning: No valid products found in {csv_path}")
            
            self.products_by_component[component_type] = products

    def find_single_vendor_solution(self) -> Tuple[float, Optional[Dict[str, Dict[str, Product]]]]:
        """Try to find a solution using a single vendor for all components"""
        print("\nChecking single-vendor solutions...")
        best_cost = float('inf')
        best_vendor = None
        best_products = None
        
        for vendor in self.products_by_vendor:
            vendor_products = {}
            total = 0
            shipping = 0
            can_fulfill_all = True
            
            for component in self.required_components:
                vendor_options = [p for p in self.products_by_component[component] if p.vendor == vendor]
                if not vendor_options:
                    can_fulfill_all = False
                    break
                
                best_product = min(vendor_options, key=lambda p: p.total_price)
                vendor_products[component] = best_product
                total += best_product.total_price
                shipping = max(shipping, best_product.shipping)
            
            if can_fulfill_all and total >= self.minimum_order:
                total_cost = total + shipping
                if total_cost < best_cost:
                    best_cost = total_cost
                    best_vendor = vendor
                    best_products = vendor_products
        
        if best_vendor:
            print(f"\nFound single-vendor solution with {best_vendor}:")
            print_order_table(best_vendor, best_products, max(p.shipping for p in best_products.values()))
            print(f"Total cost: €{best_cost:.2f}")
            return best_cost, {best_vendor: best_products}
        
        print("No valid single-vendor solution found")
        return float('inf'), None

    def evaluate_vendor_group(self, vendor_group: List[str], components: Set[str]) -> Tuple[float, Optional[Dict[str, Dict[str, Product]]]]:
        """Evaluate a group of vendors for the given components"""
        orders = {}
        total_cost = 0
        components_covered = set()
        
        # Try to assign components to vendors optimally
        for component in components:
            best_cost = float('inf')
            best_vendor = None
            best_product = None
            
            for vendor in vendor_group:
                vendor_products = [p for p in self.products_by_component[component] if p.vendor == vendor]
                if vendor_products:
                    product = min(vendor_products, key=lambda p: p.total_price)
                    if product.total_price < best_cost:
                        best_cost = product.total_price
                        best_vendor = vendor
                        best_product = product
            
            if best_vendor:
                if best_vendor not in orders:
                    orders[best_vendor] = {}
                orders[best_vendor][component] = best_product
                components_covered.add(component)
        
        if components_covered != components:
            return float('inf'), None
            
        # Verify minimum order requirements and calculate total cost
        valid_orders = {}
        for vendor, products in orders.items():
            products_total = sum(p.total_price for p in products.values())
            if products_total >= self.minimum_order:
                shipping_cost = max(p.shipping for p in products.values())
                total_cost += products_total + shipping_cost
                valid_orders[vendor] = products
            else:
                return float('inf'), None
        
        return total_cost, valid_orders if valid_orders else None

    def find_optimal_solution(self) -> Tuple[float, Dict[str, Dict[str, Product]]]:
        """Find optimal solution by trying different vendor groupings"""
        print("\nFinding optimal solution...")
        best_cost = float('inf')
        best_orders = None
        
        # Get vendors that can fulfill at least one component
        capable_vendors = set()
        for component in self.required_components:
            for product in self.products_by_component[component]:
                capable_vendors.add(product.vendor)
        
        # Sort vendors by number of components they can fulfill
        vendor_capabilities = {}
        for vendor in capable_vendors:
            components = set()
            for component in self.required_components:
                if any(p.vendor == vendor for p in self.products_by_component[component]):
                    components.add(component)
            vendor_capabilities[vendor] = len(components)
        
        # Add early termination if we find a good enough solution
        # Consider a threshold like 10% above the best single vendor solution
        single_cost, _ = self.find_single_vendor_solution()
        early_termination_threshold = single_cost * 0.9 if single_cost < float('inf') else None
        
        sorted_vendors = sorted(capable_vendors, 
                              key=lambda v: (-vendor_capabilities[v], 
                                           min(p.shipping for p in self.products_by_vendor[v])))
        
        # Try different numbers of vendors, starting with smaller groups
        max_vendors = min(self.max_vendor_combinations, len(sorted_vendors))
        for num_vendors in range(1, max_vendors + 1):
            print(f"Trying combinations of {num_vendors} vendors...")
            
            # Calculate total combinations for progress reporting
            total_combinations = len(list(itertools.combinations(sorted_vendors, num_vendors)))
            print(f"Total combinations to evaluate: {total_combinations}")
            
            # Use a proper progress bar if available
            try:
                from tqdm import tqdm
                progress_bar = tqdm(total=total_combinations, desc=f"Evaluating {num_vendors} vendors")
                use_tqdm = True
            except ImportError:
                use_tqdm = False
                last_update_time = time.time()
                i = 0
            
            # Generate vendor combinations, prioritizing vendors that can fulfill more components
            for i, vendor_group in enumerate(itertools.combinations(sorted_vendors, num_vendors)):
                if use_tqdm:
                    progress_bar.update(1)
                else:
                    current_time = time.time()
                    # Update progress every 1 second on the same line
                    if current_time - last_update_time >= 1:
                        progress_percent = i/total_combinations*100 if total_combinations > 0 else 100
                        print(f"\rProgress: {i}/{total_combinations} combinations evaluated ({progress_percent:.1f}%)", end="", flush=True)
                        last_update_time = current_time
                
                # Skip vendor groups that can't cover all components (early pruning)
                covered_components = set()
                for vendor in vendor_group:
                    for component in self.required_components:
                        if any(p.vendor == vendor for p in self.products_by_component[component]):
                            covered_components.add(component)
                
                if covered_components != self.required_components:
                    continue
                
                cost, orders = self.evaluate_vendor_group(list(vendor_group), self.required_components)
                if orders and cost < best_cost:
                    best_cost = cost
                    best_orders = orders
                    print(f"\nFound better solution: €{best_cost:.2f}")
                    # Print the current best solution
                    print("\nCurrent best solution:")
                    for vendor, products in orders.items():
                        shipping_cost = max(p.shipping for p in products.values())
                        print_order_table(vendor, products, shipping_cost)
                    
                    # Early termination if we found a solution that's good enough
                    if early_termination_threshold and best_cost <= early_termination_threshold:
                        print(f"Found solution below threshold (€{early_termination_threshold:.2f}), stopping search.")
                        if use_tqdm:
                            progress_bar.close()
                        return best_cost, best_orders
            
            if use_tqdm:
                progress_bar.close()
            else:
                # Print final progress for this vendor count
                print(f"\rProgress: {total_combinations}/{total_combinations} combinations evaluated (100.0%)")
        
        if best_orders:
            print("\nBest multi-vendor solution found:")
            for vendor, products in best_orders.items():
                shipping_cost = max(p.shipping for p in products.values())
                print_order_table(vendor, products, shipping_cost)
            print(f"Total cost: €{best_cost:.2f}")
        else:
            print("No valid multi-vendor solution found")
            
        return best_cost, best_orders

    def optimize(self) -> Tuple[float, Dict[str, Dict[str, Product]]]:
        """Find the optimal purchase plan"""
        # First try single vendor solution
        single_cost, single_orders = self.find_single_vendor_solution()
        
        # Then try multi-vendor solution
        multi_cost, multi_orders = self.find_optimal_solution()
        
        # Return the better solution
        if single_cost < multi_cost:
            print("\nSingle-vendor solution is better!")
            return single_cost, single_orders
        elif multi_cost < float('inf'):
            print("\nMulti-vendor solution is better!")
            return multi_cost, multi_orders
        else:
            print("\nNo valid solution found.")
            print("\nSuggestion: Try to lower minimum order costs to 0 in search.cfg and see if this solves the problem.")
            return float('inf'), None
    
    def generate_purchase_plan(self) -> None:
        print("=== Piano di Acquisto Ottimale ===")
        print(f"Numero di componenti da acquistare: {len(self.required_components)}")
        print(f"Ordine minimo per venditore: €{self.minimum_order:.2f} (esclusa spedizione)")
        print(f"Numero massimo di venditori da combinare: {self.max_vendor_combinations}")
        
        start_time = time.time()
        try:
            total_cost, orders = self.optimize()
            end_time = time.time()
            execution_time = end_time - start_time
            
            if orders:
                print("\nSoluzione finale:")
                for vendor, products in orders.items():
                    shipping_cost = max(p.shipping for p in products.values())
                    print_order_table(vendor, products, shipping_cost)
                
                print("=" * 80)
                print(f"Costo Totale Finale: €{total_cost:>.2f}")
                print(f"Tempo di elaborazione: {execution_time:.2f} secondi")
                print("=" * 80)
                
                # Generate HTML report
                html_content = self._generate_html_content(total_cost, orders, execution_time)
                html_filename = f"{self.project_name}_purchase_plan.html"
                
                # Write HTML file
                with open(html_filename, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                print(f"\nReport HTML generato in '{html_filename}'")
                
                # Open the HTML file in the default web browser
                import webbrowser
                html_path = os.path.abspath(html_filename)
                print(f"Apertura del report nel browser predefinito...")
                webbrowser.open(f'file://{html_path}')
                
        except KeyboardInterrupt:
            print("\nOptimization interrupted by user.")
            sys.exit(1)
        except Exception as e:
            print(f"Error during optimization: {str(e)}")
            sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description='Optimize purchase plan from product data'
    )
    parser.add_argument(
        'input_file',
        type=str,
        help='Input file with shopping list (e.g., farmacia.txt, list.csv)'
    )
    
    args = parser.parse_args()
    optimizer = PurchaseOptimizer(args.input_file)
    optimizer.load_data()
    optimizer.generate_purchase_plan()

if __name__ == "__main__":
    main()

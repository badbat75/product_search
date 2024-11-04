import pandas as pd
import os
import argparse
from typing import Dict, List, Tuple, Set
from dataclasses import dataclass
from pathlib import Path
import multiprocessing as mp
import numpy as np
import time
import sys
import re
import shutil
from utils import read_config, normalize_product_name, read_products
from config import VAR_DATA_DIR, TEMPLATES_DIR, DEFAULT_MINIMUM_ORDER
from itertools import combinations, product
from concurrent.futures import TimeoutError
from functools import partial

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

def evaluate_assignments_chunk(chunk_data: Tuple[List[Tuple], Dict, Set, float], timeout: int = 60) -> Tuple[float, Dict]:
    assignments, products_by_vendor, required_components, minimum_order = chunk_data
    best_cost = float('inf')
    best_orders = None
    best_shipping_cost = float('inf')
    
    start_time = time.time()
    
    for assignment in assignments:
        # Check timeout
        if time.time() - start_time > timeout:
            print(f"Chunk evaluation timed out after {timeout} seconds")
            return best_cost, best_orders
            
        orders = {}
        total_cost = 0
        total_shipping = 0
        components_covered = set()
        
        # Group products by vendor
        for component, vendor in assignment:
            if vendor not in orders:
                orders[vendor] = {}
            
            vendor_products = [p for p in products_by_vendor[vendor] if p.component_type == component]
            if vendor_products:
                best_product = get_best_product_for_component(vendor_products)
                orders[vendor][component] = best_product
                components_covered.add(component)
        
        if components_covered != required_components:
            continue

        # Check minimum order requirements and calculate total cost
        valid_orders = {}
        for vendor, products in orders.items():
            products_total = sum(p.total_price for p in products.values())
            if products_total >= minimum_order:
                shipping_cost = max(p.shipping for p in products.values())
                total_cost += products_total + shipping_cost
                total_shipping += shipping_cost
                valid_orders[vendor] = products
            else:
                # Try to find another vendor that can fulfill these products
                best_alt_vendor = None
                best_alt_cost = float('inf')
                best_alt_products = None
                best_alt_shipping = float('inf')
                
                for alt_vendor, vendor_products in products_by_vendor.items():
                    if alt_vendor == vendor:
                        continue
                        
                    alt_products = {}
                    alt_total = 0
                    valid = True
                    
                    for component in products:
                        alt_vendor_products = [p for p in vendor_products if p.component_type == component]
                        if alt_vendor_products:
                            best_alt_product = get_best_product_for_component(alt_vendor_products)
                            alt_products[component] = best_alt_product
                            alt_total += best_alt_product.total_price
                        else:
                            valid = False
                            break
                    
                    if valid and alt_total >= minimum_order:
                        alt_shipping = max(p.shipping for p in alt_products.values())
                        alt_cost = alt_total + alt_shipping
                        if alt_cost < best_alt_cost or (alt_cost == best_alt_cost and alt_shipping < best_alt_shipping):
                            best_alt_cost = alt_cost
                            best_alt_shipping = alt_shipping
                            best_alt_vendor = alt_vendor
                            best_alt_products = alt_products
                
                if best_alt_vendor:
                    total_cost += best_alt_cost
                    total_shipping += best_alt_shipping
                    valid_orders[best_alt_vendor] = best_alt_products
                else:
                    total_cost = float('inf')
                    total_shipping = float('inf')
                    break
        
        # Prioritize solutions with lower total cost, using shipping as a tiebreaker
        if total_cost < best_cost or (total_cost == best_cost and total_shipping < best_shipping_cost):
            best_cost = total_cost
            best_shipping_cost = total_shipping
            best_orders = valid_orders
    
    return best_cost, best_orders

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
        
        # Add timeout and max combinations settings
        self.timeout = 300  # 5 minutes timeout
        self.max_combinations = 1000000  # Limit number of combinations to prevent memory issues

    def _print_order_table(self, vendor: str, products: Dict[str, Product], shipping_cost: float) -> None:
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

    def _generate_excluded_components_html(self) -> str:
        """Generate HTML for excluded components section"""
        if not self.excluded_components:
            return ""
            
        excluded_html = """
    <div class="excluded">
        <h3>Componenti Esclusi</h3>
        <p>I seguenti componenti sono stati esclusi perché non è stato possibile raggrupparli per raggiungere l'ordine minimo:</p>
        <ul>"""
            
        for component in sorted(self.excluded_components):
            excluded_html += f"""
            <li>{component}</li>"""
            
        excluded_html += """
        </ul>
    </div>"""
        
        return excluded_html

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
            return css_path.read_text(encoding='utf-8')
        except Exception as e:
            print(f"Error reading CSS template: {str(e)}")
            sys.exit(1)

    def _generate_html_content(self, total_cost: float, orders: Dict, execution_time: float) -> str:
        """Generate HTML content using template"""
        template = self._read_html_template()
        css_content = self._read_css_template()
        
        # Generate excluded components count HTML
        excluded_count_html = ""
        if self.excluded_components:
            excluded_count_html = f"""
        <p style="color: #e74c3c;">Componenti esclusi: {len(self.excluded_components)}</p>"""
        
        # Generate orders and excluded components HTML
        orders_html = self._generate_orders_html(orders)
        excluded_components_html = self._generate_excluded_components_html()
        
        # Fill template with data
        return template.format(
            css_content=css_content,
            num_components=len(self.required_components),
            execution_time=execution_time,
            minimum_order=self.minimum_order,
            excluded_components_count=excluded_count_html,
            orders_html=orders_html,
            total_cost=total_cost,
            excluded_components_html=excluded_components_html
        )

    def load_data(self) -> None:
        # Process each product from the input file
        for product_name, quantity in self.products.items():
            try:
                quantity = int(quantity)  # Ensure quantity is an integer
            except ValueError:
                print(f"Error: Invalid quantity for product '{product_name}': {quantity}")
                print("Quantities must be integers. Please check your input file.")
                sys.exit(1)
                
            # Convert product name to CSV filename
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
                    print(f"Row data: {row.to_dict()}")
                    sys.exit(1)
            
            if not products:
                print(f"Warning: No valid products found in {csv_path}")
            
            self.products_by_component[component_type] = products

    def find_single_vendor_solution(self) -> Tuple[float, Dict[str, Dict[str, Product]]]:
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
            print(f"Found valid single-vendor solution with {best_vendor}")
            return best_cost, {best_vendor: best_products}
        
        print("No valid single-vendor solution found")
        return float('inf'), None

    def find_optimal_combination(self, components_to_try: Set[str]) -> Tuple[float, Dict]:
        if not components_to_try:
            print("Error: No components to optimize.")
            sys.exit(1)
            
        # Get all vendors that can fulfill at least one component
        vendor_capabilities = {}
        for vendor in self.products_by_vendor:
            components = set()
            total_cost = 0
            for component in components_to_try:
                vendor_products = [p for p in self.products_by_component[component] if p.vendor == vendor]
                if vendor_products:
                    components.add(component)
                    best_product = get_best_product_for_component(vendor_products)
                    total_cost += best_product.total_cost
            if components:
                avg_cost = total_cost / len(components)
                vendor_capabilities[vendor] = (len(components), -avg_cost)  # Negative cost for reverse sorting
        
        # Sort vendors by number of components they can fulfill and average cost
        sorted_vendors = sorted(vendor_capabilities.items(), 
                              key=lambda x: x[1], 
                              reverse=True)
        
        # Create all possible component-vendor assignments, prioritizing efficient vendors
        assignments = []
        for component in components_to_try:
            component_vendors = []
            for vendor, _ in sorted_vendors:
                if any(p.vendor == vendor for p in self.products_by_component[component]):
                    component_vendors.append((component, vendor))
            assignments.append(component_vendors)
        
        # Generate all possible combinations
        all_combinations = list(product(*assignments))
        num_combinations = len(all_combinations)
        
        if num_combinations == 0:
            return float('inf'), None
            
        if num_combinations > self.max_combinations:
            print(f"Warning: Large number of combinations ({num_combinations}). This might take a while...")
            print("Consider reducing the number of components or vendors if the process is too slow.")
            all_combinations = all_combinations[:self.max_combinations]
        
        num_cores = min(mp.cpu_count(), 8)  # Limit max cores to prevent excessive CPU usage
        chunk_size = max(1, len(all_combinations) // num_cores)
        chunks = [all_combinations[i:i + chunk_size] for i in range(0, len(all_combinations), chunk_size)]
        
        chunk_data = [(chunk, self.products_by_vendor, components_to_try, self.minimum_order) for chunk in chunks]
        
        best_cost = float('inf')
        best_orders = None
        
        try:
            with mp.Pool(processes=num_cores) as pool:
                results = []
                for i, result in enumerate(pool.imap_unordered(evaluate_assignments_chunk, chunk_data)):
                    results.append(result)
                    print(f"Progress: {i+1}/{len(chunks)} chunks processed")
                    
                    cost, orders = result
                    if cost and cost < best_cost:
                        best_cost = cost
                        best_orders = orders
                        
        except TimeoutError:
            print("Warning: Optimization timed out. Using best result found so far.")
        except Exception as e:
            print(f"Error during optimization: {str(e)}")
            if best_orders is None:
                sys.exit(1)
        
        return best_cost, best_orders

    def optimize_with_exclusions(self) -> Tuple[float, Dict]:
        # First try single-vendor solution
        single_vendor_cost, single_vendor_orders = self.find_single_vendor_solution()
        
        # Then try multi-vendor solution
        print("\nTrying multi-vendor optimization...")
        multi_vendor_cost, multi_vendor_orders = self.find_optimal_combination(self.required_components)
        
        # Compare solutions
        if single_vendor_cost < multi_vendor_cost:
            print("\nSingle-vendor solution is better!")
            return single_vendor_cost, single_vendor_orders
        elif multi_vendor_orders:
            print("\nMulti-vendor solution is better!")
            return multi_vendor_cost, multi_vendor_orders
            
        # If no complete solution found, try removing components
        components_to_try = self.required_components.copy()
        best_cost = float('inf')
        best_orders = None
        
        while components_to_try and not best_orders:
            print(f"\nTrying optimization with {len(components_to_try)} components...")
            cost, orders = self.find_optimal_combination(components_to_try)
            if orders:
                best_cost = cost
                best_orders = orders
                break
            
            # No solution found, try removing components that are harder to group
            component_values = {}
            for comp in components_to_try:
                vendors = set(p.vendor for p in self.products_by_component[comp])
                best_product = get_best_product_for_component(self.products_by_component[comp])
                # Score based on total cost and vendor availability
                component_values[comp] = best_product.total_cost / len(vendors)
            
            component_to_remove = max(component_values.items(), key=lambda x: x[1])[0]
            components_to_try.remove(component_to_remove)
            self.excluded_components.add(component_to_remove)
            print(f"Excluding component: {component_to_remove}")
        
        if not best_orders:
            print("Error: Could not find any valid solution even after excluding components.")
            sys.exit(1)
            
        return best_cost, best_orders
    
    def generate_purchase_plan(self) -> None:
        print("=== Piano di Acquisto Ottimale ===")
        print(f"Numero di CPU utilizzate: {min(mp.cpu_count(), 8)}")
        print(f"Numero di componenti da acquistare: {len(self.required_components)}")
        print(f"Ordine minimo per venditore: €{self.minimum_order:.2f} (esclusa spedizione)")
        
        start_time = time.time()
        try:
            total_cost, orders = self.optimize_with_exclusions()
            end_time = time.time()
            execution_time = end_time - start_time
            
            if self.excluded_components:
                print("\nComponenti esclusi:")
                for component in sorted(self.excluded_components):
                    print(f"- {component}")
                print()
            
            if orders:
                for vendor, products in orders.items():
                    shipping_cost = max(p.shipping for p in products.values())
                    self._print_order_table(vendor, products, shipping_cost)
                
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

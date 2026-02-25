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

        self._prepare_lookups()

    def _prepare_lookups(self) -> None:
        """Pre-compute lookup tables for efficient optimization"""
        # (component, vendor) -> cheapest Product by total_cost
        self.best_product_lookup: Dict[Tuple[str, str], Product] = {}
        for component, products in self.products_by_component.items():
            for p in products:
                key = (component, p.vendor)
                if key not in self.best_product_lookup or p.total_cost < self.best_product_lookup[key].total_cost:
                    self.best_product_lookup[key] = p

        # vendor -> set of components they carry
        self.vendor_coverage: Dict[str, Set[str]] = {}
        for (component, vendor) in self.best_product_lookup:
            if vendor not in self.vendor_coverage:
                self.vendor_coverage[vendor] = set()
            self.vendor_coverage[vendor].add(component)

        # component -> absolute cheapest total_cost across all vendors
        self.cheapest_per_component: Dict[str, float] = {}
        for component in self.required_components:
            self.cheapest_per_component[component] = min(
                self.best_product_lookup[(component, v)].total_cost
                for v in self.vendor_coverage
                if (component, v) in self.best_product_lookup
            )
        self.absolute_lower_bound = sum(self.cheapest_per_component.values())

        # Vendors sorted by coverage desc, min shipping asc
        self.capable_vendors = sorted(
            self.vendor_coverage.keys(),
            key=lambda v: (
                -len(self.vendor_coverage[v]),
                min(self.best_product_lookup[(c, v)].shipping for c in self.vendor_coverage[v])
            )
        )

        # Filter out dominated vendors
        self._filter_dominated_vendors()

    def _filter_dominated_vendors(self) -> None:
        """Remove vendors strictly dominated by another vendor (same or worse on all components)"""
        non_dominated = []
        for v in self.capable_vendors:
            dominated = False
            for other in self.capable_vendors:
                if other == v:
                    continue
                if self.vendor_coverage[v].issubset(self.vendor_coverage[other]):
                    all_cheaper = all(
                        self.best_product_lookup[(c, other)].total_cost <= self.best_product_lookup[(c, v)].total_cost
                        for c in self.vendor_coverage[v]
                    )
                    if all_cheaper:
                        dominated = True
                        break
            if not dominated:
                non_dominated.append(v)

        # Only use filtered list if it can still cover all components
        filtered_coverage = set()
        for v in non_dominated:
            filtered_coverage |= self.vendor_coverage[v]
        if self.required_components.issubset(filtered_coverage):
            self.capable_vendors = non_dominated

    def evaluate_vendor_group(self, vendor_group: List[str], components: Set[str]) -> Tuple[float, Optional[Dict[str, Dict[str, Product]]]]:
        """Evaluate a group of vendors for the given components"""
        orders: Dict[str, Dict[str, Product]] = {}

        # Phase 1: Greedy assignment using pre-computed lookups
        for component in components:
            best_cost = float('inf')
            best_vendor = None
            best_product = None

            for vendor in vendor_group:
                key = (component, vendor)
                if key in self.best_product_lookup:
                    product = self.best_product_lookup[key]
                    if product.total_cost < best_cost:
                        best_cost = product.total_cost
                        best_vendor = vendor
                        best_product = product

            if best_vendor is None:
                return float('inf'), None

            if best_vendor not in orders:
                orders[best_vendor] = {}
            orders[best_vendor][component] = best_product

        # Phase 2: Repair minimum order violations
        for _ in range(len(components)):
            failing_vendors = []
            for vendor, products in orders.items():
                vendor_total = sum(p.total_price for p in products.values())
                if vendor_total < self.minimum_order:
                    failing_vendors.append((vendor, vendor_total))

            if not failing_vendors:
                break

            repaired = False
            for failing_vendor, failing_total in failing_vendors:
                best_swap = None  # (component, donor_vendor, cost_delta)

                for donor_vendor, donor_products in orders.items():
                    if donor_vendor == failing_vendor:
                        continue
                    donor_total = sum(p.total_price for p in donor_products.values())

                    for component in list(donor_products.keys()):
                        key = (component, failing_vendor)
                        if key not in self.best_product_lookup:
                            continue

                        replacement = self.best_product_lookup[key]
                        donor_product = donor_products[component]
                        new_donor_total = donor_total - donor_product.total_price
                        new_failing_total = failing_total + replacement.total_price

                        # Donor becomes empty — ok if failing vendor gets enough
                        if len(donor_products) <= 1:
                            if new_failing_total < self.minimum_order:
                                continue
                        else:
                            if new_donor_total < self.minimum_order:
                                continue

                        cost_delta = replacement.total_cost - donor_product.total_cost
                        if best_swap is None or cost_delta < best_swap[2]:
                            best_swap = (component, donor_vendor, cost_delta)

                if best_swap:
                    component, donor_vendor, _ = best_swap
                    replacement = self.best_product_lookup[(component, failing_vendor)]
                    del orders[donor_vendor][component]
                    orders[failing_vendor][component] = replacement
                    if not orders[donor_vendor]:
                        del orders[donor_vendor]
                    repaired = True

            if not repaired:
                break

        # Final validation and cost calculation
        total_cost = 0.0
        for vendor, products in orders.items():
            products_total = sum(p.total_price for p in products.values())
            if products_total < self.minimum_order:
                return float('inf'), None
            shipping_cost = max(p.shipping for p in products.values())
            total_cost += products_total + shipping_cost

        return total_cost, orders if orders else None

    def find_optimal_solution(self) -> Tuple[float, Optional[Dict[str, Dict[str, Product]]]]:
        """Find optimal solution by trying different vendor groupings"""
        print("\nFinding optimal solution...")
        best_cost = float('inf')
        best_orders = None
        combinations_tried = 0
        combinations_skipped = 0

        max_vendors = min(self.max_vendor_combinations, len(self.capable_vendors))
        for num_vendors in range(1, max_vendors + 1):
            print(f"Trying combinations of {num_vendors} vendors...")

            for vendor_group in itertools.combinations(self.capable_vendors, num_vendors):
                # Coverage pre-check: can this group cover all required components?
                combined_coverage = set()
                for v in vendor_group:
                    combined_coverage |= self.vendor_coverage[v]
                if not self.required_components.issubset(combined_coverage):
                    combinations_skipped += 1
                    continue

                # Lower-bound pruning: cheapest possible cost from this group
                lower_bound = 0.0
                for component in self.required_components:
                    cheapest_in_group = float('inf')
                    for v in vendor_group:
                        key = (component, v)
                        if key in self.best_product_lookup:
                            cost = self.best_product_lookup[key].total_cost
                            if cost < cheapest_in_group:
                                cheapest_in_group = cost
                    lower_bound += cheapest_in_group

                if lower_bound >= best_cost:
                    combinations_skipped += 1
                    continue

                combinations_tried += 1
                cost, orders = self.evaluate_vendor_group(list(vendor_group), self.required_components)
                if orders and cost < best_cost:
                    best_cost = cost
                    best_orders = orders
                    print(f"Found better solution: €{best_cost:.2f}")
                    print("\nCurrent best solution:")
                    for vendor, products in orders.items():
                        shipping_cost = max(p.shipping for p in products.values())
                        print_order_table(vendor, products, shipping_cost)

            # Early termination: if within 5% of theoretical minimum, skip larger groups
            if best_cost <= self.absolute_lower_bound * 1.05:
                print(f"Solution within 5% of theoretical minimum, skipping larger groups")
                break

        print(f"\nCombinations evaluated: {combinations_tried}, skipped: {combinations_skipped}")

        if best_orders:
            print(f"\nBest solution found: €{best_cost:.2f}")
            for vendor, products in best_orders.items():
                shipping_cost = max(p.shipping for p in products.values())
                print_order_table(vendor, products, shipping_cost)
        else:
            print("No valid solution found")

        return best_cost, best_orders

    def optimize(self) -> Tuple[float, Optional[Dict[str, Dict[str, Product]]]]:
        """Find the optimal purchase plan"""
        cost, orders = self.find_optimal_solution()

        if cost < float('inf') and orders:
            num_vendors = len(orders)
            if num_vendors == 1:
                print("\nBest solution uses a single vendor!")
            else:
                print(f"\nBest solution uses {num_vendors} vendors.")
            return cost, orders
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

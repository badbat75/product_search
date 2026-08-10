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
import pulp
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
        self.vendor_minimum_orders = self._parse_vendor_minimum_orders()

    def _parse_vendor_minimum_orders(self) -> Dict[str, float]:
        """Parse per-vendor minimum order overrides from config"""
        vendor_mins = {}
        raw = self.config.get('VENDOR_MINIMUM_ORDERS', '').strip()
        if not raw:
            return vendor_mins
        for entry in raw.split(','):
            entry = entry.strip()
            if ':' not in entry:
                continue
            vendor_name, amount_str = entry.rsplit(':', 1)
            try:
                vendor_mins[vendor_name.strip()] = float(amount_str.strip())
            except ValueError:
                print(f"Warning: Invalid vendor minimum order entry: {entry}")
        return vendor_mins

    def get_minimum_order(self, vendor: str) -> float:
        """Get the minimum order for a specific vendor"""
        return self.vendor_minimum_orders.get(vendor, self.minimum_order)

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

        # Generate per-vendor minimum orders HTML
        vendor_min_html = ""
        if self.vendor_minimum_orders:
            for vendor, min_order in sorted(self.vendor_minimum_orders.items()):
                vendor_min_html += f"<p>Ordine minimo per {vendor}: €{min_order:.2f}</p>\n        "

        # Fill template with data
        return template.format(
            css_content=css_content,
            num_components=len(self.required_components),
            execution_time=execution_time,
            minimum_order=self.minimum_order,
            vendor_minimum_orders_html=vendor_min_html,
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
                except (ValueError, KeyError) as e:
                    print(f"Error processing row in {csv_path}: {str(e)}")
                    sys.exit(1)
            
            if not products:
                print(f"Warning: No valid products found in {csv_path}")

            self.products_by_component[component_type] = products

    def find_optimal_solution(self) -> Tuple[float, Optional[Dict[str, Dict[str, Product]]]]:
        """Find the optimal purchase plan by solving a mixed-integer linear program.

        Model (solved exactly by CBC):
            x[p] ∈ {0,1}   offer p is purchased
            y[v] ∈ {0,1}   vendor v is used
            s[v] ≥ 0       shipping charged by vendor v

            minimize    Σ total_price(p)·x[p] + Σ s[v]
            subject to  Σ x[p] = 1                 over offers of each component
                        x[p] ≤ y[vendor(p)]
                        s[v] ≥ shipping(p)·x[p]    for each offer p of vendor v
                        Σ total_price(p)·x[p] ≥ minimum_order(v)·y[v]   per vendor
                        Σ y[v] ≤ max_vendor_combinations
        """
        print("\nFinding optimal solution...")

        missing = sorted(c for c in self.required_components if not self.products_by_component.get(c))
        if missing:
            print(f"No offers available for: {', '.join(missing)}")
            return float('inf'), None

        # Flat list of all offers; index into it is the x-variable key
        offers: List[Tuple[str, Product]] = [
            (component, product)
            for component, products in sorted(self.products_by_component.items())
            for product in products
        ]
        vendors = sorted({product.vendor for _, product in offers})
        vendor_index = {vendor: j for j, vendor in enumerate(vendors)}
        print(f"Solving MILP: {len(offers)} offers, {len(vendors)} vendors, {len(self.required_components)} components")

        prob = pulp.LpProblem("purchase_plan", pulp.LpMinimize)
        x = [pulp.LpVariable(f"x_{i}", cat="Binary") for i in range(len(offers))]
        y = [pulp.LpVariable(f"y_{j}", cat="Binary") for j in range(len(vendors))]
        s = [pulp.LpVariable(f"s_{j}", lowBound=0) for j in range(len(vendors))]

        prob += (
            pulp.lpSum(product.total_price * x[i] for i, (_, product) in enumerate(offers))
            + pulp.lpSum(s)
        )

        offers_by_component: Dict[str, List[int]] = {}
        offers_by_vendor: Dict[str, List[int]] = {}
        for i, (component, product) in enumerate(offers):
            offers_by_component.setdefault(component, []).append(i)
            offers_by_vendor.setdefault(product.vendor, []).append(i)

        # Exactly one offer per required component
        for component, indices in offers_by_component.items():
            prob += pulp.lpSum(x[i] for i in indices) == 1

        for vendor, indices in offers_by_vendor.items():
            j = vendor_index[vendor]
            for i in indices:
                # Buying an offer marks its vendor as used and sets the
                # order's shipping to the max over the chosen offers
                prob += x[i] <= y[j]
                prob += s[j] >= offers[i][1].shipping * x[i]

            vendor_min = self.get_minimum_order(vendor)
            if vendor_min > 0:
                prob += (
                    pulp.lpSum(offers[i][1].total_price * x[i] for i in indices)
                    >= vendor_min * y[j]
                )

        prob += pulp.lpSum(y) <= self.max_vendor_combinations

        status = prob.solve(pulp.PULP_CBC_CMD(msg=False))
        if pulp.LpStatus[status] != 'Optimal':
            print(f"Solver finished with status: {pulp.LpStatus[status]}")
            return float('inf'), None

        orders: Dict[str, Dict[str, Product]] = {}
        for i, (component, product) in enumerate(offers):
            if x[i].value() > 0.5:
                orders.setdefault(product.vendor, {})[component] = product

        # Recompute the cost from the solution (avoids solver float noise)
        total_cost = sum(
            sum(p.total_price for p in products.values()) + max(p.shipping for p in products.values())
            for products in orders.values()
        )

        print(f"\nOptimal solution found: €{total_cost:.2f}")
        return total_cost, orders

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
            print("\nSuggestion: Try to lower minimum order costs to 0 or raise MAX_VENDOR_COMBINATIONS in search.cfg and see if this solves the problem.")
            return float('inf'), None
    
    def generate_purchase_plan(self) -> None:
        print("=== Piano di Acquisto Ottimale ===")
        print(f"Numero di componenti da acquistare: {len(self.required_components)}")
        print(f"Ordine minimo default: €{self.minimum_order:.2f} (esclusa spedizione)")
        if self.vendor_minimum_orders:
            for vendor, min_order in sorted(self.vendor_minimum_orders.items()):
                print(f"  Ordine minimo per {vendor}: €{min_order:.2f}")
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

import pandas as pd
import os
import argparse
from typing import Dict, List, Tuple, Set
from dataclasses import dataclass
from pathlib import Path
from itertools import combinations, product
import multiprocessing as mp
import numpy as np
import time
import sys
import re
from utils import read_config, normalize_product_name, read_products

# Minimum order value required by vendors (excluding shipping)
MINIMUM_ORDER = float(read_config(['MINIMUM_ORDER'])['MINIMUM_ORDER'])

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

@dataclass(frozen=True)
class Order:
    vendor: str
    products: Dict[str, Product]
    shipping_cost: float
    
    @property
    def total_price(self) -> float:
        return sum(p.total_price for p in self.products.values()) + self.shipping_cost
    
    @property
    def products_price(self) -> float:
        """Total price of products only, excluding shipping"""
        return sum(p.total_price for p in self.products.values())

def evaluate_assignments_chunk(chunk_data: Tuple[List[Tuple], Dict, Set]) -> Tuple[float, List[Dict]]:
    assignments, products_by_vendor, required_components = chunk_data
    best_cost = float('inf')
    best_orders = None
    
    for assignment in assignments:
        vendor_assignments = dict(assignment)
        orders = {}
        total_cost = 0
        components_covered = set()
        
        # First pass: Create initial orders
        for component, vendor in vendor_assignments.items():
            if vendor not in orders:
                orders[vendor] = {}
            
            vendor_products = [p for p in products_by_vendor[vendor] if p.component_type == component]
            if vendor_products:
                best_product = min(vendor_products, key=lambda p: p.total_price)
                orders[vendor][component] = best_product
                components_covered.add(component)
        
        if components_covered != required_components:
            continue

        # Second pass: Check for minimum order requirements and regroup if needed
        regrouped_orders = {}
        pending_components = set()

        for vendor, products in orders.items():
            products_total = sum(p.total_price for p in products.values())  # Exclude shipping from minimum check
            
            if products_total >= MINIMUM_ORDER:
                # Order meets minimum requirement, keep as is
                regrouped_orders[vendor] = products
            else:
                # Order doesn't meet minimum, add components to pending
                for component, product in products.items():
                    pending_components.add(component)

        # Try to regroup pending components
        if pending_components:
            # Find vendors who can fulfill all pending components
            capable_vendors = set()
            for vendor, vendor_products in products_by_vendor.items():
                can_fulfill_all = True
                for component in pending_components:
                    if not any(p.component_type == component for p in vendor_products):
                        can_fulfill_all = False
                        break
                if can_fulfill_all:
                    capable_vendors.add(vendor)

            if capable_vendors:
                # Find vendor with lowest total cost for pending components
                best_regroup_cost = float('inf')
                best_regroup_vendor = None
                best_regroup_products = None

                for vendor in capable_vendors:
                    regroup_products = {}
                    total = 0
                    valid = True

                    for component in pending_components:
                        vendor_products = [p for p in products_by_vendor[vendor] 
                                         if p.component_type == component]
                        if vendor_products:
                            best_product = min(vendor_products, key=lambda p: p.total_price)
                            regroup_products[component] = best_product
                            total += best_product.total_price
                        else:
                            valid = False
                            break

                    if valid:
                        products_total = sum(p.total_price for p in regroup_products.values())  # Exclude shipping from minimum check
                        if products_total >= MINIMUM_ORDER:
                            shipping = max(p.shipping for p in regroup_products.values())
                            total_cost = products_total + shipping
                            if total_cost < best_regroup_cost:
                                best_regroup_cost = total_cost
                                best_regroup_vendor = vendor
                                best_regroup_products = regroup_products

                if best_regroup_vendor:
                    regrouped_orders[best_regroup_vendor] = best_regroup_products
                else:
                    continue  # Skip this assignment if regrouping failed
            else:
                continue  # Skip this assignment if no vendor can fulfill all pending components

        # Calculate total cost for regrouped orders
        total_cost = 0
        for vendor, products in regrouped_orders.items():
            shipping_cost = max(p.shipping for p in products.values())
            total_cost += sum(p.total_price for p in products.values()) + shipping_cost
        
        if total_cost < best_cost:
            best_cost = total_cost
            best_orders = regrouped_orders
    
    return best_cost, best_orders

class PurchaseOptimizer:
    def __init__(self, input_file: str):
        self.input_file = f"{input_file}.txt"
        self.csv_folder = Path(input_file)
        self.products_by_component: Dict[str, List[Product]] = {}
        self.products_by_vendor: Dict[str, List[Product]] = {}
        self.required_components: Set[str] = set()
        self.excluded_components: Set[str] = set()
        self.project_name = input_file
        self.products = read_products(self.input_file)

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

    def _generate_html_content(self, total_cost: float, orders: Dict, execution_time: float) -> str:
        html_content = f"""
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Piano di Acquisto Ottimale</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .header {{
            background-color: #2c3e50;
            color: white;
            padding: 20px;
            border-radius: 5px;
            margin-bottom: 20px;
        }}
        .order-card {{
            background-color: white;
            border-radius: 5px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .vendor-header {{
            background-color: #34495e;
            color: white;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 15px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 15px;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #f8f9fa;
        }}
        .price {{
            text-align: right;
            font-family: monospace;
        }}
        .quantity {{
            text-align: right;
            font-family: monospace;
        }}
        .total-row {{
            font-weight: bold;
            background-color: #f8f9fa;
        }}
        .final-total {{
            background-color: #2c3e50;
            color: white;
            padding: 20px;
            border-radius: 5px;
            margin-top: 20px;
            font-size: 1.2em;
        }}
        .excluded {{
            background-color: #e74c3c;
            color: white;
            padding: 20px;
            border-radius: 5px;
            margin-top: 20px;
        }}
        a {{
            color: #3498db;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        .subtotal {{
            font-size: 0.9em;
            color: #666;
            margin-top: 5px;
            text-align: right;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Piano di Acquisto Ottimale</h1>
        <p>Numero di componenti da acquistare: {len(self.required_components)}</p>
        <p>Tempo di elaborazione: {execution_time:.2f} secondi</p>
        <p>Ordine minimo per venditore: €{MINIMUM_ORDER:.2f} (esclusa spedizione)</p>
"""
        if self.excluded_components:
            html_content += f"""
        <p style="color: #e74c3c;">Componenti esclusi: {len(self.excluded_components)}</p>
"""
        html_content += """
    </div>
"""
        
        for vendor, products in orders.items():
            shipping_cost = max(p.shipping for p in products.values())
            products_total = sum(p.total_price for p in products.values())
            order_total = products_total + shipping_cost
            
            html_content += f"""
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
            <tbody>
"""
            
            for component, product in sorted(products.items()):
                html_content += f"""
                <tr>
                    <td>{product.component_type}</td>
                    <td><a href="{product.url}" target="_blank">{product.name}</a></td>
                    <td class="quantity">{product.quantity}</td>
                    <td class="price">€{product.total_price:.2f}</td>
                </tr>
"""
            
            html_content += f"""
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
    </div>
"""

        html_content += f"""
    <div class="final-total">
        <h2>Costo Totale Finale: €{total_cost:.2f}</h2>
    </div>
"""

        if self.excluded_components:
            html_content += f"""
    <div class="excluded">
        <h3>Componenti Esclusi</h3>
        <p>I seguenti componenti sono stati esclusi perché non è stato possibile raggrupparli per raggiungere l'ordine minimo:</p>
        <ul>
"""
            for component in sorted(self.excluded_components):
                html_content += f"""
            <li>{component}</li>
"""
            html_content += """
        </ul>
    </div>
"""

        html_content += """
</body>
</html>
"""
        return html_content

    def load_data(self) -> None:
        # Process each product from the input file
        for product_name, quantity in self.products.items():
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
            except Exception as e:
                print(f"Error reading CSV file {csv_path}: {str(e)}")
                sys.exit(1)
            
            products = []
            for _, row in df.iterrows():
                product = Product(
                    name=row['nome_prodotto'],
                    price=float(row['prezzo']),
                    shipping=float(row['spedizione']),
                    vendor=row['venditore'],
                    component_type=component_type,
                    url=row['link_venditore'],
                    quantity=quantity
                )
                products.append(product)
                
                if product.vendor not in self.products_by_vendor:
                    self.products_by_vendor[product.vendor] = []
                self.products_by_vendor[product.vendor].append(product)
            
            self.products_by_component[component_type] = products

    def find_optimal_combination(self, components_to_try: Set[str]) -> Tuple[float, List[Dict]]:
        if not components_to_try:
            print("Error: No components to optimize.")
            sys.exit(1)
            
        vendors_by_component = {
            component: {p.vendor for p in self.products_by_component[component]}
            for component in components_to_try
        }
        
        vendor_options = [
            (component, vendors_by_component[component])
            for component in components_to_try
        ]
        
        all_combinations = list(product(*([(c, v) for v in vs] for c, vs in vendor_options)))
        
        if not all_combinations:
            return float('inf'), None
            
        num_cores = mp.cpu_count()
        chunk_size = max(1, len(all_combinations) // num_cores)
        chunks = [all_combinations[i:i + chunk_size] for i in range(0, len(all_combinations), chunk_size)]
        
        chunk_data = [(chunk, self.products_by_vendor, components_to_try) for chunk in chunks]
        
        with mp.Pool(processes=num_cores) as pool:
            results = pool.map(evaluate_assignments_chunk, chunk_data)
        
        best_cost = float('inf')
        best_orders = None
        
        for cost, orders in results:
            if cost and cost < best_cost:
                best_cost = cost
                best_orders = orders
        
        return best_cost, best_orders

    def optimize_with_exclusions(self) -> Tuple[float, Dict]:
        components_to_try = self.required_components.copy()
        best_cost = float('inf')
        best_orders = None
        
        while components_to_try and not best_orders:
            cost, orders = self.find_optimal_combination(components_to_try)
            if orders:
                best_cost = cost
                best_orders = orders
                break
            
            # No solution found, remove the lowest value component
            component_values = {
                comp: min(p.total_price for p in self.products_by_component[comp])
                for comp in components_to_try
            }
            component_to_remove = min(component_values.items(), key=lambda x: x[1])[0]
            components_to_try.remove(component_to_remove)
            self.excluded_components.add(component_to_remove)
            print(f"Excluding component: {component_to_remove}")
        
        if not best_orders:
            print("Error: Could not find any valid solution even after excluding components.")
            sys.exit(1)
            
        return best_cost, best_orders
    
    def generate_purchase_plan(self) -> None:
        print("=== Piano di Acquisto Ottimale ===")
        print(f"Numero di CPU disponibili: {mp.cpu_count()}")
        print(f"Numero di componenti da acquistare: {len(self.required_components)}")
        print(f"Ordine minimo per venditore: €{MINIMUM_ORDER:.2f} (esclusa spedizione)")
        
        start_time = time.time()
        total_cost, orders = self.optimize_with_exclusions()
        end_time = time.time()
        execution_time = end_time - start_time
        
        if self.excluded_components:
            print("\nComponenti esclusi:")
            for component in sorted(self.excluded_components):
                print(f"- {component}")
            print()
        
        if orders:  # Only process orders if they exist
            for vendor, products in orders.items():
                shipping_cost = max(p.shipping for p in products.values())
                self._print_order_table(vendor, products, shipping_cost)
            
            print("=" * 80)
            print(f"Costo Totale Finale: €{total_cost:>.2f}")
            print(f"Tempo di elaborazione: {execution_time:.2f} secondi")
            print("=" * 80)

            html_content = self._generate_html_content(total_cost, orders, execution_time)
            html_filename = f"{self.project_name}_purchase_plan.html"
            with open(html_filename, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"\nReport HTML generato in '{html_filename}'")

def main():
    parser = argparse.ArgumentParser(
        description='Optimize purchase plan from product data'
    )
    parser.add_argument(
        '-f', '--file',
        type=str,
        default='products',
        help='Input file name (without .txt extension)'
    )
    
    args = parser.parse_args()
    optimizer = PurchaseOptimizer(args.file)
    optimizer.load_data()
    optimizer.generate_purchase_plan()

if __name__ == "__main__":
    main()

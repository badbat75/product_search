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

@dataclass(frozen=True)
class Product:
    name: str
    price: float
    shipping: float
    vendor: str
    component_type: str
    url: str

@dataclass(frozen=True)
class Order:
    vendor: str
    products: Dict[str, Product]
    shipping_cost: float
    
    @property
    def total_price(self) -> float:
        return sum(p.price for p in self.products.values()) + self.shipping_cost

def evaluate_assignments_chunk(chunk_data: Tuple[List[Tuple], Dict, Set]) -> Tuple[float, List[Dict]]:
    assignments, products_by_vendor, required_components = chunk_data
    best_cost = float('inf')
    best_orders = None
    
    for assignment in assignments:
        vendor_assignments = dict(assignment)
        orders = {}
        total_cost = 0
        components_covered = set()
        
        for component, vendor in vendor_assignments.items():
            if vendor not in orders:
                orders[vendor] = {}
            
            vendor_products = [p for p in products_by_vendor[vendor] if p.component_type == component]
            if vendor_products:
                best_product = min(vendor_products, key=lambda p: p.price)
                orders[vendor][component] = best_product
                components_covered.add(component)
        
        if components_covered != required_components:
            continue
        
        for vendor, products in orders.items():
            shipping_cost = max(p.shipping for p in products.values())
            total_cost += sum(p.price for p in products.values()) + shipping_cost
        
        if total_cost < best_cost:
            best_cost = total_cost  # Fixed: Changed 'cost' to 'total_cost'
            best_orders = orders
    
    return best_cost, best_orders

class PurchaseOptimizer:
    def __init__(self, csv_folder: str):
        self.csv_folder = Path(csv_folder)
        self.products_by_component: Dict[str, List[Product]] = {}
        self.products_by_vendor: Dict[str, List[Product]] = {}
        self.required_components: Set[str] = set()
        self.project_name = csv_folder

    def _print_order_table(self, vendor: str, products: Dict[str, Product], shipping_cost: float) -> None:
        col1_width = max(30, max(len(p.component_type) for p in products.values()))
        col2_width = 40
        col3_width = 12

        print(f"\nOrdine da {vendor}")
        print("-" * (col1_width + col2_width + col3_width + 4))
        
        header = (f"{'Componente':<{col1_width}} "
                 f"{'Prodotto':<{col2_width}} "
                 f"{'Prezzo':>{col3_width}}")
        print(header)
        print("-" * (col1_width + col2_width + col3_width + 4))
        
        order_total = 0
        for component, product in sorted(products.items()):
            truncated_name = product.name[:40] if len(product.name) > 40 else product.name
            row = (f"{product.component_type:<{col1_width}} "
                   f"{truncated_name:<{col2_width}} "
                   f"€{product.price:>{10}.2f}")
            print(row)
            order_total += product.price
        
        print("-" * (col1_width + col2_width + col3_width + 4))
        shipping_row = (f"{'Spese di spedizione':<{col1_width + col2_width + 1}}"
                       f"€{shipping_cost:>{10}.2f}")
        print(shipping_row)
        
        print("-" * (col1_width + col2_width + col3_width + 4))
        total_row = (f"{'TOTALE':<{col1_width + col2_width + 1}}"
                     f"€{(order_total + shipping_cost):>{10}.2f}")
        print(total_row)
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
        a {{
            color: #3498db;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Piano di Acquisto Ottimale</h1>
        <p>Numero di componenti da acquistare: {len(self.required_components)}</p>
        <p>Tempo di elaborazione: {execution_time:.2f} secondi</p>
    </div>
"""
        
        for vendor, products in orders.items():
            shipping_cost = max(p.shipping for p in products.values())
            order_total = sum(p.price for p in products.values())
            
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
                    <td class="price">€{product.price:.2f}</td>
                </tr>
"""
            
            html_content += f"""
                <tr>
                    <td colspan="2">Spese di spedizione</td>
                    <td class="price">€{shipping_cost:.2f}</td>
                </tr>
                <tr class="total-row">
                    <td colspan="2">Totale ordine</td>
                    <td class="price">€{(order_total + shipping_cost):.2f}</td>
                </tr>
            </tbody>
        </table>
    </div>
"""

        html_content += f"""
    <div class="final-total">
        <h2>Costo Totale Finale: €{total_cost:.2f}</h2>
    </div>
</body>
</html>
"""
        return html_content
        
    def load_data(self) -> None:
        for csv_file in self.csv_folder.glob("*.csv"):
            component_type = csv_file.stem
            self.required_components.add(component_type)
            df = pd.read_csv(csv_file)
            
            products = []
            for _, row in df.iterrows():
                product = Product(
                    name=row['nome_prodotto'],
                    price=float(row['prezzo']),
                    shipping=float(row['spedizione']),
                    vendor=row['venditore'],
                    component_type=component_type,
                    url=row['link_venditore']
                )
                products.append(product)
                
                if product.vendor not in self.products_by_vendor:
                    self.products_by_vendor[product.vendor] = []
                self.products_by_vendor[product.vendor].append(product)
            
            self.products_by_component[component_type] = products

    def find_optimal_combination(self) -> Tuple[float, List[Dict]]:
        vendors_by_component = {
            component: {p.vendor for p in products}
            for component, products in self.products_by_component.items()
        }
        
        vendor_options = [
            (component, vendors_by_component[component])
            for component in self.required_components
        ]
        
        all_combinations = list(product(*([(c, v) for v in vs] for c, vs in vendor_options)))
        
        num_cores = mp.cpu_count()
        chunk_size = max(1, len(all_combinations) // num_cores)
        chunks = [all_combinations[i:i + chunk_size] for i in range(0, len(all_combinations), chunk_size)]
        
        chunk_data = [(chunk, self.products_by_vendor, self.required_components) for chunk in chunks]
        
        with mp.Pool(processes=num_cores) as pool:
            results = pool.map(evaluate_assignments_chunk, chunk_data)
        
        best_cost = float('inf')
        best_orders = None
        
        for cost, orders in results:
            if cost and cost < best_cost:
                best_cost = cost
                best_orders = orders
        
        return best_cost, best_orders
    
    def generate_purchase_plan(self) -> None:
        print("=== Piano di Acquisto Ottimale ===")
        print(f"Numero di CPU disponibili: {mp.cpu_count()}")
        print(f"Numero di componenti da acquistare: {len(self.required_components)}")
        
        start_time = time.time()
        total_cost, orders = self.find_optimal_combination()
        end_time = time.time()
        execution_time = end_time - start_time
        
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
        help='Input folder name containing CSV files'
    )
    
    args = parser.parse_args()
    optimizer = PurchaseOptimizer(args.file)
    optimizer.load_data()
    optimizer.generate_purchase_plan()

if __name__ == "__main__":
    main()

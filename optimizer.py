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
from lib.config import (VAR_DATA_DIR, TEMPLATES_DIR, DEFAULT_MINIMUM_ORDER, 
                      DEFAULT_MAX_VENDOR_COMBINATIONS, DEFAULT_MAX_COMBINATIONS,
                      get_config_value)

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
        self.minimum_order = get_config_value(self.config, 'MINIMUM_ORDER', DEFAULT_MINIMUM_ORDER)
        self.max_vendor_combinations = get_config_value(self.config, 'MAX_VENDOR_COMBINATIONS', DEFAULT_MAX_VENDOR_COMBINATIONS)

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
        
        # Create component-vendor price matrix for faster lookups
        price_matrix = {}
        for component in self.required_components:
            price_matrix[component] = {}
            for product in self.products_by_component[component]:
                if product.vendor not in price_matrix[component] or product.total_price < price_matrix[component][product.vendor].total_price:
                    price_matrix[component][product.vendor] = product
        
        # Vendor dominance analysis
        vendor_capabilities = {}
        vendor_competitiveness = {}
        for vendor in capable_vendors:
            components = set()
            competitive_count = 0
            for component in self.required_components:
                if vendor in price_matrix[component]:
                    components.add(component)
                    # Check if this vendor is among the top 3 cheapest for this component
                    sorted_vendors = sorted(price_matrix[component].keys(), 
                                          key=lambda v: price_matrix[component][v].total_price)
                    if vendor in sorted_vendors[:3]:
                        competitive_count += 1
            vendor_capabilities[vendor] = len(components)
            vendor_competitiveness[vendor] = competitive_count
        
        # Get single vendor solution for early termination threshold
        single_cost, _ = self.find_single_vendor_solution()
        early_termination_threshold = single_cost * 0.9 if single_cost < float('inf') else None
        
        # Sort vendors by competitiveness and capabilities
        sorted_vendors = sorted(capable_vendors, 
                              key=lambda v: (-vendor_competitiveness[v], -vendor_capabilities[v], 
                                           min(p.shipping for p in self.products_by_vendor[v])))
        
        # IMPORTANT: Ensure we try ALL combinations up to a reasonable limit
        # This ensures we don't miss the optimal solution found by the former algorithm
        max_vendors = min(self.max_vendor_combinations, len(sorted_vendors))
        vendor_groups_to_try = []
        
        # Generate ALL combinations up to max_vendors
        for num_vendors in range(1, max_vendors + 1):
            vendor_groups_to_try.extend(itertools.combinations(sorted_vendors, num_vendors))
        
        # Limit the number of combinations if too many
        max_combinations = get_config_value(self.config, 'MAX_COMBINATIONS', DEFAULT_MAX_COMBINATIONS)
            
        if len(vendor_groups_to_try) > max_combinations:
            print(f"Limiting evaluation to {max_combinations} most promising vendor combinations")
            # Sort combinations by potential (sum of competitiveness scores)
            vendor_groups_to_try = sorted(
                vendor_groups_to_try,
                key=lambda group: sum(vendor_competitiveness[v] for v in group),
                reverse=True
            )[:max_combinations]
        
        total_combinations = len(vendor_groups_to_try)
        print(f"Total combinations to evaluate: {total_combinations}")
        
        # Memoization to avoid re-evaluating the same vendor groups
        evaluated_combinations = set()
        
        # Use a proper progress bar if available
        try:
            from tqdm import tqdm
            progress_bar = tqdm(total=total_combinations, desc="Evaluating vendor combinations")
            use_tqdm = True
        except ImportError:
            use_tqdm = False
            last_update_time = time.time()
        
        # Evaluate vendor combinations
        for i, vendor_group in enumerate(vendor_groups_to_try):
            if use_tqdm:
                progress_bar.update(1)
            else:
                current_time = time.time()
                # Update progress every 1 second on the same line
                if current_time - last_update_time >= 1:
                    progress_percent = i/total_combinations*100 if total_combinations > 0 else 100
                    print(f"\rProgress: {i}/{total_combinations} combinations evaluated ({progress_percent:.1f}%)", end="", flush=True)
                    last_update_time = current_time
            
            # Skip if we've already evaluated this combination
            vendor_group_key = frozenset(vendor_group)
            if vendor_group_key in evaluated_combinations:
                continue
            evaluated_combinations.add(vendor_group_key)
            
            # Early pruning: Skip vendor groups that can't cover all components
            covered_components = set()
            for vendor in vendor_group:
                for component in self.required_components:
                    if vendor in price_matrix[component]:
                        covered_components.add(component)
            
            if covered_components != self.required_components:
                continue
            
            # Try both optimized and exhaustive approaches to ensure we don't miss solutions
            # First try the optimized approach
            cost, orders = self._assign_components_to_vendors(list(vendor_group), price_matrix)
            
            # If the optimized method fails or gives a suboptimal solution, try the exhaustive method
            if not orders or cost > best_cost:
                exhaustive_cost, exhaustive_orders = self._exhaustive_component_assignment(list(vendor_group), price_matrix)
                if exhaustive_orders and (not orders or exhaustive_cost < cost):
                    cost = exhaustive_cost
                    orders = exhaustive_orders
            
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
            # Print final progress
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

    def _assign_components_to_vendors(self, vendor_group: List[str], price_matrix: Dict) -> Tuple[float, Optional[Dict[str, Dict[str, Product]]]]:
        """Assign components to vendors optimally"""
        # Try multiple assignment strategies and pick the best one
        
        # Strategy 1: Greedy assignment by component price
        orders1 = {}
        for component in sorted(self.required_components, 
                               key=lambda c: max(price_matrix[c][v].total_price 
                                               for v in vendor_group if v in price_matrix[c]),
                               reverse=True):
            best_cost = float('inf')
            best_vendor = None
            best_product = None
            
            for vendor in vendor_group:
                if vendor not in price_matrix[component]:
                    continue
                    
                product = price_matrix[component][vendor]
                
                # Consider existing order if any
                if vendor in orders1:
                    effective_cost = product.total_price
                else:
                    effective_cost = product.total_price + product.shipping
                
                if effective_cost < best_cost:
                    best_cost = effective_cost
                    best_vendor = vendor
                    best_product = product
            
            if best_vendor:
                if best_vendor not in orders1:
                    orders1[best_vendor] = {}
                orders1[best_vendor][component] = best_product
        
        # Strategy 2: Minimize number of vendors
        orders2 = {}
        # Sort vendors by number of components they can provide
        vendor_coverage = {}
        for vendor in vendor_group:
            vendor_coverage[vendor] = sum(1 for c in self.required_components if vendor in price_matrix[c])
        
        sorted_vendors = sorted(vendor_group, key=lambda v: (-vendor_coverage[v], 
                                                           min(p.shipping for p in self.products_by_vendor[v])))
        
        remaining_components = set(self.required_components)
        for vendor in sorted_vendors:
            if not remaining_components:
                break
                
            vendor_components = {}
            for component in list(remaining_components):
                if vendor in price_matrix[component]:
                    vendor_components[component] = price_matrix[component][vendor]
                    remaining_components.remove(component)
            
            if vendor_components:
                orders2[vendor] = vendor_components
        
        # Strategy 3: Cluster components by vendor shipping costs
        orders3 = {}
        # Group vendors by shipping cost tiers
        shipping_tiers = {}
        for vendor in vendor_group:
            shipping = min(p.shipping for p in self.products_by_vendor[vendor])
            tier = round(shipping * 2) / 2  # Round to nearest 0.5
            if tier not in shipping_tiers:
                shipping_tiers[tier] = []
            shipping_tiers[tier].append(vendor)
        
        # Assign components to vendors in the same shipping tier when possible
        remaining = set(self.required_components)
        for tier in sorted(shipping_tiers.keys()):
            tier_vendors = shipping_tiers[tier]
            tier_assignments = {}
            
            for component in list(remaining):
                best_vendor = None
                best_price = float('inf')
                
                for vendor in tier_vendors:
                    if vendor in price_matrix[component] and price_matrix[component][vendor].total_price < best_price:
                        best_price = price_matrix[component][vendor].total_price
                        best_vendor = vendor
                
                if best_vendor:
                    if best_vendor not in tier_assignments:
                        tier_assignments[best_vendor] = {}
                    tier_assignments[best_vendor][component] = price_matrix[component][best_vendor]
                    remaining.remove(component)
            
            orders3.update(tier_assignments)
        
        # If any components remain, assign them to any available vendor
        if remaining:
            for component in remaining:
                best_vendor = None
                best_cost = float('inf')
                
                for vendor in vendor_group:
                    if vendor in price_matrix[component] and price_matrix[component][vendor].total_price < best_cost:
                        best_cost = price_matrix[component][vendor].total_price
                        best_vendor = vendor
                
                if best_vendor:
                    if best_vendor not in orders3:
                        orders3[best_vendor] = {}
                    orders3[best_vendor][component] = price_matrix[component][best_vendor]
        
        # Evaluate all strategies
        strategies = [orders1, orders2, orders3]
        best_cost = float('inf')
        best_orders = None
        
        for orders in strategies:
            # Check if all components are covered
            components_covered = set(comp for vendor_products in orders.values() for comp in vendor_products)
            if components_covered != self.required_components:
                continue
            
            # Validate and redistribute components to meet minimum order requirements
            cost, valid_orders = self._redistribute_for_minimum_order(orders)
            
            if valid_orders and cost < best_cost:
                best_cost = cost
                best_orders = valid_orders
        
        return best_cost, best_orders

    def _exhaustive_component_assignment(self, vendor_group: List[str], price_matrix: Dict) -> Tuple[float, Optional[Dict[str, Dict[str, Product]]]]:
        """Try different component assignments to find the optimal solution"""
        # Create a mapping of components to possible vendors
        component_vendors = {}
        for component in self.required_components:
            component_vendors[component] = []
            for vendor in vendor_group:
                if vendor in price_matrix[component]:
                    component_vendors[component].append(vendor)
        
        # Check if all components can be fulfilled
        for component, vendors in component_vendors.items():
            if not vendors:
                return float('inf'), None
        
        # Sort components by number of vendor options (fewer options first)
        sorted_components = sorted(component_vendors.keys(), key=lambda c: len(component_vendors[c]))
        
        # Try different assignments recursively
        best_cost = float('inf')
        best_assignment = None
        
        def assign_components(index, current_assignment):
            nonlocal best_cost, best_assignment
            
            # Base case: all components assigned
            if index == len(sorted_components):
                # Convert assignment to orders format
                orders = {}
                for component, vendor in current_assignment.items():
                    if vendor not in orders:
                        orders[vendor] = {}
                    orders[vendor][component] = price_matrix[component][vendor]
                
                # Validate and redistribute to meet minimum order requirements
                cost, valid_orders = self._redistribute_for_minimum_order(orders)
                
                if valid_orders and cost < best_cost:
                    best_cost = cost
                    best_assignment = valid_orders
                return
            
            # Get current component to assign
            component = sorted_components[index]
            
            # Try each possible vendor for this component
            for vendor in component_vendors[component]:
                current_assignment[component] = vendor
                assign_components(index + 1, current_assignment)
        
        # Start recursive assignment with limited depth for efficiency
        if len(sorted_components) <= 10:  # Only do exhaustive search for reasonable number of components
            assign_components(0, {})
        else:
            # For larger problems, use a greedy approach
            return self._assign_components_to_vendors(vendor_group, price_matrix)
        
        return best_cost, best_assignment
    
    def _redistribute_for_minimum_order(self, assignment: Dict[str, Dict[str, Product]]) -> Tuple[float, Optional[Dict[str, Dict[str, Product]]]]:
        """Redistribute components to meet minimum order requirements"""
        # Check which vendors don't meet minimum requirements
        valid_orders = {}
        vendors_below_minimum = []
        
        for vendor, products in assignment.items():
            products_total = sum(p.total_price for p in products.values())
            if products_total >= self.minimum_order:
                valid_orders[vendor] = products
            else:
                vendors_below_minimum.append((vendor, products, products_total))
        
        # If all vendors meet minimum requirements, calculate total cost and return
        if not vendors_below_minimum:
            total_cost = sum(sum(p.total_price for p in products.values()) + 
                            max(p.shipping for p in products.values())
                            for vendor, products in valid_orders.items())
            return total_cost, valid_orders
        
        # Try to redistribute components from vendors below minimum to valid vendors
        for vendor, products, _ in list(vendors_below_minimum):
            # Sort components by price (try to move expensive ones first)
            sorted_components = sorted(products.items(), key=lambda x: x[1].total_price, reverse=True)
            
            for component, product in sorted_components:
                # Try to find another vendor who can supply this component
                alternative_vendors = []
                for v in valid_orders:
                    for p in self.products_by_component[component]:
                        if p.vendor == v:
                            alternative_vendors.append((v, p))
                
                if alternative_vendors:
                    # Choose the vendor with the lowest price
                    best_alt_vendor, best_alt_product = min(alternative_vendors, key=lambda x: x[1].total_price)
                    
                    # Move the component to this vendor
                    valid_orders[best_alt_vendor][component] = best_alt_product
                    
                    # Remove from original vendor's products
                    products.pop(component)
                    
                    # If we've moved all components, remove this vendor from below minimum
                    if not products:
                        vendors_below_minimum.remove((vendor, products, _))
                        break
        
        # Try to consolidate orders from vendors below minimum
        if len(vendors_below_minimum) > 1:
            # Sort vendors by total (try to eliminate smallest orders first)
            vendors_below_minimum.sort(key=lambda x: x[2])
            
            for i, (vendor1, products1, total1) in enumerate(list(vendors_below_minimum)):
                if not products1:  # Skip if all products were moved
                    continue
                    
                for j, (vendor2, products2, total2) in enumerate(list(vendors_below_minimum)[i+1:], i+1):
                    if not products2:  # Skip if all products were moved
                        continue
                        
                    # Check if combining these vendors would meet minimum order
                    if total1 + total2 >= self.minimum_order:
                        # Try to move all products from vendor2 to vendor1
                        moved_all = True
                        for component, product in list(products2.items()):
                            # Find equivalent product from vendor1
                            vendor1_product = None
                            for p in self.products_by_component[component]:
                                if p.vendor == vendor1:
                                    vendor1_product = p
                                    break
                            
                            if vendor1_product:
                                products1[component] = vendor1_product
                                products2.pop(component)
                            else:
                                moved_all = False
                        
                        # Check if vendor1 now meets minimum
                        new_total = sum(p.total_price for p in products1.values())
                        if new_total >= self.minimum_order:
                            valid_orders[vendor1] = products1
                            # Remove vendor1 from below minimum
                            vendors_below_minimum = [(v, p, t) for v, p, t in vendors_below_minimum 
                                                    if v != vendor1]
                            
                            # If we moved all products from vendor2, remove it too
                            if moved_all or not products2:
                                vendors_below_minimum = [(v, p, t) for v, p, t in vendors_below_minimum 
                                                        if v != vendor2]
                            break
        
        # Try a more aggressive redistribution approach for remaining vendors
        remaining_vendors = [v for v, p, _ in vendors_below_minimum if p]
        if remaining_vendors:
            # Try to move components between vendors to meet minimum requirements
            # This is a more complex approach that tries different combinations
            remaining_assignment = {v: p for v, p, _ in vendors_below_minimum if p}
            improved_assignment = self._optimize_remaining_vendors(remaining_assignment, valid_orders)
            if improved_assignment:
                valid_orders.update(improved_assignment)
                # Update the list of vendors below minimum
                vendors_below_minimum = [(v, p, sum(prod.total_price for prod in p.values())) 
                                        for v, p in remaining_assignment.items() 
                                        if v not in improved_assignment]
        
        # Check if there are still vendors below minimum
        remaining_below_min = []
        for vendor, products, _ in vendors_below_minimum:
            if products:  # If there are still products assigned to this vendor
                products_total = sum(p.total_price for p in products.values())
                if products_total < self.minimum_order:
                    remaining_below_min.append(vendor)
                else:
                    # This vendor now meets minimum
                    valid_orders[vendor] = products
        
        # If there are still vendors below minimum, this solution is invalid
        if remaining_below_min:
            return float('inf'), None
        
        # Calculate total cost for valid orders
        total_cost = sum(sum(p.total_price for p in products.values()) + 
                        max(p.shipping for p in products.values())
                        for vendor, products in valid_orders.items())
        
        return total_cost, valid_orders
    
    def _optimize_remaining_vendors(self, remaining: Dict[str, Dict[str, Product]], 
                                   valid: Dict[str, Dict[str, Product]]) -> Dict[str, Dict[str, Product]]:
        """Try to optimize the assignment of components for remaining vendors"""
        # If no remaining vendors, nothing to do
        if not remaining:
            return {}
            
        # Try to combine all remaining vendors into one order if possible
        all_components = {}
        for vendor, products in remaining.items():
            for component, product in products.items():
                if component not in all_components or product.total_price < all_components[component].total_price:
                    all_components[component] = product
        
        # Check if the combined order meets minimum requirements
        total = sum(p.total_price for p in all_components.values())
        if total >= self.minimum_order:
            # Find the vendor with the lowest shipping cost
            best_vendor = min(remaining.keys(), 
                             key=lambda v: min(p.shipping for p in self.products_by_vendor[v]))
            
            # Create a new order for this vendor with all components
            new_order = {}
            for component, product in all_components.items():
                # Find the product from the best vendor
                vendor_product = None
                for p in self.products_by_component[component]:
                    if p.vendor == best_vendor:
                        vendor_product = p
                        break
                
                if vendor_product:
                    new_order[component] = vendor_product
                else:
                    # If best vendor doesn't have this component, use the original product
                    new_order[component] = product
            
            # Check if the new order meets minimum requirements
            new_total = sum(p.total_price for p in new_order.values())
            if new_total >= self.minimum_order:
                return {best_vendor: new_order}
        
        # If combining all doesn't work, try pairwise combinations
        for vendor1 in remaining:
            for vendor2 in remaining:
                if vendor1 != vendor2:
                    combined = {}
                    # Add all products from vendor1
                    for component, product in remaining[vendor1].items():
                        combined[component] = product
                    
                    # Add products from vendor2 if not already present
                    for component, product in remaining[vendor2].items():
                        if component not in combined:
                            combined[component] = product
                    
                    # Check if combined order meets minimum
                    combined_total = sum(p.total_price for p in combined.values())
                    if combined_total >= self.minimum_order:
                        # Find the vendor with better shipping
                        if min(p.shipping for p in self.products_by_vendor[vendor1]) <= min(p.shipping for p in self.products_by_vendor[vendor2]):
                            best_vendor = vendor1
                        else:
                            best_vendor = vendor2
                        
                        # Create optimized order for this vendor
                        optimized_order = {}
                        for component, product in combined.items():
                            vendor_product = None
                            for p in self.products_by_component[component]:
                                if p.vendor == best_vendor:
                                    vendor_product = p
                                    break
                            
                            if vendor_product:
                                optimized_order[component] = vendor_product
                            else:
                                # If best vendor doesn't have this component, use the original product
                                optimized_order[component] = product
                        
                        # Check if optimized order meets minimum
                        optimized_total = sum(p.total_price for p in optimized_order.values())
                        if optimized_total >= self.minimum_order:
                            return {best_vendor: optimized_order}
        
        # If no combination works, return empty dict
        return {}

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

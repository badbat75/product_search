# Optimization Algorithm

The optimizer (`optimizer.py`) finds the cheapest way to purchase a set of required products across multiple vendors, subject to minimum order constraints and shipping costs.

## Problem Definition

**Given:**
- A set of required components (products), each with a desired quantity
- For each component, a list of vendor offers (price, shipping cost, vendor name)

**Find:** An assignment of components to vendors that minimizes total cost.

**Constraints:**
- Every required component must be purchased from exactly one vendor
- Each vendor's product total (excluding shipping) must meet the `MINIMUM_ORDER` threshold (default: €50)
- At most `MAX_VENDOR_COMBINATIONS` vendors can be used (default: 4)

**Cost model:**
- Per-vendor cost = sum of (unit price x quantity) for assigned products + one shipping charge
- Shipping charge per vendor = max shipping cost among that vendor's assigned products (assumes a single shipment per vendor)
- Total cost = sum of all per-vendor costs

## Data Structures

### Product

Frozen dataclass representing a single vendor offer:
- `price` — unit price
- `shipping` — shipping cost for this offer
- `quantity` — how many units needed
- `total_price` = price x quantity
- `total_cost` = total_price + shipping

### Pre-computed Lookups (built once after loading data)

| Lookup | Type | Purpose |
|--------|------|---------|
| `best_product_lookup` | `(component, vendor) -> Product` | Cheapest offer per component per vendor (by `total_cost`) |
| `vendor_coverage` | `vendor -> {components}` | Which components each vendor carries |
| `cheapest_per_component` | `component -> float` | Absolute cheapest `total_cost` across all vendors |
| `absolute_lower_bound` | `float` | Sum of all cheapest products — theoretical cost floor |
| `capable_vendors` | `[vendor]` | Vendors sorted by coverage count desc, min shipping asc |

These replace per-combination list filtering with O(1) dictionary lookups.

## Algorithm Overview

```
load CSVs
    |
build lookup tables
    |
filter dominated vendors
    |
for k = 1 to MAX_VENDOR_COMBINATIONS:
    for each combination of k vendors:
        |-- coverage pre-check --> skip if can't cover all components
        |-- lower-bound pruning --> skip if can't beat current best
        |-- greedy assignment (Phase 1)
        |-- minimum-order repair (Phase 2)
        |-- validate and score
    |
    early termination if solution is within 5% of theoretical minimum
    |
return best solution found
```

## Phase 1: Greedy Assignment

For each required component, assign it to the vendor in the group that offers the lowest `total_cost` (price x quantity + shipping). Uses `best_product_lookup` for O(1) access.

This produces the cheapest possible assignment when ignoring minimum order constraints.

## Phase 2: Minimum Order Repair

After greedy assignment, some vendors may fall below the minimum order threshold. The repair loop attempts to fix this:

1. Identify vendors whose product total < `MINIMUM_ORDER`
2. For each failing vendor, search for a component that can be reassigned **from** another vendor **to** the failing one:
   - The failing vendor must be able to supply that component
   - The donor vendor must still meet minimum order after losing the component (or become empty and be removed)
   - Among all valid swaps, pick the one with the smallest cost increase
3. Execute the best swap found
4. Repeat until no vendors are failing or no more repairs are possible

The loop runs at most `len(components)` iterations (each moves one component). If repair fails, the combination is rejected.

**Why this matters:** Pure greedy assignment can reject valid combinations. Example:
- Components A, B. Vendors X, Y. Min order €50.
- Greedy assigns A to X (€45), B to Y (€10). Y fails minimum → combination rejected.
- Repair reassigns A to Y (€50), B to X (€60). Both meet minimum. Valid solution.

## Pruning Strategies

### Dominated Vendor Filtering

A vendor V is **dominated** if there exists another vendor that:
1. Covers every component V covers (superset coverage)
2. Has equal or lower `total_cost` for every one of those components

Dominated vendors are removed from the candidate pool before generating combinations. This is safe: any solution using a dominated vendor can be improved by substituting the dominating vendor.

Safety check: the filtered set must still cover all required components, otherwise the filter is not applied.

### Coverage Pre-check

Before evaluating a vendor combination, verify the union of their coverage sets includes all required components. Cost: O(k x |components|), much cheaper than full evaluation.

### Lower-bound Pruning

For each combination, compute a lower bound: sum of the cheapest `total_cost` per component from any vendor in the group, ignoring constraints. If this lower bound already exceeds the current best solution, skip the combination entirely.

### Early Termination

After completing all combinations of size k, if the best solution found is within 5% of the `absolute_lower_bound` (theoretical minimum ignoring all constraints), skip larger group sizes. Adding more vendors introduces additional shipping charges, making improvement unlikely.

## Complexity

**Without pruning:** O(C(V, k) x |components| x k) where V = vendors, k = max combination size

**With pruning:** Most combinations are skipped by coverage and lower-bound checks. Dominated vendor filtering reduces V before combination generation.

Typical performance for 10 components, 50 vendors, k=4: sub-second.

## Configuration

Set in `conf/search.cfg`:

| Parameter | Default | Effect |
|-----------|---------|--------|
| `MINIMUM_ORDER` | 50.0 | Minimum product total per vendor (€). Set to 0 to disable. |
| `MAX_VENDOR_COMBINATIONS` | 4 | Maximum vendors in a solution. Higher = slower but potentially cheaper. |

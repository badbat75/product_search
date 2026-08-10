# Optimization Algorithm

The optimizer (`optimizer.py`) finds the cheapest way to purchase a set of required products across multiple vendors, subject to minimum order constraints and shipping costs. It solves the problem **exactly** as a mixed-integer linear program (MILP) using [PuLP](https://coin-or.github.io/pulp/) with the bundled CBC solver.

## Problem Definition

**Given:**

- A set of required components (products), each with a desired quantity
- For each component, a list of vendor offers (price, shipping cost, vendor name)

**Find:** An assignment of components to vendors that minimizes total cost.

**Constraints:**

- Every required component must be purchased from exactly one vendor (one specific offer)
- Each vendor's product total (excluding shipping) must meet its minimum order threshold (per-vendor override or global `MINIMUM_ORDER` default)
- At most `MAX_VENDOR_COMBINATIONS` vendors can be used (default: 4)

**Cost model:**

- Per-vendor cost = sum of (unit price x quantity) for assigned products + one shipping charge
- Shipping charge per vendor = max shipping cost among that vendor's assigned offers (assumes a single shipment per vendor)
- Total cost = sum of all per-vendor costs

## MILP Formulation

The whole problem is a *fixed-charge assignment problem*: buying from a vendor incurs a one-off shipping charge shared by all products in that order. This structure is linear, so it can be solved to guaranteed optimality.

**Variables:**

| Variable | Type | Meaning |
| -------- | ---- | ------- |
| `x[p]` | binary | offer `p` (a CSV row) is purchased |
| `y[v]` | binary | vendor `v` is used |
| `s[v]` | continuous ≥ 0 | shipping charged by vendor `v` |

**Objective:**

```text
minimize  Σ total_price(p)·x[p]  +  Σ s[v]
```

where `total_price(p)` = unit price × required quantity.

**Constraints:**

1. `Σ x[p] = 1` over the offers of each component — exactly one offer per component
2. `x[p] ≤ y[vendor(p)]` — buying an offer marks its vendor as used
3. `s[v] ≥ shipping(p)·x[p]` for each offer `p` of vendor `v` — the order's shipping is the max shipping among chosen offers (minimization makes `s[v]` settle exactly at that max, and at 0 for unused vendors)
4. `Σ total_price(p)·x[p] ≥ minimum_order(v)·y[v]` per vendor — minimum order applies only if the vendor is used
5. `Σ y[v] ≤ MAX_VENDOR_COMBINATIONS`

All offers are kept in the model (not just the cheapest per component/vendor): a pricier variant of the same product can be the globally optimal pick when it helps a vendor reach its minimum order threshold.

If a required component has no offers at all, the optimizer reports it and stops instead of submitting an infeasible model.

**Infeasibility** (e.g. minimum orders too high for the basket, or too few vendors allowed) is reported by the solver and surfaced to the user with a suggestion to relax `MINIMUM_ORDER` / `MAX_VENDOR_COMBINATIONS`.

## Why MILP instead of the previous heuristic

The previous implementation enumerated vendor combinations (`itertools.combinations`) with greedy assignment, repair, and pruning. Its estimates counted shipping *per product* while the real cost charges it *once per vendor*, so its "lower bounds" were not actual lower bounds: pruning and early termination could silently discard the optimal solution, and the greedy assignment over-penalized consolidating items at one vendor. On the reference basket (`farmacia.txt`) the heuristic returned €108.16 where the MILP finds €103.62.

The MILP is exact by construction, needs no pruning/repair/dominance machinery, and is fast at this scale: ~140 offers × ~50 vendors solves in well under a second.

## Complexity

Model size is linear in the number of offers: one binary per CSV row, two per vendor, and O(offers) constraints. CBC solves typical instances (tens of components, hundreds of offers) in milliseconds to seconds. Runtime is dominated by pandas CSV loading, not the solver.

## Configuration

Set in `conf/search.cfg`:

| Parameter | Default | Effect |
| --------- | ------- | ------ |
| `MINIMUM_ORDER` | 50.0 | Default minimum product total per vendor (€). Set to 0 to disable. |
| `MAX_VENDOR_COMBINATIONS` | 4 | Maximum number of vendors in a solution. Higher = potentially cheaper plan, more parcels. |
| `VENDOR_MINIMUM_ORDERS` | *(empty)* | Per-vendor minimum order overrides, comma-separated `vendor:amount` pairs. Vendors not listed use `MINIMUM_ORDER`. Example: `Zfarmacia:30,Dr. Max:25` |

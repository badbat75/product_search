# Product Search

A two-phase tool that finds the cheapest way to buy a list of products from Italian e-commerce vendors. It scrapes [Trovaprezzi.it](https://www.trovaprezzi.it) for prices, then solves the vendor selection problem to minimize total cost including shipping.

## How It Works

**Phase 1 — Search** (`search.py`): For each product in your list, opens Trovaprezzi.it via Selenium, searches using the homepage search box, and extracts structured price data from the results page. By default it parses the HTML directly; optionally it can use Claude AI for extraction. Results are saved as CSV files.

**Phase 2 — Optimize** (`optimizer.py`): Reads all the CSVs and finds the optimal combination of vendors. It first tries single-vendor solutions, then brute-forces multi-vendor combinations (up to a configurable limit), respecting minimum order thresholds per vendor. Outputs an HTML purchase plan report.

## Requirements

- Python 3.9+
- A browser driver installed and in PATH (Edge, Firefox, or Chrome)
- An [Anthropic API key](https://console.anthropic.com/) (only if using `--ai` mode)

Install dependencies:

```bash
pip install selenium beautifulsoup4
pip install anthropic  # only needed for --ai mode
```

## Setup

Copy the configuration template and fill in your settings:

```bash
cp conf/search.cfg.template conf/search.cfg
```

Edit `conf/search.cfg`:

| Key | Default | Description |
|-----|---------|-------------|
| `CLAUDE_API_KEY` | — | Your Anthropic API key (only required with `--ai`) |
| `BROWSER_TYPE` | `edge` | Browser to use: `edge`, `firefox`, or `chrome` |
| `THROTTLE_DELAY_SEC` | `1` | Seconds between requests |
| `RETRY_COUNT` | `3` | Max retries on errors |
| `MINIMUM_ORDER` | `50` | Minimum order value per vendor (EUR, excluding shipping) |
| `MAX_VENDOR_COMBINATIONS` | `4` | Max number of vendors to combine in optimization |

## Usage

### 1. Prepare an input file

Create a text file with one product per line. Optionally add a quantity after a comma:

```
Aspirina C 40 compresse
Tachipirina 1000mg,2
Voltaren Emulgel 2%
```

### 2. Search for prices

```bash
python search.py products.txt
```

Options:
- `--ai` — use Claude AI for HTML extraction instead of the built-in HTML parser (requires `CLAUDE_API_KEY`)
- `--debug` — save scraped HTML pages to `var/debug/`
- `--debug-ai` — save Claude API responses to `var/debug/ai/` (only with `--ai`)
- `-f` / `--force` — re-search products that already have a CSV file

The search skips products that already have a CSV in `var/data/` (unless `-f` is used). If a CAPTCHA appears (DataDome, reCAPTCHA, etc.), the browser will wait up to 5 minutes for you to solve it manually.

### 3. Optimize the purchase plan

```bash
python optimizer.py products.txt
```

This reads the CSVs from `var/data/`, finds the cheapest vendor combination, and generates `products_purchase_plan.html` (named after your input file).

## Output

- `var/data/*.csv` — one CSV per product with columns: `nome_prodotto`, `prezzo`, `spedizione`, `venditore`, `link_venditore`
- `var/log/` — log files
- `<name>_purchase_plan.html` — the final optimized purchase plan with clickable vendor links

## Example

```bash
# Search all products (HTML parser, no API key needed)
python search.py farmacia.txt

# Search using Claude AI extraction
python search.py farmacia.txt --ai

# If some failed or you want to re-fetch
python search.py farmacia.txt --force

# Generate the optimal purchase plan
python optimizer.py farmacia.txt
# Opens farmacia_purchase_plan.html
```

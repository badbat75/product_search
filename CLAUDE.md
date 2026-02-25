# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A two-phase Python pipeline for Italian e-commerce price comparison:
1. **search.py** scrapes Trovaprezzi.it using Selenium, extracts structured product data from HTML (via built-in parser or optionally Claude AI), and saves results as CSV files
2. **optimizer.py** reads those CSVs and finds the optimal vendor combination that minimizes total cost (prices + shipping) while respecting minimum order constraints

## Python Environment

Always use the project's virtual environment when running Python commands:
```bash
.venv/Scripts/python.exe <script>    # Windows
```

## Commands

### Setup
```bash
cp conf/search.cfg.template conf/search.cfg
# Edit conf/search.cfg with your settings (CLAUDE_API_KEY only needed for --ai mode)
```

### Run Search (Phase 1)
```bash
.venv/Scripts/python.exe search.py <input_file>              # HTML parser (default, no API key needed)
.venv/Scripts/python.exe search.py <input_file> --ai         # Use Claude AI for extraction
.venv/Scripts/python.exe search.py <input_file> --debug      # Save HTML pages to var/debug/
.venv/Scripts/python.exe search.py <input_file> --debug-ai   # Save AI responses to var/debug/ai/
.venv/Scripts/python.exe search.py <input_file> -f           # Force re-search existing products
```

Input file format: one product per line, or `product_name,quantity`.

### Run Optimizer (Phase 2)
```bash
.venv/Scripts/python.exe optimizer.py <input_file>
```

Reads CSVs from `var/data/`, outputs `purchase_plan.html`.

## Architecture

### Data Flow
```
Product list → Selenium (Trovaprezzi.it homepage search) → HTML parser or Claude AI → CSV files → Optimizer → HTML report
```

### Key Classes
- **`TrovaprezziProcessor`** (search.py): Orchestrates browser automation, anti-detection measures, CAPTCHA detection (DataDome, reCAPTCHA, hCaptcha, Cloudflare — waits up to 300s for human), homepage search box interaction, and CSV output
- **`HtmlProcessor`** (lib/htmlparser.py): BeautifulSoup-based parser that extracts product data directly from Trovaprezzi listing HTML (`li.listing_item` elements)
- **`AIProcessor`** (lib/aisearch.py): Claude API client with rate limiting, retry logic, and European price format parsing (1.234,56 → 1234.56). Used when `--ai` flag is passed
- **`PurchaseOptimizer`** (optimizer.py): Brute-force vendor combination solver using `itertools.combinations`, respects minimum order thresholds
- **`Product`** (optimizer.py): Frozen dataclass with computed `total_price` and `total_cost` properties

### HTML Extraction (lib/htmlparser.py)
Parses Trovaprezzi search results directly from HTML using CSS selectors:
- `li.listing_item` — each product offer
- `.item_name` — product name
- `.item_basic_price` — price (European format: `6,25 €`)
- `.item_delivery_price` — shipping cost (or `free_shipping` class for free)
- `.merchant_name` — vendor name
- `a.listing_item_button` — vendor link

### Browser Anti-Detection
The Selenium browser is configured to reduce bot detection:
- `--disable-blink-features=AutomationControlled` — removes automation flag
- `excludeSwitches: ['enable-automation']` — hides "controlled by automated software" banner
- `navigator.webdriver` overridden to `undefined` via CDP
- Searches via homepage search box (not direct URL navigation) to mimic human behavior

### CAPTCHA Handling
Detects DataDome (`captcha-delivery.com`), reCAPTCHA, hCaptcha, and Cloudflare challenges. When detected, logs a message and polls every 2 seconds for up to 5 minutes, waiting for manual resolution.

### Configuration
All config lives in `conf/search.cfg` (INI-style key=value, parsed by `lib/utils.read_config()`). Constants and paths are centralized in `lib/config.py`. The config file is gitignored; use `conf/search.cfg.template` as reference.

### Output Directories
All under `var/` (gitignored, auto-created by `lib/config.py`):
- `var/data/` — product CSV files (columns: nome_prodotto, prezzo, spedizione, venditore, link_venditore)
- `var/log/` — log files
- `var/debug/` — HTML snapshots, `var/debug/ai/` — AI response JSON

### HTML Report
Templates in `templates/` (`purchase_plan.html` + `style.css`). The optimizer generates the final HTML report by string-formatting into the template.

## Key Technical Details

- **Browser support**: Edge (default), Firefox, Chrome — configured via `BROWSER_TYPE` in search.cfg
- **Default extraction**: Built-in HTML parser via BeautifulSoup (no API key needed)
- **AI extraction**: `claude-3-haiku-20240307` for HTML extraction (pipe-delimited output format), enabled with `--ai` flag
- **Price format**: European (comma decimal, dot thousands) — handled by both `HtmlProcessor._parse_price()` and `AIProcessor._parse_price()`
- **CAPTCHA handling**: Detects DataDome, reCAPTCHA, hCaptcha, Cloudflare via visible element selectors and page source checks; pauses for manual resolution
- **Vendor optimization**: Tries single-vendor first, then multi-vendor combinations up to `MAX_VENDOR_COMBINATIONS` (default 4)

# Leoni Government Bid Scraper

A robust Python web scraper for extracting government bid information from multiple procurement portals.

## Overview

This project consists of multiple robust scrapers, each targeting a different government bid portal:
- **PlanetBids Scraper**: Scrapes bid data from vendors.planetbids.com
- **OpenGov Scraper**: Scrapes procurement data from procurement.opengov.com
- **QuestCDN Scraper**: Scrapes bids from QuestCDN portals
- **Additional City/Portal Scrapers**: Includes artesia_scraper.py, bell_gardens_scraper.py, bidnet_scraper.py, calabasas_scraper.py, compton_scraper.py, earc_scraper.py, elsegundo_scraper.py, inglewood_scraper.py, lomita_scraper.py, monterey_park_scraper.py, new_city_scraper.py, paramount_scraper.py, planet_bids.py, san_fernando_scraper.py, san_gabriel_scraper.py, and more.

All scrapers are integrated into a single pipeline via `main.py`, with centralized date filtering, logging, and Airtable upload support.

## Features

- **Multi-site support**: Scrapes multiple cities/portals in a single run
- **📅 Centralized Date Filtering**: Single date filter configuration in main.py applies to all scrapers
- **⚡ Smart Filtering**: Early termination when old bids are found, saving time
- **Detail extraction**: Visits individual bid pages to extract comprehensive data
- **Session management**: Reuses browser sessions to minimize CAPTCHA solving
- **Robust error handling**: Continues scraping even if individual pages fail
- **Organized output**: Saves individual CSV files per city plus combined files
- **🤖 AI-Powered Analysis**: Automatic bid categorization using OpenRouter LLM integration
- **🔍 Smart Insights**: Risk assessment and business opportunity analysis

## File Structure

```
├── main.py                 # Entry point
├── planet_bids.py         # PlanetBids scraper
├── opengov.py            # OpenGov scraper  
├── utils.py              # Shared utility functions
├── planetbid/            # PlanetBids CSV outputs
├── opengov/              # OpenGov CSV outputs
└── requirements.txt      # Python dependencies
```

## Supported Cities

### PlanetBids (29 cities)
- Agoura Hills, Baldwin Park, Beverly Hills, Burbank, Carson
- Commerce, Culver City, Downey, Duarte, El Monte
- Gardena, Glendale, Hermosa Beach, Huntington Park
- La Cañada Flintridge, Lancaster, Lynwood, Maywood
- Norwalk, Palmdale, Palos Verdes Estates, Pico Rivera
- Pomona, Rosemead, San Dimas, Santa Fe Springs
- South Gate, Torrance, West Covina

### OpenGov (5 cities)
- Redondo Beach, City of Bell, Manhattan Beach
- Pasadena, Santa Monica

## Setup

1. **Create and activate a virtual environment (recommended):**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables (.env file)**:
   - **End users:** Ask your project admin or developer for the `.env` file and place it in the project folder. You do not need to edit or create this file yourself.
   - **Developers:** Copy `.env.example` to `.env` (or create a new `.env` file) and add your API keys and configuration as needed.

**End users:** You are done! You can now run the scraper as described above. You do not need to read further unless you plan to change or develop the code.

4. Configure date filters in `main.py`:
## Date Filter Configuration

The application uses centralized date filtering configured in `main.py`. You can adjust the date range in two ways:

**Option 1: Filter by days (recommended)**
```python
FILTER_DAYS = 150  # Only scrape bids from last X days
```

**Option 2: Filter by specific date**
```python
BID_FILTER_DATE = "06/01/2025"  # mm/dd/yyyy format
```

The date filter is automatically passed to both scrapers, ensuring consistent filtering across all portals.

## Usage

Run the main scraper (recommended):
```bash
python main.py
```

Or run individual scrapers:
```bash
python planet_bids.py    # PlanetBids only
python opengov.py        # OpenGov only
```

## Output

- Individual CSV files saved per city (e.g. `baldwin_park_planetbids_data.csv`)
- Combined CSV files with all data (`planetbids_data.csv`, `opengov.csv`)

## Requirements

- Python 3.8+
- Chrome browser
- Internet connection
- Manual CAPTCHA solving when prompted

## Retry Failed Pages

If some detail pages fail during scraping, you can retry them using several methods:

### 1. Automatic Retry (During Main Scraping)
The main scraper will offer to retry failed pages after completing the initial run:
```bash
python main.py
# After scraping completes, you'll be prompted:
# "🔄 X pages failed. Retry them? (y/n):"
```

### 2. Manual Retry Utility
Use the dedicated retry script for more control:

```bash
# Interactive mode
python retry_failed.py

# Retry specific URLs
python retry_failed.py --urls "url1,url2,url3"

# Retry URLs from a text file
python retry_failed.py --file failed_urls.txt
```

### 3. Programmatic Retry
In Python code:
```python
from planet_bids import retry_failed_pages

# retry_failed_pages expects a list of failed page dictionaries
# (same format as scraping_stats['failed_pages'])
recovered, still_failed = retry_failed_pages(failed_pages_list)
```

## AI Features 🤖

### Automatic Bid Categorization
The scraper automatically categorizes bids using AI:
```bash
python main.py  # AI categorization runs automatically
```

Categories include: Construction, IT Services, Professional Services, Maintenance, Equipment, Transportation, etc.

### Manual Analysis Tools

**Test LLM Integration:**
```bash
python test_llm.py
```

**Analyze Existing Data:**
```bash
python analyze_existing_data.py planetbid/planetbids_data.csv
```

**Custom Analysis in Python:**
```python
from utils import query_llm, analyze_bid_with_llm, batch_categorize_bids

# Basic LLM query
response = query_llm("What are key factors in government contracting?")

# Categorize a single bid
category = analyze_bid_with_llm(bid_data, "categorize")
risk = analyze_bid_with_llm(bid_data, "risk") 
insights = analyze_bid_with_llm(bid_data, "insights")

# Batch categorize multiple bids
categorized_bids = batch_categorize_bids(bids_list)
```

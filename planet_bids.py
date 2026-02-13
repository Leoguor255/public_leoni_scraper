"""
PlanetBids Scraper - Comprehensive Selenium-based Government Bid Scraper

This module provides complete scraping functionality for PlanetBids portals across
multiple California cities. It handles CAPTCHA solving, session management, 
summary table parsing, and detailed bid information extraction.

Key Features:
    - Multi-portal support with 29+ configured California cities
    - Interactive CAPTCHA solving workflow
    - Robust session management and retry logic
    - Individual and combined CSV output
    - Date filtering for recent bids only
    - Comprehensive bid detail extraction (35+ fields)

Author: Leonardo Gutarra
Created: 2025-01-27

Dependencies:
    - selenium: Web automation and browser control
    - beautifulsoup4: HTML parsing and data extraction
    - pandas: Data manipulation and CSV output
    - webdriver_manager: Automatic ChromeDriver management
    - python-dotenv: Environment variable management
    - requests: HTTP requests for LLM API integration

Usage:
    python planet_bids.py
    
    or
    
    from planet_bids import main
    main()
"""

# Standard library imports
import csv
import datetime
import re
import time
from typing import Dict, List, Optional, Tuple
import random

# Third-party imports
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

# Local imports
from utils import (
    analyze_bid_with_llm,
    batch_categorize_bids,
    clear_failed_urls_file,
    get_chromedriver_path,
    is_session_expired, 
    parse_mmddyyyy,
    save_failed_pages_batch, 
    query_llm,
    save_to_airtable_and_csv,
    send_to_airtable,
    upload_dataframe_to_airtable,
    wait_for_detail_page, 
    wait_for_summary_table,
    save_airtable_format_csv
)

# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================

# Portal ID to City Name Mapping
# Maps PlanetBids portal identifiers to human-readable city names for CSV output
# Used to create descriptive filenames like "agoura_hills_planetbids_data.csv"
# instead of generic "39478_planetbids_data.csv"
PORTAL_CITY_MAP = {
    "39478": "agoura_hills",          # Agoura Hills, CA
    "55389": "baldwin_park",          # Baldwin Park, CA  
    "39493": "beverly_hills",         # Beverly Hills, CA
    "14210": "burbank",               # Burbank, CA
    "32461": "carson",                # Carson, CA
    "32906": "commerce",              # Commerce, CA
    "39483": "culver_city",           # Culver City, CA
    "24661": "downey",                # Downey, CA
    "42035": "duarte",                # Duarte, CA
    "43375": "el_monte",              # El Monte, CA
    "39470": "gardena",               # Gardena, CA
    "39503": "glendale",              # Glendale, CA
    "51313": "hermosa_beach",         # Hermosa Beach, CA
    "72415": "huntington_park",       # Huntington Park, CA
    "62508": "la_canada_flintridge",  # La Cañada Flintridge, CA
    "42566": "lancaster",             # Lancaster, CA
    "39486": "lynwood",               # Lynwood, CA
    "64496": "maywood",               # Maywood, CA
    "33072": "norwalk",               # Norwalk, CA
    "23532": "palmdale",              # Palmdale, CA
    "50534": "palos_verdes_estates",  # Palos Verdes Estates, CA
    "41481": "pico_rivera",           # Pico Rivera, CA
    "24662": "pomona",                # Pomona, CA
    "54150": "rosemead",              # Rosemead, CA
    "69928": "san_dimas",             # San Dimas, CA
    "65093": "santa_fe_springs",      # Santa Fe Springs, CA
    "60317": "south_gate",            # South Gate, CA
    "47426": "torrance",              # Torrance, CA
    "39468": "west_covina",           # West Covina, CA
    "47476": "azusa",                 # Azusa, CA
    "33072": "montebello"             # Montebello, CA
}

# PlanetBids Portal URLs
# Each URL corresponds to a California city's bid portal
# Format: https://vendors.planetbids.com/portal/{PORTAL_ID}/bo/bo-search
# Add or remove entries as needed for different cities
URLS = [
    "https://vendors.planetbids.com/portal/39478/bo/bo-search",  # Agoura Hills
    "https://vendors.planetbids.com/portal/55389/bo/bo-search",  # Baldwin Park
    "https://vendors.planetbids.com/portal/39493/bo/bo-search",  # Beverly Hills
    "https://vendors.planetbids.com/portal/14210/bo/bo-search",  # Burbank
    "https://vendors.planetbids.com/portal/32461/bo/bo-search",  # Carson
    "https://vendors.planetbids.com/portal/32906/bo/bo-search",  # Commerce
    "https://vendors.planetbids.com/portal/39483/bo/bo-search",  # Culver City
    "https://vendors.planetbids.com/portal/24661/bo/bo-search",  # Downey
    "https://vendors.planetbids.com/portal/42035/bo/bo-search",  # Duarte
    "https://vendors.planetbids.com/portal/43375/bo/bo-search",  # El Monte
    "https://vendors.planetbids.com/portal/39470/bo/bo-search",  # Gardena
    "https://vendors.planetbids.com/portal/39503/bo/bo-search",  # Glendale
    "https://vendors.planetbids.com/portal/51313/bo/bo-search",  # Hermosa Beach
    "https://vendors.planetbids.com/portal/72415/bo/bo-search",  # Huntington Park
    "https://vendors.planetbids.com/portal/62508/bo/bo-search",  # La Cañada Flintridge
    "https://vendors.planetbids.com/portal/42566/bo/bo-search",  # Lancaster
    "https://vendors.planetbids.com/portal/39486/bo/bo-search",  # Lynwood
    "https://vendors.planetbids.com/portal/64496/bo/bo-search",  # Maywood
    "https://vendors.planetbids.com/portal/33072/bo/bo-search",  # Norwalk
    "https://vendors.planetbids.com/portal/23532/bo/bo-search",  # Palmdale
    "https://vendors.planetbids.com/portal/50534/bo/bo-search",  # Palos Verdes Estates
    "https://vendors.planetbids.com/portal/41481/bo/bo-search",  # Pico Rivera
    "https://vendors.planetbids.com/portal/24662/bo/bo-search",  # Pomona
    "https://vendors.planetbids.com/portal/54150/bo/bo-search",  # Rosemead
    "https://vendors.planetbids.com/portal/69928/bo/bo-search",  # San Dimas
    "https://vendors.planetbids.com/portal/65093/bo/bo-search",  # Santa Fe Springs
    "https://vendors.planetbids.com/portal/60317/bo/bo-search",  # South Gate
    "https://vendors.planetbids.com/portal/47426/bo/bo-search",  # Torrance
    "https://vendors.planetbids.com/portal/39468/bo/bo-search",  # West Covina
    "https://vendors.planetbids.com/portal/47476/bo/bo-search",  # Azusa
    "https://vendors.planetbids.com/portal/33072/bo/bo-search",  # Montebello
]

# Output Configuration
OUTPUT_CSV = "planetbid/planetbids_data.csv"  # Combined output for all portals

# Date Filter Configuration
# Date filter is now centralized in main.py and passed via date_filter parameter
# This ensures consistent filtering across all scrapers


def solve_captcha_and_scrape(url: str) -> str:
    """
    Interactive CAPTCHA solving workflow for PlanetBids portals.
    
    Opens a Chrome browser window, navigates to the specified URL, and waits
    for user to manually solve any CAPTCHA challenges. Once the user confirms
    the bids table has loaded, captures and returns the page source HTML.
    
    Args:
        url (str): PlanetBids portal URL to scrape
        
    Returns:
        str: Complete HTML source of the page after CAPTCHA is solved
        
    Raises:
        WebDriverException: If browser automation fails
        
    Note:
        This function requires user interaction to solve CAPTCHAs.
        The browser will remain open until the user presses ENTER.
    """
    print("\n" + "="*60)
    print(f"OPENING BROWSER - SOLVE THE CAPTCHA FOR: {url}")
    print("="*60)
    print("\nInstructions:")
    print("1. Browser will open automatically")
    print("2. Solve the CAPTCHA")
    print("3. Wait for the bids table to fully load")
    print("4. Come back here and press ENTER")
    print("="*60 + "\n")
    
    chrome_options = Options()
    
    driver = webdriver.Chrome(
        service=ChromeService(get_chromedriver_path()),
        options=chrome_options
    )
    
    try:
        print(f"Loading: {url}")
        driver.get(url)
        
        input(f"\n>>> Press ENTER after solving CAPTCHA and seeing the bids table for:\n    {url}\n... ")
        
        print("\nWaiting for page to fully render...")
        time.sleep(3)
        
        page_source = driver.page_source
        print("✓ Captured page source")
        
        return page_source
        
    finally:
        driver.quit()
        print("✓ Browser closed\n")


def parse_html(html: str) -> List[Dict[str, str]]:
    """
    Extract bid data from PlanetBids HTML table structure.
    
    Parses the HTML to locate the data table (with class 'pb-datatable data'),
    extracts bid information from table rows, and returns structured data.
    Limits extraction to first 5 rows for testing purposes.
    
    Args:
        html (str): Complete HTML source from PlanetBids page
        
    Returns:
        List[Dict[str, str]]: List of bid records with keys:
            - posted: Posting date
            - title: Project title  
            - invitation_num: Invitation/bid number
            - due_date: Submission due date
            - remaining: Time remaining
            - stage: Current bid stage
            - format: Response format
            
    Note:
        Currently limited to first 5 rows for development/testing.
        Remove [:5] limit in production for full data extraction.
    """
    print("Parsing HTML for bid data...")
    soup = BeautifulSoup(html, "html.parser")
    items = []

    # Find the DATA table specifically (not the fixed-header table)
    # Look for table with both 'pb-datatable' and 'data' classes
    tables = soup.find_all("table", class_="pb-datatable")
    print(f"  Found {len(tables)} table(s) with class 'pb-datatable'")
    
    data_table = None
    for idx, table in enumerate(tables):
        classes = table.get('class', [])
        print(f"  Table {idx + 1} classes: {classes}")
        
        # We want the table with 'data' class
        if 'data' in classes:
            data_table = table
            print(f"✓ Found DATA table (table {idx + 1})")
            break
    
    if not data_table:
        print("✗ Could not find table with class 'data'")
        return items
    
    # Look for tbody
    tbody = data_table.find("tbody")
    
    if tbody:
        print("✓ Found tbody")
        rows = tbody.find_all("tr")
    else:
        print("  No tbody, using all tr elements")
        rows = data_table.find_all("tr")
        # Skip thead rows
        if rows and rows[0].find("th"):
            rows = rows[1:]
    
    print(f"✓ Found {len(rows)} data rows")
    
    if len(rows) == 0:
        print("✗ No data rows found in table")
        return items
    
    # Parse each row (limit to first 5 for testing)
    for idx, row in enumerate(rows[:5], 1):
        cols = row.find_all("td")
        
        if not cols:
            continue
        
        row_data = [td.get_text(strip=True) for td in cols]
        
        # Debug first row
        if idx == 1:
            print(f"\nFirst row structure ({len(row_data)} columns):")
            for i, val in enumerate(row_data):
                preview = val[:60] + "..." if len(val) > 60 else val
                print(f"  Col {i}: {preview}")
            print()
        
        # Skip rows without enough data
        if len(row_data) < 5:
            continue
        
        item = {
            "posted": row_data[0] if len(row_data) > 0 else "",
            "title": row_data[1] if len(row_data) > 1 else "",
            "invitation_num": row_data[2] if len(row_data) > 2 else "",
            "due_date": row_data[3] if len(row_data) > 3 else "",
            "remaining": row_data[4] if len(row_data) > 4 else "",
            "stage": row_data[5] if len(row_data) > 5 else "",
            "format": row_data[6] if len(row_data) > 6 else ""
        }
        
        items.append(item)
    
    print(f"✓ Successfully parsed {len(items)} bids\n")
    return items


def save_to_csv(items: List[Dict], filename: str = OUTPUT_CSV):
    """
    Save scraped items to a CSV file (Airtable format only).
    
    Simple wrapper that calls the common utility function to save only
    the 5 Airtable columns: Project Name, Summary, Published Date, Due Date, Link.
    
    Note: The input items should already be in Airtable format from prepare_airtable_data()
    
    Args:
        items (List[Dict]): List of bid records (should be in Airtable format)
        filename (str): Output CSV filename (default: OUTPUT_CSV)
    """
    save_airtable_format_csv(items, filename, "PlanetBids")


def save_debug_html(html: str, filename: str = "debug_page.html"):
    """
    Save the captured HTML for debugging purposes.
    """
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✓ Saved raw HTML to {filename} (for debugging)")


def is_captcha_present(driver) -> bool:
    """
    Check if a CAPTCHA is actually present on the page.
    
    Returns True only if CAPTCHA elements are detected, False otherwise.
    This is more precise than checking for missing table (which could just be session expiry).
    
    Returns:
        bool: True if CAPTCHA elements found, False if no CAPTCHA detected
    """
    try:
        # Check for common CAPTCHA elements
        captcha_selectors = [
            "iframe[src*='captcha']",
            "iframe[src*='recaptcha']", 
            "input[name*='captcha']",
            "div.g-recaptcha",
            "div.recaptcha",
            "[id*='captcha']",
            "[class*='captcha']",
            "iframe[title*='recaptcha']"
        ]
        
        for selector in captcha_selectors:
            elements = driver.find_elements("css selector", selector)
            if elements:
                return True
                
        return False
    except Exception:
        return False


def is_data_table_present(driver) -> bool:
    """
    Check if the expected data table is present and visible.
    
    Returns:
        bool: True if data table found and displayed, False otherwise
    """
    try:
        table = driver.find_element("css selector", "table.pb-datatable.data")
        return table.is_displayed()
    except Exception:
        return False


def get_page_source_with_session(driver, url: str, max_retries: int = 3, long_wait_on_failure: bool = False) -> str:
    """
    Load URL with intelligent session management and CAPTCHA detection.
    Handles session expiry by automatically reloading, only prompts for user
    input when actual CAPTCHA is detected (not just missing table).
    If long_wait_on_failure is True, waits longer (30-120s) between retries if data table is missing.
    """
    print(f"Loading: {url}")
    for attempt in range(max_retries):
        driver.get(url)
        time.sleep(2)
        # Check if session expired first
        if is_session_expired(driver):
            print(f"[INFO] Session expired on attempt {attempt + 1}, reloading page...")
            time.sleep(3)  # Brief pause before retry
            continue
        # Check if data table is present (success case)
        if is_data_table_present(driver):
            print("✓ Data table found, proceeding...")
            break
        # Check if actual CAPTCHA is present
        if is_captcha_present(driver):
            print("\n" + "="*60)
            print(f"🔒 CAPTCHA DETECTED for: {url}")
            print("="*60)
            print("Please solve the CAPTCHA in the browser window.")
            print("The script will wait here until you complete it.")
            input(f"\n>>> Press ENTER after solving CAPTCHA and seeing the bids table loaded.\n... ")
            print("\nWaiting for page to fully render...")
            time.sleep(3)
            # Verify table is now present after CAPTCHA solving
            if is_data_table_present(driver):
                print("✓ Data table found after CAPTCHA solving")
                break
            else:
                print("⚠️  Data table still not found, trying reload...")
                continue
        else:
            # No CAPTCHA, no table, no session expiry - might be loading issue
            print(f"[INFO] Page loaded but data table not found (attempt {attempt + 1}). Retrying...")
            if long_wait_on_failure:
                wait_time = random.randint(30, 120)
                print(f"[INFO] Waiting {wait_time} seconds before retrying summary table load...")
                time.sleep(wait_time)
            else:
                time.sleep(5)
    else:
        # All retries exhausted
        raise Exception(f"Failed to load page with data table after {max_retries} attempts: {url}")
    page_source = driver.page_source
    print("✓ Captured page source")
    return page_source


def extract_detail_data(driver) -> dict:
    """
    Extracts detail data from the bid detail page using .bid-detail-item-title and .bid-detail-item-value divs.
    Adds debug output if extraction fails.
    """
    soup = BeautifulSoup(driver.page_source, "html.parser")
    detail = {}
    def get_val(label):
        title_div = soup.find("div", class_="bid-detail-item-title", string=lambda s: s and label in s)
        if not title_div:
            return ""
        value_div = title_div.find_next_sibling("div", class_="bid-detail-item-value")
        if not value_div:
            return ""
        # Get all text, including <br> and nested <div>
        return "\n".join([t.strip() for t in value_div.stripped_strings])
    # Only extract the fields you want in the output, in the specified order
    detail["project_title"] = get_val("Project Title")
    detail["invitation_num"] = get_val("Invitation #")
    detail["bid_posting_date"] = get_val("Bid Posting Date")
    detail["project_stage"] = get_val("Project Stage")
    detail["bid_due_date"] = get_val("Bid Due Date")
    detail["response_format"] = get_val("Response Format")
    detail["project_type"] = get_val("Project Type")
    detail["response_types"] = get_val("Response Types")
    detail["type_of_award"] = get_val("Type of Award")
    detail["categories"] = get_val("Categories")
    detail["license_requirements"] = get_val("License Requirements")
    detail["department"] = get_val("Department")
    detail["address"] = get_val("Address")
    detail["county"] = get_val("County")
    detail["bid_valid"] = get_val("Bid Valid")
    detail["liquidated_damages"] = get_val("Liquidated Damages")
    detail["estimated_bid_value"] = get_val("Estimated Bid Value")
    detail["start_delivery_date"] = get_val("Start/Delivery Date")
    detail["project_duration"] = get_val("Project Duration")
    detail["bid_bond"] = get_val("Bid Bond")
    detail["payment_bond"] = get_val("Payment Bond")
    detail["performance_bond"] = get_val("Performance Bond")
    detail["pre-bid_meeting"] = get_val("Pre-Bid Meeting")
    detail["online_qa"] = get_val("Online Q&A")
    detail["contact_info"] = get_val("Contact Info")
    detail["bids_to"] = get_val("Bids to")
    detail["owners_agent"] = get_val("Owner's Agent")
    detail["scope_of_services"] = get_val("Scope of Services")
    detail["other_details"] = get_val("Other Details")
    detail["notes"] = get_val("Notes")
    detail["special_notices"] = get_val("Special Notices")
    detail["local_programs_policies"] = get_val("Local Programs & Policies")
    detail["qa_deadline"] = get_val("Q&A Deadline")
    # source_url and detail_url are added in scrape_rows_and_details
    return detail


def scroll_to_load_all_rows(driver, pause_time: float = 1.5, max_attempts: int = 30, date_filter=None) -> int:
    """
    Efficiently scroll the bids table to load rows until date filter is reached.
    
    Repeatedly scrolls to trigger loading of additional rows, with intelligent
    early stopping when older bids are encountered (saves time and resources).
    
    Args:
        driver: Selenium WebDriver instance
        pause_time (float): Seconds to wait between scroll attempts
        max_attempts (int): Maximum scroll attempts before stopping
        date_filter: datetime.date or None. Stop when last row is older than filter
        
    Returns:
        int: Total number of rows loaded
        
    Note:
        Optimized to stop scrolling as soon as old bids are found, preventing
        unnecessary loading of hundreds of irrelevant old records.
    """
    # Ensure table is present before starting scroll
    if not is_data_table_present(driver):
        print("[ERROR] Data table not found. Cannot perform infinite scroll.")
        return 0
    
    if date_filter:
        print(f"🗓️  Smart scrolling enabled - will stop at bids older than {date_filter.strftime('%m/%d/%Y')}")
    
    last_row_count = 0
    attempts = 0
    old_bids_found = 0  # Track consecutive old bids to confirm we've passed the cutoff
    
    while attempts < max_attempts:
        soup = BeautifulSoup(driver.page_source, "html.parser")
        table = soup.find("table", class_="pb-datatable data")
        if not table:
            print("[ERROR] Could not find data table during infinite scroll. Check for session expiry, CAPTCHA, or page load issues.")
            return 0
        
        tbody = table.find("tbody") if table else None
        rows = tbody.find_all("tr") if tbody else table.find_all("tr")
        row_count = len(rows)
        
        # No new rows loaded - natural end
        if row_count == last_row_count:
            print(f"📜 Scrolling complete - no more rows to load ({row_count} total)")
            break
        
        # Check if we've hit the date filter threshold
        if date_filter and rows:
            # Check last few rows for old dates (more reliable than just last row)
            recent_rows = rows[-min(5, len(rows)):]  # Check last 5 rows or fewer
            old_count = 0
            
            for row in recent_rows:
                tds = row.find_all("td")
                date_str = tds[0].get_text(strip=True) if tds else ""
                date_obj = parse_mmddyyyy(date_str)
                if date_obj and date_obj < date_filter:
                    old_count += 1
            
            # If most recent rows are old, we've passed the cutoff
            if old_count >= min(3, len(recent_rows)):
                print(f"🛑 Smart scroll stopped - found {old_count} old bids in recent rows")
                print(f"   Total rows loaded: {row_count} (efficient filtering saved time)")
                break
        
        last_row_count = row_count
        
        # Show progress for long scroll sessions
        if attempts % 10 == 0 and attempts > 0:
            print(f"   📊 Scroll progress: {row_count} rows loaded (attempt {attempts})")
        
        # Scroll to trigger more loading
        # Scroll to the last row
        try:
            last_row = driver.find_elements("css selector", "table.pb-datatable.data tbody tr")[-1]
            driver.execute_script("arguments[0].scrollIntoView();", last_row)
        except Exception:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(pause_time)
        attempts += 1
    return last_row_count


def scrape_rows_and_details(driver, url: str, city_name: str, portal_id: str, row_limit: Optional[int] = None, date_filter: str = None) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """
    Extract bid data from summary table and scrape detailed information.
    
    Loads the summary table page, performs infinite scroll to load all rows,
    extracts row identifiers, and visits each detail page to gather comprehensive
    bid information. Applies date filtering throughout the process.
    
    Args:
        driver: Selenium WebDriver instance
        url (str): Summary page URL to scrape
        row_limit (Optional[int]): Maximum rows to process (for testing)
        
    Returns:
        Tuple[List[Dict[str, str]], List[Dict[str, str]]]: Tuple containing:
            - List of complete bid records with detail data
            - List of failed detail pages with error information
    """
    # Use the improved session handling to load the page
    try:
        get_page_source_with_session(driver, url)
    except Exception as e:
        print(f"✗ Failed to load summary page: {e}")
        return [], []
    # Use passed date filter or no filtering
    if not date_filter:
        print("⚠️  No date filter provided - processing all bids")
        filter_date = None
        filter_date_str = "none"
    else:
        filter_date_str = date_filter
        filter_date = parse_mmddyyyy(filter_date_str)
    
    # Intelligent scrolling - stops early when old bids are found
    print(f"🗓️  Applying date filter: Only bids from {filter_date_str} onward")
    total_rows_loaded = scroll_to_load_all_rows(driver, date_filter=filter_date)
    
    # Parse the loaded data
    soup = BeautifulSoup(driver.page_source, "html.parser")
    table = soup.find("table", class_="pb-datatable data")
    if not table:
        print("✗ Could not find data table on page")
        return [], []
    
    tbody = table.find("tbody")
    rows = tbody.find_all("tr") if tbody else table.find_all("tr")
    print(f"✓ Found {len(rows)} data rows")
    # Extract portal id from url
    import re
    m = re.search(r"portal/(\d+)/", url)
    portal_id = m.group(1) if m else ""
    detail_urls = []
    skipped = 0
    for idx, row in enumerate(rows):
        row_id = row.get("rowattribute")
        if not row_id or not portal_id:
            continue
        # Extract bid_posting_date from the row's first cell (assumes first td is posting date)
        tds = row.find_all("td")
        bid_posting_date_str = tds[0].get_text(strip=True) if tds else ""
        bid_posting_date = parse_mmddyyyy(bid_posting_date_str)
        if not bid_posting_date:
            skipped += 1
            continue
        if filter_date and bid_posting_date < filter_date:
            skipped += 1
            continue  # Skip rows before filter date
        detail_url = f"https://vendors.planetbids.com/portal/{portal_id}/bo/bo-detail/{row_id}"
        detail_urls.append((detail_url, bid_posting_date_str))
    # Show filtering efficiency
    total_found = len(detail_urls) + skipped
    if skipped > 0:
        print(f"✓ Found {len(detail_urls)} recent bids (filtered out {skipped} older bids)")
        print(f"   📊 Efficiency: Only scraping {len(detail_urls)}/{total_found} detail pages ({(len(detail_urls)/total_found*100):.1f}%)")
    else:
        print(f"✓ Found {len(detail_urls)} bids to process (all within date filter)")
    items = []
    failed_pages_for_site = []  # Track failed pages for this specific site
    
    for idx, (detail_url, bid_posting_date_str) in enumerate(detail_urls):
        print(f"Visiting detail page {idx+1}/{len(detail_urls)}: {detail_url}")
        max_retries = 3
        loaded = False
        
        for attempt in range(max_retries):
            driver.get(detail_url)
            time.sleep(2)
            
            # Check for session expiry and handle automatically
            if is_session_expired(driver):
                print(f"[INFO] Session expired on detail page, reloading (attempt {attempt + 1})...")
                time.sleep(3)
                continue
                
            # Check for CAPTCHA on detail page (rare but possible)
            if is_captcha_present(driver):
                print("\n" + "="*60)
                print(f"🔒 CAPTCHA DETECTED on detail page: {detail_url}")
                print("="*60)
                print("Please solve the CAPTCHA in the browser window.")
                input(f"\n>>> Press ENTER after solving CAPTCHA on detail page.\n... ")
                time.sleep(3)
            
            # Try to load the detail page
            loaded = wait_for_detail_page(driver, timeout=30)
            if loaded:
                break
                
            print(f"[INFO] Detail page did not load properly, retrying (attempt {attempt + 1}/{max_retries})...")
            time.sleep(2)
        
        if not loaded:
            print(f"⚠️  Failed to load detail page after retries, skipping...")
            failed_pages_for_site.append({
                'detail_url': detail_url,
                'bid_posting_date': bid_posting_date_str,
                'reason': 'Page failed to load after multiple retries'
            })
            continue
        detail = extract_detail_data(driver)
        detail["city_name"] = city_name.replace('_', ' ').title()  # Add city name to each record
        detail["portal_id"] = portal_id  # Add portal ID to each record
        detail["source_url"] = url
        detail["detail_url"] = detail_url
        if bid_posting_date_str:
            detail["bid_posting_date"] = bid_posting_date_str
        # Only add if at least one main field is non-empty (not just bid_posting_date, source_url, detail_url)
        main_fields = [k for k in detail.keys() if k not in ("bid_posting_date", "source_url", "detail_url")]
        if any(detail[k] for k in main_fields):
            items.append(detail)
        # Skip empty detail pages silently
    return items, failed_pages_for_site


def scrape_all(urls: List[str], date_filter: str = None) -> Tuple[pd.DataFrame, Dict]:
    """
    Scrape multiple PlanetBids URLs in a single browser session.
    
    Uses a persistent Chrome browser session to scrape all configured URLs,
    handling session management, CAPTCHA solving, and data extraction.
    Saves individual CSV files for each city and returns combined results.
    
    Args:
        urls (List[str]): List of PlanetBids portal URLs to scrape
        date_filter (str): Date filter in MM/DD/YYYY format (overrides default)
        
    Returns:
        tuple[pd.DataFrame, dict]: Combined DataFrame with all scraped bid data
            and scraping statistics dictionary
        
    Raises:
        WebDriverException: If browser automation fails
        Exception: For other errors during scraping process
        
    Output:
        - Individual city CSV files in planetbid/ directory
        - Combined CSV file with all results
        - Console progress updates and error reporting
    """
    all_items = []
    scraping_stats = {
        'successful_sites': [],
        'skipped_sites': [],
        'failed_pages': [],  # Track individual failed detail pages
        'sample_bid': None,
        'total_bids': 0,
        'total_sites_attempted': len(urls),
        'total_sites_successful': 0,
        'total_pages_attempted': 0,
        'total_pages_failed': 0
    }
    
    # Open browser once for the entire session  
    chrome_options = Options()
    driver = webdriver.Chrome(
        service=ChromeService(get_chromedriver_path()),
        options=chrome_options
    )
    
    try:
        for url in urls:
            print(f"\n[INFO] Processing URL: {url}")
            
            # Extract portal id from url
            import re
            m = re.search(r"portal/(\d+)/", url)
            portal_id = m.group(1) if m else "unknown"
            city_name = PORTAL_CITY_MAP.get(portal_id, portal_id)
            
            try:
                # Get page source and handle CAPTCHA if needed
                html = get_page_source_with_session(driver, url, max_retries=5, long_wait_on_failure=True)
                
                # Scrape rows and details for this URL
                items, failed_pages = scrape_rows_and_details(driver, url, city_name, portal_id, date_filter=date_filter)
                
                # Track page-level statistics
                scraping_stats['total_pages_attempted'] += len(items) + len(failed_pages)
                scraping_stats['total_pages_failed'] += len(failed_pages)
                
                # Add failed pages to global tracking with city context
                for failed_page in failed_pages:
                    scraping_stats['failed_pages'].append({
                        'city_name': city_name.replace('_', ' ').title(),
                        'portal_id': portal_id,
                        'detail_url': failed_page['detail_url'],
                        'bid_posting_date': failed_page['bid_posting_date'],
                        'reason': failed_page['reason']
                    })
                
                if items:
                    print(f"[INFO] Extracted {len(items)} items from {url}")
                    
                    # Track successful site
                    scraping_stats['successful_sites'].append({
                        'city_name': city_name.replace('_', ' ').title(),
                        'portal_id': portal_id,
                        'url': url,
                        'bids_found': len(items)
                    })
                    scraping_stats['total_sites_successful'] += 1
                    scraping_stats['total_bids'] += len(items)
                    
                    # Capture sample bid from first successful site (if not already captured)
                    if not scraping_stats['sample_bid'] and items:
                        scraping_stats['sample_bid'] = {
                            'city_name': city_name.replace('_', ' ').title(),
                            'portal_id': portal_id,
                            'summary_page_url': url,
                            'detail_page_url': items[0].get('detail_url', 'N/A'),
                            'project_title': items[0].get('project_title', 'N/A'),
                            'bid_posting_date': items[0].get('bid_posting_date', 'N/A'),
                            'invitation_num': items[0].get('invitation_num', 'N/A')
                        }
                    
                    # Add items to combined list (no individual CSV saving)
                    all_items.extend(items)
                else:
                    print(f"[WARN] No items found for {url}")
                    # Track as skipped site with reason
                    scraping_stats['skipped_sites'].append({
                        'city_name': city_name.replace('_', ' ').title(),
                        'portal_id': portal_id,
                        'url': url,
                        'reason': 'Page did not load properly or no bids found'
                    })
                    # Also add to failed_pages so it gets saved to failed_urls.txt
                    scraping_stats['failed_pages'].append({
                        'url': url,
                        'city_name': city_name.replace('_', ' ').title(),
                        'portal_id': portal_id,
                        'reason': 'Summary page did not load or no bids found'
                    })

            except Exception as e:
                print(f"[ERROR] Failed to scrape {url}: {e}")
                # Track as skipped site with error reason
                scraping_stats['skipped_sites'].append({
                    'city_name': city_name.replace('_', ' ').title(),
                    'portal_id': portal_id,
                    'url': url,
                    'reason': f'Error: {str(e)[:100]}...' if len(str(e)) > 100 else str(e)
                })
                # Also add to failed_pages so it gets saved to failed_urls.txt
                scraping_stats['failed_pages'].append({
                    'url': url,
                    'city_name': city_name.replace('_', ' ').title(),
                    'portal_id': portal_id,
                    'reason': f'Error: {str(e)[:100]}...' if len(str(e)) > 100 else str(e)
                })
                continue
                
    finally:
        driver.quit()
        print("[INFO] Browser session closed.")
    
    # Save combined CSV
    if all_items:
        print(f"\n[INFO] Processing {len(all_items)} total items...")
        
        # Add AI categorization to scraped bids (optional)
        try:
            print(f"\n🤖 Adding AI categorization to {len(all_items)} bids...")
            all_items = batch_categorize_bids(all_items)
            print("✅ AI categorization completed!")
        except Exception as e:
            print(f"⚠️  AI categorization failed: {e}")
            print("   (Continuing without AI categories)")
        
        df = pd.DataFrame(all_items)
        
        # Ensure columns are in the right order (add city info and ai_category if present)
        cols = [
            "city_name", "portal_id", "project_title", "invitation_num", "bid_posting_date", "project_stage", "bid_due_date", 
            "response_format", "project_type", "response_types", "type_of_award", "categories", 
            "license_requirements", "department", "address", "county", "bid_valid", 
            "liquidated_damages", "estimated_bid_value", "start_delivery_date", "project_duration", 
            "bid_bond", "payment_bond", "performance_bond", "pre-bid_meeting", "online_qa", 
            "contact_info", "bids_to", "owners_agent", "scope_of_services", "other_details", 
            "notes", "special_notices", "local_programs_policies", "qa_deadline", 
            "source_url", "detail_url"
        ]
        
        # Add ai_category column if it exists in the data
        if all_items and 'ai_category' in all_items[0]:
            cols.insert(-2, "ai_category")  # Insert before source_url and detail_url
            
        df = df.reindex(columns=cols)
        df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
        print(f"✓ Saved combined CSV to {OUTPUT_CSV}")
        return df, scraping_stats
    else:
        print("[WARN] No data to save to combined CSV")
        return pd.DataFrame(), scraping_stats


def display_scraping_report(stats: dict) -> None:
    """
    Display comprehensive scraping report with statistics and sample data.
    
    Shows successful sites, skipped sites with reasons, and sample bid
    opportunity with all relevant URLs for verification.
    
    Args:
        stats (dict): Scraping statistics dictionary from scrape_all()
    """
    print("\n" + "="*80)
    print("📊 SCRAPING REPORT")
    print("="*80)
    
    # Overall Statistics
    print(f"🎯 OVERALL STATISTICS:")
    print(f"   • Total sites attempted: {stats['total_sites_attempted']}")
    print(f"   • Successfully scraped: {stats['total_sites_successful']}")
    print(f"   • Sites skipped: {len(stats['skipped_sites'])}")
    print(f"   • Total bids found: {stats['total_bids']}")
    print(f"   • Total detail pages attempted: {stats['total_pages_attempted']}")
    print(f"   • Detail pages failed: {stats['total_pages_failed']}")
    print(f"   • Site success rate: {(stats['total_sites_successful']/stats['total_sites_attempted']*100):.1f}%")
    if stats['total_pages_attempted'] > 0:
        print(f"   • Page success rate: {((stats['total_pages_attempted']-stats['total_pages_failed'])/stats['total_pages_attempted']*100):.1f}%")
    
    # Successful Sites
    if stats['successful_sites']:
        print(f"\n✅ SUCCESSFULLY SCRAPED SITES ({len(stats['successful_sites'])}):")
        for site in stats['successful_sites']:
            print(f"   • {site['city_name']} (Portal {site['portal_id']}): {site['bids_found']} bids")
    
    # Skipped Sites
    if stats['skipped_sites']:
        print(f"\n⚠️  SKIPPED SITES ({len(stats['skipped_sites'])}):")
        for site in stats['skipped_sites']:
            print(f"   • {site['city_name']} (Portal {site['portal_id']})")
            print(f"     Reason: {site['reason']}")
            print(f"     URL: {site['url']}")
    
    # Failed Detail Pages
    if stats['failed_pages']:
        print(f"\n❌ FAILED DETAIL PAGES ({len(stats['failed_pages'])}):")
        # Group by city for better organization
        from collections import defaultdict
        pages_by_city = defaultdict(list)
        for page in stats['failed_pages']:
            pages_by_city[page['city_name']].append(page)
        
        for city_name, pages in pages_by_city.items():
            print(f"   📍 {city_name}:")
            for page in pages:
                print(f"      • Posted: {page['bid_posting_date']}")
                print(f"        URL: {page['detail_url']}")
                print(f"        Reason: {page['reason']}")
    
    print("="*80)


def retry_failed_pages(failed_pages_list, retry_all=False):
    """
    Retry failed detail pages with extended timeouts and better error handling.
    """
    if not failed_pages_list:
        print("✓ No failed pages to retry")
        return [], []
    
    print(f"\n🔄 RETRY FAILED DETAIL PAGES ({len(failed_pages_list)} total)")
    print("="*60)
    
    # Group by city
    from collections import defaultdict
    pages_by_city = defaultdict(list)
    for page in failed_pages_list:
        pages_by_city[page['city_name']].append(page)
    
    recovered_items = []
    still_failed = []
    
    chrome_options = Options()
    driver = webdriver.Chrome(
        service=ChromeService(get_chromedriver_path()),
        options=chrome_options
    )
    
    try:
        for city_name, pages in pages_by_city.items():
            if not retry_all:
                response = input(f"\nRetry {len(pages)} failed pages from {city_name}? (y/n/all): ").lower()
                if response == 'n':
                    still_failed.extend(pages)
                    continue
                elif response == 'all':
                    retry_all = True
            
            print(f"\n📍 Retrying {city_name}: {len(pages)} pages")
            
            for idx, page in enumerate(pages, 1):
                detail_url = page['detail_url']
                print(f"  {idx}/{len(pages)}: {detail_url}")
                
                success = False
                for attempt in range(2):
                    try:
                        print(f"    🌐 Loading URL (attempt {attempt + 1})...")
                        driver.get(detail_url)
                        
                        # Wait longer for page to load completely
                        time.sleep(5)  # Initial wait for page load
                        
                        # Check for session expiry first
                        if is_session_expired(driver):
                            print(f"    📱 Session expired, reloading...")
                            continue
                        
                        # Check for CAPTCHA and handle it properly
                        if is_captcha_present(driver):
                            print(f"\n    🔒 CAPTCHA detected on: {detail_url}")
                            print(f"    Please solve the CAPTCHA in the browser window.")
                            input(f"    >>> Press ENTER after solving CAPTCHA and page has loaded completely...\n    ")
                            
                            # Wait for page to load after CAPTCHA solving
                            print(f"    ⏳ Waiting for page to load after CAPTCHA...")
                            time.sleep(5)
                        
                        # Now check if the detail page loaded successfully
                        if wait_for_detail_page(driver, timeout=30):
                            print(f"    ✅ Page loaded successfully, extracting data...")
                            detail = extract_detail_data(driver)
                            detail["source_url"] = f"retry_{city_name.lower().replace(' ', '_')}"
                            detail["detail_url"] = page['detail_url']
                            detail["bid_posting_date"] = page['bid_posting_date']
                            
                            main_fields = [k for k in detail.keys() if k not in ("bid_posting_date", "source_url", "detail_url")]
                            if any(detail[k] for k in main_fields):
                                recovered_items.append(detail)
                                print(f"    ✅ Recovered successfully!")
                                success = True
                                break
                            else:
                                print(f"    ⚠️  Page loaded but no meaningful data found")
                        else:
                            print(f"    ⏳ Page still loading, trying again...")
                            time.sleep(3)
                        
                    except Exception as e:
                        print(f"    ❌ Attempt {attempt + 1} failed: {str(e)[:50]}...")
                        time.sleep(3)
                
                if not success:
                    still_failed.append(page)
                    print(f"    ❌ Still failed after all attempts")
                    
    finally:
        driver.quit()
    
    print(f"\n📊 RETRY RESULTS:")
    print(f"   • Originally failed: {len(failed_pages_list)}")
    print(f"   • Recovered: {len(recovered_items)}")
    print(f"   • Still failed: {len(still_failed)}")
    if len(failed_pages_list) > 0:
        print(f"   • Recovery rate: {(len(recovered_items)/len(failed_pages_list)*100):.1f}%")
    
    return recovered_items, still_failed


def handle_session_recovery(driver, url: str, max_retries: int = 3) -> bool:
    """
    Handle automatic session recovery without user intervention.
    
    Attempts to recover from session expiry by reloading the page.
    Only prompts user if actual CAPTCHA is detected.
    
    Args:
        driver: Selenium WebDriver instance
        url (str): URL to reload
        max_retries (int): Maximum reload attempts
        
    Returns:
        bool: True if session recovered successfully, False otherwise
    """
    for attempt in range(max_retries):
        print(f"[INFO] Attempting session recovery (attempt {attempt + 1}/{max_retries})...")
        
        driver.refresh()
        time.sleep(3)
        
        # Check if session is still expired
        if is_session_expired(driver):
            print(f"[INFO] Session still expired after refresh, trying full reload...")
            driver.get(url)
            time.sleep(3)
            continue
            
        # Check if CAPTCHA appeared during reload
        if is_captcha_present(driver):
            print("\n" + "="*60)
            print(f"🔒 CAPTCHA appeared during session recovery for: {url}")
            print("="*60)
            print("Please solve the CAPTCHA to continue.")
            input(f"\n>>> Press ENTER after solving CAPTCHA.\n... ")
            time.sleep(3)
            
        # Check if we now have the data table
        if is_data_table_present(driver):
            print("✅ Session recovered successfully!")
            return True
            
        time.sleep(2)
    
    print(f"❌ Failed to recover session after {max_retries} attempts")
    return False


def print_portal_summary(city_summaries, portal_name):
    print(f"\n➡️  [{portal_name}] Scraping summary:")
    total = 0
    for city, count in city_summaries.items():
        if count > 0:
            print(f"   - {city}: {count} RFPs scraped")
        else:
            print(f"   - {city}: 0 RFPs found")
        total += count
    if total > 0:
        print(f"✅  [{portal_name}] Total: {total} RFPs scraped\n")
    else:
        print(f"❌  [{portal_name}] No RFPs found or failed to scrape\n")


def main() -> None:
    """
    Main execution function for PlanetBids scraper.
    
    Orchestrates the complete scraping workflow:
    1. Processes all configured URLs in URLS list
    2. Handles CAPTCHA solving and session management  
    3. Extracts summary and detail data for each portal
    4. Saves individual CSV files per city
    5. Creates combined CSV with all results
    6. Provides status reporting and error handling
    
    Returns:
        None
        
    Raises:
        KeyboardInterrupt: If user cancels scraping with Ctrl+C
        Exception: For other unexpected errors during scraping
        
    Output Files:
        - Individual CSVs: planetbid/{city_name}_planetbids_data.csv
        - Combined CSV: planetbid/planetbids_data.csv
    """
    print("\n" + "="*60)
    print("PLANETBIDS SCRAPER")
    print("="*60)
    
    try:
        # Scrape all configured URLs and produce a combined CSV
        df, scraping_stats = scrape_all(URLS)

        # Display comprehensive scraping report
        display_scraping_report(scraping_stats)

        # Save failed URLs to unified text file
        if scraping_stats.get('failed_pages'):
            save_failed_pages_batch(scraping_stats['failed_pages'], 'PlanetBids')
            
            # Also keep CSV for detailed analysis if needed
            failed_df = pd.DataFrame(scraping_stats['failed_pages'])
            failed_csv_path = "planetbid/failed_urls.csv"
            failed_df.to_csv(failed_csv_path, index=False, encoding="utf-8")
            print(f"📁 Detailed failed data also saved to: {failed_csv_path}")
            print(f"   ({len(scraping_stats['failed_pages'])} failed detail pages recorded)")

        if not df.empty:
            print(f"\n🎉 SCRAPING COMPLETED SUCCESSFULLY!")
            print(f"   Combined CSV saved to: {OUTPUT_CSV}")
            print(f"   Total records: {len(df)}")
        else:
            print(f"\n⚠️  SCRAPING COMPLETED WITH NO DATA")
            print(f"   Check individual site errors above for troubleshooting")

    except KeyboardInterrupt:
        print("\n\n✗ Scraping cancelled by user")
    except Exception as e:
        print(f"\n✗ An error occurred: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
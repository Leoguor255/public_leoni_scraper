"""
OpenGov Procurement Portal Scraper

This module provides comprehensive scraping functionality for OpenGov procurement
portals across multiple California cities. It extracts both summary table data
and detailed bid information with robust session management and anti-bot measures.

Key Features:
    - Multi-portal support for 5+ California cities
    - Undetected Chrome browser to bypass bot detection
    - JSON-based project ID extraction with fuzzy matching
    - Comprehensive bid detail extraction (35+ fields)
    - Date filtering for recent bids only
    - Individual and combined CSV output
    - Robust error handling and retry logic

Author: Development Team
Created: 2025-01-27
Modified: 2025-01-27

Dependencies:
    - selenium: Web automation and browser control
    - undetected-chromedriver: Anti-bot detection browser
    - beautifulsoup4: HTML parsing and data extraction
    - pandas: Data manipulation and CSV output
    - webdriver_manager: Automatic ChromeDriver management

Usage:
    python opengov.py
    
    or
    
    from opengov import main
    main()
"""

# Standard library imports
import csv
import json
import re
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# Third-party imports
import pandas as pd
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

# Local imports
from utils import (
    clear_failed_urls_file,
    parse_mmddyyyy, 
    save_failed_pages_batch,
    wait_for_summary_table,
    save_airtable_format_csv
)

def to_iso_date(date_str):
    # Try MM/DD/YYYY first
    try:
        return datetime.strptime(date_str, "%m/%d/%Y").strftime("%Y-%m-%d")
    except Exception:
        pass
    # Try already ISO
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y-%m-%d")
    except Exception:
        pass
    return ""  # fallback

def detect_human_verification(driver, wait_time: int = 3) -> bool:  # Reduced from 5 to 3
    """
    Detect if a human verification challenge (e.g., CAPTCHA, "I'm not a robot") is present.
    Waits for elements to load before checking.
    
    Args:
        driver: Selenium WebDriver instance
        wait_time: Time to wait for verification elements to appear
        
    Returns:
        bool: True if human verification is detected, False otherwise
    """
    print(f"🔍 Checking for human verification challenges...")
    
    # Wait a bit for verification elements to load
    time.sleep(wait_time)
    
    verification_selectors = [
        # Common reCAPTCHA selectors
        "iframe[src*='recaptcha']",
        ".g-recaptcha",
        "#recaptcha",
        
        # Cloudflare challenge selectors
        ".cf-challenge-running",
        ".cf-browser-verification",
        "[data-ray]",  # Cloudflare ray ID
        ".challenge-running",
        ".challenge-form",
        
        # Generic verification patterns
        "*[title*='robot']",
        "*[title*='verification']",
        "*[title*='human']",
        "*[aria-label*='robot']",
        "*[aria-label*='verification']",
        
        # Common button text patterns
        "*[value*='robot']",
        "*[value*='human']",
        
        # Checkbox patterns
        "input[type='checkbox'][title*='robot']",
        "input[type='checkbox'][aria-label*='robot']",
        
        # Specific OpenGov/security challenge patterns
        ".challenge-container",
        ".security-check",
        ".verify-container"
    ]
    
    try:
        for selector in verification_selectors:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                # Double-check if element is visible
                for element in elements:
                    if element.is_displayed():
                        print(f"   ✓ Found verification element: {selector}")
                        return True
        
        # Also check for common text patterns in page content
        page_text = driver.page_source.lower()
        verification_texts = [
            "i'm not a robot",
            "verify you are human", 
            "security check",
            "please verify",
            "captcha",
            "cloudflare",
            "checking your browser",
            "verifying you are human",
            "complete the security check"
        ]
        
        for text in verification_texts:
            if text in page_text:
                print(f"   ✓ Found verification text: '{text}'")
                return True
        
        # Check for loading/challenge indicators
        loading_indicators = [
            ".challenge-running",
            ".cf-spinner",
            "[data-testid='challenge-spinner']"
        ]
        
        for selector in loading_indicators:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            if elements and any(el.is_displayed() for el in elements):
                print(f"   ⏳ Found loading challenge indicator: {selector}")
                return True
                
        print(f"   ✓ No verification challenges detected")
        return False
        
    except Exception as e:
        print(f"   ⚠️  Error detecting verification: {e}")
        # If we can't determine, assume verification might be needed for safety
        return True

# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================

# OpenGov Procurement Portal URLs  
# Each URL corresponds to a California city's procurement portal
# Format: https://procurement.opengov.com/portal/{PORTAL_CODE}
# Add or remove entries as needed for different cities
URLS = [
    "https://procurement.opengov.com/portal/cityofbell",     # City of Bell, CA
    "https://procurement.opengov.com/portal/redondo",        # Redondo Beach, CA
    "https://procurement.opengov.com/portal/citymb",         # Manhattan Beach, CA
    "https://procurement.opengov.com/portal/pasadena",       # Pasadena, CA
    "https://procurement.opengov.com/portal/santa-monica-ca" # Santa Monica, CA
]

# Output Configuration
OUTPUT_CSV = "opengov/opengov.csv"  # Combined output for all portals

# Date Filter Configuration  
# Date filter is now centralized in main.py and passed via date_filter parameter
# This ensures consistent filtering across all scrapers


# =============================================================================
# CORE SCRAPING FUNCTIONS
# =============================================================================

def scrape_detail_page(driver, portal_code: str, project_id: str, source_url: Optional[str] = None, summary_project_title: Optional[str] = None) -> Tuple[Dict[str, str], str]:
    """
    Extract detailed bid information from OpenGov project detail page.
    
    Navigates to the project detail page and scrapes comprehensive information
    including bid process details, timeline, summary, contact information,
    and additional project metadata.
    
    Args:
        driver: Selenium WebDriver instance for browser automation
        portal_code (str): Portal identifier (e.g., 'redondo', 'cityofbell')
        project_id (str): Unique project identifier from summary table
        source_url (Optional[str]): Original URL where project was found
        
    Returns:
        Tuple[Dict[str, str], str]: A tuple containing:
            - detail_dict: Extracted project details with 35+ fields
            - detail_url: Full URL of the project detail page
            
    Raises:
        TimeoutException: If page fails to load within 60 seconds
        WebDriverException: If browser automation fails
        
    Note:
        Waits for '.internal-information-section' element to ensure
        page has fully loaded before scraping.
    """
    detail_url = f"https://procurement.opengov.com/portal/{portal_code}/projects/{project_id}"
    print(f"  Visiting detail page: {detail_url}")
    driver.get(detail_url)
    # Wait for the Post Information section to load
    WebDriverWait(driver, 60).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".internal-information-section"))
    )
    # Check for human verification after navigation
    if detect_human_verification(driver):
        print("\n" + "="*60)
        print(f"🤖 HUMAN VERIFICATION DETECTED (DETAIL PAGE)")
        print(f"Portal: {portal_code}")
        print(f"URL: {detail_url}")
        print("="*60)
        print("Instructions:")
        print("1. Complete the human verification (checkbox/CAPTCHA)")
        print("2. Wait for the detail page to load completely")
        print("3. Press ENTER here to continue scraping")
        print("="*60)
        input(f">>> Press ENTER when verification is complete and detail is visible for {portal_code}...\n")
        print(f"⏳ Waiting for detail page to load after verification...")
        time.sleep(3)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    # Sealed Bid Process & Private Bid
    info = {}
    for dt in soup.select(".internal-information-dl-list dt"):
        dd = dt.find_next_sibling("dd")
        if not dd:
            continue
        label = dt.get_text(strip=True)
        value = dd.get_text(strip=True)
        if "Sealed Bid Process" in label:
            info["sealed_bid_process"] = value
        elif "Private Bid" in label:
            info["private_bid"] = value
    # Summary
    summary = ""
    summary_div = soup.select_one(".introduction-description.article")
    if summary_div:
        summary = summary_div.get_text(strip=True)
    info["summary"] = summary
    # Timeline
    timeline = {}
    for group in soup.select(".timeline-group"):
        header = group.select_one(".timeline-header")
        value = header.find_next_sibling("div") if header else None
        if not (header and value):
            continue
        label = header.get_text(strip=True)
        val = value.get_text(" ", strip=True)
        if "Release Project Date" in label:
            timeline["release_project_date"] = val
        elif "Question Submission Deadline" in label:
            timeline["question_submission_deadline"] = val
        elif "Proposal Submission Deadline" in label:
            timeline["proposal_submission_deadline"] = val
    info.update(timeline)
    
    # Map timeline fields to Airtable-compatible names for main.py
    # Preserve original field names and also create Airtable-compatible mappings
    if timeline.get("release_project_date"):
        info["Release Date"] = timeline["release_project_date"]  # For Airtable Published Date mapping
    if timeline.get("proposal_submission_deadline"):
        info["Due Date"] = timeline["proposal_submission_deadline"]  # For Airtable Due Date mapping
    
    # Ensure we have the summary field properly set for Airtable
    if summary:
        info["Summary"] = summary  # Capital S for Airtable mapping consistency
    # Ensure Project Name is always present
    if "project_title" in info and info["project_title"]:
        info["Project Name"] = info["project_title"]
    elif summary_project_title:
        info["Project Name"] = summary_project_title
    
    info["detail_url"] = detail_url
    if source_url:
        info["source_url"] = source_url
    return info, detail_url


def parse_html(html: str, date_filter: str = None) -> List[Dict[str, str]]:
    """
    Extract bid data from OpenGov React-based summary table.
    
    Parses HTML to locate React Table elements, extracts summary data,
    and matches project IDs using embedded JSON data with fuzzy matching.
    Applies date filtering based on BID_POSTING_DATE_FILTER.
    
    Args:
        html (str): Complete HTML source from OpenGov procurement page
        
    Returns:
        List[Dict[str, str]]: List of bid records with summary data and project IDs
        
    Process:
        1. Locates React Table header and maps column positions
        2. Extracts summary data from table rows
        3. Applies date filtering based on release_date
        4. Extracts project data from embedded JSON using regex
        5. Matches project IDs to summary items using fuzzy title matching
        
    Note:
        Uses sophisticated project ID extraction from window.__data JSON
        with fallback regex extraction for robust ID matching.
    """
    print("Parsing HTML for bid data...")
    soup = BeautifulSoup(html, "html.parser")
    items = []
    # Find header row
    header_row = soup.select_one(".rt-thead .rt-tr")
    if not header_row:
        print("✗ Could not find header row")
        return items
    header_cells = [div.get_text(strip=True).lower() for div in header_row.select(".rt-th .rt-resizable-header-content")]
    col_map = {
        "project title": None,
        "status": None,
        "addenda": None,
        "release date": None,
        "due date": None
    }
    for idx, col in enumerate(header_cells):
        for key in col_map:
            if key in col:
                col_map[key] = idx
    if not all(v is not None for v in col_map.values()):
        print(f"✗ Could not map all required columns: {col_map}")
        return items
    # Find all data rows
    data_rows = soup.select(".rt-tbody .rt-tr")
    print(f"✓ Found {len(data_rows)} data rows")
    # Use passed date filter or no filtering
    if not date_filter:
        print("⚠️  No date filter provided - processing all bids")
        filter_date = None
        filter_date_str = "none"
    else:
        filter_date_str = date_filter
        filter_date = parse_mmddyyyy(filter_date_str)
        print(f"🗓️  Applying date filter: Only bids from {filter_date_str} onward")
    for row in data_rows:
        cells = row.select(".rt-td")
        if len(cells) < len(col_map):
            continue
        # Extract fields
        project_title = cells[col_map["project title"]].get_text(strip=True)
        status = cells[col_map["status"]].get_text(strip=True)
        addenda = cells[col_map["addenda"]].get_text(strip=True)
        release_date = cells[col_map["release date"]].get_text(strip=True)
        due_date = cells[col_map["due date"]].get_text(strip=True)
        # Filter by release_date
        release_dt = parse_mmddyyyy(release_date)
        if filter_date and release_dt and release_dt < filter_date:
            continue
        # Skip empty/pad rows
        if not any([project_title, status, addenda, release_date, due_date]):
            continue
        items.append({
            "project_title": project_title,
            "status": status,
            "addenda": addenda,
            "release_date": release_date,
            "due_date": due_date,
            "project_id": None  # Will fill in below
        })
    print(f"✓ Successfully parsed {len(items)} bids (pre-matching IDs)")

    # --- Extract project IDs using targeted extraction (inspired by your solution) ---
    import re, json
    
    def extract_projects_from_html(html_content):
        """Extract all project objects from govProjects.rows using targeted regex."""
        projects = []
        
        # Find all project IDs in the HTML
        id_pattern = r'"id":\s*(\d+)'
        id_matches = re.finditer(id_pattern, html_content)
        
        for match in id_matches:
            project_id = match.group(1)
            id_pos = match.start()
            
            # Work backwards to find the start of this project object
            brace_count = 0
            start_pos = id_pos
            
            for i in range(id_pos, max(0, id_pos - 5000), -1):
                char = html_content[i]
                if char == '}':
                    brace_count += 1
                elif char == '{':
                    if brace_count == 0:
                        start_pos = i
                        break
                    brace_count -= 1
            
            # Work forwards to find the end of this project object
            brace_count = 0
            in_string = False
            escape_next = False
            end_pos = id_pos
            
            for i in range(start_pos, min(len(html_content), start_pos + 10000)):
                char = html_content[i]
                
                if escape_next:
                    escape_next = False
                    continue
                    
                if char == '\\' and in_string:
                    escape_next = True
                    continue
                    
                if char == '"' and not escape_next:
                    in_string = not in_string
                    continue
                    
                if not in_string:
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        
                        if brace_count == 0:
                            end_pos = i + 1
                            break
            
            # Extract the project JSON
            project_json = html_content[start_pos:end_pos]
            
            try:
                project = json.loads(project_json)
                # Only keep projects with title (actual project objects, not other objects with IDs)
                if 'title' in project and 'id' in project:
                    projects.append(project)
            except json.JSONDecodeError:
                # Try regex extraction as fallback
                title_match = re.search(r'"title":\s*"([^"]*)"', project_json)
                if title_match:
                    projects.append({
                        'id': int(project_id),
                        'title': title_match.group(1)
                    })
        
        return projects
    
    # Extract projects using the robust method
    script_text = None
    for script in soup.find_all("script"):
        if script.string and "window.__data" in script.string:
            script_text = script.string
            break
    
    if not script_text:
        script_text = html  # fallback to full HTML
    
    extracted_projects = extract_projects_from_html(script_text)
    print(f"[INFO] Extracted {len(extracted_projects)} projects from JSON")
    
    if not extracted_projects:
        print("[WARN] Could not extract any projects for ID matching.")
        return items
    # Build a lookup by normalized title
    def normalize_title(t):
        return re.sub(r"\s+", " ", t.strip().lower())
    id_lookup = {normalize_title(proj["title"]): proj["id"] for proj in extracted_projects if "title" in proj and "id" in proj}
    # Assign project_id to each item by matching title
    for item in items:
        norm_title = normalize_title(item["project_title"])
        item["project_id"] = id_lookup.get(norm_title)
        if not item["project_id"]:
            # Try fuzzy match (contains)
            for k, v in id_lookup.items():
                if norm_title in k or k in norm_title:
                    item["project_id"] = v
                    break
    print(f"✓ Project IDs matched for {sum(1 for i in items if i['project_id'])} of {len(items)} items\n")
    return items


def save_to_csv(items: List[Dict[str, str]], filename: str = OUTPUT_CSV) -> None:
    """
    Save OpenGov bid data to CSV file (Airtable format only).
    
    Simple wrapper that calls the common utility function to save only
    the 5 Airtable columns: Project Name, Summary, Published Date, Due Date, Link.
    
    Note: The input items should already be in Airtable format from prepare_airtable_data()
    
    Args:
        items (List[Dict[str, str]]): List of bid records (should be in Airtable format)
        filename (str): Output CSV filename (default: OUTPUT_CSV)
    """
    save_airtable_format_csv(items, filename, "OpenGov")


def scrape_all(urls: List[str], date_filter: str = None) -> Tuple[pd.DataFrame, Dict]:
    """
    Scrape multiple OpenGov URLs in a single browser session.
    
    Uses undetected Chrome browser to scrape all configured URLs,
    handling bot detection, project ID extraction, and data collection.
    Returns combined results without individual CSV files.
    
    Args:
        urls (List[str]): List of OpenGov portal URLs to scrape
        date_filter (str): Date filter in MM/DD/YYYY format (overrides default)
        
    Returns:
        tuple[pd.DataFrame, dict]: Combined DataFrame with all scraped bid data
            and scraping statistics dictionary
        
    Raises:
        WebDriverException: If browser automation fails
        Exception: For other errors during scraping process
    """
    print("\n" + "="*60)
    print("OPENGOV SCRAPER")
    print("="*60)
    
    all_items = []
    scraping_stats = {
        'successful_sites': [],
        'skipped_sites': [],
        'failed_pages': [],
        'total_bids': 0,
        'total_sites_attempted': len(urls),
        'total_sites_successful': 0,
        'total_pages_attempted': 0,
        'total_pages_failed': 0
    }
    
    driver = uc.Chrome()
    
    try:
        for url in urls:
            print(f"\n[INFO] Processing summary page: {url}")
            
            # Extract portal code from url
            import re
            m = re.search(r"portal/([\w-]+)", url)
            portal_code = m.group(1) if m else "unknown"
            
            # Add retry logic for each portal
            max_retries = 3
            portal_success = False
            
            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        print(f"[INFO] Retry attempt {attempt + 1}/{max_retries} for {portal_code}")
                    
                    # Load summary page with timeout
                    print(f"Loading: {url}")
                    driver.set_page_load_timeout(30)  # 30 second page load timeout
                    driver.get(url)
                    
                    # Check for portal accessibility errors first
                    page_title = driver.title.lower()
                    page_source = driver.page_source.lower()
                    
                    # Detect if portal doesn't exist or is inaccessible
                    error_indicators = [
                        'forbidden' in page_title,
                        '403' in page_title,
                        '404' in page_title, 
                        'not found' in page_title,
                        'access denied' in page_source,
                        'portal not found' in page_source,
                        'does not exist' in page_source
                    ]
                    
                    if any(error_indicators):
                        print(f"❌ Portal {portal_code} appears to be inaccessible (403/404/etc)")
                        print(f"   This portal may not exist or may not be publicly available")
                        scraping_stats['skipped_sites'].append({
                            'portal_code': portal_code,
                            'url': url,
                            'reason': 'Portal not accessible (403/404 error)'
                        })
                        break  # Don't retry for access errors
                    
                    # Give page time to fully load and render all elements
                    print(f"⏳ Waiting for page to fully load...")
                    time.sleep(3)  # Reduced from 8 to 3 seconds for faster processing
                    
                    # Check for human verification elements after page has time to render
                    verification_needed = detect_human_verification(driver)
                    
                    if verification_needed:
                        print(f"\n" + "="*60)
                        print(f"🤖 HUMAN VERIFICATION DETECTED")
                        print(f"Portal: {portal_code}")
                        print(f"URL: {url}")
                        print("="*60)
                        print("Instructions:")
                        print("1. Complete the human verification (checkbox/CAPTCHA)")
                        print("2. Wait for the bids table to load completely")
                        print("3. Press ENTER here to continue scraping")
                        print("="*60)
                        input(f">>> Press ENTER when verification is complete and table is visible for {portal_code}...\n")
                        print(f"⏳ Waiting for table to load after verification...")
                        time.sleep(3)
                    else:
                        print(f"✓ No human verification detected for {portal_code}, proceeding...")
                        # Give additional time for table to load even without verification
                        print(f"⏳ Waiting for table to load...")
                        time.sleep(2)  # Reduced from 5 to 2 seconds
                    
                    # Now check if table loaded successfully with faster timeout
                    try:
                        # Reduced timeout for quicker detection
                        timeout = 8 if verification_needed else 10  # Reduced from 15/20
                        print(f"🔍 Looking for data table (timeout: {timeout}s)...")
                        WebDriverWait(driver, timeout).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, ".rt-tbody .rt-tr"))
                        )
                        print(f"✓ Table loaded for {portal_code}")
                        time.sleep(1)  # Reduced from 2 to 1 second
                        portal_success = True
                        break
                        
                    except TimeoutException:
                        print(f"⚠️  Table not immediately found for {portal_code} - checking for empty state...")
                        
                        # Check if page loaded successfully but just has no data
                        try:
                            # Reduced wait time for empty state check
                            time.sleep(1)  # Reduced from 3 to 1 second
                            
                            # More comprehensive empty state detection
                            # 1. Look for OpenGov-specific elements that indicate page loaded successfully
                            page_loaded = any([
                                driver.find_elements(By.CSS_SELECTOR, ".rt-table"),
                                driver.find_elements(By.CSS_SELECTOR, ".react-table"), 
                                driver.find_elements(By.CSS_SELECTOR, "[class*='procurement']"),
                                driver.find_elements(By.CSS_SELECTOR, "[class*='project']"),
                                driver.find_elements(By.CSS_SELECTOR, ".container"),
                                driver.find_elements(By.CSS_SELECTOR, ".main-content"),
                                # Check for any OpenGov-specific UI elements
                                driver.find_elements(By.XPATH, "//*[contains(@class, 'opengov')]"),
                                # Check for header/navigation elements
                                driver.find_elements(By.CSS_SELECTOR, "header"),
                                driver.find_elements(By.CSS_SELECTOR, "nav"),
                            ])
                            
                            # 2. Look for explicit "no records" messages
                            no_results_indicators = []
                            no_results_patterns = [
                                "No records", "no data", "0 of 0", "No data", 
                                "No results", "no results", "No projects",
                                "No current", "0 results", "Nothing to display"
                            ]
                            
                            for pattern in no_results_patterns:
                                no_results_indicators.extend(
                                    driver.find_elements(By.XPATH, f"//*[contains(text(), '{pattern}')]")
                                )
                            
                            # Add CSS-based no data indicators
                            no_results_indicators.extend(driver.find_elements(By.CSS_SELECTOR, ".rt-noData"))
                            no_results_indicators.extend(driver.find_elements(By.CSS_SELECTOR, "[class*='no-data']"))
                            no_results_indicators.extend(driver.find_elements(By.CSS_SELECTOR, "[class*='empty']"))
                            
                            # 3. Check if table structure exists but is empty
                            table_body = driver.find_elements(By.CSS_SELECTOR, ".rt-tbody")
                            table_rows = driver.find_elements(By.CSS_SELECTOR, ".rt-tbody .rt-tr")
                            table_headers = driver.find_elements(By.CSS_SELECTOR, ".rt-thead")
                            
                            # 4. Check for pagination showing 0 results
                            pagination_zero = driver.find_elements(
                                By.XPATH, 
                                "//*[contains(text(), 'Showing 0') or contains(text(), 'Total: 0') or contains(text(), '0 entries')]"
                            )
                            
                            # 5. Check for filter/search interface (suggests functional page with no results)
                            has_filters = any([
                                driver.find_elements(By.CSS_SELECTOR, "input[type='search']"),
                                driver.find_elements(By.CSS_SELECTOR, ".filter"),
                                driver.find_elements(By.CSS_SELECTOR, ".search"),
                                driver.find_elements(By.CSS_SELECTOR, "[placeholder*='search']"),
                                driver.find_elements(By.CSS_SELECTOR, "[placeholder*='filter']")
                            ])
                            
                            if page_loaded:
                                print(f"✓ {portal_code}: Page structure loaded successfully")
                                
                                # Determine if this is an empty state
                                is_empty = any([
                                    bool(no_results_indicators),  # Explicit "no data" message
                                    (bool(table_headers) and not bool(table_rows)),  # Table header but no rows
                                    (bool(table_body) and len(table_rows) == 0),  # Empty table body
                                    bool(pagination_zero),  # Pagination showing 0 results
                                ])
                                
                                if is_empty:
                                    print(f"✅ {portal_code}: Successfully detected empty state (no current bids)")
                                    scraping_stats['successful_sites'].append({
                                        'portal_code': portal_code,
                                        'url': url,
                                        'bids_found': 0
                                    })
                                    scraping_stats['total_sites_successful'] += 1
                                    portal_success = True
                                    break
                                else:
                                    print(f"✓ {portal_code}: Page loaded, checking for data with different structure...")
                                    # Continue to parsing - maybe data exists with different table structure
                                    portal_success = True
                                    break
                            else:
                                print(f"⚠️  {portal_code}: Page structure not recognized")
                                
                        except Exception as e:
                            print(f"⚠️  {portal_code}: Error during empty state check: {e}")
                            pass
                        
                        
                        if attempt < max_retries - 1:
                            print(f"[INFO] Refreshing page for {portal_code}...")
                            continue
                        else:
                            print(f"❌ Failed to load table after {max_retries} attempts for {portal_code}")
                            break
                
                except TimeoutException:
                    print(f"⚠️  Page load timeout for {portal_code} (attempt {attempt + 1})")
                    if attempt < max_retries - 1:
                        continue
                    else:
                        break
                        
                except Exception as e:
                    print(f"❌ Error loading {portal_code} (attempt {attempt + 1}): {str(e)[:100]}")
                    if attempt < max_retries - 1:
                        continue
                    else:
                        break
            
            if not portal_success:
                print(f"❌ Skipping {portal_code} after {max_retries} failed attempts")
                scraping_stats['skipped_sites'].append({
                    'portal_code': portal_code,
                    'url': url,
                    'reason': f'Failed to load after {max_retries} attempts'
                })
                continue
            
            # If we reach here, the portal loaded successfully
            try:
                html = driver.page_source
                summary_items = parse_html(html, date_filter=date_filter)
                
                # Track page statistics
                scraping_stats['total_pages_attempted'] += len(summary_items)
                
                if not summary_items:
                    print(f"✓ Page loaded successfully but no bids found for {portal_code}")
                    # This is a successful scrape with 0 results, not a failure
                    scraping_stats['successful_sites'].append({
                        'portal_code': portal_code,
                        'url': url,
                        'bids_found': 0
                    })
                    scraping_stats['total_sites_successful'] += 1
                    continue
                
                print(f"[INFO] Extracted {len(summary_items)} summary items.")
                
                # Filter for valid project IDs
                valid_items = [item for item in summary_items if item.get('project_id')]
                
                if not valid_items:
                    print(f"[WARN] Found {len(summary_items)} bids but no valid project IDs for detail scraping")
                    # Still count as successful since we got summary data, just couldn't get details
                    scraping_stats['successful_sites'].append({
                        'portal_code': portal_code,
                        'url': url,
                        'bids_found': 0  # 0 detailed bids, but we did find summary items
                    })
                    scraping_stats['total_sites_successful'] += 1
                    continue
                
                # Scrape details for each valid item
                successfully_scraped = 0
                for idx, item in enumerate(valid_items):
                    project_id = item.get("project_id")
                    try:
                        detail_info, detail_url = scrape_detail_page(driver, portal_code, project_id, source_url=url, summary_project_title=item.get("project_title"))
                        
                        # Preserve summary table data and map to Airtable-compatible field names
                        # Before updating with detail data, ensure we don't lose summary table dates
                        summary_release_date = item.get("release_date", "")
                        summary_due_date = item.get("due_date", "")
                        
                        item.update(detail_info)
                        
                        # Ensure Airtable-compatible field mappings from summary table if detail page didn't provide them
                        if not item.get("Release Date") and summary_release_date:
                            item["Release Date"] = summary_release_date
                        if not item.get("Due Date") and summary_due_date:
                            item["Due Date"] = summary_due_date
                        
                        # Map project_title to Project Title for Airtable consistency
                        if item.get("project_title") and not item.get("Project Title"):
                            item["Project Title"] = item["project_title"]
                        
                        # Add portal and city info
                        item["portal_code"] = portal_code
                        item["city_name"] = portal_code.replace('-', ' ').title()
                        
                        successfully_scraped += 1
                    except Exception as e:
                        print(f"[ERROR] Failed to scrape detail for project_id={project_id}: {e}")
                        scraping_stats['failed_pages'].append({
                            'portal_code': portal_code,
                            'project_id': project_id,
                            'reason': f'Detail scraping failed: {str(e)[:100]}...'
                        })
                        scraping_stats['total_pages_failed'] += 1
                        continue
                    
                    all_items.append(item)
                
                if successfully_scraped > 0:
                    scraping_stats['successful_sites'].append({
                        'portal_code': portal_code,
                        'url': url,
                        'bids_found': successfully_scraped
                    })
                    scraping_stats['total_sites_successful'] += 1
                    scraping_stats['total_bids'] += successfully_scraped
                    print(f"[INFO] Successfully scraped {successfully_scraped} items from {portal_code}")
                else:
                    scraping_stats['skipped_sites'].append({
                        'portal_code': portal_code,
                        'url': url,
                        'reason': 'All detail page scraping failed'
                    })
                    
            except Exception as e:
                print(f"[ERROR] Failed to process {url}: {e}")
                scraping_stats['skipped_sites'].append({
                    'portal_code': portal_code,
                    'url': url,
                    'reason': f'Processing error: {str(e)[:100]}...'
                })
                continue
                
    finally:
        driver.quit()
        print("[INFO] Browser session closed.")
    
    # Save failed URLs to unified text file
    if scraping_stats.get('failed_pages'):
        save_failed_pages_batch(scraping_stats['failed_pages'], 'OpenGov')

    # Ensure Airtable fields before saving
    for item in all_items:
        item["Link"] = item.get("detail_url", "")
        # Always use summary table values for Published Date and Due Date
        item["Published Date"] = to_iso_date(item.get("release_date", ""))
        item["Due Date"] = to_iso_date(item.get("due_date", ""))

    # Create DataFrame
    if all_items:
        # Add flooring/carpeting detection for OpenGov data
        try:
            print(f"\n🏠 Analyzing {len(all_items)} OpenGov bids for flooring opportunities...")
            
            flooring_keywords = [
                'floor', 'carpet', 'tile', 'hardwood', 'vinyl', 'laminate', 
                'flooring', 'carpeting', 'gymnasium floor', 'floor covering',
                'floor refinish', 'floor maintenance', 'floor repair', 'floor install'
            ]
            
            flooring_count = 0
            for item in all_items:
                # Check summary and description fields for flooring keywords
                text_to_check = ' '.join([
                    item.get('project_title', '').lower(),
                    item.get('summary', '').lower(), 
                    item.get('status', '').lower(),
                    item.get('release_project_date', '').lower()
                ])
                
                # Simple keyword matching
                is_flooring_related = any(keyword in text_to_check for keyword in flooring_keywords)
                item['is_flooring_related'] = is_flooring_related
                
                if is_flooring_related:
                    flooring_count += 1
            
            print(f"🏠 Found {flooring_count}/{len(all_items)} potentially flooring-related OpenGov bids")
            
            if flooring_count > 0:
                print(f"🎯 OpenGov flooring opportunities:")
                flooring_bids = [item for item in all_items if item.get('is_flooring_related')]
                for bid in flooring_bids[:3]:  # Show top 3
                    print(f"   • {bid.get('project_title', 'Unknown')[:60]}...")
            
        except Exception as e:
            print(f"⚠️  OpenGov flooring analysis failed: {e}")
            print("   (Continuing without flooring analysis)")
        
        # Save CSV file for manual inspection
        print(f"\n💾 Saving OpenGov data to CSV...")
        save_to_csv(all_items, OUTPUT_CSV)
        print(f"✅ OpenGov data saved to: {OUTPUT_CSV}")
        
        df = pd.DataFrame(all_items)
        return df, scraping_stats
    else:
        print("⚠️  No OpenGov data to save to CSV")
        return pd.DataFrame(), scraping_stats


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
    print("\n" + "="*50)
    print("🚀 Starting OpenGov Scraper")
    print("="*50)
    all_items = []
    city_summary = {}
    driver = uc.Chrome()
    try:
        print("\n➡️  [OpenGov] Scraping {} cities...".format(len(URLS)))
        # Only check for human verification once at the start
        print("\n➡️  Checking for human verification (first portal)...")
        driver.get(URLS[0])
        if detect_human_verification(driver):
            print("\n" + "="*60)
            print(f"🤖 HUMAN VERIFICATION DETECTED")
            print(f"Portal: {URLS[0]}")
            print("="*60)
            print("Instructions:")
            print("1. Complete the human verification (checkbox/CAPTCHA)")
            print("2. Wait for the bids table to load completely")
            print("3. Press ENTER here to continue scraping")
            print("="*60)
            input(f">>> Press ENTER when verification is complete and table is visible for first portal...\n")
            print(f"⏳ Waiting for table to load after verification...")
            time.sleep(3)
        print("✅ Human verification complete. Proceeding with all portals.\n")
        for url in URLS:
            import re
            m = re.search(r"portal/([\w-]+)", url)
            portal_code = m.group(1) if m else "unknown"
            city_name = portal_code.replace('-', ' ').title()
            print(f"➡️  [{city_name}] Scraping...")
            try:
                driver.get(url)
                time.sleep(2)
                html = driver.page_source
                summary_items = parse_html(html, date_filter=None)
                valid_items = [item for item in summary_items if item.get('project_id')]
                if not summary_items:
                    print(f"   - {city_name}: 0 RFPs found")
                    city_summary[city_name] = 0
                    continue
                if not valid_items:
                    print(f"   - {city_name}: 0 RFPs found (no valid project IDs)")
                    city_summary[city_name] = 0
                    continue
                scraped_count = 0
                for item in valid_items:
                    project_id = item.get("project_id")
                    try:
                        detail_info, detail_url = scrape_detail_page(driver, portal_code, project_id, source_url=url, summary_project_title=item.get("project_title"))
                        item.update(detail_info)
                        scraped_count += 1
                    except Exception as e:
                        # Only print a concise error line, not details
                        print(f"   ❌ Failed to scrape detail for project_id={project_id}")
                        continue
                    all_items.append(item)
                # Ensure Airtable fields for per-portal output
                for item in valid_items:
                    item["Link"] = item.get("detail_url", "")
                    item["Published Date"] = to_iso_date(item.get("release_date", ""))
                    item["Due Date"] = to_iso_date(item.get("due_date", ""))
                print(f"   - {city_name}: {scraped_count} RFP{'s' if scraped_count != 1 else ''} scraped")
                city_summary[city_name] = scraped_count
                # Save individual CSV for this portal
                portal_csv = f"opengov/{portal_code}_opengov_data.csv"
                save_to_csv(valid_items, portal_csv)
            except Exception as e:
                print(f"   ❌ [{city_name}] Failed to scrape ({e})")
                city_summary[city_name] = 0
                continue
    finally:
        driver.quit()
        print("[INFO] Browser session closed.")
    # Save combined CSV with all data
    if all_items:
        # Ensure Airtable fields for combined output
        for item in all_items:
            item["Link"] = item.get("detail_url", "")
            item["Published Date"] = to_iso_date(item.get("release_date", ""))
            item["Due Date"] = to_iso_date(item.get("due_date", ""))
        print(f"\n💾 Saving OpenGov data to CSV...")
        save_to_csv(all_items, OUTPUT_CSV)
        print(f"✅ OpenGov data saved to: {OUTPUT_CSV}")
    else:
        print("⚠️  No OpenGov data to save to CSV")
    # Print summary for each city
    print("\n📊 OpenGov Scraping Summary:")
    total = 0
    for city, count in city_summary.items():
        if count > 0:
            print(f"   - {city}: {count} RFP{'s' if count != 1 else ''} scraped")
        else:
            print(f"   - {city}: 0 RFPs found or failed")
        total += count
    if total > 0:
        print(f"✅  [OpenGov] Total: {total} RFP{'s' if total != 1 else ''} scraped\n")
    else:
        print(f"❌  [OpenGov] No RFPs scraped\n")
    print("="*50)
    print("✅  OpenGov scraping completed successfully")
    print("="*50)
    print("Done.\n")


if __name__ == "__main__":
    main()
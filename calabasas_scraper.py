#!/usr/bin/env python3
"""
City of Calabasas Government Bids Scraper - Simplified Version

Scrapes government bid opportunities from City of Calabasas public notices portal.
Extracts title, due date, and PDF URL from the main page only.
Published date is left blank and summary is set to the title.

Author: Assistant
Created: 2025-11-08
Updated: 2025-11-09
"""

import os
import re
import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict, Tuple
from urllib.parse import urljoin

# Local imports
from utils import (
    get_chromedriver_path,
    parse_mmddyyyy,
    save_failed_pages_batch,
    save_airtable_format_csv
)


# =============================================================================
# CONFIGURATION
# =============================================================================

BASE_URL = "https://www.cityofcalabasas.com/services/public-notices"
OUTPUT_CSV = "calabasas/calabasas_bids.csv"

# Retry Configuration
MAX_RETRIES = 3
RETRY_DELAY = 3  # seconds


def extract_rfp_listings(driver) -> List[Dict]:
    """
    Extract RFP listings from Calabasas public notices page.
    
    Returns:
        List[Dict]: List of basic RFP information from main page
    """
    print("📋 Extracting RFP listings from accordion section...")
    rfps = []
    
    try:
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Find the RFP accordion section
        rfp_section = soup.find('div', id='RequestforProposalsRFP')
        if not rfp_section:
            print("  ⚠️  RFP section not found")
            return rfps
            
        # Find the content area within the accordion
        content_area = rfp_section.find('div', class_='accordion-content')
        if not content_area:
            print("  ⚠️  RFP content area not found")
            return rfps
        
        # Find all list items with RFPs
        rfp_items = content_area.find_all('li')
        print(f"  📋 Found {len(rfp_items)} total items")
        
        current_rfp = None  # Track the current RFP for addendums
        
        for i, item in enumerate(rfp_items, 1):
            try:
                # Extract project name from the <a> tag (always use this for both title and summary)
                link_elem = item.find('a')
                if not link_elem:
                    print(f"    ❌ Item {i}: No link found")
                    continue
                project_name = link_elem.get_text(strip=True)
                relative_url = link_elem.get('href')
                pdf_url = urljoin(BASE_URL, relative_url) if relative_url else ""

                # Extract due date from the first <strong> tag (at the start of the <li>)
                # This is robust even if there are nested <strong> tags
                due_date_text = ""
                strongs = item.find_all('strong')
                if strongs:
                    # Use the first <strong> tag's text
                    due_date_text = strongs[0].get_text(strip=True)
                    # Remove trailing dash and whitespace
                    due_date_text = due_date_text.rstrip(' -')

                # Check if this is an addendum (starts with "Addendum" or similar)
                if project_name.lower().startswith(('addendum', 'amendment', 'correction')):
                    print(f"    📄 Item {i}: Addendum detected - {project_name[:30]}...")
                    print(f"      Skipping (addendum to previous RFP)")
                    if current_rfp:
                        if 'addendums' not in current_rfp:
                            current_rfp['addendums'] = []
                        current_rfp['addendums'].append({
                            'title': project_name,
                            'url': pdf_url
                        })
                        print(f"      Associated with: {current_rfp['project_title'][:40]}...")
                    continue

                print(f"    ✓ Item {i}: RFP - {project_name[:50]}...")
                print(f"      Due: {due_date_text}")
                print(f"      PDF: {pdf_url}")

                rfp_data = {
                    'project_title': project_name,
                    'scope_of_services': project_name,  # Use project name as summary
                    'due_date_text': due_date_text,
                    'detail_url': pdf_url
                }

                rfps.append(rfp_data)
                current_rfp = rfp_data

            except Exception as e:
                print(f"    ❌ Error processing RFP item {i}: {e}")
                continue
        
        print(f"  📊 Extracted {len(rfp_items)} total items → {len(rfps)} actual RFPs (filtered out addendums)")
        
        return rfps
        
    except Exception as e:
        print(f"❌ Error extracting RFP listings: {e}")
        return rfps


def parse_calabasas_date(date_text: str) -> str:
    """
    Parse Calabasas date format to MM/DD/YYYY.
    
    Args:
        date_text: Date string like "Monday, November 17, 2025 at 2:00 p.m."
        
    Returns:
        str: Date in MM/DD/YYYY format
    """
    if not date_text:
        return ''
    
    try:
        # Remove day of week and time
        clean_text = date_text
        
        # Remove day of week (e.g., "Monday, ")
        clean_text = re.sub(r'^[A-Za-z]+,\s*', '', clean_text)
        
        # Remove time portion and extra text
        clean_text = re.sub(r'\s+at\s+.*$', '', clean_text)
        clean_text = re.sub(r',\s+on\s+or\s+before.*$', '', clean_text)
        
        # Handle cases where year is missing (add current year)
        clean_text = clean_text.strip()
        if not re.search(r'\d{4}', clean_text):
            # If no year found, assume current year
            clean_text += f', {datetime.now().year}'
        
        # Parse the date
        parsed_date = datetime.strptime(clean_text.strip(), '%B %d, %Y')
        return parsed_date.strftime('%m/%d/%Y')
        
    except Exception as e:
        print(f"    ⚠️  Could not parse date '{date_text}': {e}")
        return ''


def scrape_calabasas(cutoff_date: datetime, headless: bool = True) -> Tuple[List[Dict], List[str]]:
    """
    Scrape all RFP opportunities from Calabasas portal.
    
    Args:
        cutoff_date: Only include RFPs published after this date
        headless: Whether to run Chrome in headless mode
        
    Returns:
        Tuple[List[Dict], List[str]]: (rfp_data, failed_urls)
    """
    print("🚀 Starting Calabasas RFP scraping...")
    
    driver = None
    failed_urls = []
    all_rfps = []
    
    try:
        # Setup Chrome driver
        chrome_options = Options()
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        
        if headless:
            chrome_options.add_argument('--headless')
        
        service = ChromeService(executable_path=get_chromedriver_path())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        print(f"🌐 Navigating to: {BASE_URL}")
        driver.get(BASE_URL)
        
        # Wait for page load
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # Extra wait for dynamic content to load
        wait_time = 10 if headless else 5
        time.sleep(wait_time)
        
        print("🔄 Waiting for page to fully load...")
        
        # Try to find and interact with the accordion
        accordion_found = False
        try:
            # Wait for the RFP section to be present
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.ID, "RequestforProposalsRFP"))
            )
            
            print("✅ RFP section found")
            accordion_found = True
            
            rfp_accordion = driver.find_element(By.ID, "RequestforProposalsRFP")
            if "state-open" not in rfp_accordion.get_attribute("class"):
                print("🔄 Opening RFP accordion...")
                accordion_header = rfp_accordion.find_element(By.CLASS_NAME, "accordion-heading")
                driver.execute_script("arguments[0].click();", accordion_header)
                time.sleep(5)  # Wait for accordion to expand
            else:
                print("✅ RFP accordion already open")
                
        except Exception as e:
            print(f"⚠️  Could not interact with accordion: {e}")
            if headless:
                print("🔄 Retrying without headless mode...")
                driver.quit()
                return scrape_calabasas(cutoff_date, headless=False)
        
        print("⏳ Extracting RFP listings...")
        
        # Extract RFP summary information
        summary_rfps = extract_rfp_listings(driver)
        
        if not summary_rfps:
            print("❌ No RFPs found on main page")
            if headless and accordion_found:
                print("🔄 Retrying without headless mode...")
                driver.quit()
                return scrape_calabasas(cutoff_date, headless=False)
            return all_rfps, failed_urls
        
        print(f"📊 Processing {len(summary_rfps)} RFPs...")
        
        # Process each RFP - simplified without PDF extraction
        for i, rfp in enumerate(summary_rfps, 1):
            print(f"\n🔍 Processing RFP {i}/{len(summary_rfps)}: {rfp.get('project_title', 'Unknown')[:60]}...")
            
            try:
                # Parse due date from main page
                due_date = parse_calabasas_date(rfp.get('due_date_text', ''))
                pdf_url = rfp.get('detail_url', '')
                title = rfp.get('project_title', '')
                
                # Build the final record with simplified data
                rfp_record = {
                    'bid_title': title,
                    'bid_posting_date': '',  # Leave blank as requested
                    'bid_due_date': due_date,
                    'scope_of_services': title,  # Use title as summary
                    'bid_url': pdf_url,
                    'source': 'Calabasas',
                    'scraped_at': datetime.now().isoformat()
                }
                
                # Always include the RFP since we're not filtering by published date
                all_rfps.append(rfp_record)
                print(f"    ✅ Added RFP (due: {due_date})")
                
            except Exception as e:
                print(f"    ❌ Error processing RFP {i}: {e}")
                continue
        
        print(f"\n✅ Calabasas scraping completed!")
        print(f"   📊 Total RFPs found: {len(summary_rfps)}")
        print(f"   ✅ RFPs added to results: {len(all_rfps)}")
        
        return all_rfps, failed_urls
        
    except Exception as e:
        print(f"❌ Calabasas scraping failed: {e}")
        if headless:
            print("🔄 Retrying without headless mode...")
            if driver:
                driver.quit()
            return scrape_calabasas(cutoff_date, headless=False)
        return all_rfps, failed_urls
        
    finally:
        if driver:
            driver.quit()


def print_portal_summary(count, portal_name, error=None):
    """
    Print a summary of the scraping result for the portal.
    
    Args:
        count: Number of RFPs scraped
        portal_name: Name of the portal (for logging)
        error: Optional error message if scraping failed
    """
    if error:
        print(f"❌  [{portal_name}] Failed to scrape ({error})\n")
    elif count > 0:
        print(f"✅  [{portal_name}] {count} RFPs scraped\n")
    else:
        print(f"❌  [{portal_name}] No RFPs found\n")


def scrape_all(date_filter: str = None) -> Tuple[pd.DataFrame, Dict]:
    """
    Main function to scrape all Calabasas RFPs and return DataFrame.
    
    Args:
        date_filter: Date string in MM/DD/YYYY format for filtering
        
    Returns:
        Tuple[pd.DataFrame, Dict]: (dataframe, stats)
    """
    print("=" * 80)
    print("🏛️  CALABASAS RFP SCRAPER")
    print("=" * 80)
    
    # Parse date filter
    if date_filter:
        cutoff_date = parse_mmddyyyy(date_filter)
        print(f"📅 Date filter: {date_filter} (only RFPs published after this date)")
    else:
        cutoff_date = datetime(2020, 1, 1)  # Very old date to include all
        print("📅 No date filter applied (including all RFPs)")
    
    # Scrape data
    rfp_data, failed_urls = scrape_calabasas(cutoff_date)
    
    # Convert to DataFrame
    if rfp_data:
        df = pd.DataFrame(rfp_data)
        print(f"\n📊 Created DataFrame with {len(df)} records")
        print(f"   Columns: {list(df.columns)}")
    else:
        df = pd.DataFrame()
        print(f"\n📊 No data to create DataFrame")
    
    # Save failed URLs
    if failed_urls:
        save_failed_pages_batch(failed_urls, 'calabasas')
    
    # Statistics
    stats = {
        'total_scraped': len(rfp_data),
        'failed_urls': len(failed_urls),
        'source': 'Calabasas'
    }
    
    # Save to CSV
    if not df.empty:
        os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
        df.to_csv(OUTPUT_CSV, index=False)
        print(f"💾 Saved to: {OUTPUT_CSV}")
        
        # Save in Airtable format
        airtable_csv = OUTPUT_CSV.replace('.csv', '_airtable.csv')
        
        # Convert DataFrame to Airtable format
        airtable_data = []
        for _, row in df.iterrows():
            airtable_record = {
                "Project Name": row['bid_title'],
                "Summary": row['scope_of_services'],
                "Published Date": row['bid_posting_date'],
                "Due Date": row['bid_due_date'],
                "Link": row['bid_url'],
                "Date Scraped": datetime.now().strftime('%Y-%m-%d')
            }
            airtable_data.append(airtable_record)
        
        save_airtable_format_csv(airtable_data, airtable_csv, 'Calabasas')
        print(f"💾 Airtable format saved to: {airtable_csv}")
    
    print_portal_summary(len(df), 'Calabasas')
    
    return df, stats


if __name__ == "__main__":
    # Test the scraper
    df, stats = scrape_all(date_filter="01/01/2024")
    
    if not df.empty:
        print(f"\n📋 Sample of scraped data:")
        print(df.head())
    else:
        print(f"\n❌ No data scraped")

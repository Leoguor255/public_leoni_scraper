#!/usr/bin/env python3
"""
New City Government Bids Scraper

Scrapes government bid opportunities from [City Name] portal.
Extracts bid information from listing page only (no detail pages needed).
Uses bid title as summary since no additional details are available.

Author: [Your Name]
Created: 2025-01-27
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

BASE_URL = "https://example-city.gov/bids"  # Replace with actual URL
OUTPUT_CSV = "new_city/new_city_bids.csv"   # Update folder name

# Retry Configuration
MAX_RETRIES = 3
RETRY_DELAY = 3  # seconds


def extract_summary_table(driver) -> List[Dict]:
    """
    Extract bid listings from New City bid overview page.
    
    Returns:
        List[Dict]: List of basic bid information from overview table
    """
    print("📋 Extracting bid listings from page...")
    bids = []
    
    try:
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # TODO: Update selectors based on actual website structure
        # Example structure - replace with actual selectors
        bid_containers = soup.find_all('div', class_='bid-item')  # Update selector
        
        if not bid_containers:
            print("  ⚠️  No bid containers found")
            return bids
            
        print(f"  📋 Found {len(bid_containers)} bid containers")
        
        for i, container in enumerate(bid_containers, 1):
            try:
                # Extract title and link
                title_elem = container.find('a', class_='bid-title')  # Update selector
                if not title_elem:
                    title_elem = container.find('h3')  # Alternative selector
                    
                if not title_elem:
                    print(f"    ❌ Row {i}: No title found")
                    continue
                    
                title = title_elem.get_text(strip=True)
                
                # Get detail URL
                link_elem = title_elem if title_elem.name == 'a' else title_elem.find('a')
                detail_url = ""
                if link_elem and link_elem.get('href'):
                    relative_url = link_elem.get('href')
                    detail_url = urljoin(BASE_URL, relative_url)
                
                # Extract dates - update selectors based on actual structure
                published_date = ""
                due_date = ""
                
                date_elem = container.find('span', class_='published-date')  # Update selector
                if date_elem:
                    published_date = date_elem.get_text(strip=True)
                
                due_elem = container.find('span', class_='due-date')  # Update selector
                if due_elem:
                    due_date = due_elem.get_text(strip=True)
                
                # Create bid record - use title as summary since no detail page needed
                bid = {
                    'title': title,
                    'detail_url': detail_url,
                    'published_date': published_date,
                    'due_date': due_date,
                    'summary': title  # Use title as summary - no detail page needed
                }
                
                bids.append(bid)
                print(f"    ✅ Row {i}: {title}")
                
            except Exception as e:
                print(f"    ❌ Error processing row {i}: {e}")
                continue
        
    except Exception as e:
        print(f"  ❌ Error extracting summary table: {e}")
    
    return bids


def extract_bid_detail(driver, bid: Dict) -> Dict:
    """
    Extract detailed information from a bid's detail page.
    
    Args:
        driver: Selenium WebDriver instance
        bid: Bid dictionary with basic information
        
    Returns:
        Dict: Enhanced bid dictionary with detailed information
    """
    if not bid.get('detail_url'):
        print(f"    ⚠️  No detail URL for: {bid.get('title', 'Unknown')}")
        return bid
        
    try:
        print(f"    🔍 Accessing detail page: {bid['detail_url']}")
        driver.get(bid['detail_url'])
        
        # Wait for page to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Extract summary/description - update selectors based on actual structure
        summary = ""
        summary_selectors = [
            'div.bid-description',    # Update with actual selectors
            'div.summary',
            'div.content',
            'p.description',
            'div#description'
        ]
        
        for selector in summary_selectors:
            if '.' in selector:
                class_name = selector.split('.')[1]
                elem = soup.find('div', class_=class_name)
            elif '#' in selector:
                id_name = selector.split('#')[1]
                elem = soup.find('div', id=id_name)
            else:
                elem = soup.find(selector.split('.')[0])
                
            if elem:
                summary = elem.get_text(strip=True)
                if summary:
                    break
        
        # Extract dates if not already present
        if not bid.get('published_date') or not bid.get('due_date'):
            # Look for date information on detail page
            date_text = soup.get_text()
            
            # Extract published date patterns
            if not bid.get('published_date'):
                pub_patterns = [
                    r'Published[:\s]+(\d{1,2}/\d{1,2}/\d{4})',
                    r'Posted[:\s]+(\d{1,2}/\d{1,2}/\d{4})',
                    r'Date[:\s]+(\d{1,2}/\d{1,2}/\d{4})'
                ]
                
                for pattern in pub_patterns:
                    match = re.search(pattern, date_text, re.IGNORECASE)
                    if match:
                        bid['published_date'] = match.group(1)
                        break
            
            # Extract due date patterns
            if not bid.get('due_date'):
                due_patterns = [
                    r'Due[:\s]+(\d{1,2}/\d{1,2}/\d{4})',
                    r'Closing[:\s]+(\d{1,2}/\d{1,2}/\d{4})',
                    r'Deadline[:\s]+(\d{1,2}/\d{1,2}/\d{4})'
                ]
                
                for pattern in due_patterns:
                    match = re.search(pattern, date_text, re.IGNORECASE)
                    if match:
                        bid['due_date'] = match.group(1)
                        break
        
        # Update bid with extracted information
        bid['summary'] = summary
        
        print(f"    ✅ Detail extracted for: {bid['title']}")
        
    except Exception as e:
        print(f"    ❌ Error extracting detail for {bid.get('title', 'Unknown')}: {e}")
    
    return bid


def scrape_all(urls, date_filter=None):
    """
    Interface function to match other scrapers for integration with main.py.
    
    Args:
        urls: Not used for single-site scraper, but kept for compatibility
        date_filter: Date filter string in MM/DD/YYYY format
        
    Returns:
        Tuple[pd.DataFrame, dict]: (scraped_data_df, stats_dict)
    """
    from datetime import datetime
    
    # Parse date filter
    if date_filter:
        try:
            cutoff_date = datetime.strptime(date_filter, '%m/%d/%Y')
        except:
            cutoff_date = datetime.now() - pd.Timedelta(days=30)
    else:
        cutoff_date = datetime.now() - pd.Timedelta(days=30)
    
    # Scrape the data
    scraped_bids, failed_urls = scrape_new_city(cutoff_date)
    
    # Convert to DataFrame
    df = pd.DataFrame(scraped_bids) if scraped_bids else pd.DataFrame()
    
    # Create stats
    stats = {
        'total_bids': len(scraped_bids),
        'failed_urls': len(failed_urls),
        'date_filter': date_filter
    }
    
    return df, stats


def scrape_new_city(cutoff_date: datetime) -> Tuple[List[Dict], List[str]]:
    """
    Scrape all bid opportunities from New City portal.
    
    Args:
        cutoff_date: Only include bids published after this date
        
    Returns:
        Tuple[List[Dict], List[str]]: (bid_data, failed_urls)
    """
    print("🚀 Starting New City bid scraping...")
    
    driver = None
    failed_urls = []
    all_bids = []
    
    try:
        # Setup Chrome driver
        chrome_options = Options()
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        # chrome_options.add_argument('--headless')  # Uncomment for headless mode
        
        service = ChromeService(executable_path=get_chromedriver_path())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        print(f"🌐 Navigating to: {BASE_URL}")
        driver.get(BASE_URL)
        
        # Wait for page load
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        print("⏳ Page loaded, extracting bid listings...")
        
        # Extract bid summary information
        summary_bids = extract_summary_table(driver)
        
        if not summary_bids:
            print("❌ No bids found in summary table")
            return all_bids, failed_urls
        
        print(f"📊 Found {len(summary_bids)} bids in summary")
        
        # Process each bid - no detail page extraction needed
        for i, bid in enumerate(summary_bids, 1):
            print(f"\n� Processing bid {i}/{len(summary_bids)}: {bid.get('title', 'Unknown')}")
            
            try:
                # Parse and validate dates (no detail page needed)
                published_date = None
                if bid.get('published_date'):
                    try:
                        published_date = parse_mmddyyyy(bid['published_date'])
                    except:
                        print(f"    ⚠️  Could not parse published date: {bid['published_date']}")
                
                due_date = None
                if bid.get('due_date'):
                    try:
                        due_date = parse_mmddyyyy(bid['due_date'])
                    except:
                        print(f"    ⚠️  Could not parse due date: {bid['due_date']}")
                
                # Apply date filtering
                if published_date and published_date < cutoff_date:
                    print(f"    📅 Skipping old bid: {published_date.strftime('%m/%d/%Y')}")
                    continue
                
                # Create final bid record (title serves as both title and summary)
                bid_record = {
                    'project_title': bid.get('title', ''),           # Use standard field names for main.py
                    'scope_of_services': bid.get('summary', ''),    # Title as summary
                    'bid_posting_date': bid.get('published_date', ''),
                    'bid_due_date': bid.get('due_date', ''),
                    'detail_url': bid.get('detail_url', ''),
                    'source': 'New City'  # Update with actual city name
                }
                
                all_bids.append(bid_record)
                print(f"    ✅ Added bid: {bid_record['project_title']}")
                
            except Exception as e:
                print(f"    ❌ Error processing bid {i}: {e}")
                continue
        
    except Exception as e:
        print(f"❌ Critical error in New City scraping: {e}")
        failed_urls.append(BASE_URL)
        
    finally:
        if driver:
            driver.quit()
    
    print(f"\n✅ New City scraping completed!")
    print(f"   📊 Total bids extracted: {len(all_bids)}")
    print(f"   ❌ Failed URLs: {len(failed_urls)}")
    
    return all_bids, failed_urls


def main():
    """
    Main function to run New City scraping with all processing steps.
    """
    try:
        print("=" * 60)
        print("🏛️  NEW CITY GOVERNMENT BIDS SCRAPER")
        print("=" * 60)
        
        # Set cutoff date (30 days ago)
        cutoff_date = datetime.now() - pd.Timedelta(days=30)
        print(f"📅 Date filter: Only bids published after {cutoff_date.strftime('%m/%d/%Y')}")
        
        # Scrape bids
        scraped_bids, failed_urls = scrape_new_city(cutoff_date)
        
        if not scraped_bids:
            print("❌ No bids were scraped successfully")
            return
        
        # Create DataFrame
        df = pd.DataFrame(scraped_bids)
        
        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
        
        # Save to CSV in original format
        df.to_csv(OUTPUT_CSV, index=False, encoding='utf-8')
        print(f"💾 Saved {len(df)} bids to: {OUTPUT_CSV}")
        
        # Save in Airtable format
        airtable_csv = OUTPUT_CSV.replace('.csv', '_airtable.csv')
        save_airtable_format_csv(scraped_bids, airtable_csv)
        print(f"💾 Saved Airtable format to: {airtable_csv}")
        
        # Save failed URLs if any
        if failed_urls:
            save_failed_pages_batch(failed_urls, f"failed_urls_new_city_{datetime.now().strftime('%Y%m%d')}.txt")
        
        # Display summary
        print(f"\n📊 SCRAPING SUMMARY:")
        print(f"   🎯 Bids found: {len(scraped_bids)}")
        print(f"   ❌ Failed pages: {len(failed_urls)}")
        
        # Show sample bids
        if len(scraped_bids) > 0:
            print(f"\n📋 Sample bids:")
            for i, bid in enumerate(scraped_bids[:3]):  # Show first 3
                print(f"   {i+1}. {bid['title']}")
                if bid.get('published_date'):
                    print(f"      📅 Published: {bid['published_date']}")
                if bid.get('due_date'):
                    print(f"      ⏰ Due: {bid['due_date']}")
        
    except Exception as e:
        print(f"❌ Error in main execution: {e}")


if __name__ == "__main__":
    main()

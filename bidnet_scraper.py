"""
BidNet Direct Scraper for Santa Clarita

This module provides comprehensive scraping functionality for BidNet Direct 
procurement portals with SAML authentication. It extracts summary table data
and detailed bid information including descriptions from individual bid pages.

Key Features:
    - SAML authentication handling
    - Summary table data extraction
    - Individual bid page scraping for descriptions
    - Date filtering for recent bids only
    - CSV output with Airtable-compatible format
    - Robust error handling and retry logic

Author: Development Team
Created: 2025-11-09

Dependencies:
    - selenium: Web automation and browser control
    - undetected-chromedriver: Anti-bot detection browser
    - beautifulsoup4: HTML parsing and data extraction
    - pandas: Data manipulation and CSV output

Usage:
    python bidnet_scraper.py
    
    or
    
    from bidnet_scraper import scrape_all
    data, stats = scrape_all(date_filter="11/01/2025")
"""

# Standard library imports
import csv
import os
import re
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Third-party imports
import pandas as pd
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, WebDriverException
from dotenv import load_dotenv

# Local imports
from utils import (
    parse_mmddyyyy, 
    save_failed_pages_batch,
    save_airtable_format_csv
)

# Load environment variables
load_dotenv()

# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================

# BidNet Direct URLs
LOGIN_URL = "https://www.bidnetdirect.com/saml/login"
SANTA_CLARITA_URL = "https://www.bidnetdirect.com/california/cityofsantaclarita"

# Output Configuration
OUTPUT_CSV = "bidnet/bidnet_santa_clarita_bids.csv"

# =============================================================================
# AUTHENTICATION FUNCTIONS
# =============================================================================

def login_to_bidnet(driver) -> bool:
    """
    Handle SAML authentication for BidNet Direct.
    
    Args:
        driver: Selenium WebDriver instance
        
    Returns:
        bool: True if login successful, False otherwise
    """
    try:
        print("🔐 Navigating to BidNet Direct login page...")
        driver.get(LOGIN_URL)
        
        # Wait for login form to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # Get credentials from environment variables
        username = os.getenv('BIDNET_USERNAME')
        password = os.getenv('BIDNET_PASSWORD')
        
        if not username or not password:
            print("❌ BidNet credentials not found in environment variables")
            print("   Please set BIDNET_USERNAME and BIDNET_PASSWORD")
            return False
        
        print("🔍 Looking for login form elements...")
        
        # Wait a moment for the page to fully load
        time.sleep(3)
        
        # Look for common login form elements
        username_selectors = [
            "input[name='username']",
            "input[name='email']", 
            "input[type='email']",
            "input[id*='username']",
            "input[id*='email']",
            "input[placeholder*='username']",
            "input[placeholder*='email']"
        ]
        
        password_selectors = [
            "input[name='password']",
            "input[type='password']",
            "input[id*='password']",
            "input[placeholder*='password']"
        ]
        
        username_field = None
        password_field = None
        
        # Try to find username field
        for selector in username_selectors:
            try:
                username_field = driver.find_element(By.CSS_SELECTOR, selector)
                if username_field.is_displayed():
                    print(f"✓ Found username field: {selector}")
                    break
            except:
                continue
        
        # Try to find password field
        for selector in password_selectors:
            try:
                password_field = driver.find_element(By.CSS_SELECTOR, selector)
                if password_field.is_displayed():
                    print(f"✓ Found password field: {selector}")
                    break
            except:
                continue
        
        if not username_field or not password_field:
            print("❌ Could not locate login form fields")
            print("🤖 Manual intervention required:")
            print("   1. Complete the login process manually in the browser")
            print("   2. Navigate to the bid listing page")
            print("   3. Press ENTER here to continue scraping")
            input(">>> Press ENTER when logged in and ready to continue...\n")
            return True
        
        # Fill in credentials
        print("📝 Entering credentials...")
        username_field.clear()
        username_field.send_keys(username)
        
        password_field.clear()
        password_field.send_keys(password)
        
        # Look for submit button
        submit_selectors = [
            "input[type='submit']",
            "button[type='submit']", 
            "button:contains('Login')",
            "button:contains('Sign In')",
            "input[value*='Login']",
            "input[value*='Sign In']"
        ]
        
        submit_button = None
        for selector in submit_selectors:
            try:
                submit_button = driver.find_element(By.CSS_SELECTOR, selector)
                if submit_button.is_displayed():
                    print(f"✓ Found submit button: {selector}")
                    break
            except:
                continue
        
        if submit_button:
            print("🚀 Submitting login form...")
            submit_button.click()
            
            # Wait for redirect or next page
            time.sleep(5)
            
            # Check if login was successful
            if "login" in driver.current_url.lower():
                print("⚠️  Still on login page - may need manual intervention")
            else:
                print("✅ Login appears successful")
                
        else:
            print("❌ Could not find submit button")
            print("🤖 Manual intervention required:")
            print("   1. Complete the login process manually in the browser")
            print("   2. Press ENTER here to continue")
            input(">>> Press ENTER when logged in and ready to continue...\n")
        
        return True
        
    except Exception as e:
        print(f"❌ Login error: {e}")
        print("🤖 Manual intervention required:")
        print("   1. Complete the login process manually in the browser")
        print("   2. Press ENTER here to continue scraping")
        input(">>> Press ENTER when logged in and ready to continue...\n")
        return True

# =============================================================================
# SCRAPING FUNCTIONS
# =============================================================================

def extract_summary_data(driver, date_filter: str = None) -> List[Dict[str, str]]:
    """
    Extract summary bid data from Santa Clarita listing page.
    
    Args:
        driver: Selenium WebDriver instance
        date_filter: Date filter in MM/DD/YYYY format
        
    Returns:
        List[Dict[str, str]]: List of bid records with summary data
    """
    print("📊 Extracting summary data from bid listing page...")
    
    try:
        # Wait for the bid table to load
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".sol-table, .mets-table"))
        )
        
        soup = BeautifulSoup(driver.page_source, "html.parser")
        items = []
        
        # Find the bid table
        table = soup.select_one(".sol-table, .mets-table")
        if not table:
            print("❌ Could not find bid table")
            return items
        
        # Find all bid rows (exclude header and empty rows)
        bid_rows = table.select("tr.mets-table-row:not(.mets-table-row-empty)")
        print(f"✓ Found {len(bid_rows)} bid rows")
        
        # Parse date filter
        filter_date = None
        if date_filter:
            filter_date = parse_mmddyyyy(date_filter)
            print(f"🗓️  Applying date filter: Only bids from {date_filter} onward")
        
        for row in bid_rows:
            try:
                # Extract solicitation number
                sol_num_div = row.select_one(".sol-num")
                solicitation_number = sol_num_div.get_text(strip=True) if sol_num_div else ""
                
                # Extract title and URL
                title_link = row.select_one(".sol-title a")
                if title_link:
                    title = title_link.get_text(strip=True)
                    detail_href = title_link.get('href', '')
                    # Convert relative URL to absolute
                    if detail_href.startswith('/'):
                        detail_url = f"https://www.bidnetdirect.com{detail_href}"
                    else:
                        detail_url = detail_href
                else:
                    title = ""
                    detail_url = ""
                
                # Extract region
                region_span = row.select_one(".sol-region-item")
                region = region_span.get_text(strip=True) if region_span else ""
                
                # Extract publication date
                pub_date_span = row.select_one(".sol-publication-date .date-value")
                published_date = pub_date_span.get_text(strip=True) if pub_date_span else ""
                
                # Extract closing date  
                close_date_span = row.select_one(".sol-closing-date .date-value")
                closing_date = close_date_span.get_text(strip=True) if close_date_span else ""
                
                # Apply date filter if specified
                if filter_date and published_date:
                    # Convert published_date to datetime for comparison
                    pub_dt = parse_mmddyyyy(published_date)
                    if pub_dt and pub_dt < filter_date:
                        continue
                
                # Skip if essential fields are missing
                if not title or not solicitation_number:
                    continue
                
                item = {
                    'solicitation_number': solicitation_number,
                    'project_title': title,
                    'region': region,
                    'published_date': published_date,
                    'closing_date': closing_date,
                    'detail_url': detail_url,
                    'source_url': driver.current_url,
                    'scraped_at': datetime.now().isoformat()
                }
                
                items.append(item)
                print(f"✓ Extracted: {solicitation_number} - {title[:50]}...")
                
            except Exception as e:
                print(f"⚠️  Error parsing row: {e}")
                continue
        
        print(f"✅ Successfully extracted {len(items)} summary items")
        return items
        
    except TimeoutException:
        print("❌ Timeout waiting for bid table to load")
        return []
    except Exception as e:
        print(f"❌ Error extracting summary data: {e}")
        return []

def scrape_bid_description(driver, detail_url: str) -> str:
    """
    Scrape the detailed description from an individual bid page.
    
    Args:
        driver: Selenium WebDriver instance
        detail_url: URL of the individual bid page
        
    Returns:
        str: The bid description/summary
    """
    try:
        print(f"  📖 Fetching description from: {detail_url}")
        driver.get(detail_url)
        
        # Wait for the description section to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        time.sleep(2)  # Allow page to fully render
        
        soup = BeautifulSoup(driver.page_source, "html.parser")
        
        # Look for the description field based on the HTML structure you provided
        description_selectors = [
            "#descriptionText",  # Primary selector from your HTML
            ".description .mets-field-body",
            ".wysiwyg",
            ".mets-ellipsis-wrapper",
            "[class*='description'] p",
            ".mets-field-view .mets-field-body"
        ]
        
        description = ""
        for selector in description_selectors:
            desc_element = soup.select_one(selector)
            if desc_element:
                description = desc_element.get_text(strip=True)
                if description:
                    print(f"    ✓ Found description ({len(description)} chars)")
                    break
        
        # If no description found, try to get any substantial text content
        if not description:
            # Look for paragraphs with substantial content
            paragraphs = soup.select("p")
            for p in paragraphs:
                text = p.get_text(strip=True)
                if len(text) > 50:  # Substantial content
                    description = text
                    break
        
        return description[:1000] + "..." if len(description) > 1000 else description
        
    except Exception as e:
        print(f"    ❌ Error fetching description: {e}")
        return ""

def scrape_bid_description_and_dates(driver, detail_url: str) -> Tuple[str, Optional[str]]:
    """
    Scrape the detailed description and published date from an individual bid page.
    Returns (description, published_date)
    """
    try:
        print(f"  📖 Fetching description and dates from: {detail_url}")
        driver.get(detail_url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(2)
        soup = BeautifulSoup(driver.page_source, "html.parser")

        # --- Description extraction (existing logic) ---
        description = ""
        description_selectors = [
            "#descriptionText", ".description .mets-field-body", ".wysiwyg",
            ".mets-ellipsis-wrapper", "[class*='description'] p", ".mets-field-view .mets-field-body"
        ]
        for selector in description_selectors:
            desc_element = soup.select_one(selector)
            if desc_element:
                description = desc_element.get_text(strip=True)
                if description:
                    break
        if not description:
            paragraphs = soup.select("p")
            for p in paragraphs:
                text = p.get_text(strip=True)
                if len(text) > 50:
                    description = text
                    break

        # --- Published date extraction ---
        published_date = None
        pub_label = soup.find("span", string=re.compile(r"Publication", re.I))
        if pub_label:
            pub_body = pub_label.find_next("div", class_="mets-field-body")
            if pub_body:
                pub_text = pub_body.get_text(strip=True)
                match = re.search(r"\d{2}/\d{2}/\d{4}", pub_text)
                if match:
                    published_date = match.group(0)
                else:
                    published_date = pub_text  # fallback: raw text

        return description[:1000] + "..." if len(description) > 1000 else description, published_date

    except Exception as e:
        print(f"    ❌ Error fetching description/dates: {e}")
        return "", None

def scrape_all(date_filter: str = None) -> Tuple[pd.DataFrame, Dict]:
    """
    Main scraping function for BidNet Direct Santa Clarita.
    
    Args:
        date_filter: Date filter in MM/DD/YYYY format
        
    Returns:
        Tuple[pd.DataFrame, Dict]: Scraped data and statistics
    """
    print("\n" + "="*60)
    print("BIDNET DIRECT SCRAPER - SANTA CLARITA")
    print("="*60)
    
    # Initialize stats tracking
    scraping_stats = {
        'successful_sites': [],
        'skipped_sites': [],
        'failed_pages': [],
        'total_bids': 0,
        'total_sites_attempted': 1,
        'total_sites_successful': 0,
        'total_pages_attempted': 0,
        'total_pages_failed': 0
    }
    
    all_items = []
    
    # Create browser instance
    driver = uc.Chrome()
    
    try:
        # Step 1: Login to BidNet Direct
        login_success = login_to_bidnet(driver)
        if not login_success:
            print("❌ Login failed, aborting scrape")
            return pd.DataFrame(), scraping_stats
        
        # Step 2: Navigate to Santa Clarita bid listing
        print(f"\n🌐 Navigating to Santa Clarita bid listing...")
        driver.get(SANTA_CLARITA_URL)
        
        # Wait for page to load
        time.sleep(5)
        
        # Step 3: Extract summary data from listing page
        summary_items = extract_summary_data(driver, date_filter)
        
        if not summary_items:
            print("⚠️  No summary items found")
            scraping_stats['skipped_sites'].append({
                'portal_code': 'santa_clarita',
                'url': SANTA_CLARITA_URL,
                'reason': 'No bids found'
            })
            return pd.DataFrame(), scraping_stats
        
        scraping_stats['total_pages_attempted'] = len(summary_items)
        
        # Step 4: Scrape detailed descriptions from individual pages
        print(f"\n📖 Scraping detailed descriptions for {len(summary_items)} bids...")
        
        for i, item in enumerate(summary_items):
            detail_url = item.get('detail_url')
            if detail_url:
                try:
                    # Scrape description and published date from detail page
                    description, published_date_detail = scrape_bid_description_and_dates(driver, detail_url)
                    item['summary'] = description

                    # Add Airtable-compatible field mappings
                    item['Project Title'] = item['project_title']
                    item['Summary'] = description
                    # Prefer summary published_date, else use detail page
                    item['Published Date'] = item['published_date'] if item['published_date'] else (published_date_detail or "")
                    item['Due Date'] = item['closing_date']
                    item['Link'] = detail_url

                    # Add metadata
                    item['portal_code'] = 'bidnet_santa_clarita'
                    item['city_name'] = 'Santa Clarita'

                    all_items.append(item)

                except Exception as e:
                    print(f"    ❌ Failed to scrape detail for {item.get('solicitation_number')}: {e}")
                    scraping_stats['failed_pages'].append({
                        'portal_code': 'santa_clarita',
                        'solicitation_number': item.get('solicitation_number'),
                        'detail_url': detail_url,
                        'reason': f'Detail scraping failed: {str(e)[:100]}...'
                    })
                    scraping_stats['total_pages_failed'] += 1
                    # Add item without description as fallback
                    item['summary'] = ""
                    item['Project Title'] = item['project_title']
                    item['Summary'] = ""
                    item['Published Date'] = item['published_date']
                    item['Due Date'] = item['closing_date']
                    item['Link'] = detail_url
                    item['portal_code'] = 'bidnet_santa_clarita'
                    item['city_name'] = 'Santa Clarita'
                    all_items.append(item)
            else:
                print(f"    ⚠️  No detail URL for {item.get('solicitation_number')}")
                # Add item without detail URL
                item['summary'] = ""
                item['Project Title'] = item['project_title']
                item['Summary'] = ""
                item['Published Date'] = item['published_date']
                item['Due Date'] = item['closing_date']
                item['Link'] = ""
                item['portal_code'] = 'bidnet_santa_clarita'
                item['city_name'] = 'Santa Clarita'
                all_items.append(item)
        
        # Update statistics
        if all_items:
            scraping_stats['successful_sites'].append({
                'portal_code': 'santa_clarita',
                'url': SANTA_CLARITA_URL,
                'bids_found': len(all_items)
            })
            scraping_stats['total_sites_successful'] = 1
            scraping_stats['total_bids'] = len(all_items)
            
            print(f"✅ Successfully scraped {len(all_items)} items from Santa Clarita")
        
    except Exception as e:
        print(f"❌ Critical error during scraping: {e}")
        scraping_stats['skipped_sites'].append({
            'portal_code': 'santa_clarita',
            'url': SANTA_CLARITA_URL,
            'reason': f'Critical error: {str(e)[:100]}...'
        })
        
    finally:
        driver.quit()
        print("🔒 Browser session closed")
    
    # Save failed URLs if any
    if scraping_stats.get('failed_pages'):
        save_failed_pages_batch(scraping_stats['failed_pages'], 'BidNet Direct')
    
    # Create DataFrame and save CSV
    if all_items:
        # Create output directory if it doesn't exist
        os.makedirs("bidnet", exist_ok=True)
        
        # Save raw data CSV
        print(f"\n💾 Saving BidNet data to CSV...")
        save_airtable_format_csv(all_items, OUTPUT_CSV, "BidNet Direct")
        print(f"✅ BidNet data saved to: {OUTPUT_CSV}")
        
        df = pd.DataFrame(all_items)
        return df, scraping_stats
    else:
        print("⚠️  No BidNet data to save to CSV")
        return pd.DataFrame(), scraping_stats

# =============================================================================
# MAIN EXECUTION
# =============================================================================

def main() -> None:
    """
    Main execution function for BidNet Direct scraper.
    """
    print("\n" + "="*60)
    print("BIDNET DIRECT SCRAPER - SANTA CLARITA")
    print("="*60)
    print("⚠️  This scraper requires BidNet Direct login credentials")
    print("   Set BIDNET_USERNAME and BIDNET_PASSWORD environment variables")
    print("="*60 + "\n")
    
    # Run scraper without date filter for testing
    df, stats = scrape_all()
    
    if not df.empty:
        print(f"\n📊 Scraping completed successfully!")
        print(f"   Total records: {len(df)}")
        print(f"   Output file: {OUTPUT_CSV}")
    else:
        print(f"\n⚠️  No data was scraped")
    
    print("\n✅ BidNet Direct scraper completed")

if __name__ == "__main__":
    main()

"""
E-ARC Procurement Portal Scraper

CITI OF WHITTIER

This module provides scraping functionality for the E-ARC procurement portal,
specifically targeting public bid projects. It extracts bid information from
the summary table and constructs detail URLs for each project.

Key Features:
    - Robust table parsing for project data extraction
    - Date filtering for recent bids only  
    - Error handling for failed pages
    - CSV output in Airtable-compatible format
    - Anti-bot measures with undetected Chrome

Author: Development Team
Created: 2025-11-09
Modified: 2025-11-09

Dependencies:
    - selenium: Web automation and browser control
    - undetected-chromedriver: Anti-bot detection browser
    - beautifulsoup4: HTML parsing and data extraction
    - pandas: Data manipulation and CSV output

Usage:
    python earc_scraper.py
    
    or
    
    from earc_scraper import scrape_all
    scrape_all()
"""

# Standard library imports
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

# Local imports
from utils import (
    parse_mmddyyyy,
    save_failed_pages_batch,
    save_airtable_format_csv
)

# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================

# E-ARC Portal URL
PORTAL_URL = "https://customer.e-arc.com/arcEOC/Secures/PWELL_PrivateList.aspx?PrjType=pub"

# Output Configuration
OUTPUT_CSV = "earc/earc_bids.csv"

# =============================================================================
# CORE SCRAPING FUNCTIONS
# =============================================================================

def extract_project_id_from_onclick(onclick_text: str) -> Optional[str]:
    """
    Extract project ID from JavaScript onclick function.
    
    Args:
        onclick_text (str): The onclick attribute text
        
    Returns:
        Optional[str]: Extracted project ID or None if not found
    """
    if not onclick_text:
        return None
        
    # Look for patterns like "LogintoProject('0-99-7')" or "javascript:LogintoProject('0-99-7')"
    patterns = [
        r"LogintoProject\(['\"]([^'\"]+)['\"]",
        r"javascript:\s*LogintoProject\(['\"]([^'\"]+)['\"]",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, onclick_text)
        if match:
            return match.group(1)
    
    # Debug: print what we actually found
    print(f"   🔍 Debug onclick: {onclick_text}")
    return None


def construct_detail_url(project_id: str) -> str:
    """
    Construct the detail URL for a project based on its ID.
    
    Args:
        project_id (str): The project identifier
        
    Returns:
        str: Complete URL to the project detail page
    """
    # The detail URL appears to be a JavaScript function call, so we'll use the main portal
    # URL with the project ID as a parameter (this may need adjustment based on actual behavior)
    return f"https://customer.e-arc.com/arcEOC/Secures/PWELL_PrivateList.aspx?PrjType=pub&pid={project_id}"


def parse_date_string(date_str: str) -> Optional[datetime]:
    """
    Parse E-ARC date strings into datetime objects.
    
    Args:
        date_str (str): Date string from the portal
        
    Returns:
        Optional[datetime]: Parsed datetime or None if parsing fails
    """
    if not date_str or date_str.strip() in ['Not Available', '', 'N/A']:
        return None
        
    date_str = date_str.strip()
    
    # Try common date formats found in E-ARC
    formats = [
        '%m/%d/%Y %I:%M %p',  # "06/10/2021 12:59 PM"
        '%m/%d/%Y %H:%M',     # "06/10/2021 12:59"
        '%m/%d/%Y',           # "06/10/2021"
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    return None


def scrape_earc_portal(driver, date_filter: str = None) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """
    Scrape the E-ARC portal for bid information.
    
    Args:
        driver: Selenium WebDriver instance
        date_filter (str): Date filter in MM/DD/YYYY format
        
    Returns:
        Tuple containing:
            - List of successfully scraped bid records
            - List of failed page records
    """
    print(f"\n🌐 Scraping E-ARC portal: {PORTAL_URL}")
    
    successful_bids = []
    failed_pages = []
    
    try:
        # Load the main portal page
        print("⏳ Loading E-ARC portal...")
        driver.get(PORTAL_URL)
        
        # Wait for the page to load
        time.sleep(5)
        
        # Wait for the project grid to be present
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.ID, "divProjectGrid"))
            )
            print("✅ E-ARC portal loaded successfully")
        except TimeoutException:
            print("❌ E-ARC portal failed to load - project grid not found")
            failed_pages.append({
                'url': PORTAL_URL,
                'reason': 'Portal page failed to load - project grid not found',
                'timestamp': datetime.now().isoformat()
            })
            return successful_bids, failed_pages
        
        # Parse the page content
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Find the project grid table
        project_grid = soup.find('div', {'id': 'divProjectGrid'})
        if not project_grid:
            print("❌ Could not find project grid")
            failed_pages.append({
                'url': PORTAL_URL,
                'reason': 'Project grid not found in page content',
                'timestamp': datetime.now().isoformat()
            })
            return successful_bids, failed_pages
        
        # Find the data table within the grid
        data_table = project_grid.find('table', class_='obj')
        if not data_table:
            print("❌ Could not find data table")
            failed_pages.append({
                'url': PORTAL_URL,
                'reason': 'Data table not found in project grid',
                'timestamp': datetime.now().isoformat()
            })
            return successful_bids, failed_pages
        
        # Find all data rows (skip header rows)
        data_rows = data_table.find_all('tr', class_=['ev_light', 'odd_light'])
        print(f"📊 Found {len(data_rows)} project rows")
        
        # Process date filter
        filter_date = None
        if date_filter:
            filter_date = parse_mmddyyyy(date_filter)
            print(f"🗓️  Applying date filter: Only projects from {date_filter} onward")
        else:
            print("⚠️  No date filter provided - processing all projects")
        
        # Extract data from each row
        for idx, row in enumerate(data_rows, 1):
            try:
                cells = row.find_all('td')
                if len(cells) < 8:  # Should have 8 columns based on the structure
                    print(f"⚠️  Row {idx}: Insufficient columns ({len(cells)}), skipping")
                    continue
                
                # Extract project information
                # Column structure: Address, Project Number, Project Name, Description, Due Date, Post Date, Company, More Info
                
                # Project Number (contains the link and project ID)
                project_number_cell = cells[1]
                project_link = project_number_cell.find('a')
                
                if not project_link:
                    print(f"⚠️  Row {idx}: No project link found, skipping")
                    continue
                
                project_number = project_link.get_text(strip=True)
                onclick_attr = project_link.get('onclick', '')
                href_attr = project_link.get('href', '')
                
                # Try to extract project ID from onclick first
                project_id = extract_project_id_from_onclick(onclick_attr)
                
                # If that fails, try to extract from href or use project number as fallback
                if not project_id:
                    # Try href attribute
                    if href_attr and 'LogintoProject' in href_attr:
                        project_id = extract_project_id_from_onclick(href_attr)
                    
                    # If still no project ID, use the project number itself as the ID
                    if not project_id and project_number:
                        project_id = project_number
                        print(f"   ℹ️  Row {idx}: Using project number as ID: {project_id}")
                
                if not project_id:
                    print(f"⚠️  Row {idx}: Could not extract any project ID, skipping")
                    print(f"      onclick: {onclick_attr}")
                    print(f"      href: {href_attr}")
                    print(f"      project_number: {project_number}")
                    continue
                
                # Extract other fields
                project_name = cells[2].get_text(strip=True)
                project_description = cells[3].get_text(strip=True)
                due_date_str = cells[4].get_text(strip=True)
                post_date_str = cells[5].get_text(strip=True)
                company_name = cells[6].get_text(strip=True)
                
                # Parse dates
                due_date = parse_date_string(due_date_str)
                post_date = parse_date_string(post_date_str)
                
                # Apply date filter on post date
                if filter_date and post_date and post_date < filter_date:
                    continue
                
                # Construct detail URL
                detail_url = construct_detail_url(project_id)
                
                # Create bid record
                bid_record = {
                    'project_id': project_id,
                    'project_number': project_number,
                    'project_title': project_name,  # This is the main title field
                    'project_description': project_description,
                    'due_date_str': due_date_str,
                    'post_date_str': post_date_str,
                    'company_name': company_name,
                    'detail_url': detail_url,
                    'source_url': PORTAL_URL,
                    'scraped_at': datetime.now().isoformat(),
                    
                    # Airtable-compatible field mappings that match main.py expectations
                    'Project Title': project_name or project_number,  # Use number as fallback
                    'Summary': project_description or 'No description available',
                    'bid_posting_date': post_date_str,  # For main.py field mapping
                    'Release Date': post_date_str,       # Direct Airtable mapping
                    'bid_due_date': due_date_str,        # For main.py field mapping  
                    'Due Date': due_date_str,            # Direct Airtable mapping
                    'detail_url': detail_url,            # For main.py field mapping
                    'Link': detail_url                   # Direct Airtable mapping
                }
                
                successful_bids.append(bid_record)
                print(f"✅ Row {idx}: {project_number} - {project_name[:50]}...")
                
            except Exception as e:
                print(f"❌ Row {idx}: Error extracting data - {str(e)}")
                failed_pages.append({
                    'url': PORTAL_URL,
                    'reason': f'Row {idx} data extraction failed: {str(e)}',
                    'timestamp': datetime.now().isoformat()
                })
                continue
        
        print(f"✅ E-ARC scraping completed: {len(successful_bids)} projects extracted")
        
    except Exception as e:
        print(f"❌ E-ARC portal scraping failed: {str(e)}")
        failed_pages.append({
            'url': PORTAL_URL,
            'reason': f'Portal scraping failed: {str(e)}',
            'timestamp': datetime.now().isoformat()
        })
    
    return successful_bids, failed_pages


def scrape_all(date_filter: str = None) -> Tuple[pd.DataFrame, Dict]:
    """
    Scrape the E-ARC portal with robust error handling.
    
    Args:
        date_filter (str): Date filter in MM/DD/YYYY format
        
    Returns:
        tuple[pd.DataFrame, dict]: Scraped DataFrame and statistics
    """
    print("\n" + "="*60)
    print("E-ARC SCRAPER")
    print("="*60)
    
    scraping_stats = {
        'successful_sites': [],
        'failed_pages': [],
        'total_bids': 0,
        'total_sites_attempted': 1,
        'total_sites_successful': 0,
        'portal_name': 'E-ARC'
    }
    
    all_bids = []
    all_failed_pages = []
    
    # Use undetected Chrome for anti-bot protection
    driver = uc.Chrome()
    
    try:
        # Scrape the portal with retry logic
        max_retries = 3
        success = False
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    print(f"🔄 Retry attempt {attempt + 1}/{max_retries}")
                    time.sleep(3)  # Wait before retry
                
                bids, failed_pages = scrape_earc_portal(driver, date_filter)
                all_bids.extend(bids)
                all_failed_pages.extend(failed_pages)
                
                # Consider success if we got any data or confirmed empty state
                if bids or not failed_pages:
                    success = True
                    break
                    
            except Exception as e:
                print(f"⚠️  Attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    continue
                else:
                    all_failed_pages.append({
                        'url': PORTAL_URL,
                        'reason': f'All {max_retries} attempts failed: {str(e)}',
                        'timestamp': datetime.now().isoformat()
                    })
        
        # Update statistics
        if success:
            scraping_stats['successful_sites'].append({
                'portal_name': 'E-ARC',
                'url': PORTAL_URL,
                'bids_found': len(all_bids)
            })
            scraping_stats['total_sites_successful'] = 1
        
        scraping_stats['total_bids'] = len(all_bids)
        scraping_stats['failed_pages'] = all_failed_pages
        
    except Exception as e:
        print(f"❌ E-ARC scraper setup failed: {str(e)}")
        all_failed_pages.append({
            'url': PORTAL_URL,
            'reason': f'Scraper setup failed: {str(e)}',
            'timestamp': datetime.now().isoformat()
        })
        scraping_stats['failed_pages'] = all_failed_pages
        
    finally:
        driver.quit()
        print("🔒 Browser session closed")
    
    # Save failed URLs if any
    if all_failed_pages:
        print(f"💾 Saving {len(all_failed_pages)} failed pages to failed_urls.txt")
        save_failed_pages_batch(all_failed_pages, 'E-ARC')
    
    # Create DataFrame and save CSV
    if all_bids:
        df = pd.DataFrame(all_bids)
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
        
        # Save raw CSV (not Airtable format - that's handled in main.py)
        print(f"💾 Saving E-ARC raw data to {OUTPUT_CSV}")
        df.to_csv(OUTPUT_CSV, index=False)
        
        print(f"✅ E-ARC scraper completed successfully")
        print(f"   📊 Total bids: {len(all_bids)}")
        print(f"   🎯 Success rate: {scraping_stats['total_sites_successful']}/{scraping_stats['total_sites_attempted']}")
        
        return df, scraping_stats
    else:
        print("⚠️  No E-ARC data to save")
        return pd.DataFrame(), scraping_stats


def print_portal_summary(count, portal_name, error=None):
    if error:
        print(f"❌  [{portal_name}] Failed to scrape ({error})\n")
    elif count > 0:
        print(f"✅  [{portal_name}] {count} RFPs scraped\n")
    else:
        print(f"❌  [{portal_name}] No RFPs found\n")


def main() -> None:
    """
    Main execution function for E-ARC scraper.
    """
    print("\n" + "="*60)
    print("E-ARC SCRAPER - STANDALONE")
    print("="*60)
    
    # Run without date filter for testing
    df, stats = scrape_all()
    
    if not df.empty:
        print(f"\n📋 Sample of scraped data:")
        print(df[['Project Title', 'Summary', 'Release Date', 'Due Date']].head())
    
    print("\n✅ E-ARC scraper test completed")
    
    # Print summary for the portal
    print_portal_summary(len(df), 'E-ARC')


if __name__ == "__main__":
    main()

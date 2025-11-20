#!/usr/bin/env python3
"""
Bell Gardens RFP/Bids Scraper

Scrapes government bid opportunities from Bell Gardens, CA RFP portal.
Extracts bid information including title, dates, and detailed descriptions.

Author: Assistant
Created: 2025-11-08
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

BASE_URL = "https://www.bellgardens.org/i-want-to/view-bids-rfps/rfps-and-bids"
OUTPUT_CSV = "bell_gardens/bell_gardens_bids.csv"

# Retry Configuration
MAX_RETRIES = 3
RETRY_DELAY = 3  # seconds


def extract_summary_table(driver) -> List[Dict]:
    """
    Extract bid listings from Bell Gardens RFP overview page.
    
    Returns:
        List[Dict]: List of basic bid information from overview table
    """
    print("📋 Extracting bid listings from table...")
    bids = []
    
    try:
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Find the bids table
        table = soup.find('table', class_='listtable')
        if not table:
            print("  ⚠️  No bids table found")
            return bids
            
        # Find table body rows (skip header)
        tbody = table.find('tbody')
        if not tbody:
            print("  ⚠️  No table body found")
            return bids
            
        rows = tbody.find_all('tr')
        print(f"  📋 Found {len(rows)} bid rows")
        
        for i, row in enumerate(rows, 1):
            try:
                cells = row.find_all('td')
                if len(cells) < 4:
                    continue
                    
                # Extract title and link (first cell)
                title_cell = cells[0]
                link_elem = title_cell.find('a')
                if not link_elem:
                    continue
                    
                title = link_elem.get_text(strip=True)
                relative_url = link_elem.get('href')
                detail_url = urljoin(BASE_URL, relative_url) if relative_url else ""
                
                # Extract starting date (second cell)
                starting_date = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                
                # Extract closing date (third cell)  
                closing_date = cells[2].get_text(strip=True) if len(cells) > 2 else ""
                
                # Extract status (fourth cell)
                status = cells[3].get_text(strip=True) if len(cells) > 3 else ""
                
                bid_data = {
                    'project_title': title,
                    'bid_posting_date': starting_date,
                    'bid_due_date': closing_date,
                    'status': status,
                    'detail_url': detail_url,
                    'source_url': BASE_URL
                }
                
                bids.append(bid_data)
                print(f"  ✓ Extracted: {title[:60]}...")
                
            except Exception as e:
                print(f"  ✗ Error parsing row {i}: {e}")
                continue
                
    except Exception as e:
        print(f"❌ Error extracting summary table: {e}")
        
    return bids


def extract_detail_page(driver, detail_url: str) -> Dict[str, str]:
    """
    Extract detailed information from individual Bell Gardens bid page.
    
    Args:
        driver: Selenium WebDriver instance
        detail_url: URL to the detail page
        
    Returns:
        dict: Detailed bid information including scope of work
    """
    print(f"  🔍 Visiting detail page: {detail_url}")
    
    try:
        driver.get(detail_url)
        
        # Wait for page to load
        time.sleep(3)
        
        # Wait for main content
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except TimeoutException:
            print("  ⚠️  Page load timeout")

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        detail = {
            'detail_url': detail_url
        }
        
        # Extract detailed description from content areas
        description_parts = []
        
        # Remove navigation and script elements
        for element in soup(['script', 'style', 'nav', 'header', 'footer']):
            element.decompose()
        
        # Look for main content areas
        content_areas = soup.find_all(['div', 'section'], class_=lambda x: x and 'content' in str(x).lower())
        for area in content_areas:
            text = area.get_text(separator=' ', strip=True)
            if text and len(text) > 50:  # Only substantial content
                description_parts.append(text)
        
        # Also look for specific RFP content sections
        main_content = soup.find('main') or soup.find('article') or soup.find('div', class_='content_area')
        if main_content:
            text = main_content.get_text(separator=' ', strip=True)
            if text and len(text) > 50:
                description_parts.append(text)
        
        # If still no content, try to get all visible text
        if not description_parts:
            body_text = soup.get_text(separator=' ', strip=True)
            if body_text and len(body_text) > 100:
                description_parts.append(body_text)
        
        # Combine and clean description
        if description_parts:
            full_description = ' '.join(description_parts)
            # Clean up whitespace and limit length
            full_description = re.sub(r'\s+', ' ', full_description).strip()
            detail['scope_of_services'] = full_description[:2000] + "..." if len(full_description) > 2000 else full_description
        else:
            detail['scope_of_services'] = 'No detailed description available'
        
        print(f"  ✓ Extracted detail data - Description length: {len(detail['scope_of_services'])}")
        
        return detail

    except Exception as e:
        print(f"  ✗ Error extracting detail page: {e}")
        return {'detail_url': detail_url, 'error': str(e)}


def scrape_all(date_filter: str = None) -> Tuple[pd.DataFrame, Dict]:
    """
    Main scraping function for Bell Gardens RFPs/Bids.
    
    Args:
        date_filter: Date filter in MM/DD/YYYY format (optional)
        
    Returns:
        Tuple[pd.DataFrame, Dict]: Scraped data and statistics
    """
    print("\n" + "="*60)
    print("BELL GARDENS RFP/BIDS SCRAPER")
    print("="*60)
    
    all_items = []
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
    
    # Setup Chrome driver
    chrome_options = Options()
    # Uncomment for headless mode
    # chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--page-load-strategy=eager')

    driver = webdriver.Chrome(
        service=ChromeService(get_chromedriver_path()),
        options=chrome_options
    )
    
    try:
        print(f"\n🌐 Loading: {BASE_URL}")
        
        # Load main page with retry logic
        success = False
        for attempt in range(MAX_RETRIES):
            try:
                driver.get(BASE_URL)
                
                # Wait for page load
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                
                print(f"✓ Page loaded successfully")
                success = True
                break
                
            except TimeoutException:
                print(f"⚠️  Page load timeout (attempt {attempt + 1}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                    continue
                else:
                    raise
        
        if not success:
            raise Exception(f"Failed to load page after {MAX_RETRIES} attempts")
        
        # Give page extra time to render
        time.sleep(3)
        
        # Extract bid listings
        bid_items = extract_summary_table(driver)
        
        if not bid_items:
            print("⚠️  No bids found on overview page")
            scraping_stats['skipped_sites'].append({
                'url': BASE_URL,
                'reason': 'No bids found on overview page'
            })
            return pd.DataFrame(), scraping_stats
        
        print(f"✓ Found {len(bid_items)} bids on overview page\n")
        
        # Filter by date if provided
        if date_filter:
            print(f"🗓️  Applying date filter: {date_filter}")
            filter_date = parse_mmddyyyy(date_filter)
            if filter_date:
                filtered_items = []
                for item in bid_items:
                    # Check starting date
                    item_date = parse_mmddyyyy(item.get('bid_posting_date', ''))
                    if item_date and item_date >= filter_date:
                        filtered_items.append(item)
                
                print(f"✓ Filtered to {len(filtered_items)} bids after {date_filter}")
                bid_items = filtered_items
        
        scraping_stats['total_pages_attempted'] = len(bid_items)
        
        # Visit each detail page
        for idx, bid_item in enumerate(bid_items, 1):
            detail_link = bid_item.get('detail_url')
            
            if not detail_link:
                print(f"⚠️  Bid {idx}: No detail link found, using summary data only")
                all_items.append(bid_item)
                continue
            
            print(f"\n📄 Processing bid {idx}/{len(bid_items)}")
            print(f"   Title: {bid_item.get('project_title', 'Unknown')[:60]}...")
            
            # Scrape detail page with retry logic
            detail_data = None
            for attempt in range(MAX_RETRIES):
                try:
                    detail_data = extract_detail_page(driver, detail_link)
                    
                    if detail_data and not detail_data.get('error'):
                        break
                        
                except Exception as e:
                    print(f"  ⚠️  Attempt {attempt + 1} failed: {e}")
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY)
                        continue
                    else:
                        detail_data = {
                            'detail_url': detail_link,
                            'error': str(e)
                        }
            
            # Combine summary and detail data
            combined_item = {**bid_item, **detail_data} if detail_data else bid_item
            
            # Add source info
            combined_item['source_url'] = BASE_URL
            combined_item['city_name'] = 'Bell Gardens'
            
            if detail_data and not detail_data.get('error'):
                all_items.append(combined_item)
                scraping_stats['total_bids'] += 1
            else:
                # Track failed page
                scraping_stats['failed_pages'].append({
                    'detail_url': detail_link,
                    'reason': detail_data.get('error', 'Unknown error') if detail_data else 'No data extracted'
                })
                scraping_stats['total_pages_failed'] += 1
        
        if all_items:
            scraping_stats['successful_sites'].append({
                'city_name': 'Bell Gardens',
                'url': BASE_URL,
                'bids_found': len(all_items)
            })
            scraping_stats['total_sites_successful'] = 1
        
    except Exception as e:
        print(f"\n❌ Scraping failed: {e}")
        scraping_stats['skipped_sites'].append({
            'url': BASE_URL,
            'reason': f'Error: {str(e)[:100]}'
        })
        
    finally:
        driver.quit()
        print("\n[INFO] Browser session closed.")
    
    # Create DataFrame
    if all_items:
        df = pd.DataFrame(all_items)
        
        # Save to CSV in Airtable format
        print(f"\n💾 Saving data to CSV...")
        
        # Prepare data for Airtable format
        airtable_data = prepare_airtable_format(all_items)
        save_airtable_format_csv(airtable_data, OUTPUT_CSV, "Bell Gardens")
        
        print(f"✅ Saved {len(all_items)} records to: {OUTPUT_CSV}")
        
        return df, scraping_stats
    else:
        print("⚠️  No data to save")
        return pd.DataFrame(), scraping_stats


def prepare_airtable_format(items: List[Dict]) -> List[Dict]:
    """
    Convert scraped data to Airtable-compatible format.
    
    Maps scraped fields to the 6 standard Airtable columns:
    - Project Name
    - Summary (scope of services)
    - Published Date
    - Due Date (closing date)
    - Link
    - Date Scraped
    
    Args:
        items (List[Dict]): Raw scraped bid records
        
    Returns:
        List[Dict]: Records formatted for Airtable upload
    """
    from datetime import datetime
    
    airtable_records = []
    current_timestamp = datetime.now().strftime('%Y-%m-%d')
    
    for item in items:
        # Extract project name
        project_name = (
            item.get('project_title') or
            item.get('title') or
            'Unnamed Project'
        )
        
        # Extract scope/summary
        summary = (
            item.get('scope_of_services') or
            item.get('description') or
            'No description available'
        )
        
        # Extract publication date - clean to just date part
        published_date = item.get('bid_posting_date', '')
        if published_date:
            # Extract just the date part (remove time if present)
            date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', published_date)
            if date_match:
                published_date = date_match.group(1)
        
        # Extract closing/due date - clean to just date part
        due_date = item.get('bid_due_date', '')
        if due_date:
            # Extract just the date part (remove time if present)
            date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', due_date)
            if date_match:
                due_date = date_match.group(1)
        
        # Extract link
        link = item.get('detail_url') or BASE_URL
        
        record = {
            'Project Name': project_name,
            'Summary': summary[:2000] if len(summary) > 2000 else summary,  # Limit length for Airtable
            'Published Date': published_date,
            'Due Date': due_date,
            'Link': link,
            'Date Scraped': current_timestamp
        }
        
        airtable_records.append(record)
    
    return airtable_records


def display_scraping_report(stats: Dict) -> None:
    """
    Display comprehensive scraping report with statistics.
    
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
    print(f"   • Total bids found: {stats['total_bids']}")
    print(f"   • Total pages attempted: {stats['total_pages_attempted']}")
    print(f"   • Pages failed: {stats['total_pages_failed']}")
    
    if stats['total_pages_attempted'] > 0:
        success_rate = ((stats['total_pages_attempted'] - stats['total_pages_failed']) /
                       stats['total_pages_attempted'] * 100)
        print(f"   • Page success rate: {success_rate:.1f}%")
    
    # Successful Sites
    if stats['successful_sites']:
        print(f"\n✅ SUCCESSFULLY SCRAPED:")
        for site in stats['successful_sites']:
            print(f"   • {site['city_name']}: {site['bids_found']} bids")
    
    # Failed Pages
    if stats['failed_pages']:
        print(f"\n❌ FAILED PAGES ({len(stats['failed_pages'])}):")
        for page in stats['failed_pages'][:5]:  # Show first 5
            print(f"   • {page['detail_url']}")
            print(f"     Reason: {page['reason']}")
        
        if len(stats['failed_pages']) > 5:
            print(f"   ... and {len(stats['failed_pages']) - 5} more")
    
    print("="*80)


def print_portal_summary(count, portal_name, error=None):
    """
    Print summary of scraping results for a single portal.
    
    Args:
        count (int): Number of RFPs scraped
        portal_name (str): Name of the portal (e.g., city name)
        error (str, optional): Error message if scraping failed
    """
    if error:
        print(f"❌  [{portal_name}] Failed to scrape ({error})\n")
    elif count > 0:
        print(f"✅  [{portal_name}] {count} RFPs scraped\n")
    else:
        print(f"❌  [{portal_name}] No RFPs found\n")


def main() -> None:
    """
    Main execution function for Bell Gardens RFP/Bids scraper.
    
    Orchestrates the scraping workflow and saves results.
    """
    try:
        # Scrape all bids
        df, stats = scrape_all()
        
        # Display report
        display_scraping_report(stats)
        
        # Save failed pages if any
        if stats['failed_pages']:
            save_failed_pages_batch(stats['failed_pages'], 'Bell Gardens')
        
        # Print portal summary
        print_portal_summary(len(df), 'Bell Gardens')
        
        if not df.empty:
            print(f"\n🎉 SCRAPING COMPLETED SUCCESSFULLY!")
            print(f"   Data saved to: {OUTPUT_CSV}")
            print(f"   Total records: {len(df)}")
        else:
            print(f"\n⚠️  SCRAPING COMPLETED WITH NO DATA")
            
    except KeyboardInterrupt:
        print("\n\n✗ Scraping cancelled by user")
    except Exception as e:
        print(f"\n✗ An error occurred: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

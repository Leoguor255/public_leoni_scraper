"""
City of Artesia Bids Portal Scraper

This module provides scraping functionality for the City of Artesia bids portal.
Extracts bid information including scope of work, publication dates, and closing dates.

Key Features:
    - Selenium-based scraping for dynamic content
    - Summary table extraction
    - Detail page scraping for complete information
    - Date filtering for recent bids
    - Airtable-compatible CSV output
    - Robust error handling and retry logic

Author: Development Team
Created: 2025-11-08

Dependencies:
    - selenium: Web automation and browser control
    - beautifulsoup4: HTML parsing and data extraction
    - pandas: Data manipulation and CSV output
    - webdriver_manager: Automatic ChromeDriver management

Usage:
    python artesia_scraper.py

    or

    from artesia_scraper import scrape_all
    df, stats = scrape_all()
"""

# Standard library imports
import re
import time
from typing import Dict, List, Optional, Tuple

# Third-party imports
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Local imports
from utils import (
    get_chromedriver_path,
    parse_mmddyyyy,
    save_failed_pages_batch,
    save_airtable_format_csv
)

# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================

# City of Artesia Bids Portal URL
BASE_URL = "https://www.cityofartesia.us/Bids.aspx"

# Output Configuration
OUTPUT_CSV = "artesia/artesia_bids.csv"

# Retry Configuration
MAX_RETRIES = 3
RETRY_DELAY = 3  # seconds


# =============================================================================
# CORE SCRAPING FUNCTIONS
# =============================================================================

def extract_summary_table(driver) -> List[Dict[str, str]]:
    """
    Extract bid summary data from the main bids page.

    Parses the HTML div structure to extract basic bid information visible
    in the overview/listing page.

    Args:
        driver: Selenium WebDriver instance

    Returns:
        List[Dict[str, str]]: List of bid summary records with available fields

    Note:
        This function extracts what's visible in the overview. Full details
        require visiting individual bid pages.
    """
    print("📋 Extracting summary table data...")

    soup = BeautifulSoup(driver.page_source, 'html.parser')
    items = []

    # Look for all bid rows in the structure we identified:
    # <div class="listItemsRow bid">
    #   <div class="bidTitle">
    #     <a href="...">TITLE</a>
    #   </div>
    #   <div class="bidStatus">
    #     <span>Open</span>
    #     <span>12/19/2024 2:00 PM</span>
    #   </div>
    # </div>
    
    bid_rows = soup.find_all('div', class_='listItemsRow bid')
    print(f"✓ Found {len(bid_rows)} bid rows")
    
    for idx, bid_row in enumerate(bid_rows):
        try:
            # Extract bid title and link
            bid_title_div = bid_row.find('div', class_='bidTitle')
            if not bid_title_div:
                print(f"  ⚠️  Row {idx}: No bidTitle div found")
                continue
            
            # Get the main title link
            title_link = bid_title_div.find('a')
            if not title_link:
                print(f"  ⚠️  Row {idx}: No title link found")
                continue
                
            title = title_link.get_text(strip=True)
            href = title_link.get('href')
            
            # Handle relative URLs
            if href:
                if href.startswith('http'):
                    detail_link = href
                elif href.startswith('/'):
                    detail_link = f"https://www.cityofartesia.us{href}"
                else:
                    detail_link = f"https://www.cityofartesia.us/{href}"
            else:
                print(f"  ⚠️  Row {idx}: No href found for {title}")
                continue
            
            # Extract status information  
            bid_status_div = bid_row.find('div', class_='bidStatus')
            status = ""
            closing_date = ""
            
            if bid_status_div:
                status_spans = bid_status_div.find_all('span')
                for span in status_spans:
                    span_text = span.get_text(strip=True)
                    # Check for status (Open/Closed)
                    if span_text.lower() in ['open', 'closed']:
                        status = span_text
                    # Check for date (contains / and :)
                    elif '/' in span_text and ':' in span_text:
                        closing_date = span_text
            
            # Create record
            record = {
                'row_index': idx,
                'project_title': title,
                'status': status,
                'closing_date': closing_date,
                'detail_link': detail_link,
                'raw_data': bid_row.get_text(separator=' | ', strip=True)
            }
            
            items.append(record)
            print(f"  ✓ Extracted: {title} -> {detail_link}")
            
        except Exception as e:
            print(f"  ✗ Error parsing bid row {idx}: {e}")
            continue
    
    print(f"✓ Extracted {len(items)} summary records\n")

    # Show sample of first record for debugging
    if items:
        print(f"📝 Sample record (first row):")
        for key, value in list(items[0].items())[:5]:
            print(f"   • {key}: {value}")
        print()

    return items


def extract_detail_page(driver, detail_url: str) -> Dict[str, str]:
    """
    Extract detailed bid information from individual bid detail page.

    Navigates to the bid detail page and scrapes comprehensive information
    from the table structure, including full description, publication date,
    and closing date from the structured content.

    Args:
        driver: Selenium WebDriver instance
        detail_url (str): URL of the detail page

    Returns:
        Dict[str, str]: Detailed bid information including Summary field

    Note:
        Focuses on extracting:
        - Full description (for Summary field in Airtable)
        - Publication Date  
        - Closing Date/Time
        - Bid title and number
    """
    print(f"  🔍 Visiting detail page: {detail_url}")

    try:
        driver.get(detail_url)

        # Wait for page to load and give time for dynamic content
        time.sleep(5)

        # Wait for main content
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except TimeoutException:
            print("  ⚠️  Page load timeout")

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        detail = {
            'detail_url': detail_url
        }

        # Extract full page content for Summary (since content is in tables, not BidDetail span)
        # Remove navigation and script elements
        for element in soup(['script', 'style', 'nav', 'header', 'footer']):
            element.decompose()
        
        # Get all visible content
        full_content = soup.get_text(separator='\n', strip=True)
        
        # Clean up the content
        clean_content = re.sub(r'\n\s*\n', '\n\n', full_content)  # Normalize double line breaks
        clean_content = re.sub(r'\n{3,}', '\n\n', clean_content)  # Limit to max 2 line breaks
        
        # Use the cleaned content as the Summary (description)
        detail['summary'] = clean_content
        
        print(f"  ✓ Extracted full content - Summary length: {len(detail['summary'])}")
        
        # Extract specific fields from tables and content
        tables = soup.find_all('table')
        
        # Look for the main bid information table
        for table in tables:
            table_text = table.get_text(separator='\n', strip=True)
            
            # Extract bid number
            bid_num_match = re.search(r'Bid Number:\s*([^\n]+)', table_text, re.IGNORECASE)
            if bid_num_match:
                detail['bid_number'] = bid_num_match.group(1).strip()
            
            # Extract project title  
            title_match = re.search(r'Bid Title:\s*([^\n]+)', table_text, re.IGNORECASE)
            if title_match:
                detail['project_title'] = title_match.group(1).strip()
                
            # Extract closing date - look for date patterns and extract only the date part
            closing_patterns = [
                r'up to\s+\d{1,2}:\d{2}\s*[AP]\.?M\.?,\s*([A-Z]+\s+\d{1,2},\s*\d{4})',
                r'until\s+\d{1,2}:\d{2}\s*[AP]\.?M\.?,\s*([A-Z]+\s+\d{1,2},\s*\d{4})',
                r'\d{1,2}:\d{2}\s*[AP]\.?M\.?,\s*([A-Z]+\s+\d{1,2},\s*\d{4})',
                r'([A-Z]+\s+\d{1,2},\s*\d{4})',  # Just the date part
                r'(\d{1,2}/\d{1,2}/\d{4})',  # MM/DD/YYYY format
            ]
            
            for pattern in closing_patterns:
                closing_match = re.search(pattern, table_text, re.IGNORECASE)
                if closing_match:
                    date_text = closing_match.group(1).strip()
                    # Clean up the date (remove day names, extra text)
                    date_text = re.sub(r'^(MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|SUNDAY)\s*', '', date_text, flags=re.IGNORECASE)
                    detail['closing_date'] = date_text
                    break
        
        # Extract publication date from the full content and tables
        # Look for patterns in the NOTICE section and table structure
        pub_patterns = [
            r'Publication\s+Date[:/]Time[:/]\s*([A-Z]+\s+\d{1,2},\s*\d{4})',
            r'Publication\s+Date[:/]Time[:/]\s*(\d{1,2}/\d{1,2}/\d{4})',
            r'Publication\s+Date[:/]\s*([A-Z]+\s+\d{1,2},\s*\d{4})',
            r'Publication\s+Date[:/]\s*(\d{1,2}/\d{1,2}/\d{4})',
            r'Posted\s+on:?\s*([A-Z]+\s+\d{1,2},\s*\d{4})',
            r'Posted\s+on:?\s*(\d{1,2}/\d{1,2}/\d{4})',
            r'NOTICE IS HEREBY GIVEN\s+that.*?on\s+([A-Z]+\s+\d{1,2},\s*\d{4})',
        ]
        
        # First try to extract from tables (more structured)
        for table in tables:
            table_text = table.get_text(separator='\n', strip=True)
            
            # Look for "Publication Date/Time:" pattern in table and extract only date part
            for pattern in pub_patterns:
                pub_match = re.search(pattern, table_text, re.IGNORECASE | re.DOTALL)
                if pub_match:
                    date_text = pub_match.group(1).strip()
                    # Clean up the date (remove day names, time stamps)
                    date_text = re.sub(r'^(MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|SUNDAY)\s*', '', date_text, flags=re.IGNORECASE)
                    date_text = re.sub(r'\s+\d{1,2}:\d{2}.*$', '', date_text)  # Remove time portion
                    detail['publication_date'] = date_text
                    break
            
            if 'publication_date' in detail:
                break
        
        # If not found in tables, try full content
        if 'publication_date' not in detail:
            for pattern in pub_patterns:
                pub_match = re.search(pattern, full_content, re.IGNORECASE | re.DOTALL)
                if pub_match:
                    date_text = pub_match.group(1).strip()
                    # Clean up the date (remove day names, time stamps)
                    date_text = re.sub(r'^(MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|SUNDAY)\s*', '', date_text, flags=re.IGNORECASE)
                    date_text = re.sub(r'\s+\d{1,2}:\d{2}.*$', '', date_text)  # Remove time portion
                    detail['publication_date'] = date_text
                    break
        
        # Extract status from content
        status_match = re.search(r'Status:\s*([^\n]+)', full_content, re.IGNORECASE)
        if status_match:
            detail['status'] = status_match.group(1).strip()

        return detail

    except Exception as e:
        print(f"  ✗ Error extracting detail page: {e}")
        return {'detail_url': detail_url, 'error': str(e)}


def scrape_all(date_filter: str = None) -> Tuple[pd.DataFrame, Dict]:
    """
    Scrape City of Artesia bids portal.

    Opens browser, extracts summary table, visits detail pages for each bid,
    and returns comprehensive bid data with statistics.

    Args:
        date_filter (str): Date filter in MM/DD/YYYY format (e.g., "01/01/2025")

    Returns:
        Tuple[pd.DataFrame, Dict]: DataFrame with all scraped bid data and statistics dictionary

    Raises:
        WebDriverException: If browser automation fails
        Exception: For other errors during scraping
    """
    print("\n" + "="*60)
    print("CITY OF ARTESIA BIDS SCRAPER")
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

        # Extract summary table
        summary_items = extract_summary_table(driver)

        if not summary_items:
            print("⚠️  No bids found in summary table")
            scraping_stats['skipped_sites'].append({
                'url': BASE_URL,
                'reason': 'No bids found in summary table'
            })
            return pd.DataFrame(), scraping_stats

        print(f"✓ Found {len(summary_items)} bids in summary table\n")

        # Filter by date if provided
        if date_filter:
            print(f"🗓️  Applying date filter: {date_filter}")
            filter_date = parse_mmddyyyy(date_filter)
            if filter_date:
                # Try to filter based on available date fields
                filtered_items = []
                for item in summary_items:
                    # Check all fields for dates
                    item_has_recent_date = False
                    for key, value in item.items():
                        if 'date' in key.lower() and value:
                            item_date = parse_mmddyyyy(value)
                            if item_date and item_date >= filter_date:
                                item_has_recent_date = True
                                break

                    if item_has_recent_date:
                        filtered_items.append(item)

                print(f"✓ Filtered to {len(filtered_items)} bids after {date_filter}")
                summary_items = filtered_items

        scraping_stats['total_pages_attempted'] = len(summary_items)

        # Visit each detail page
        for idx, summary_item in enumerate(summary_items, 1):
            detail_link = summary_item.get('detail_link')

            if not detail_link:
                print(f"⚠️  Bid {idx}: No detail link found, using summary data only")
                all_items.append(summary_item)
                continue

            print(f"\n📄 Processing bid {idx}/{len(summary_items)}")

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
            combined_item = {**summary_item, **detail_data} if detail_data else summary_item

            # Add source info
            combined_item['source_url'] = BASE_URL
            combined_item['city_name'] = 'Artesia'

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
                'city_name': 'Artesia',
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
        save_airtable_format_csv(airtable_data, OUTPUT_CSV, "Artesia")

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
    - Summary (full description from detail page)
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
        # Extract project name from various possible fields
        project_name = (
            item.get('project_title') or
            item.get('bid_title') or
            item.get('title') or
            item.get('name') or
            'Unnamed Project'
        )

        # Extract summary - prioritize the detailed 'summary' field from detail page
        summary = (
            item.get('summary') or           # Full description from detail page
            item.get('scope_of_work') or
            item.get('description') or
            item.get('raw_data') or
            'No description available'
        )

        # Extract publication date
        published_date = (
            item.get('publication_date') or
            item.get('posted_date') or
            item.get('post_date') or
            item.get('published') or
            ''
        )

        # Extract closing/due date
        due_date = (
            item.get('closing_date') or
            item.get('due_date') or
            item.get('deadline') or
            item.get('close_date') or
            ''
        )

        # Extract link - use detail link if available, otherwise base URL
        link = item.get('detail_url') or item.get('detail_link') or BASE_URL

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
    Print summary of portal scraping results for a single city.

    Args:
        count (int): Number of RFPs (bids) scraped
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
    Main execution function for City of Artesia bids scraper.

    Orchestrates the scraping workflow and saves results.
    """
    try:
        # Scrape all bids
        df, stats = scrape_all()

        # Display report
        display_scraping_report(stats)

        # Save failed pages if any
        if stats['failed_pages']:
            save_failed_pages_batch(stats['failed_pages'], 'Artesia')

        if not df.empty:
            print(f"\n🎉 SCRAPING COMPLETED SUCCESSFULLY!")
            print(f"   Data saved to: {OUTPUT_CSV}")
            print(f"   Total records: {len(df)}")
        else:
            print(f"\n⚠️  SCRAPING COMPLETED WITH NO DATA")

        # Print portal summary
        print_portal_summary(len(df), 'Artesia')

    except KeyboardInterrupt:
        print("\n\n✗ Scraping cancelled by user")
    except Exception as e:
        print(f"\n✗ An error occurred: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

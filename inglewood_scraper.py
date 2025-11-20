"""
City of Inglewood Bids Portal Scraper ----- It's using Project name as summary

This module provides scraping functionality for the City of Inglewood bids portal.
Extracts bid information including scope of work, publication dates, and closing dates.

Key Features:
    - Selenium-based scraping for dynamic content
    - Summary table extraction
    - Detail page scraping for complete information
    - Date filtering for recent bids
    - Airtable-compatible CSV output
    - Robust error handling and retry logic

Author: Development Team
Created: 2025-11-09

Dependencies:
    - selenium: Web automation and browser control
    - beautifulsoup4: HTML parsing and data extraction
    - pandas: Data manipulation and CSV output
    - webdriver_manager: Automatic ChromeDriver management

Usage:
    python inglewood_scraper.py

    or

    from inglewood_scraper import scrape_all
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
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import undetected_chromedriver as uc

# Local imports
from utils import (
    parse_mmddyyyy,
    save_failed_pages_batch,
    save_airtable_format_csv
)

# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================

BASE_URL = "https://www.cityofinglewood.org/Bids.aspx"
OUTPUT_CSV = "inglewood/inglewood_bids.csv"
MAX_RETRIES = 3
RETRY_DELAY = 3  # seconds

# =============================================================================
# CORE SCRAPING FUNCTIONS
# =============================================================================

def handle_human_checkbox(driver):
    """
    If a 'confirm you are human' checkbox is present, tick it and wait for verification to clear.
    """
    try:
        # Wait for checkbox to be present and clickable
        checkbox = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//input[@type='checkbox' and contains(@aria-label, 'human')]"))
        )
        if not checkbox.is_selected():
            checkbox.click()
            print("✓ Ticked 'confirm you are human' checkbox.")
            # Wait longer for verification to clear
            time.sleep(8)
            # Try to interact with the page (scroll, mouse move)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)
    except Exception as e:
        print(f"[INFO] No or unclickable human checkbox found: {e}")
        pass  # Checkbox not present or not clickable

def detect_human_verification(driver, wait_time: int = 3) -> bool:
    """
    Detect if a human verification challenge (e.g., CAPTCHA, "I'm not a robot") is present.
    Waits for elements to load before checking.
    """
    print(f"🔍 Checking for human verification challenges...")
    time.sleep(wait_time)
    verification_selectors = [
        "iframe[src*='recaptcha']", ".g-recaptcha", "#recaptcha",
        ".cf-challenge-running", ".cf-browser-verification", "[data-ray]", ".challenge-running", ".challenge-form",
        "*[title*='robot']", "*[title*='verification']", "*[title*='human']", "*[aria-label*='robot']", "*[aria-label*='verification']",
        "*[value*='robot']", "*[value*='human']",
        "input[type='checkbox'][title*='robot']", "input[type='checkbox'][aria-label*='robot']",
        ".challenge-container", ".security-check", ".verify-container"
    ]
    try:
        for selector in verification_selectors:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                for element in elements:
                    if element.is_displayed():
                        print(f"   ✓ Found verification element: {selector}")
                        return True
        page_text = driver.page_source.lower()
        verification_texts = [
            "i'm not a robot", "verify you are human", "security check", "please verify", "captcha", "cloudflare",
            "checking your browser", "verifying you are human", "complete the security check"
        ]
        for text in verification_texts:
            if text in page_text:
                print(f"   ✓ Found verification text: '{text}'")
                return True
        loading_indicators = [
            ".challenge-running", ".cf-spinner", "[data-testid='challenge-spinner']"
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
        return True

def extract_summary_table(driver) -> List[Dict[str, str]]:
    print("📋 Extracting summary table data...")
    # Wait for at least one bid row to appear (dynamic content)
    try:
        WebDriverWait(driver, 20).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, 'div.listItemsRow.bid')
        )
    except TimeoutException:
        print("⚠️  Timeout waiting for bid rows to load.")
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    items = []
    bid_rows = soup.find_all('div', class_='listItemsRow bid')
    print(f"✓ Found {len(bid_rows)} bid rows")
    for idx, bid_row in enumerate(bid_rows):
        try:
            bid_title_div = bid_row.find('div', class_='bidTitle')
            if not bid_title_div:
                print(f"  ⚠️  Row {idx}: No bidTitle div found")
                continue
            # Find the <a> tag anywhere inside bidTitle
            title_link = bid_title_div.find('a', href=True)
            if not title_link:
                print(f"  ⚠️  Row {idx}: No title link found")
                continue
            title = title_link.get_text(strip=True)
            href = title_link.get('href')
            if href:
                if href.startswith('http'):
                    detail_link = href
                elif href.startswith('/'):
                    detail_link = f"https://www.cityofinglewood.org{href}"
                else:
                    detail_link = f"https://www.cityofinglewood.org/{href}"
            else:
                print(f"  ⚠️  Row {idx}: No href found for {title}")
                continue
            # Extract bid number from <span> with <strong>Bid No.</strong>
            bid_number = None
            for span in bid_title_div.find_all('span'):
                strong = span.find('strong')
                if strong and 'Bid No.' in strong.get_text():
                    bid_number = span.get_text(strip=True).replace('Bid No.', '').strip()
            # Extract status and closing date from the second inner <div> of .bidStatus
            bid_status_div = bid_row.find('div', class_='bidStatus')
            status = ""
            closing_date = ""
            if bid_status_div:
                inner_divs = bid_status_div.find_all('div')
                if len(inner_divs) > 1:
                    status_spans = inner_divs[1].find_all('span')
                    if len(status_spans) > 0:
                        status = status_spans[0].get_text(strip=True)
                    if len(status_spans) > 1:
                        closing_date = status_spans[1].get_text(strip=True)
            record = {
                'row_index': idx,
                'project_title': title,
                'bid_number': bid_number,
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
    return items

def extract_detail_page(driver, detail_url: str) -> Dict[str, str]:
    print(f"  🔍 Visiting detail page: {detail_url}")
    try:
        driver.get(detail_url)
        time.sleep(5)
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except TimeoutException:
            print("  ⚠️  Page load timeout")
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        detail = {'detail_url': detail_url}
        for element in soup(['script', 'style', 'nav', 'header', 'footer']):
            element.decompose()
        full_content = soup.get_text(separator='\n', strip=True)
        clean_content = re.sub(r'\n\s*\n', '\n\n', full_content)
        clean_content = re.sub(r'\n{3,}', '\n\n', clean_content)
        detail['summary'] = clean_content
        print(f"  ✓ Extracted full content - Summary length: {len(detail['summary'])}")
        tables = soup.find_all('table')
        for table in tables:
            table_text = table.get_text(separator='\n', strip=True)
            # Extract bid number
            bid_num_match = re.search(r'Bid No.\s*([\w-]+)', table_text, re.IGNORECASE)
            if bid_num_match:
                detail['bid_number'] = bid_num_match.group(1).strip()
            # Extract closing date
            closing_match = re.search(r'Closing Date/Time:\s*([\w\s:/]+)', table_text, re.IGNORECASE)
            if closing_match:
                detail['closing_date'] = closing_match.group(1).strip()
            # Extract publication date
            pub_match = re.search(r'Publication Date/Time:\s*([\w\s:/]+)', table_text, re.IGNORECASE)
            if pub_match:
                detail['publication_date'] = pub_match.group(1).strip()
            # Extract project title
            title_match = re.search(r'Description:\s*([\s\S]+?)(?:Publication Date/Time:|$)', table_text, re.IGNORECASE)
            if title_match:
                detail['description'] = title_match.group(1).strip()
        # Extract status
        status_match = re.search(r'Status:\s*([\w ]+)', full_content, re.IGNORECASE)
        if status_match:
            detail['status'] = status_match.group(1).strip()
        return detail
    except Exception as e:
        print(f"  ✗ Error extracting detail page: {e}")
        return {'detail_url': detail_url, 'error': str(e)}

def scrape_all(date_filter: str = None) -> Tuple[pd.DataFrame, Dict]:
    print("\n" + "="*60)
    print("CITY OF INGLEWOOD BIDS SCRAPER")
    print("="*60)
    print("➡️  [Inglewood] Scraping...")
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
    chrome_options = Options()
    # chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    driver = uc.Chrome(options=chrome_options)
    try:
        print(f"\n🌐 Loading: {BASE_URL}")
        success = False
        for attempt in range(MAX_RETRIES):
            try:
                driver.get(BASE_URL)
                if detect_human_verification(driver):
                    print("\n[MANUAL STEP] If you see a 'I am human' or captcha, please solve it in the browser window.")
                    input("Press Enter here in the terminal after you have solved the captcha and the bids are visible...")
                handle_human_checkbox(driver)
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
        time.sleep(3)
        summary_items = extract_summary_table(driver)
        if not summary_items:
            print("⚠️  No bids found in summary table")
            scraping_stats['skipped_sites'].append({
                'url': BASE_URL,
                'reason': 'No bids found in summary table'
            })
            return pd.DataFrame(), scraping_stats
        print(f"✓ Found {len(summary_items)} bids in summary table\n")
        if date_filter:
            print(f"🗓️  Applying date filter: {date_filter}")
            filter_date = parse_mmddyyyy(date_filter)
            if filter_date:
                filtered_items = []
                for item in summary_items:
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
        for idx, summary_item in enumerate(summary_items, 1):
            detail_link = summary_item.get('detail_link')
            if not detail_link:
                print(f"⚠️  Bid {idx}: No detail link found, using summary data only")
                all_items.append(summary_item)
                continue
            print(f"\n📄 Processing bid {idx}/{len(summary_items)}")
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
            combined_item = {**summary_item, **detail_data} if detail_data else summary_item
            combined_item['source_url'] = BASE_URL
            combined_item['city_name'] = 'Inglewood'
            if detail_data and not detail_data.get('error'):
                all_items.append(combined_item)
                scraping_stats['total_bids'] += 1
            else:
                scraping_stats['failed_pages'].append({
                    'detail_url': detail_link,
                    'reason': detail_data.get('error', 'Unknown error') if detail_data else 'No data extracted'
                })
                scraping_stats['total_pages_failed'] += 1
        if all_items:
            scraping_stats['successful_sites'].append({
                'city_name': 'Inglewood',
                'url': BASE_URL,
                'bids_found': len(all_items)
            })
            scraping_stats['total_sites_successful'] = 1
            print(f"✅  [Inglewood] {len(all_items)} RFP{'s' if len(all_items) != 1 else ''} scraped\n")
        else:
            print(f"❌  [Inglewood] No RFPs found\n")
    except Exception as e:
        print(f"\n❌  [Inglewood] Failed to scrape ({e})")
        scraping_stats['skipped_sites'].append({
            'url': BASE_URL,
            'reason': f'Error: {str(e)[:100]}'
        })
    finally:
        driver.quit()
        print("\n[INFO] Browser session closed.")
    if all_items:
        df = pd.DataFrame(all_items)
        print(f"\n💾 Saving data to CSV...")
        airtable_data = prepare_airtable_format(all_items)
        save_airtable_format_csv(airtable_data, OUTPUT_CSV, "Inglewood")
        print(f"✅ Saved {len(all_items)} records to: {OUTPUT_CSV}")
        return df, scraping_stats
    else:
        print("⚠️  No data to save")
        return pd.DataFrame(), scraping_stats

def prepare_airtable_format(items: List[Dict]) -> List[Dict]:
    from datetime import datetime
    import re
    airtable_records = []
    def to_iso_date(date_str):
        if not date_str:
            return ''
        # Try MM/DD/YYYY or MM/DD/YYYY HH:MM AM/PM
        m = re.match(r'(\d{1,2}/\d{1,2}/\d{4})', date_str)
        if m:
            try:
                return datetime.strptime(m.group(1), "%m/%d/%Y").strftime("%Y-%m-%d")
            except Exception:
                return ''
        # Try YYYY-MM-DD
        m = re.match(r'(\d{4}-\d{2}-\d{2})', date_str)
        if m:
            return m.group(1)
        return ''
    def is_valid_date(date_str):
        # Accept MM/DD/YYYY or YYYY-MM-DD
        try:
            if re.match(r'\d{1,2}/\d{1,2}/\d{4}', date_str):
                datetime.strptime(date_str.split()[0], "%m/%d/%Y")
                return True
            if re.match(r'\d{4}-\d{2}-\d{2}', date_str):
                datetime.strptime(date_str, "%Y-%m-%d")
                return True
        except Exception:
            return False
        return False
    for item in items:
        project_name = (
            item.get('project_title') or
            item.get('bid_title') or
            item.get('title') or
            item.get('name') or
            'Unnamed Project'
        )
        summary = project_name
        published_date_raw = (
            item.get('publication_date') or
            item.get('posted_date') or
            item.get('post_date') or
            item.get('published') or
            ''
        )
        published_date = to_iso_date(published_date_raw)
        due_date_raw = (
            item.get('closing_date') or
            item.get('due_date') or
            item.get('deadline') or
            item.get('close_date') or
            ''
        )
        due_date = to_iso_date(due_date_raw) if is_valid_date(due_date_raw) else ''
        link = item.get('detail_url') or item.get('detail_link') or BASE_URL
        record = {
            'Project Name': project_name,
            'Summary': summary,
            'Published Date': published_date,
            'Due Date': due_date,
            'Link': link
        }
        airtable_records.append(record)
    return airtable_records

def display_scraping_report(stats: Dict) -> None:
    print("\n" + "="*80)
    print("📊 SCRAPING REPORT")
    print("="*80)
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
    if stats['successful_sites']:
        print(f"\n✅ SUCCESSFULLY SCRAPED:")
        for site in stats['successful_sites']:
            print(f"   • {site['city_name']}: {site['bids_found']} bids")
    if stats['failed_pages']:
        print(f"\n❌ FAILED PAGES ({len(stats['failed_pages'])}):")
        for page in stats['failed_pages'][:5]:
            print(f"   • {page['detail_url']}")
            print(f"     Reason: {page['reason']}")
        if len(stats['failed_pages']) > 5:
            print(f"   ... and {len(stats['failed_pages']) - 5} more")
    print("="*80)

def print_portal_summary(count, portal_name, error=None):
    if error:
        print(f"❌  [{portal_name}] Failed to scrape ({error})\n")
    elif count > 0:
        print(f"✅  [{portal_name}] {count} RFPs scraped\n")
    else:
        print(f"❌  [{portal_name}] No RFPs found\n")

def main() -> None:
    try:
        df, stats = scrape_all()
        display_scraping_report(stats)
        if stats['failed_pages']:
            save_failed_pages_batch(stats['failed_pages'], 'Inglewood')
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

"""
City of San Gabriel Bids Portal Scraper

Scrapes bid opportunities from https://www.sangabrielcity.com/bids.aspx
Similar to inglewood_scraper, but no human verification required.

Author: Development Team
Created: 2025-11-09

Usage:
    python san_gabriel_scraper.py
    or
    from san_gabriel_scraper import scrape_all
    df, stats = scrape_all()
"""

import re
import time
from typing import Dict, List, Optional, Tuple
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
import undetected_chromedriver as uc
from utils import parse_mmddyyyy, save_failed_pages_batch, save_airtable_format_csv

BASE_URL = "https://www.sangabrielcity.com/bids.aspx"
OUTPUT_CSV = "san_gabriel/san_gabriel_bids.csv"
MAX_RETRIES = 2
RETRY_DELAY = 2


def extract_summary_table(driver) -> List[Dict[str, str]]:
    print("📋 Extracting summary table data...")
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
                continue
            title_link = bid_title_div.find('a', href=True)
            if not title_link:
                continue
            title = title_link.get_text(strip=True)
            href = title_link.get('href')
            if href.startswith('http'):
                detail_link = href
            else:
                detail_link = f"https://www.sangabrielcity.com/{href.lstrip('/')}"
            bid_number = None
            for span in bid_title_div.find_all('span'):
                strong = span.find('strong')
                if strong and 'Bid No.' in strong.get_text():
                    bid_number = span.get_text(strip=True).replace('Bid No.', '').strip()
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
        except Exception as e:
            print(f"  ✗ Error parsing bid row {idx}: {e}")
            continue
    print(f"✓ Extracted {len(items)} summary records\n")
    return items

def extract_detail_page(driver, detail_url: str) -> Dict[str, str]:
    print(f"  🔍 Visiting detail page: {detail_url}")
    try:
        driver.get(detail_url)
        time.sleep(3)
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except TimeoutException:
            print("  ⚠️  Page load timeout")
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        detail = {'detail_url': detail_url}
        # Extract Description
        desc = ""
        pub_date = ""
        closing_date = ""
        table = soup.find('table')
        if table:
            rows = table.find_all('tr')
            for i, row in enumerate(rows):
                header = row.find('span', class_='BidListHeader')
                if not header:
                    continue
                header_text = header.get_text(strip=True)
                if header_text == 'Description:':
                    desc_td = rows[i+1].find('span', class_='BidDetail')
                    if desc_td:
                        desc = desc_td.get_text(separator=' ', strip=True)
                elif header_text == 'Publication Date/Time:':
                    pub_td = rows[i+1].find('span', class_='BidDetail')
                    if pub_td:
                        pub_date = pub_td.get_text(strip=True)
                elif header_text == 'Closing Date/Time:':
                    close_td = rows[i+1].find('span', class_='BidDetail')
                    if close_td:
                        closing_date = close_td.get_text(strip=True)
        detail['summary'] = desc
        detail['publication_date'] = pub_date
        detail['closing_date'] = closing_date
        return detail
    except Exception as e:
        print(f"  ✗ Error extracting detail page: {e}")
        return {'detail_url': detail_url, 'error': str(e)}

def scrape_all(date_filter: str = None) -> Tuple[pd.DataFrame, Dict]:
    print("\n" + "="*60)
    print("CITY OF SAN GABRIEL BIDS SCRAPER")
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
    chrome_options = Options()
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    driver = uc.Chrome(options=chrome_options)
    try:
        print(f"\n🌐 Loading: {BASE_URL}")
        driver.get(BASE_URL)
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(2)
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
            combined_item['city_name'] = 'San Gabriel'
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
                'city_name': 'San Gabriel',
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
    if all_items:
        df = pd.DataFrame(all_items)
        print(f"\n💾 Saving data to CSV...")
        airtable_data = prepare_airtable_format(all_items)
        save_airtable_format_csv(airtable_data, OUTPUT_CSV, "San Gabriel")
        print(f"✅ Saved {len(all_items)} records to: {OUTPUT_CSV}")
        return df, scraping_stats
    else:
        print("⚠️  No data to save")
        return pd.DataFrame(), scraping_stats

def prepare_airtable_format(items: List[Dict]) -> List[Dict]:
    from datetime import datetime
    airtable_records = []
    for item in items:
        project_name = (
            item.get('project_title') or
            item.get('bid_title') or
            item.get('title') or
            item.get('name') or
            'Unnamed Project'
        )
        summary = item.get('summary') or item.get('description') or item.get('raw_data') or 'No description available'
        published_date = item.get('publication_date') or item.get('posted_date') or item.get('post_date') or item.get('published') or ''
        due_date = item.get('closing_date') or item.get('due_date') or item.get('deadline') or item.get('close_date') or ''
        link = item.get('detail_url') or item.get('detail_link') or BASE_URL
        record = {
            'Project Name': project_name,
            'Summary': summary[:2000] if len(summary) > 2000 else summary,
            'Published Date': published_date,
            'Due Date': due_date,
            'Link': link
        }
        airtable_records.append(record)
    return airtable_records

def main() -> None:
    try:
        df, stats = scrape_all()
        print(stats)
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

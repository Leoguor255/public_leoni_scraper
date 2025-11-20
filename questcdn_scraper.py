"""
QuestCDN Scraper for Glendora/Provider 5645931 (SPA-aware Selenium version)

Scrapes summary table and detail page for each bid/request in single-page application.

Author: Leonardo Gutarra
Created: 2025-11-12

Usage:
    python questcdn_scraper.py
"""

import os
import time
import re
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

# Supported QuestCDN URLs by city
URLS = {
    'glendora': "https://qcpi.questcdn.com/cdn/posting/?projType=all&provider=5645931&group=5645931",
    'monterey_park': "https://qcpi.questcdn.com/cdn/posting/?projType=all&provider=6486888&group=6486888"
}

SELENIUM_TIMEOUT = 20

def extract_detail_content(driver, quest_number):
    detail_data = {
        'description': '',
        'est_value': '',
        'scope': '',
        'contact_info': '',
        'documents': ''
    }
    try:
        WebDriverWait(driver, 15).until(
            EC.visibility_of_element_located((By.ID, "current_project"))
        )
        time.sleep(2)
        detail_soup = BeautifulSoup(driver.page_source, 'html.parser')
        current_project = detail_soup.find('div', id='current_project')
        if not current_project:
            print(f"   ⚠️  No current_project div found for {quest_number}")
            return detail_data
        # --- NEW LOGIC: Find Project Description accordion and extract only the correct Description row ---
        project_desc_summary = ''
        # Find all accordions and panels
        accordions = current_project.find_all('button', class_='accordion')
        panels = current_project.find_all('div', class_='panel')
        for btn, panel in zip(accordions, panels):
            btn_text = btn.get_text(strip=True).lower()
            if 'project description' in btn_text:
                # This is the Project Description panel
                table = panel.find('table')
                if table:
                    for tr in table.find_all('tr'):
                        tds = tr.find_all('td')
                        if len(tds) >= 2:
                            label = tds[0].get_text(strip=True).lower().rstrip(':')
                            if label == 'description':
                                project_desc_summary = tds[1].get_text(" ", strip=True)
                                break
                break  # Only one Project Description panel expected
        if project_desc_summary:
            detail_data['description'] = project_desc_summary
        # Fallback: original logic for other fields
        tables = current_project.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True).lower()
                    value = cells[1].get_text(" ", strip=True)
                    if not detail_data['description'] and 'description' in label and value:
                        # Only use if not already set by the Project Description panel
                        detail_data['description'] = value
                    elif 'estimate' in label or 'value' in label:
                        detail_data['est_value'] = value
                    elif 'scope' in label:
                        detail_data['scope'] = value
                    elif 'contact' in label or 'engineer' in label:
                        detail_data['contact_info'] = value
        # Fallback: if still no description, try to find any tr with first td 'Description:'
        if not detail_data['description']:
            for tr in current_project.find_all('tr'):
                tds = tr.find_all('td')
                if len(tds) >= 2 and tds[0].get_text(strip=True).lower().startswith('description'):
                    detail_data['description'] = tds[1].get_text(" ", strip=True)
                    break
        all_text = current_project.get_text(" ", strip=True)
        if all_text and len(all_text) > 50:
            if not detail_data['description']:
                detail_data['description'] = all_text[:500] + "..." if len(all_text) > 500 else all_text
        print(f"   📄 Extracted detail content for {quest_number}")
    except Exception as e:
        print(f"   ⚠️  Error extracting detail content for {quest_number}: {e}")
    return detail_data

def scrape_questcdn(base_url, output_csv, date_filter=None):
    print(f"🌐 Fetching: {base_url} (SPA-aware Selenium)")
    chrome_options = Options()
    # chrome_options.add_argument('--headless')  # DISABLED for debugging
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    # Debug: Print and check ChromeDriver path
    chromedriver_path = ChromeDriverManager().install()
    print(f"[DEBUG] ChromeDriverManager returned path: {chromedriver_path}")
    chromedriver_dir = os.path.dirname(chromedriver_path)
    chromedriver_bin = os.path.join(chromedriver_dir, 'chromedriver')
    print(f"[DEBUG] Checking for binary at: {chromedriver_bin}")
    if os.path.exists(chromedriver_bin):
        print(f"[DEBUG] Found file: {chromedriver_bin}")
        import stat
        st = os.stat(chromedriver_bin)
        print(f"[DEBUG] File mode: {oct(st.st_mode)}")
        if not os.access(chromedriver_bin, os.X_OK):
            print(f"[WARN] 'chromedriver' is not marked executable. Attempting to set permissions...")
            try:
                os.chmod(chromedriver_bin, st.st_mode | stat.S_IEXEC | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                print(f"[INFO] Set executable permissions on {chromedriver_bin}")
            except Exception as e:
                print(f"[ERROR] Could not set executable permissions: {e}")
        # Force use of chromedriver binary
        chromedriver_path = chromedriver_bin
        print(f"[PATCH] Forcing use of ChromeDriver binary: {chromedriver_path}")
    else:
        print(f"[ERROR] Could not find 'chromedriver' in {chromedriver_dir}, using default path: {chromedriver_path}")
    if not os.path.isfile(chromedriver_path):
        print(f"[ERROR] ChromeDriver binary not found at {chromedriver_path}")
    elif not os.access(chromedriver_path, os.X_OK):
        print(f"[ERROR] ChromeDriver at {chromedriver_path} is not executable!")
    else:
        with open(chromedriver_path, 'rb') as f:
            start = f.read(200)
            if b'THIRD_PARTY_NOTICES' in start or b'Copyright' in start:
                print(f"[ERROR] ChromeDriver at {chromedriver_path} appears to be a text file, not a binary!")
    service = Service(chromedriver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)
    all_bids = []
    failed_pages = []
    try:
        driver.get(base_url)
        WebDriverWait(driver, SELENIUM_TIMEOUT).until(
            EC.presence_of_element_located((By.ID, "table_id"))
        )
        WebDriverWait(driver, SELENIUM_TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#table_id tbody tr"))
        )
        time.sleep(3)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        table = soup.find('table', id='table_id')
        if not table:
            print("❌ Could not find bids table!")
            driver.quit()
            return pd.DataFrame(), {'total_bids': 0, 'failed_pages': failed_pages}
        rows = table.find('tbody').find_all('tr')
        print(f"📊 Found {len(rows)} bid rows in table")
        main_bid_info = []
        for i, row in enumerate(rows):
            try:
                cols = row.find_all('td')
                if len(cols) < 5:
                    continue
                post_date = cols[0].get_text(strip=True)
                quest_number = None
                quest_a = cols[1].find('a', onclick=True)
                if quest_a and 'prevnext' in quest_a['onclick']:
                    quest_number = re.search(r'prevnext\((\d+)\)', quest_a['onclick'])
                    if quest_number:
                        quest_number = quest_number.group(1)
                bid_name = ""
                bid_name_div = cols[3].find('div', attrs={'data-toggle': 'tooltip'})
                if bid_name_div and bid_name_div.has_attr('title'):
                    bid_name = bid_name_div['title'].strip()
                else:
                    bid_name = cols[3].get_text(" ", strip=True)
                due_date = cols[4].get_text(strip=True)
                if date_filter and post_date:
                    try:
                        bid_date = datetime.strptime(post_date, '%m/%d/%Y')
                        filter_date = datetime.strptime(date_filter, '%m/%d/%Y')
                        if bid_date < filter_date:
                            print(f"   ⏩ Skipping {quest_number} (older than filter)")
                            continue
                    except Exception as e:
                        print(f"   ⚠️  Date parsing error for {post_date}: {e}")
                main_bid_info.append({
                    'index': i,
                    'quest_number': quest_number,
                    'bid_name': bid_name,
                    'post_date': post_date,
                    'due_date': due_date
                })
            except Exception as e:
                print(f"❌ Error extracting main info from row {i}: {e}")
                failed_pages.append({
                    'url': base_url,
                    'error': f"Row {i} extraction: {e}",
                    'context': 'Main table parsing'
                })
        for bid_info in main_bid_info:
            quest_number = bid_info['quest_number']
            if not quest_number:
                continue
            print(f"🔄 Processing bid {bid_info['index']+1}: {bid_info['bid_name'][:60]}...")
            try:
                print(f"   👆 Clicking bid: {quest_number}")
                click_success = False
                try:
                    quest_link = driver.find_element(By.XPATH, f"//a[contains(@onclick, 'prevnext({quest_number})')]")
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", quest_link)
                    time.sleep(1)
                    quest_link.click()
                    click_success = True
                    print(f"   ✅ Clicked quest number link for {quest_number}")
                except Exception as e:
                    print(f"   ⚠️  Could not click quest number link: {e}")
                if not click_success:
                    try:
                        bid_link = driver.find_element(By.XPATH, f"//tr[.//a[contains(@onclick, 'prevnext({quest_number})')]]//td[4]//a")
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", bid_link)
                        time.sleep(1)
                        bid_link.click()
                        click_success = True
                        print(f"   ✅ Clicked bid name link for {quest_number}")
                    except Exception as e:
                        print(f"   ⚠️  Could not click bid name link: {e}")
                if click_success:
                    detail_content = extract_detail_content(driver, quest_number)
                    combined_summary = ""
                    if detail_content['description']:
                        combined_summary = detail_content['description']
                    elif detail_content['scope']:
                        combined_summary = detail_content['scope']
                    if not combined_summary:
                        combined_summary = f"Bid for {bid_info['bid_name']}. Due: {bid_info['due_date']}"
                    bid = {
                        'project_title': bid_info['bid_name'],
                        'bid_number': quest_number,
                        'published_date': bid_info['post_date'],
                        'due_date': bid_info['due_date'],
                        'scope_of_services': combined_summary,
                        'detail_url': base_url,
                        'source': 'QuestCDN',
                        'est_value': detail_content['est_value'],
                        'contact_info': detail_content['contact_info']
                    }
                    all_bids.append(bid)
                    print(f"   ✅ Saved bid {quest_number} with detail content")
                    try:
                        print(f"   ↩️  Returning to main listing")
                        search_postings_link = driver.find_element(By.XPATH, "//a[contains(@href, '/cdn/posting/') and contains(text(), 'Search Postings')]")
                        search_postings_link.click()
                        WebDriverWait(driver, 15).until(
                            EC.presence_of_element_located((By.ID, "table_id"))
                        )
                        time.sleep(2)
                    except Exception as e:
                        print(f"   ⚠️  Could not return via nav, refreshing page: {e}")
                        driver.get(base_url)
                        WebDriverWait(driver, 15).until(
                            EC.presence_of_element_located((By.ID, "table_id"))
                        )
                        time.sleep(2)
                else:
                    print(f"   ❌ Could not click any link for {quest_number}")
                    bid = {
                        'project_title': bid_info['bid_name'],
                        'bid_number': quest_number,
                        'published_date': bid_info['post_date'],
                        'due_date': bid_info['due_date'],
                        'scope_of_services': f"Bid for {bid_info['bid_name']}. Due: {bid_info['due_date']}",
                        'detail_url': base_url,
                        'source': 'QuestCDN'
                    }
                    all_bids.append(bid)
            except Exception as e:
                error_msg = f"Error processing bid {quest_number}: {e}"
                print(f"   ❌ {error_msg}")
                failed_pages.append({
                    'url': base_url,
                    'error': error_msg,
                    'context': f'Bid {quest_number} processing'
                })
        df = pd.DataFrame(all_bids)
        stats = {
            'total_bids': len(df),
            'failed_pages': failed_pages
        }
        print(f"✅ Successfully processed {len(df)} bids from QuestCDN")
        return df, stats
    except Exception as e:
        error_msg = f"Selenium error: {e}"
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        failed_pages.append({
            'url': base_url,
            'error': error_msg,
            'context': 'Main scraping process'
        })
        return pd.DataFrame(), {'total_bids': 0, 'failed_pages': failed_pages}
    finally:
        if driver:
            driver.quit()
            print("🔚 Browser closed")

def scrape_all(date_filter=None, url_keys=None):
    """
    Scrape all QuestCDN URLs (or a subset by url_keys).
    Returns a dict of DataFrames and stats keyed by city.
    Also saves per-city CSVs and a combined CSV for main pipeline use.
    """
    if url_keys is None:
        url_keys = list(URLS.keys())
    results = {}
    all_dfs = []
    for key in url_keys:
        base_url = URLS[key]
        output_csv = f"questcdn/questcdn_bids_{key}.csv"
        df, stats = scrape_questcdn(base_url, output_csv, date_filter)
        results[key] = (df, stats)
        # Save only Airtable columns for each city (for manual checking)
        if not df.empty:
            airtable_cols = ['project_title', 'scope_of_services', 'published_date', 'due_date', 'detail_url']
            df_airtable = df[airtable_cols].copy()
            # Normalize date fields
            def normalize_date(date_string):
                import re
                from datetime import datetime
                if not date_string or pd.isna(date_string):
                    return ""
                date_str = str(date_string).strip()
                if not date_str:
                    return ""
                date_str = re.sub(r'\s+\d{1,2}:\d{2}\s*(AM|PM).*$', '', date_str, flags=re.IGNORECASE)
                date_str = re.sub(r',.*$', '', date_str)
                if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', date_str):
                    try:
                        dt = datetime.strptime(date_str, '%m/%d/%Y')
                        return dt.strftime('%Y-%m-%d')
                    except:
                        pass
                month_day_year = re.match(r'^([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})$', date_str)
                if month_day_year:
                    try:
                        dt = datetime.strptime(date_str.replace(',', ''), '%B %d %Y')
                        return dt.strftime('%Y-%m-%d')
                    except:
                        pass
                month_day_only = re.match(r'^([A-Za-z]+)\s+(\d{1,2})$', date_str.strip())
                if month_day_only:
                    try:
                        current_year = datetime.now().year
                        full_date_str = f"{date_str.strip()} {current_year}"
                        dt = datetime.strptime(full_date_str, '%B %d %Y')
                        return dt.strftime('%Y-%m-%d')
                    except:
                        pass
                return ""
            df_airtable['published_date'] = df_airtable['published_date'].apply(normalize_date)
            df_airtable['due_date'] = df_airtable['due_date'].apply(normalize_date)
            df_airtable.to_csv(f"questcdn/questcdn_bids_{key}_airtable.csv", index=False)
            all_dfs.append(df_airtable)
    # Save combined CSV for main pipeline (questcdn_bids.csv)
    if all_dfs:
        combined = pd.concat(all_dfs, ignore_index=True)
        combined.to_csv("questcdn/questcdn_bids.csv", index=False)
    return results

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

if __name__ == "__main__":
    # By default, run all cities
    results = scrape_all()
    city_summaries = {key: len(df) for key, (df, stats) in results.items()}
    print_portal_summary(city_summaries, 'QuestCDN')
    for key, (df, stats) in results.items():
        if not df.empty:
            print(f"\n💾 Saved {len(df)} bids to questcdn/questcdn_bids_{key}.csv")
            print(f"📋 Sample data for {key}:")
            print(df.head())
        else:
            print(f"❌ No bids scraped for {key}")

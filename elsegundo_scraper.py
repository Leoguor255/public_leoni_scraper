"""
El Segundo Bids/RFP Scraper

Scrapes summary table and detail page for each bid/request from:
https://www.elsegundo.org/government/departments/city-clerk/bid-rfp

Outputs CSV with columns: project_title, scope_of_services, published_date, due_date, detail_url

Usage:
    python elsegundo_scraper.py
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import re
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

BASE_URL = "https://www.elsegundo.org"
LIST_URL = f"{BASE_URL}/government/departments/city-clerk/bid-rfp"
OUTPUT_CSV = "elsegundo/elsegundo_bids.csv"
SELENIUM_TIMEOUT = 20

# Utility to normalize date to YYYY-MM-DD

def normalize_date(date_string):
    if not date_string:
        return ""
    date_str = str(date_string).strip()
    date_str = re.sub(r'\s+\d{1,2}:\d{2}\s*(AM|PM).*$', '', date_str, flags=re.IGNORECASE)
    date_str = re.sub(r',.*$', '', date_str)
    # Try MM/DD/YYYY
    try:
        dt = datetime.strptime(date_str, '%m/%d/%Y')
        return dt.strftime('%Y-%m-%d')
    except:
        pass
    # Try MM/DD/YYYY H:MM AM/PM
    try:
        dt = datetime.strptime(date_string, '%m/%d/%Y %I:%M %p')
        return dt.strftime('%Y-%m-%d')
    except:
        pass
    return date_string

def scrape_elsgundo_bids():
    print(f"🌐 Fetching: {LIST_URL} (Selenium)")
    chrome_options = Options()
    # chrome_options.add_argument('--headless')  # DISABLED for debugging, run with browser visible
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    bids = []
    try:
        driver.get(LIST_URL)
        try:
            WebDriverWait(driver, SELENIUM_TIMEOUT * 2).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table.listtable tbody tr"))
            )
        except Exception as e:
            print("❌ Could not find bids table after waiting. Dumping page source for debugging:")
            with open("elsegundo/elsegundo_debug.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            driver.quit()
            print("🔚 Browser closed")
            return
        time.sleep(2)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        table = soup.find('table', class_='listtable')
        if not table:
            print("❌ Could not find bids table!")
            return
        rows = table.find('tbody').find_all('tr')
        print(f"📊 Found {len(rows)} bid rows in table")
        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 4:
                continue
            title_cell = cols[1]
            title_a = title_cell.find('a')
            project_title = title_a.get_text(strip=True) if title_a else title_cell.get_text(strip=True)
            detail_url = BASE_URL + title_a['href'] if title_a and title_a.has_attr('href') else LIST_URL
            published_date = normalize_date(cols[2].get_text(strip=True))
            due_date = normalize_date(cols[3].get_text(strip=True))
            print(f"🔄 Processing: {project_title}")
            # Get summary from detail page
            summary = ""
            try:
                driver.execute_script("window.open('');")
                driver.switch_to.window(driver.window_handles[1])
                driver.get(detail_url)
                WebDriverWait(driver, SELENIUM_TIMEOUT).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.detail-content"))
                )
                time.sleep(1)
                detail_soup = BeautifulSoup(driver.page_source, 'html.parser')
                detail_content = detail_soup.find('div', class_='detail-content')
                if detail_content:
                    summary = detail_content.get_text("\n", strip=True)
                driver.close()
                driver.switch_to.window(driver.window_handles[0])
            except Exception as e:
                print(f"  ⚠️  Error fetching detail: {e}")
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
            bid = {
                'project_title': project_title,
                'scope_of_services': summary,
                'published_date': published_date,
                'due_date': due_date,
                'detail_url': detail_url
            }
            bids.append(bid)
            time.sleep(0.5)
        df = pd.DataFrame(bids)
        if not df.empty:
            import os
            os.makedirs("elsegundo", exist_ok=True)
            df.to_csv(OUTPUT_CSV, index=False)
            print(f"💾 Saved {len(df)} bids to {OUTPUT_CSV}")
        else:
            print("❌ No bids found!")
    finally:
        driver.quit()
        print("🔚 Browser closed")

def scrape_all(date_filter=None):
    """
    Main integration point for pipeline. Scrapes bids, filters by published_date >= date_filter (YYYY-MM-DD), returns DataFrame and error list.
    """
    bids = []
    errors = []
    chrome_options = Options()
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    try:
        driver.get(LIST_URL)
        try:
            WebDriverWait(driver, SELENIUM_TIMEOUT * 2).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table.listtable tbody tr"))
            )
        except Exception as e:
            errors.append(f"Could not find bids table after waiting: {e}")
            driver.quit()
            return pd.DataFrame(), errors
        time.sleep(2)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        table = soup.find('table', class_='listtable')
        if not table:
            errors.append("Could not find bids table!")
            return pd.DataFrame(), errors
        rows = table.find('tbody').find_all('tr')
        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 4:
                continue
            title_cell = cols[1]
            title_a = title_cell.find('a')
            project_title = title_a.get_text(strip=True) if title_a else title_cell.get_text(strip=True)
            detail_url = BASE_URL + title_a['href'] if title_a and title_a.has_attr('href') else LIST_URL
            published_date = normalize_date(cols[2].get_text(strip=True))
            due_date = normalize_date(cols[3].get_text(strip=True))
            # Date filtering
            if date_filter:
                try:
                    if published_date and published_date >= date_filter:
                        pass
                    else:
                        continue
                except Exception as e:
                    errors.append(f"Date filter error for {project_title}: {e}")
                    continue
            summary = ""
            try:
                driver.execute_script("window.open('');")
                driver.switch_to.window(driver.window_handles[1])
                driver.get(detail_url)
                WebDriverWait(driver, SELENIUM_TIMEOUT).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.detail-content"))
                )
                time.sleep(1)
                detail_soup = BeautifulSoup(driver.page_source, 'html.parser')
                detail_content = detail_soup.find('div', class_='detail-content')
                if detail_content:
                    summary = detail_content.get_text("\n", strip=True)
                driver.close()
                driver.switch_to.window(driver.window_handles[0])
            except Exception as e:
                errors.append(f"Error fetching detail for {project_title}: {e}")
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
            bid = {
                'project_title': project_title,
                'scope_of_services': summary,
                'published_date': published_date,
                'due_date': due_date,
                'detail_url': detail_url
            }
            bids.append(bid)
            time.sleep(0.5)
        df = pd.DataFrame(bids)
        if not df.empty:
            import os
            os.makedirs("elsegundo", exist_ok=True)
            df.to_csv(OUTPUT_CSV, index=False)
        return df, errors
    finally:
        driver.quit()

def print_portal_summary(count, portal_name, error=None):
    if error:
        print(f"❌  [{portal_name}] Failed to scrape ({error})\n")
    elif count > 0:
        print(f"✅  [{portal_name}] {count} RFPs scraped\n")
    else:
        print(f"❌  [{portal_name}] No RFPs found\n")

if __name__ == "__main__":
    scrape_elsgundo_bids()

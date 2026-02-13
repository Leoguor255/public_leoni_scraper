"""
Monterey Park Government Bids Scraper

Scrapes government bid opportunities from the QuestCDN portal for Monterey Park.

Author: Leonardo Gutarra
Created: 2025-11-11

Usage:
    python monterey_park_scraper.py
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import os
from utils import get_chromedriver_path
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# =============================================================================
# CONFIGURATION
# =============================================================================
BASE_URL = "https://qcpi.questcdn.com/cdn/posting/?projType=all&provider=6486888&group=6486888"
OUTPUT_CSV = "monterey_park/monterey_park_bids.csv"


def parse_date(date_str):
    """Parse date in 'MM/DD/YYYY' or 'MM/DD/YYYY HH:MM AM/PM' format."""
    try:
        return datetime.strptime(date_str.strip(), '%m/%d/%Y').strftime('%m/%d/%Y')
    except Exception:
        try:
            return datetime.strptime(date_str.strip(), '%m/%d/%Y %I:%M %p %Z').strftime('%m/%d/%Y')
        except Exception:
            try:
                return datetime.strptime(date_str.strip(), '%m/%d/%Y %I:%M %p').strftime('%m/%d/%Y')
            except Exception:
                return date_str  # fallback to raw string


def scrape_monterey_park(date_filter=None):
    """
    Scrape the QuestCDN bid opportunities page for Monterey Park using Selenium.
    Returns: (DataFrame, stats_dict)
    """
    print(f"🌐 Fetching: {BASE_URL}")
    chromedriver_path = get_chromedriver_path()
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    service = Service(executable_path=chromedriver_path)
    driver = webdriver.Chrome(service=service, options=options)
    try:
        driver.get(BASE_URL)
        # Wait for the table to load or timeout after 20s
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.TAG_NAME, 'body'))
        )
        html = driver.page_source
        # Save the full page source for debugging
        with open('monterey_park/monterey_park_debug.html', 'w', encoding='utf-8') as f:
            f.write(html)
        soup = BeautifulSoup(html, 'html.parser')
        table = soup.find('table', id='table_id')
        if not table:
            print("❌ Could not find bid table.")
            return pd.DataFrame(), {'total_bids': 0}
        bids = []
        for row in table.find('tbody').find_all('tr'):
            cells = row.find_all('td')
            if len(cells) < 5:
                continue
            published = parse_date(cells[0].get_text(strip=True))
            category_code = cells[2].get_text(strip=True)
            project_name = cells[3].get_text(strip=True)
            summary = f"{category_code}, {project_name}"
            due_date = parse_date(cells[4].get_text(strip=True))
            link = ''
            if date_filter and published:
                try:
                    published_dt = datetime.strptime(published, '%m/%d/%Y')
                    cutoff_dt = datetime.strptime(date_filter, '%m/%d/%Y')
                    if published_dt < cutoff_dt:
                        continue
                except Exception:
                    pass
            bid = {
                'Project Name': project_name,
                'Summary': summary,
                'Published Date': published,
                'Due Date': due_date,
                'Link': link
            }
            bids.append(bid)
        df = pd.DataFrame(bids)
        stats = {'total_bids': len(df)}
        print(f"✅ Scraped {len(df)} bids from Monterey Park (QuestCDN)")
        return df, stats
    finally:
        driver.quit()


def scrape_all(date_filter=None):
    """
    Main entry point for Monterey Park scraper (for main.py integration)
    Returns: (DataFrame, stats_dict)
    """
    return scrape_monterey_park(date_filter)


if __name__ == "__main__":
    # For standalone testing
    df, stats = scrape_monterey_park()
    if not os.path.exists('monterey_park'):
        os.makedirs('monterey_park')
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"💾 Saved to {OUTPUT_CSV}")

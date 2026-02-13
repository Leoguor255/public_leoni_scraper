"""
Paramount Government Bids Scraper

Scrapes government bid opportunities from the City of Paramount portal.

Author: Leonardo Gutarra
Created: 2025-11-11

Usage:
    python paramount_scraper.py
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import os

# =============================================================================
# CONFIGURATION
# =============================================================================
BASE_URL = "https://www.paramountcity.gov/services/bid-opportunities/"
OUTPUT_CSV = "paramount/paramount_bids.csv"


def parse_due_date(text):
    """Extract and parse due date from text like '10:00 am on Thursday, December 4, 2025'"""
    import re
    # Look for 'on <weekday>, <Month> <day>, <year>'
    match = re.search(r'on [A-Za-z]+, ([A-Za-z]+ \d{1,2}, \d{4})', text)
    if match:
        try:
            return datetime.strptime(match.group(1), '%B %d, %Y').strftime('%m/%d/%Y')
        except Exception:
            return match.group(1)
    # Fallback: look for '<Month> <day>, <year>'
    match = re.search(r'([A-Za-z]+ \d{1,2}, \d{4})', text)
    if match:
        try:
            return datetime.strptime(match.group(1), '%B %d, %Y').strftime('%m/%d/%Y')
        except Exception:
            return match.group(1)
    return ''


def scrape_paramount(date_filter=None):
    """
    Scrape the City of Paramount bid opportunities page.
    Returns: (DataFrame, stats_dict)
    """
    print(f"🌐 Fetching: {BASE_URL}")
    resp = requests.get(BASE_URL)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'html.parser')

    bid_items = soup.find_all('div', class_='pc-accordion-item')
    bids = []
    for item in bid_items:
        header = item.find('div', class_='pc-accordion-header')
        if not header:
            continue
        project_name = header.find('span', class_='pc-accordion-title')
        if not project_name:
            continue
        project_name = project_name.get_text(strip=True)
        # Find content div
        content = item.find('div', class_='pc-accordion-content')
        if not content:
            continue
        # Find due date in content (look for <strong> with date)
        due_date = ''
        for strong in content.find_all('strong'):
            due_date = parse_due_date(strong.get_text())
            if due_date:
                break
        # Find link in "NOTICE TO BID"
        notice_link = ''
        for a in content.find_all('a', href=True):
            if 'NOTICE TO BID' in a.get_text(strip=True).upper():
                notice_link = a['href']
                break
        # Date filtering (if provided)
        if date_filter and due_date:
            try:
                due_dt = datetime.strptime(due_date, '%m/%d/%Y')
                cutoff_dt = datetime.strptime(date_filter, '%m/%d/%Y')
                if due_dt < cutoff_dt:
                    continue
            except Exception:
                pass  # If date parsing fails, include the bid
        bid = {
            'Project Name': project_name,
            'Summary': project_name,  # Use project name as summary
            'Published Date': '',     # Not available
            'Due Date': due_date,
            'Link': notice_link
        }
        bids.append(bid)
    df = pd.DataFrame(bids)
    stats = {'total_bids': len(df)}
    print(f"✅ Scraped {len(df)} bids from Paramount")
    return df, stats


def scrape_all(date_filter=None):
    """
    Main entry point for Paramount scraper (for main.py integration)
    Returns: (DataFrame, stats_dict)
    """
    return scrape_paramount(date_filter)


if __name__ == "__main__":
    # For standalone testing
    df, stats = scrape_paramount()
    if not os.path.exists('paramount'):
        os.makedirs('paramount')
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"💾 Saved to {OUTPUT_CSV}")

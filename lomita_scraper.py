"""
Lomita Government Bids Scraper

Scrapes RFP opportunities from the City of Lomita portal.

Author: Leonardo Gutarra
Created: 2025-11-11

Usage:
    python lomita_scraper.py
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
from datetime import datetime
import os

BASE_URL = "https://lomitacity.com/current-bids-rfps/"
OUTPUT_CSV = "lomita/lomita_bids.csv"

def extract_due_date(panel_body):
    """Extract due date from various possible phrases in the panel body."""
    # Look for common due date phrases
    patterns = [
        r"Proposals Due: ([A-Za-z]+,? \w+ \d{1,2},? \d{4}(?: at [\d:apm\. ]+)?(?:\.?))",
        r"Bid Submission Deadline: ([A-Za-z]+,? \w+ \d{1,2},? \d{4}(?: at [\d:apm\. ]+)?(?:\.?))",
        r"submitted before ([A-Za-z]+,? \w+ \d{1,2},? \d{4}(?: at [\d:apm\. ]+)?(?:\.?))",
        r"Deadline: ([A-Za-z]+,? \w+ \d{1,2},? \d{4}(?: at [\d:apm\. ]+)?(?:\.?))",
        r"due ([A-Za-z]+,? \w+ \d{1,2},? \d{4}(?: at [\d:apm\. ]+)?(?:\.?))",
        r"([A-Za-z]+ \d{1,2}, \d{4}(?: at [\d:apm\. ]+)?(?:\.?))"
    ]
    text = panel_body.get_text(" ", strip=True)
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).replace('\xa0', ' ').strip()
    # Try to find a <b> or <strong> with a date
    for tag in panel_body.find_all(['b', 'strong']):
        date_match = re.search(r'([A-Za-z]+ \d{1,2}, \d{4})', tag.get_text())
        if date_match:
            return date_match.group(1)
    return ''

def scrape_lomita(date_filter=None):
    """
    Scrape the City of Lomita RFPs page.
    Returns: (DataFrame, stats_dict)
    """
    print(f"🌐 Fetching: {BASE_URL}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Connection': 'keep-alive',
        'Referer': 'https://www.google.com/'
    }
    resp = requests.get(BASE_URL, headers=headers)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'html.parser')
    rfp_panels = soup.select('.fusion-panel')
    bids = []
    for panel in rfp_panels:
        heading = panel.find('span', class_='fusion-toggle-heading')
        if not heading:
            continue
        project_name = heading.get_text(strip=True)
        if not project_name.upper().startswith('RFP:'):
            continue
        # Find the panel body
        panel_body = panel.find('div', class_='panel-body')
        if not panel_body:
            continue
        due_date = extract_due_date(panel_body)
        # Find the last <a> in the panel body (the RFP link)
        rfp_link = ''
        for a in panel_body.find_all('a', href=True):
            if a.get('href') and a.get_text(strip=True).upper().startswith('RFP:'):
                rfp_link = a['href']
        # Ensure rfp_link is absolute
        if rfp_link and not rfp_link.startswith('http'):
            rfp_link = 'https://lomitacity.com' + rfp_link
        # Date filtering (if provided)
        if date_filter and due_date:
            try:
                # Try to parse date in various formats
                dt = None
                for fmt in ("%A, %B %d, %Y", "%B %d, %Y", "%A, %B %d, %Y at %I:%M %p", "%B %d, %Y at %I:%M %p"):
                    try:
                        dt = datetime.strptime(due_date.split(' at ')[0].replace('.', ''), fmt)
                        break
                    except Exception:
                        continue
                if dt and dt < datetime.strptime(date_filter, '%m/%d/%Y'):
                    continue
            except Exception:
                pass
        bid = {
            'Project Name': project_name,
            'Summary': project_name,
            'Published Date': '',
            'Due Date': due_date,
            'Link': rfp_link
        }
        bids.append(bid)
    df = pd.DataFrame(bids)
    stats = {'total_bids': len(df)}
    print(f"✅ Scraped {len(df)} RFPs from Lomita")
    return df, stats

def scrape_all(date_filter=None):
    """
    Main entry point for Lomita scraper (for main.py integration)
    Returns: (DataFrame, stats_dict)
    """
    return scrape_lomita(date_filter)

if __name__ == "__main__":
    df, stats = scrape_lomita()
    if not os.path.exists('lomita'):
        os.makedirs('lomita')
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"💾 Saved to {OUTPUT_CSV}")

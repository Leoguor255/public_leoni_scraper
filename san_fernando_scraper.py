"""
San Fernando Government Bids Scraper

Scrapes government bid opportunities from the City of San Fernando portal.

Author: Leonardo Gutarra
Created: 2025-11-11

Usage:
    python san_fernando_scraper.py
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import os
from utils import parse_mmddyyyy  # Use your existing date parser if needed

# =============================================================================
# CONFIGURATION
# =============================================================================
BASE_URL = "https://ci.san-fernando.ca.us/rfps-rfqs-nibs-nois/"
OUTPUT_CSV = "san_fernando/san_fernando_bids.csv"


def parse_date(date_str):
    """Parse dates in format like 'October 23, 2025' or 'November 13, 2025'"""
    try:
        return datetime.strptime(date_str.strip(), '%B %d, %Y').strftime('%m/%d/%Y')
    except Exception:
        try:
            return datetime.strptime(date_str.strip(), '%B %d, %Y').strftime('%m/%d/%Y')
        except Exception:
            return date_str  # fallback to raw string


def scrape_san_fernando(date_filter=None):
    """
    Scrape the City of San Fernando bid opportunities page.
    Returns: (DataFrame, stats_dict)
    """
    print(f"🌐 Fetching: {BASE_URL}")
    resp = requests.get(BASE_URL)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'html.parser')

    # Find the ARCHIVE section and collect all its bid links for exclusion
    archive_section = soup.find('h2', string=lambda s: s and 'ARCHIVE' in s.upper())
    archive_links = set()
    if archive_section:
        archive_col = archive_section.find_parent('div', class_='col')
        if archive_col:
            for a in archive_col.find_all('a', href=True):
                archive_links.add(a['href'])

    # Find all bid sections (each is a div.nz-column-text with a <ul> and <table> after)
    bid_blocks = soup.find_all('div', class_='nz-column-text')
    bids = []
    for block in bid_blocks:
        # Find the project name and link
        a_tag = block.find('a', href=True)
        if not a_tag:
            continue
        detail_url = a_tag['href']
        project_name = a_tag.get_text(strip=True)
        # Exclude if in archive or not an RFP (e.g., "CLICK HERE for More Information")
        if detail_url in archive_links:
            continue
        # Heuristic: skip if project_name is very short or generic (e.g., 'CLICK HERE for More Information')
        if project_name.strip().upper().startswith('CLICK HERE') or len(project_name.strip()) < 10:
            continue
        # Find the table with dates
        table = block.find_next('table', class_='nz-table')
        if not table:
            continue
        rows = table.find_all('tr')
        published = ''
        due = ''
        for row in rows:
            tds = row.find_all('td')
            if len(tds) != 2:
                continue
            label = tds[0].get_text(strip=True)
            value = tds[1].get_text(strip=True)
            if 'Release Date' in label:
                published = parse_date(value)
            if 'Proposal Deadline' in label or 'Proposal Deadline:' in label:
                due = parse_date(value)
        # Date filtering
        if date_filter:
            try:
                published_dt = datetime.strptime(published, '%m/%d/%Y')
                cutoff_dt = datetime.strptime(date_filter, '%m/%d/%Y')
                if published_dt < cutoff_dt:
                    continue
            except Exception:
                pass  # If date parsing fails, include the bid
        bid = {
            'Project Name': project_name,
            'Summary': project_name,  # As requested, use project name as summary
            'Published Date': published,
            'Due Date': due,
            'Link': detail_url
        }
        bids.append(bid)
    df = pd.DataFrame(bids)
    stats = {'total_bids': len(df)}
    print(f"✅ Scraped {len(df)} bids from San Fernando (archive filtered)")
    return df, stats


def scrape_all(date_filter=None):
    """
    Main entry point for San Fernando scraper (for main.py integration)
    Returns: (DataFrame, stats_dict)
    """
    return scrape_san_fernando(date_filter)


if __name__ == "__main__":
    # For standalone testing
    df, stats = scrape_san_fernando()
    if not os.path.exists('san_fernando'):
        os.makedirs('san_fernando')
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"💾 Saved to {OUTPUT_CSV}")

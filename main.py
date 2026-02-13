"""
Government Bid Scraping Application

This module serves as the main entry point for the government bid scraping system.
Runs both PlanetBids and OpenGov scrapers, combines results, and uploads to Airtable.

Author: Leonardo Gutarra
Created: 2025-01-27
Modified: 2025-11-06

Usage:
    python main.py
"""

import os
import pandas as pd
from typing import Dict, List, Any
import logging
import sys

# =========================
# CONFIGURATION: Date Filter
# =========================
from datetime import datetime, timedelta
FILTER_DAYS = 42  # Only scrape bids from last X days
cutoff_date = datetime.now() - timedelta(days=FILTER_DAYS)
BID_FILTER_DATE = cutoff_date.strftime("%m/%d/%Y")

# Local imports
from planet_bids import scrape_all as planet_bids_scrape_all
from opengov import scrape_all as opengov_scrape_all
from artesia_scraper import scrape_all as artesia_scrape_all
from bell_gardens_scraper import scrape_all as bell_gardens_scrape_all
from calabasas_scraper import scrape_all as calabasas_scrape_all
from earc_scraper import scrape_all as earc_scrape_all
from bidnet_scraper import scrape_all as bidnet_scrape_all
from inglewood_scraper import scrape_all as inglewood_scrape_all
from san_gabriel_scraper import scrape_all as san_gabriel_scrape_all
# from san_fernando_scraper import scrape_all as san_fernando_scrape_all  # Disabled: URL returns 404
from questcdn_scraper import scrape_all as questcdn_scrape_all
from elsegundo_scraper import scrape_all as elsegundo_scrape_all
from compton_scraper import scrape_all as compton_scrape_all
from utils import clear_failed_urls_file, upload_dataframe_to_airtable, query_llm, save_airtable_format_csv, save_failed_pages_batch


# Set up normalized logging for all scrapers
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)

# Suppress undetected_chromedriver and webdriver_manager logs
logging.getLogger('undetected_chromedriver').setLevel(logging.WARNING)
logging.getLogger('WDM').setLevel(logging.WARNING)
# Optionally, suppress all selenium/urllib3 debug logs
logging.getLogger('selenium').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

def collect_failed_urls(stats: dict) -> list:
    """Extract all failed URLs from scraper stats (both failed_pages and skipped_sites)."""
    failed = []
    for key in ('failed_pages', 'skipped_sites'):
        for page in (stats.get(key) or []):
            url = page.get('detail_url', page.get('url', ''))
            if url:
                failed.append({'url': url})
    return failed


def log_status(site, step, message, level='info'):
    prefix = f"[{site}][{step}]"
    if level == 'error':
        logging.error(f"{prefix} {message}")
    elif level == 'warning':
        logging.warning(f"{prefix} {message}")
    else:
        logging.info(f"{prefix} {message}")


def prepare_airtable_data(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """
    Prepare scraped data for Airtable upload with ONLY the required fields.
    
    Maps scraped data to your exact Airtable fields:
    - Project Name: project_title or Project Title (OpenGov)
    - Summary: scope_of_services, other_details, or Summary (OpenGov) 
    - Published Date: bid_posting_date or Release Date (OpenGov)
    - Due Date: bid_due_date or Due Date (OpenGov)
    - Link: detail_url (individual bid page)
    
    Args:
        df (pd.DataFrame): Scraped data from either portal
        source (str): Source identifier ('PlanetBids' or 'OpenGov')
        
    Returns:
        pd.DataFrame: Data formatted for Airtable upload with ONLY 5 fields
    """
    if df.empty:
        return pd.DataFrame()
    
    # Helper function to get field value from multiple possible column names
    def get_field_value(row, field_options, default=''):
        """Get value from first available field option"""
        for field in field_options:
            if field in row and pd.notna(row[field]) and str(row[field]).strip():
                return str(row[field]).strip()
        return default
    
    # Format date for Airtable (extract just the date part)
    def format_date_for_airtable(date_string):
        """Convert various date formats to YYYY-MM-DD for Airtable"""
        if not date_string or pd.isna(date_string):
            return ""
        
        date_str = str(date_string).strip()
        if not date_str:
            return ""
        
        # Handle various date formats
        import re
        from datetime import datetime
        
        # Remove time and timezone info (keep just the date part)
        # Examples: "11/06/2025 2:00 PM (PDT)" -> "11/06/2025"
        date_str = re.sub(r'\s+\d{1,2}:\d{2}\s*(AM|PM).*$', '', date_str, flags=re.IGNORECASE)
        date_str = re.sub(r',.*$', '', date_str)  # Remove everything after comma
        
        # Try to parse MM/DD/YYYY format
        if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', date_str):
            try:
                dt = datetime.strptime(date_str, '%m/%d/%Y')
                return dt.strftime('%Y-%m-%d')
            except:
                pass
        
        # Try to parse Month DD, YYYY format (like "October 23, 2025")
        month_day_year = re.match(r'^([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})$', date_str)
        if month_day_year:
            try:
                dt = datetime.strptime(date_str.replace(',', ''), '%B %d %Y')
                return dt.strftime('%Y-%m-%d')
            except:
                pass
        
        # Try to parse Month DD format (like "November 4") - assume current year
        month_day_only = re.match(r'^([A-Za-z]+)\s+(\d{1,2})$', date_str.strip())
        if month_day_only:
            try:
                # Add current year
                current_year = datetime.now().year
                full_date_str = f"{date_str.strip()} {current_year}"
                dt = datetime.strptime(full_date_str, '%B %d %Y')
                return dt.strftime('%Y-%m-%d')
            except:
                pass
        
        # Try to parse Month DD format without year (like "November 4" -> assume current year)
        month_day_only = re.match(r'^([A-Za-z]+)\s+(\d{1,2})$', date_str)
        if month_day_only:
            try:
                # Assume current year for dates without year
                current_year = datetime.now().year
                dt = datetime.strptime(f"{date_str} {current_year}", '%B %d %Y')
                return dt.strftime('%Y-%m-%d')
            except:
                pass
        
        # If we can't parse it, return empty (better than causing errors)
        print(f"   ⚠️  Could not parse date: '{date_str}' - leaving empty")
        return ""
    
    # Get summary field directly from the data
    def get_summary(row):
        # For OpenGov: use 'Summary' field directly
        # For PlanetBids: use 'scope_of_services' or other fields
        summary_fields = [
            'Summary',           # OpenGov summary field (exact match)
            'scope_of_services', # PlanetBids detailed scope
            'other_details',     # PlanetBids additional details
            'project_type',      # Project categorization
            'department'         # Department info as fallback
        ]
        
        for field in summary_fields:
            value = get_field_value(row, [field])
            if value and len(value.strip()) > 0:  # Use any non-empty content
                # Limit summary length for Airtable
                return value[:1000] + "..." if len(value) > 1000 else value
        
        return "No summary available"
    
    # Map to ONLY your 5 Airtable fields (no timestamp)
    airtable_data = []
    for _, row in df.iterrows():
        record = {
            'Project Name': get_field_value(row, ['project_title', 'Project Title', 'bid_title']),
            'Summary': get_summary(row),
            'Published Date': format_date_for_airtable(get_field_value(row, ['bid_posting_date', 'Release Date'])),
            'Due Date': format_date_for_airtable(get_field_value(row, ['bid_due_date', 'Due Date'])),
            'Link': get_field_value(row, ['detail_url', 'bid_url'])
        }
        # Only add record if it has essential data
        if record['Project Name'] and record['Link']:
            airtable_data.append(record)
    result_df = pd.DataFrame(airtable_data)
    print(f"📋 Mapped {len(df)} {source} records → {len(result_df)} Airtable records")
    if len(result_df) < len(df):
        print(f"   (Filtered out {len(df) - len(result_df)} records missing Project Name or Link)")
    return result_df


def main() -> None:
    """
    Main application entry point.
    
    Runs both PlanetBids and OpenGov scrapers, combines results,
    applies date filtering, and uploads to Airtable.
    """
    print("🚀 Starting Government Bid Scraping Application")
    print("=" * 50)
    
    # ====================================================================
    # CENTRALIZED DATE FILTER CONFIGURATION - EDIT HERE TO CHANGE ALL SCRAPERS
    # ====================================================================
    # (Moved to top of file for easy access)
    print(f"📅 Centralized date filter: Only bids posted after {BID_FILTER_DATE}")
    print(f"   (Using last {FILTER_DAYS} days from today)")
    # ====================================================================
    
    # Ensure all output directories exist
    output_dirs = [
        "planetbid", "opengov", "artesia", "bell_gardens", "calabasas",
        "bidnet", "inglewood", "san_gabriel", "questcdn", "elsegundo",
        "compton", "earc", "san_fernando", "paramount", "lomita"
    ]
    for d in output_dirs:
        os.makedirs(d, exist_ok=True)

    # Clear failed URLs file for fresh run
    clear_failed_urls_file()
    print("🗑️  Cleared failed URLs log for fresh run")
    
    all_airtable_data = []
    all_failed_urls = []  # Collect failed URLs from all scrapers
    scraping_summary = {
        'planetbids': {'success': False, 'records': 0, 'errors': []},
        'opengov': {'success': False, 'records': 0, 'errors': []},
        'artesia': {'success': False, 'records': 0, 'errors': []},
        'bell_gardens': {'success': False, 'records': 0, 'errors': []},
        'calabasas': {'success': False, 'records': 0, 'errors': []},
        'bidnet': {'success': False, 'records': 0, 'errors': []},
        'inglewood': {'success': False, 'records': 0, 'errors': []},
        'san_gabriel': {'success': False, 'records': 0, 'errors': []},
        # 'san_fernando': {'success': False, 'records': 0, 'errors': []},  # Disabled: URL returns 404
        'questcdn': {'success': False, 'records': 0, 'errors': []},
        'elsegundo': {'success': False, 'records': 0, 'errors': []},
        'compton': {'success': False, 'records': 0, 'errors': []},
        # 'earc': {'success': False, 'records': 0, 'errors': []}  # Disabled pending client input
    }
    
    # Run PlanetBids scraper
    log_status('PlanetBids', 'Start', 'Starting PlanetBids scraper...')
    try:
        from planet_bids import URLS as PLANET_URLS
        planet_df, planet_stats = planet_bids_scrape_all(PLANET_URLS, date_filter=BID_FILTER_DATE)
        if not planet_df.empty:
            log_status('PlanetBids', 'Scrape', f'Raw data: {len(planet_df)} records')
            planet_airtable = prepare_airtable_data(planet_df, 'PlanetBids')
            if not planet_airtable.empty:
                all_airtable_data.append(planet_airtable)
                scraping_summary['planetbids']['success'] = True
                scraping_summary['planetbids']['records'] = len(planet_airtable)
                log_status('PlanetBids', 'Airtable Mapping', f'Mapped for Airtable: {len(planet_airtable)} records')
                save_airtable_format_csv(planet_airtable.to_dict('records'), "planetbid/planetbids_data.csv", "PlanetBids")
            else:
                log_status('PlanetBids', 'Airtable Mapping', 'Data mapping failed (no records mapped for Airtable)', level='warning')
        else:
            log_status('PlanetBids', 'Scrape', 'No data scraped (no RFPs found or failed to parse table)', level='warning')
        if planet_stats:
            failed = collect_failed_urls(planet_stats)
            if failed:
                log_status('PlanetBids', 'Failed URLs', f'{len(failed)} failed URLs collected', level='warning')
                all_failed_urls.extend(failed)
    except Exception as e:
        error_msg = f"PlanetBids scraper failed to run: {e}"
        log_status('PlanetBids', 'Error', error_msg, level='error')
        scraping_summary['planetbids']['errors'].append(error_msg)

    # Run OpenGov scraper
    log_status('OpenGov', 'Start', 'Starting OpenGov scraper...')
    try:
        from opengov import URLS as OPENGOV_URLS
        opengov_df, opengov_stats = opengov_scrape_all(OPENGOV_URLS, date_filter=BID_FILTER_DATE)
        if not opengov_df.empty:
            log_status('OpenGov', 'Scrape', f'Raw data: {len(opengov_df)} records')
            opengov_airtable = prepare_airtable_data(opengov_df, 'OpenGov')
            if not opengov_airtable.empty:
                all_airtable_data.append(opengov_airtable)
                scraping_summary['opengov']['success'] = True
                scraping_summary['opengov']['records'] = len(opengov_airtable)
                log_status('OpenGov', 'Airtable Mapping', f'Mapped for Airtable: {len(opengov_airtable)} records')
                save_airtable_format_csv(opengov_airtable.to_dict('records'), "opengov/opengov.csv", "OpenGov")
            else:
                log_status('OpenGov', 'Airtable Mapping', 'Data mapping failed', level='warning')
        else:
            log_status('OpenGov', 'Scrape', 'No data scraped (no RFPs found or failed to parse table)', level='warning')
        if opengov_stats:
            failed = collect_failed_urls(opengov_stats)
            if failed:
                log_status('OpenGov', 'Failed URLs', f'{len(failed)} failed URLs collected', level='warning')
                all_failed_urls.extend(failed)
    except Exception as e:
        error_msg = f"OpenGov scraper failed to run: {e}"
        log_status('OpenGov', 'Error', error_msg, level='error')
        scraping_summary['opengov']['errors'].append(error_msg)

    # Run Artesia scraper
    log_status('Artesia', 'Start', 'Starting Artesia scraper...')
    try:
        artesia_df, artesia_stats = artesia_scrape_all(date_filter=BID_FILTER_DATE)
        if not artesia_df.empty:
            log_status('Artesia', 'Scrape', f'Raw data: {len(artesia_df)} records')
            artesia_airtable = prepare_airtable_data(artesia_df, 'Artesia')
            if not artesia_airtable.empty:
                all_airtable_data.append(artesia_airtable)
                scraping_summary['artesia']['success'] = True
                scraping_summary['artesia']['records'] = len(artesia_airtable)
                log_status('Artesia', 'Airtable Mapping', f'Mapped for Airtable: {len(artesia_airtable)} records')
                save_airtable_format_csv(artesia_airtable.to_dict('records'), "artesia/artesia_bids.csv", "Artesia")
            else:
                log_status('Artesia', 'Airtable Mapping', 'Data mapping failed', level='warning')
        else:
            log_status('Artesia', 'Scrape', 'No data scraped (no RFPs found or failed to parse table)', level='warning')
        if artesia_stats:
            failed = collect_failed_urls(artesia_stats)
            if failed:
                log_status('Artesia', 'Failed URLs', f'{len(failed)} failed URLs collected', level='warning')
                all_failed_urls.extend(failed)
    except Exception as e:
        error_msg = f"Artesia scraper failed to run: {e}"
        log_status('Artesia', 'Error', error_msg, level='error')
        scraping_summary['artesia']['errors'].append(error_msg)

    # Run Bell Gardens scraper
    log_status('Bell Gardens', 'Start', 'Starting Bell Gardens scraper...')
    try:
        bell_gardens_df, bell_gardens_stats = bell_gardens_scrape_all(date_filter=BID_FILTER_DATE)
        if not bell_gardens_df.empty:
            log_status('Bell Gardens', 'Scrape', f'Raw data: {len(bell_gardens_df)} records')
            bell_gardens_airtable = prepare_airtable_data(bell_gardens_df, 'Bell Gardens')
            if not bell_gardens_airtable.empty:
                all_airtable_data.append(bell_gardens_airtable)
                scraping_summary['bell_gardens']['success'] = True
                scraping_summary['bell_gardens']['records'] = len(bell_gardens_airtable)
                log_status('Bell Gardens', 'Airtable Mapping', f'Mapped for Airtable: {len(bell_gardens_airtable)} records')
                save_airtable_format_csv(bell_gardens_airtable.to_dict('records'), "bell_gardens/bell_gardens_bids.csv", "Bell Gardens")
            else:
                log_status('Bell Gardens', 'Airtable Mapping', 'Data mapping failed', level='warning')
        else:
            log_status('Bell Gardens', 'Scrape', 'No data scraped (no RFPs found or failed to parse table)', level='warning')
        if bell_gardens_stats:
            failed = collect_failed_urls(bell_gardens_stats)
            if failed:
                log_status('Bell Gardens', 'Failed URLs', f'{len(failed)} failed URLs collected', level='warning')
                all_failed_urls.extend(failed)
    except Exception as e:
        error_msg = f"Bell Gardens scraper failed to run: {e}"
        log_status('Bell Gardens', 'Error', error_msg, level='error')
        scraping_summary['bell_gardens']['errors'].append(error_msg)

    # Run Calabasas scraper
    log_status('Calabasas', 'Start', 'Starting Calabasas scraper...')
    try:
        calabasas_df, calabasas_stats = calabasas_scrape_all(date_filter=BID_FILTER_DATE)
        if not calabasas_df.empty:
            log_status('Calabasas', 'Scrape', f'Raw data: {len(calabasas_df)} records')
            calabasas_airtable = prepare_airtable_data(calabasas_df, 'Calabasas')
            if not calabasas_airtable.empty:
                all_airtable_data.append(calabasas_airtable)
                scraping_summary['calabasas']['success'] = True
                scraping_summary['calabasas']['records'] = len(calabasas_airtable)
                log_status('Calabasas', 'Airtable Mapping', f'Mapped for Airtable: {len(calabasas_airtable)} records')
                save_airtable_format_csv(calabasas_airtable.to_dict('records'), "calabasas/calabasas_bids.csv", "Calabasas")
            else:
                log_status('Calabasas', 'Airtable Mapping', 'Data mapping failed', level='warning')
        else:
            log_status('Calabasas', 'Scrape', 'No data scraped (no RFPs found or failed to parse table)', level='warning')
        if calabasas_stats:
            failed = collect_failed_urls(calabasas_stats)
            if failed:
                log_status('Calabasas', 'Failed URLs', f'{len(failed)} failed URLs collected', level='warning')
                all_failed_urls.extend(failed)
    except Exception as e:
        error_msg = f"Calabasas scraper failed to run: {e}"
        log_status('Calabasas', 'Error', error_msg, level='error')
        scraping_summary['calabasas']['errors'].append(error_msg)

    # Run BidNet Direct scraper (Santa Clarita)
    log_status('BidNet', 'Start', 'Starting BidNet Direct scraper...')
    try:
        bidnet_df, bidnet_stats = bidnet_scrape_all(date_filter=BID_FILTER_DATE)
        if not bidnet_df.empty:
            log_status('BidNet', 'Scrape', f'Raw data: {len(bidnet_df)} records')
            bidnet_airtable = prepare_airtable_data(bidnet_df, 'BidNet Direct')
            if not bidnet_airtable.empty:
                all_airtable_data.append(bidnet_airtable)
                scraping_summary['bidnet']['success'] = True
                scraping_summary['bidnet']['records'] = len(bidnet_airtable)
                log_status('BidNet', 'Airtable Mapping', f'Mapped for Airtable: {len(bidnet_airtable)} records')
                save_airtable_format_csv(bidnet_airtable.to_dict('records'), "bidnet/bidnet_santa_clarita_bids.csv", "BidNet Direct")
            else:
                log_status('BidNet', 'Airtable Mapping', 'Data mapping failed', level='warning')
        else:
            log_status('BidNet', 'Scrape', 'No data scraped (no RFPs found or failed to parse table)', level='warning')
        if bidnet_stats:
            failed = collect_failed_urls(bidnet_stats)
            if failed:
                log_status('BidNet', 'Failed URLs', f'{len(failed)} failed URLs collected', level='warning')
                all_failed_urls.extend(failed)
    except Exception as e:
        error_msg = f"BidNet Direct scraper failed to run: {e}"
        log_status('BidNet', 'Error', error_msg, level='error')
        scraping_summary['bidnet']['errors'].append(error_msg)

    # Run Inglewood scraper
    log_status('Inglewood', 'Start', 'Starting Inglewood scraper...')
    try:
        inglewood_df, inglewood_stats = inglewood_scrape_all(date_filter=BID_FILTER_DATE)
        if not inglewood_df.empty:
            log_status('Inglewood', 'Scrape', f'Raw data: {len(inglewood_df)} records')
            inglewood_airtable = pd.DataFrame(prepare_airtable_data(inglewood_df, 'Inglewood'))
            if not inglewood_airtable.empty:
                all_airtable_data.append(inglewood_airtable)
                scraping_summary['inglewood']['success'] = True
                scraping_summary['inglewood']['records'] = len(inglewood_airtable)
                log_status('Inglewood', 'Airtable Mapping', f'Mapped for Airtable: {len(inglewood_airtable)} records')
                save_airtable_format_csv(inglewood_airtable.to_dict('records'), "inglewood/inglewood_bids.csv", "Inglewood")
            else:
                log_status('Inglewood', 'Airtable Mapping', 'Data mapping failed', level='warning')
        else:
            log_status('Inglewood', 'Scrape', 'No data scraped (no RFPs found or failed to parse table)', level='warning')
        if inglewood_stats:
            failed = collect_failed_urls(inglewood_stats)
            if failed:
                log_status('Inglewood', 'Failed URLs', f'{len(failed)} failed URLs collected', level='warning')
                all_failed_urls.extend(failed)
    except Exception as e:
        error_msg = f"Inglewood scraper failed to run: {e}"
        log_status('Inglewood', 'Error', error_msg, level='error')
        scraping_summary['inglewood']['errors'].append(error_msg)

    # Run San Gabriel scraper
    log_status('San Gabriel', 'Start', 'Starting San Gabriel scraper...')
    try:
        san_gabriel_df, san_gabriel_stats = san_gabriel_scrape_all(date_filter=BID_FILTER_DATE)
        if not san_gabriel_df.empty:
            log_status('San Gabriel', 'Scrape', f'Raw data: {len(san_gabriel_df)} records')
            from san_gabriel_scraper import prepare_airtable_format
            san_gabriel_airtable = pd.DataFrame(prepare_airtable_format(san_gabriel_df.to_dict('records')))
            if not san_gabriel_airtable.empty:
                all_airtable_data.append(san_gabriel_airtable)
                scraping_summary['san_gabriel']['success'] = True
                scraping_summary['san_gabriel']['records'] = len(san_gabriel_airtable)
                log_status('San Gabriel', 'Airtable Mapping', f'Mapped for Airtable: {len(san_gabriel_airtable)} records')
                save_airtable_format_csv(san_gabriel_airtable.to_dict('records'), "san_gabriel/san_gabriel_bids.csv", "San Gabriel")
            else:
                log_status('San Gabriel', 'Airtable Mapping', 'Data mapping failed', level='warning')
        else:
            log_status('San Gabriel', 'Scrape', 'No data scraped (no RFPs found or failed to parse table)', level='warning')
        if san_gabriel_stats:
            failed = collect_failed_urls(san_gabriel_stats)
            if failed:
                log_status('San Gabriel', 'Failed URLs', f'{len(failed)} failed URLs collected', level='warning')
                all_failed_urls.extend(failed)
    except Exception as e:
        error_msg = f"San Gabriel scraper failed to run: {e}"
        log_status('San Gabriel', 'Error', error_msg, level='error')
        scraping_summary['san_gabriel']['errors'].append(error_msg)
    
    # =============================================================================
    # SAN FERNANDO SCRAPER - DISABLED (URL returns 404)
    # =============================================================================

    # =============================================================================
    # E-ARC SCRAPER - DISABLED PENDING CLIENT INPUT
    # =============================================================================
    # Run E-ARC scraper (COMMENTED OUT - ready for future activation)
    # print("\n📊 Running E-ARC scraper...")
    # try:
    #     earc_df, earc_stats = earc_scrape_all(date_filter=BID_FILTER_DATE)
    #     
    #     if not earc_df.empty:
    #         print(f"✅ E-ARC raw data: {len(earc_df)} records")
    #         earc_airtable = prepare_airtable_data(earc_df, 'E-ARC')
    #         
    #         if not earc_airtable.empty:
    #             all_airtable_data.append(earc_airtable)
    #             scraping_summary['earc']['success'] = True
    #             scraping_summary['earc']['records'] = len(earc_airtable)
    #             print(f"✅ E-ARC mapped for Airtable: {len(earc_airtable)} records")
    #             
    #             # Save CSV with Airtable format
    #             save_airtable_format_csv(earc_airtable.to_dict('records'), "earc/earc_bids.csv", "E-ARC")
    #         else:
    #             print("⚠️  E-ARC: Data mapping failed")
    #     else:
    #         print("⚠️  E-ARC: No data scraped")
    #         
    #     # Collect failed URLs from E-ARC stats
    #     if earc_stats and 'failed_pages' in earc_stats:
    #         failed_pages = earc_stats['failed_pages']
    #         if failed_pages:
    #             print(f"📋 E-ARC: {len(failed_pages)} failed URLs collected")
    #             all_failed_urls.extend([{**page, 'source': 'E-ARC'} for page in failed_pages])
    #         
    # except Exception as e:
    #     error_msg = f"E-ARC scraper failed: {e}"
    #     print(f"❌ {error_msg}")
    #     scraping_summary['earc']['errors'].append(error_msg)
    # =============================================================================
    
    # Run QuestCDN scraper
    log_status('QuestCDN', 'Start', 'Starting QuestCDN scraper...')
    try:
        questcdn_df, questcdn_stats = questcdn_scrape_all(date_filter=BID_FILTER_DATE)
        if not questcdn_df.empty:
            log_status('QuestCDN', 'Scrape', f'Raw data: {len(questcdn_df)} records')
            questcdn_airtable = prepare_airtable_data(questcdn_df, 'QuestCDN')
            if not questcdn_airtable.empty:
                all_airtable_data.append(questcdn_airtable)
                scraping_summary['questcdn']['success'] = True
                scraping_summary['questcdn']['records'] = len(questcdn_airtable)
                log_status('QuestCDN', 'Airtable Mapping', f'Mapped for Airtable: {len(questcdn_airtable)} records')
                save_airtable_format_csv(questcdn_airtable.to_dict('records'), "questcdn/questcdn_bids.csv", "QuestCDN")
            else:
                log_status('QuestCDN', 'Airtable Mapping', 'Data mapping failed', level='warning')
        else:
            log_status('QuestCDN', 'Scrape', 'No data scraped (no RFPs found or failed to parse table)', level='warning')
        if questcdn_stats:
            failed = collect_failed_urls(questcdn_stats)
            if failed:
                log_status('QuestCDN', 'Failed URLs', f'{len(failed)} failed URLs collected', level='warning')
                all_failed_urls.extend(failed)
    except Exception as e:
        error_msg = f"QuestCDN scraper failed to run: {e}"
        log_status('QuestCDN', 'Error', error_msg, level='error')
        scraping_summary['questcdn']['errors'].append(error_msg)

    # Combine and upload to Airtable
    if all_airtable_data:
        print(f"\n📤 Combining and preparing data for Airtable...")
        combined_df = pd.concat(all_airtable_data, ignore_index=True)
        total_records = len(combined_df)
        print(f"📊 Total records before analysis: {total_records}")
        
        # Define Airtable columns before using them
        airtable_columns = ['Project Name', 'Summary', 'Published Date', 'Due Date', 'Link']
        # === UPLOAD RAW, UNFILTERED DATA TO AIRTABLE (Table 1 in new base) ===
        print(f"\n📤 Uploading RAW, unfiltered scraped data to Airtable table 'Table 1'...")
        try:
            raw_base_id = os.getenv('AIRTABLE_RAW_BASE_ID')
            raw_upload_results = upload_dataframe_to_airtable(
                combined_df[airtable_columns],
                add_metadata=False,
                table_name="Table 1",
                base_id=raw_base_id
            )
            if raw_upload_results['success_count'] == raw_upload_results['total_count']:
                print(f"✅ All {raw_upload_results['total_count']} raw records uploaded to 'Table 1' successfully!")
            else:
                print(f"⚠️  Partial upload to 'Table 1': {raw_upload_results['success_count']}/{raw_upload_results['total_count']} records uploaded")
                if raw_upload_results['errors']:
                    print(f"   Sample error: {raw_upload_results['errors'][0]}")
        except Exception as e:
            print(f"❌ Raw data upload to 'Table 1' failed: {e}")
            logging.error(f"[Airtable][Table 1][Upload] Upload failed: {e}")
        # === END RAW UPLOAD ===

        # 🏠 FLOORING/CARPETING DETECTION BEFORE AIRTABLE UPLOAD
        print(f"\n🏠 Analyzing bids for flooring and carpeting opportunities...")
        try:
            # Convert DataFrame back to list of dicts for LLM analysis
            bid_records = combined_df.to_dict('records')
            
            # Analyze for flooring opportunities
            enhanced_bids = check_flooring_carpeting_bids(bid_records)
            
            # Convert back to DataFrame
            enhanced_df = pd.DataFrame(enhanced_bids)
            
            # Only keep bids that pass the LLM filter
            filtered_df = enhanced_df[enhanced_df['is_flooring_related'] == True].copy()
            flooring_count = len(filtered_df)
            total_records = len(enhanced_df)
            
            if flooring_count > 0:
                print(f"\n🎯 FLOORING OPPORTUNITIES SUMMARY:")
                print(f"   📊 Found {flooring_count}/{total_records} flooring/carpeting related bids")
                flooring_opportunities = filtered_df.sort_values(by='flooring_confidence', ascending=False)
                print(f"   🏆 Top opportunities:")
                for i, (_, bid) in enumerate(flooring_opportunities.head(3).iterrows(), 1):
                    confidence = bid.get('flooring_confidence', 0)
                    title = bid.get('Project Name', bid.get('project_title', 'Unknown'))[:60]
                    print(f"      {i}. {title}... (Confidence: {confidence:.1f})")
            else:
                print(f"   📊 No flooring/carpeting opportunities detected in this batch")
            
            # Use only filtered bids for upload
            combined_df = filtered_df
        except Exception as e:
            print(f"⚠️  Flooring analysis failed: {e}")
            print(f"   Continuing with original data...")
        
        # Filter to only Airtable fields for upload (remove LLM analysis fields)
        airtable_columns = ['Project Name', 'Summary', 'Published Date', 'Due Date', 'Link']
        upload_df = combined_df[airtable_columns].copy()
        
        # Show sample of what will be uploaded
        print(f"\n📋 Sample fields being uploaded:")
        for col in upload_df.columns:
            sample_val = upload_df[col].iloc[0] if not upload_df[col].empty else "N/A"
            if len(str(sample_val)) > 50:
                sample_val = str(sample_val)[:50] + "..."
            print(f"   • {col}: {sample_val}")
        
        # Check Airtable configuration
        if os.getenv('AIRTABLE_ACCESS_TOKEN') and os.getenv('AIRTABLE_BASE_ID'):
            try:
                print(f"\n🔄 Uploading to Airtable...")
                results = upload_dataframe_to_airtable(upload_df, add_metadata=False)
                
                if results['success_count'] == results['total_count']:
                    print(f"✅ All {results['total_count']} records uploaded to Airtable successfully!")
                else:
                    print(f"⚠️  Partial upload: {results['success_count']}/{results['total_count']} records uploaded")
                    if results['errors']:
                        print(f"   Sample error: {results['errors'][0]}")
            except Exception as e:
                print(f"❌ Airtable upload failed: {e}")
                logging.error(f"[Airtable][Upload] Upload failed: {e}")
                backup_file = "combined_scraped_data.csv"
                upload_df.to_csv(backup_file, index=False)
                print(f"💾 Backup saved to: {backup_file}")
        else:
            print(f"⚠️  Airtable credentials not configured")
            logging.error("[Airtable][Config] Missing AIRTABLE_ACCESS_TOKEN or AIRTABLE_BASE_ID in environment.")
            backup_file = "combined_scraped_data.csv"
            upload_df.to_csv(backup_file, index=False)
            print(f"💾 Data saved to: {backup_file}")
    else:
        print("\n❌ No data scraped from any portal (all scrapers failed or no RFPs found)")
        logging.error("[Pipeline][NoData] No data scraped from any portal. Check scraper logs above.")
    
    # Save all failed URLs to failed_urls.txt
    if all_failed_urls:
        print(f"\n📋 Saving {len(all_failed_urls)} failed URLs to failed_urls.txt...")
        save_failed_pages_batch(all_failed_urls)
    else:
        print(f"\n✅ No failed URLs to save - all pages loaded successfully!")
    
    # Display final summary
    print(f"\n" + "=" * 60)
    print("📊 FINAL SCRAPING SUMMARY")
    print("=" * 60)
    
    total_success = sum(1 for portal in scraping_summary.values() if portal['success'])
    total_records = sum(portal['records'] for portal in scraping_summary.values())
    
    print(f"🎯 Portals processed: 6")
    print(f"✅ Successful: {total_success}")
    print(f"📋 Total records: {total_records}")
    
    for portal_name, stats in scraping_summary.items():
        status = "✅" if stats['success'] else "❌"
        display_name = {
            'planetbids': 'PlanetBids',
            'opengov': 'OpenGov', 
            'artesia': 'Artesia',
            'bell_gardens': 'Bell Gardens',
            'calabasas': 'Calabasas',
            'bidnet': 'BidNet Direct (Santa Clarita)',
            'inglewood': 'Inglewood',
            'san_gabriel': 'San Gabriel',
            # 'san_fernando': 'San Fernando',  # Disabled: URL returns 404
            'questcdn': 'QuestCDN',
            'elsegundo': 'El Segundo',
            'compton': 'Compton',
            # 'earc': 'E-ARC'  # Disabled pending client input
        }.get(portal_name, portal_name.title())
        
        print(f"   {status} {display_name}: {stats['records']} records")
        if stats['errors']:
            for error in stats['errors']:
                print(f"      Error: {error}")
    
    # Note about disabled scrapers
    print(f"\n📝 Note: E-ARC scraper is available but disabled pending client input")
    
    print("=" * 60)
    print("✅ Application completed successfully")


def check_flooring_carpeting_bids(bids: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Check bids for EXPLICIT flooring and carpeting related opportunities using strict LLM analysis.
    """
    print(f"\U0001F3E0 Analyzing {len(bids)} bids for EXPLICIT flooring/carpeting opportunities...")
    
    # STRICTER system prompt
    system_prompt = """You are a strict analyst for flooring and carpeting contractors. 

CRITERIA FOR FLOORING-RELATED:
- MUST contain EXPLICIT mentions of: flooring, carpet, carpeting, tile, hardwood, vinyl, laminate, floor covering, floor installation, floor replacement
- Construction/renovation projects ONLY qualify if they SPECIFICALLY mention flooring work
- General construction terms like \"new building\", \"renovation\", \"construction\" do NOT automatically qualify
- Assume NO flooring work unless explicitly stated

Respond with ONLY a JSON object in this exact format:
{"is_flooring_related": true/false, "confidence": 0.0-1.0, "reason": "brief explanation based on explicit evidence"}

Be conservative - false when uncertain."""

    enhanced_bids = []
    
    for idx, bid in enumerate(bids, 1):
        project_name = str(bid.get('Project Name', '') or '')
        summary = str(bid.get('Summary', '') or '')
        
        prompt = f"""STRICTLY analyze if this bid involves EXPLICIT flooring/carpeting work:

Project: {project_name}
Summary: {summary}

REQUIRE EXPLICIT EVIDENCE of flooring, carpet, tile, hardwood, vinyl, or floor installation/replacement.
Do NOT assume flooring work from general construction terms."""

        try:
            response = query_llm(prompt, system_prompt=system_prompt, temperature=0.1)
            
            import json
            try:
                analysis = json.loads(response.strip())
                is_flooring_related = analysis.get('is_flooring_related', False)
                confidence = analysis.get('confidence', 0.0)
                reason = analysis.get('reason', '')
                
                enhanced_bid = bid.copy()
                enhanced_bid['is_flooring_related'] = is_flooring_related
                enhanced_bid['flooring_confidence'] = confidence
                enhanced_bid['flooring_analysis'] = reason
                
                if is_flooring_related:
                    print(f"   \U0001F3AF Bid {idx}: TRUE - {project_name[:60]}...")
                    print(f"      Reason: {reason}")
                else:
                    print(f"   ❌ Bid {idx}: FALSE - {project_name[:60]}...")
            except json.JSONDecodeError:
                # Default to FALSE on any parsing errors
                enhanced_bid = bid.copy()
                enhanced_bid['is_flooring_related'] = False
                enhanced_bid['flooring_confidence'] = 0.0
                enhanced_bid['flooring_analysis'] = "Analysis failed - defaulting to false"
                print(f"   ❌ Bid {idx}: FALSE (parse error) - {project_name[:60]}...")
                
        except Exception as e:
            # Default to FALSE on any errors
            enhanced_bid = bid.copy()
            enhanced_bid['is_flooring_related'] = False
            enhanced_bid['flooring_confidence'] = 0.0
            enhanced_bid['flooring_analysis'] = f"Error: {str(e)[:50]}..."
            print(f"   ❌ Bid {idx}: FALSE (error) - {project_name[:60]}...")
        
        enhanced_bids.append(enhanced_bid)
    
    return enhanced_bids


if __name__ == "__main__":
    main()

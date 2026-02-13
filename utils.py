"""
Shared Utility Functions for Government Bid Scraping

This module provides common utility functions used across multiple scrapers
for date parsing, web element waiting, session management, and CSV output.

Author: Development Team
Created: 2025-01-27
Modified: 2025-01-27

Dependencies:
    - selenium: For web element interaction and waiting
    - pandas: For CSV output formatting
    - datetime: For date parsing and validation
"""

# Standard library imports
import csv
import datetime
import os
import stat
import time
from typing import List, Dict, Optional, Any

# Third-party imports
import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# Load environment variables
load_dotenv()


def get_chromedriver_path():
    """
    Get the correct ChromeDriver path, fixing webdriver-manager bugs.
    
    Returns:
        str: Path to the actual ChromeDriver executable
        
    Note:
        This function works around a known issue in webdriver-manager where
        it sometimes returns the path to THIRD_PARTY_NOTICES.chromedriver
        instead of the actual chromedriver executable. It also ensures the
        executable has proper permissions.
    """
    from webdriver_manager.chrome import ChromeDriverManager
    
    chromedriver_path = ChromeDriverManager().install()
    
    # Fix for webdriver-manager bug where it returns wrong file
    if chromedriver_path.endswith('THIRD_PARTY_NOTICES.chromedriver'):
        chromedriver_dir = os.path.dirname(chromedriver_path)
        actual_chromedriver = os.path.join(chromedriver_dir, 'chromedriver')
        if os.path.exists(actual_chromedriver):
            chromedriver_path = actual_chromedriver
    
    # Ensure the chromedriver has execute permissions
    if os.path.exists(chromedriver_path):
        current_permissions = os.stat(chromedriver_path).st_mode
        if not (current_permissions & stat.S_IXUSR):
            os.chmod(chromedriver_path, current_permissions | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    
    return chromedriver_path


def parse_mmddyyyy(date_str: str) -> Optional[datetime.date]:
    """
    Parse date string in mm/dd/yyyy format to datetime.date object.
    
    Args:
        date_str (str): Date string in format "mm/dd/yyyy" (e.g., "01/15/2025")
        
    Returns:
        Optional[datetime.date]: Parsed date object, or None if parsing fails
        
    Example:
        >>> parse_mmddyyyy("01/15/2025")
        datetime.date(2025, 1, 15)
        >>> parse_mmddyyyy("invalid") is None
        True
    """
    try:
        return datetime.datetime.strptime(date_str.strip(), "%m/%d/%Y").date()
    except (ValueError, AttributeError):
        return None


def wait_for_summary_table(driver, timeout: int = 30) -> bool:
    """
    Wait for PlanetBids summary table to load on the page.
    
    Args:
        driver: Selenium WebDriver instance
        timeout (int): Maximum time to wait in seconds (default: 30)
        
    Returns:
        bool: True if table loads successfully, False if timeout occurs
        
    Note:
        Specifically looks for PlanetBids table with CSS selector 
        "table.pb-datatable.data"
    """
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table.pb-datatable.data"))
        )
        return True
    except Exception:
        return False


def wait_for_detail_page(driver, timeout: int = 30) -> bool:
    """
    Wait for PlanetBids detail page to fully load.
    
    Args:
        driver: Selenium WebDriver instance
        timeout (int): Maximum time to wait in seconds (default: 30)
        
    Returns:
        bool: True if detail page loads successfully, False if timeout occurs
        
    Note:
        Looks for detail page elements with CSS selector 
        "div.bid-detail-item-title"
    """
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.bid-detail-item-title"))
        )
        return True
    except Exception:
        return False


def is_session_expired(driver) -> bool:
    """
    Check if the current browser session has expired.
    
    Args:
        driver: Selenium WebDriver instance
        
    Returns:
        bool: True if session has expired, False otherwise
        
    Note:
        Checks for common session expiration messages in page body text.
        Used to detect when re-authentication is needed.
    """
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text
        expiration_indicators = [
            "Your session has expired",
            "refresh the page to continue"
        ]
        return any(indicator in body_text for indicator in expiration_indicators)
    except Exception:
        return False


def save_site_csv(items: List[Dict[str, str]], portal_id: str, city_name: Optional[str] = None) -> None:
    """
    Save scraped bid data to a CSV file with standardized column ordering.
    
    Creates individual CSV files for each portal/city combination in the 
    planetbid/ directory. Uses city names for filenames when available,
    falling back to portal IDs.
    
    Args:
        items (List[Dict[str, str]]): List of bid records to save
        portal_id (str): Portal identifier (used for logging and fallback naming)
        city_name (Optional[str]): Human-readable city name for filename
        
    Returns:
        None
        
    Note:
        - Creates planetbid/ directory if it doesn't exist
        - Uses predefined column order for consistent CSV structure
        - Saves with UTF-8 encoding to handle special characters
        
    Example:
        >>> save_site_csv(bid_data, "39478", "agoura_hills")  
        # Creates: planetbid/agoura_hills_planetbids_data.csv
    """
    if not items:
        print(f"✗ No items to save for portal {portal_id}")
        return
        
    # Use city name if provided, otherwise fall back to portal_id
    filename_base = city_name if city_name else portal_id
    filename = f"planetbid/{filename_base}_planetbids_data.csv"
    print(f"Saving data for portal {portal_id} ({filename_base}) to {filename}...")
    
    # Standardized column order for consistent CSV output
    # Note: Order matches expected output format for downstream processing
    cols = [
        "project_title", "invitation_num", "bid_posting_date", "project_stage", 
        "bid_due_date", "response_format", "project_type", "response_types", 
        "type_of_award", "categories", "license_requirements", "department", 
        "address", "county", "bid_valid", "liquidated_damages", "estimated_bid_value", 
        "start_delivery_date", "project_duration", "bid_bond", "payment_bond", 
        "performance_bond", "pre-bid_meeting", "online_qa", "contact_info", 
        "bids_to", "owners_agent", "scope_of_services", "other_details", "notes", 
        "special_notices", "local_programs_policies", "qa_deadline", "source_url", "detail_url"
    ]
    
    # Create DataFrame and reorder columns for consistency
    df = pd.DataFrame(items)
    df = df.reindex(columns=cols)
    df.to_csv(filename, index=False, encoding="utf-8")
    print(f"✓ Saved {len(df)} rows to {filename}")


def query_llm(
    prompt: str,
    model: str = None,
    system_prompt: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 1000,
    stream: bool = False
) -> str:
    """
    Query Language Learning Model via OpenRouter API.
    
    This function provides a unified interface to query various LLMs through
    OpenRouter, making it easy to integrate AI capabilities into scraping workflows.
    
    Args:
        prompt (str): The user message/question to send to the LLM
        model (str, optional): Model to use. Defaults to env OPENROUTER_DEFAULT_MODEL
        system_prompt (str, optional): System message to set context/behavior
        temperature (float): Randomness in responses (0.0-1.0). Default 0.7
        max_tokens (int): Maximum tokens in response. Default 1000
        stream (bool): Whether to stream response. Default False
        
    Returns:
        str: The LLM's response content
        
    Raises:
        ValueError: If API key is not configured
        requests.RequestException: If API request fails
        
    Example:
        >>> # Basic usage
        >>> response = query_llm("What is web scraping?")
        >>> print(response)
        
        >>> # With system prompt for specific task
        >>> system = "You are an expert in government procurement data analysis."
        >>> response = query_llm(
        ...     "Analyze this bid title: 'Road Construction Project'",
        ...     system_prompt=system,
        ...     model="anthropic/claude-3-sonnet"
        ... )
        
        >>> # For data categorization
        >>> response = query_llm(
        ...     f"Categorize this project: {project_title}",
        ...     temperature=0.1  # Lower temperature for consistent categorization
        ... )
    """
    # Get configuration from environment
    api_key = os.getenv('OPENROUTER_API_KEY')
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not found in environment variables")
    
    # Use default model if none specified
    if not model:
        model = os.getenv('OPENROUTER_DEFAULT_MODEL', 'openai/gpt-4o-mini')
    
    # Prepare headers
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    
    # Optional headers for OpenRouter rankings
    site_url = os.getenv('OPENROUTER_SITE_URL')
    site_name = os.getenv('OPENROUTER_SITE_NAME')
    
    if site_url:
        headers['HTTP-Referer'] = site_url
    if site_name:
        headers['X-Title'] = site_name
    
    # Prepare messages
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    # Prepare request payload
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream
    }
    
    try:
        response = requests.post(
            'https://openrouter.ai/api/v1/chat/completions',
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        
        if 'choices' in data and len(data['choices']) > 0:
            return data['choices'][0]['message']['content']
        else:
            raise ValueError(f"Unexpected API response format: {data}")
            
    except requests.RequestException as e:
        raise requests.RequestException(f"OpenRouter API request failed: {e}")


def analyze_bid_with_llm(bid_data: Dict[str, Any], analysis_type: str = "categorize") -> str:
    """
    Analyze bid data using LLM for categorization, risk assessment, or insights.
    
    Specialized function for analyzing government bid data using AI.
    Provides common analysis patterns for procurement data.
    
    Args:
        bid_data (Dict[str, Any]): Bid information dictionary
        analysis_type (str): Type of analysis - "categorize", "risk", "insights"
        
    Returns:
        str: Analysis results from the LLM
        
    Example:
        >>> bid = {
        ...     'project_title': 'Road Maintenance and Repair Services',
        ...     'estimated_bid_value': '$500,000',
        ...     'project_duration': '12 months'
        ... }
        >>> category = analyze_bid_with_llm(bid, "categorize")
        >>> print(f"Category: {category}")
    """
    project_title = bid_data.get('project_title', 'Unknown Project')
    estimated_value = bid_data.get('estimated_bid_value', 'Not specified')
    project_type = bid_data.get('project_type', 'Not specified')
    department = bid_data.get('department', 'Not specified')
    
    if analysis_type == "categorize":
        system_prompt = """You are an expert in government procurement categorization. 
        Provide a single, clear category for the project (e.g., Construction, IT Services, 
        Professional Services, Maintenance, Equipment, etc.). Respond with just the category name."""
        
        prompt = f"""Categorize this government bid:
        Title: {project_title}
        Type: {project_type}
        Department: {department}
        Value: {estimated_value}"""
        
    elif analysis_type == "risk":
        system_prompt = """You are a procurement risk analyst. Assess the risk level 
        (Low, Medium, High) and provide 2-3 key risk factors. Be concise."""
        
        prompt = f"""Assess procurement risk for:
        Title: {project_title}
        Value: {estimated_value}
        Duration: {bid_data.get('project_duration', 'Not specified')}
        Type: {project_type}"""
        
    elif analysis_type == "insights":
        system_prompt = """You are a business intelligence analyst specializing in 
        government contracts. Provide 2-3 key business insights or opportunities."""
        
        prompt = f"""Analyze this government opportunity:
        Title: {project_title}
        Value: {estimated_value}
        Department: {department}
        Due Date: {bid_data.get('bid_due_date', 'Not specified')}"""
        
    else:
        raise ValueError(f"Unknown analysis_type: {analysis_type}")
    
    return query_llm(prompt, system_prompt=system_prompt, temperature=0.3)


def batch_categorize_bids(bids: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Categorize multiple bids efficiently using LLM batch processing.
    
    Args:
        bids (List[Dict[str, Any]]): List of bid dictionaries
        
    Returns:
        List[Dict[str, Any]]: Bids with added 'ai_category' field
        
    Example:
        >>> bids_with_categories = batch_categorize_bids(scraped_bids)
        >>> for bid in bids_with_categories:
        ...     print(f"{bid['project_title']} -> {bid['ai_category']}")
    """
    # Prepare batch prompt for efficiency
    bid_summaries = []
    for i, bid in enumerate(bids):
        title = bid.get('project_title', 'Unknown')
        bid_type = bid.get('project_type', 'Not specified')
        bid_summaries.append(f"{i+1}. {title} (Type: {bid_type})")
    
    batch_prompt = f"""Categorize these {len(bids)} government bids. 
    Respond with just the number and category for each, like:
    1. Construction
    2. IT Services
    3. Professional Services
    
    Bids to categorize:
    {chr(10).join(bid_summaries)}"""
    
    system_prompt = """You are an expert in government procurement categorization. 
    Use categories like: Construction, IT Services, Professional Services, Maintenance, 
    Equipment, Transportation, Healthcare, Environmental, etc."""
    
    try:
        response = query_llm(batch_prompt, system_prompt=system_prompt, temperature=0.1)
        
        # Parse response and add categories to bids
        lines = response.strip().split('\n')
        for i, bid in enumerate(bids):
            if i < len(lines):
                # Extract category from "1. Construction" format
                line = lines[i].strip()
                if '. ' in line:
                    category = line.split('. ', 1)[1]
                    bid['ai_category'] = category
                else:
                    bid['ai_category'] = 'Uncategorized'
            else:
                bid['ai_category'] = 'Uncategorized'
                
    except Exception as e:
        print(f"Warning: Batch categorization failed: {e}")
        # Fallback: mark all as uncategorized
        for bid in bids:
            bid['ai_category'] = 'Error'
    
    return bids


def send_to_airtable(
    records: List[Dict[str, Any]], 
    table_name: Optional[str] = None,
    batch_size: int = 10,
    base_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send scraped bid data to Airtable table.
    
    This function uploads bid records to Airtable using their REST API.
    Handles batch processing for large datasets and provides detailed
    status reporting for successful uploads and errors.
    
    Args:
        records (List[Dict[str, Any]]): List of bid dictionaries to upload
        table_name (str, optional): Airtable table name. Uses env default if not provided
        batch_size (int): Number of records per batch (max 10 for Airtable API)
        base_id (str, optional): Airtable base ID. Overrides env variable if provided
        
    Returns:
        Dict[str, Any]: Upload results with success/failure counts and details
        
    Raises:
        ValueError: If required Airtable credentials are missing
        requests.RequestException: If API request fails
        
    Example:
        >>> # Upload scraped bids
        >>> results = send_to_airtable(scraped_bids)
        >>> print(f"Uploaded: {results['success_count']}/{results['total_count']}")
        
        >>> # Upload to specific table
        >>> results = send_to_airtable(bids, table_name="PlanetBids_Data")
        
        >>> # Custom batch size for faster processing
        >>> results = send_to_airtable(bids, batch_size=5)
    """
    # Validate environment configuration
    access_token = os.getenv('AIRTABLE_ACCESS_TOKEN')
    if base_id is None:
        base_id = os.getenv('AIRTABLE_RAW_BASE_ID') if table_name == 'raw_scraped_data' else os.getenv('AIRTABLE_BASE_ID')
    if not access_token or not base_id:
        raise ValueError("AIRTABLE_ACCESS_TOKEN and AIRTABLE_BASE_ID must be set in environment")
    
    if not table_name:
        table_name = os.getenv('AIRTABLE_TABLE_NAME', 'Government Bids')
    
    # Prepare API configuration
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    base_url = f'https://api.airtable.com/v0/{base_id}/{table_name.replace(" ", "%20")}'
    
    # Track upload results
    results = {
        'total_count': len(records),
        'success_count': 0,
        'failure_count': 0,
        'successful_records': [],
        'failed_records': [],
        'errors': []
    }
    
    print(f"📤 Uploading {len(records)} records to Airtable...")
    print(f"   Table: {table_name}")
    print(f"   Base ID: {base_id}")
    
    # Process in batches (Airtable limit is 10 records per request)
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = ((len(records) - 1) // batch_size) + 1
        
        print(f"   Processing batch {batch_num}/{total_batches} ({len(batch)} records)...")
        
        # Format records for Airtable API
        airtable_records = []
        for record in batch:
            # Clean and format record for Airtable
            cleaned_record = clean_record_for_airtable(record)
            airtable_records.append({"fields": cleaned_record})
        
        payload = {"records": airtable_records}
        
        try:
            response = requests.post(base_url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if 'records' in data:
                batch_success_count = len(data['records'])
                results['success_count'] += batch_success_count
                results['successful_records'].extend(data['records'])
                print(f"   ✅ Batch {batch_num}: {batch_success_count} records uploaded successfully")
            else:
                results['failure_count'] += len(batch)
                results['failed_records'].extend(batch)
                error_msg = f"Batch {batch_num}: Unexpected API response format"
                results['errors'].append(error_msg)
                print(f"   ❌ {error_msg}")
                
        except requests.RequestException as e:
            results['failure_count'] += len(batch)
            results['failed_records'].extend(batch)
            
            # Get more detailed error information
            error_details = str(e)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_response = e.response.json()
                    if 'error' in error_response:
                        error_details = f"{str(e)} - {error_response['error']}"
                except:
                    error_details = f"{str(e)} - Response: {e.response.text[:200]}"
            
            error_msg = f"Batch {batch_num}: API request failed - {error_details}"
            results['errors'].append(error_msg)
            print(f"   ❌ {error_msg}")
            
            # Debug: Show the payload that failed
            print(f"   🔍 Debug - Failed payload sample:")
            if batch:
                sample_record = batch[0]
                for key, value in sample_record.items():
                    display_value = str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
                    print(f"      • {key}: {display_value}")
            
            
        # Rate limiting - pause between batches
        if i + batch_size < len(records):
            time.sleep(0.2)  # 200ms delay between batches
    
    # Final results summary
    print(f"\n📊 AIRTABLE UPLOAD RESULTS:")
    print(f"   • Total records: {results['total_count']}")
    print(f"   • Successfully uploaded: {results['success_count']}")
    print(f"   • Failed uploads: {results['failure_count']}")
    
    if results['failure_count'] > 0:
        print(f"   • Success rate: {(results['success_count']/results['total_count']*100):.1f}%")
        print(f"   ⚠️  Some records failed to upload. Check results['errors'] for details.")
    else:
        print(f"   🎉 All records uploaded successfully!")
    
    return results


def clean_record_for_airtable(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Clean and format a bid record for Airtable upload.
    
    Removes None values, converts data types, and ensures field names
    are compatible with Airtable requirements.
    
    Args:
        record (Dict[str, Any]): Raw bid record from scraper
        
    Returns:
        Dict[str, Any]: Cleaned record ready for Airtable upload
        
    Note:
        - Removes fields with None/empty values
        - Converts dates to ISO format strings
        - Truncates long text fields to Airtable limits
        - Handles special characters in field names
    """
    cleaned = {}
    # Field name mapping for Airtable (no Date Scraped)
    field_name_map = {}
    for key, value in record.items():
        # Skip None or empty values
        if value is None or value == '' or value == 'N/A':
            continue
        
        # Clean field names for Airtable compatibility
        clean_key = field_name_map.get(key, key.replace('_', ' ').title())
        
        # Handle different data types
        if isinstance(value, str):
            # Truncate very long strings (Airtable has limits)
            if len(value) > 50000:  # Airtable long text field limit
                cleaned[clean_key] = value[:50000] + "... [truncated]"
            else:
                cleaned[clean_key] = value
                
        elif isinstance(value, (int, float)):
            cleaned[clean_key] = value
            
        elif isinstance(value, bool):
            cleaned[clean_key] = value
            
        else:
            # Convert other types to string
            cleaned[clean_key] = str(value)
    
    return cleaned


def create_airtable_table_schema() -> Dict[str, Any]:
    """
    Generate recommended Airtable table schema for government bid data.
    
    Returns a dictionary describing the optimal field structure for storing
    scraped government bid data in Airtable, including field types and options.
    
    Returns:
        Dict[str, Any]: Airtable table schema configuration
        
    Example:
        >>> schema = create_airtable_table_schema()
        >>> for field in schema['fields']:
        ...     print(f"{field['name']}: {field['type']}")
    """
    schema = {
        "description": "Government Bid Tracking - Scraped Data from PlanetBids and OpenGov",
        "fields": [
            {"name": "Project Title", "type": "singleLineText"},
            {"name": "City Name", "type": "singleLineText"},
            {"name": "Portal ID", "type": "singleLineText"},
            {"name": "Detail Url", "type": "url"},
            {"name": "Bid Posting Date", "type": "date"},
            {"name": "Bid Due Date", "type": "date"},
            {"name": "Project Type", "type": "singleLineText"},
            {"name": "Department", "type": "singleLineText"},
            {"name": "Estimated Bid Value", "type": "singleLineText"},
            {"name": "Project Duration", "type": "singleLineText"},
            {"name": "Contact Name", "type": "singleLineText"},
            {"name": "Contact Email", "type": "email"},
            {"name": "Contact Phone", "type": "phoneNumber"},
            {"name": "Project Description", "type": "multilineText"},
            {"name": "Submission Requirements", "type": "multilineText"},
            {"name": "AI Category", "type": "singleSelect", "options": {
                "choices": [
                    {"name": "Construction", "color": "blue"},
                    {"name": "IT Services", "color": "green"},
                    {"name": "Professional Services", "color": "purple"},
                    {"name": "Maintenance", "color": "orange"},
                    {"name": "Equipment", "color": "red"},
                    {"name": "Transportation", "color": "yellow"},
                    {"name": "Environmental", "color": "teal"},
                    {"name": "Healthcare", "color": "pink"},
                    {"name": "Other", "color": "gray"}
                ]
            }},
            {"name": "AI Risk Level", "type": "singleSelect", "options": {
                "choices": [
                    {"name": "Low", "color": "green"},
                    {"name": "Medium", "color": "yellow"},
                    {"name": "High", "color": "red"}
                ]
            }},
            {"name": "Status", "type": "singleSelect", "options": {
                "choices": [
                    {"name": "New", "color": "blue"},
                    {"name": "Reviewing", "color": "yellow"},
                    {"name": "Bidding", "color": "orange"},
                    {"name": "Submitted", "color": "purple"},
                    {"name": "Won", "color": "green"},
                    {"name": "Lost", "color": "red"},
                    {"name": "Passed", "color": "gray"}
                ]
            }},
            {"name": "Notes", "type": "multilineText"},
            {"name": "Source Portal", "type": "singleLineText"},
            {"name": "Scraped Date", "type": "dateTime"},
            {"name": "Last Updated", "type": "lastModifiedTime"}
        ]
    }
    
    return schema


def upload_dataframe_to_airtable(
    df: pd.DataFrame, 
    table_name: Optional[str] = None,
    add_metadata: bool = True,
    base_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Upload a pandas DataFrame to Airtable.
    
    Convenience function to upload scraped bid data directly from DataFrame
    to Airtable with optional metadata addition.
    
    Args:
        df (pd.DataFrame): DataFrame containing bid data
        table_name (str, optional): Airtable table name
        add_metadata (bool): Whether to add scraped timestamp metadata (now ignored)
        base_id (str, optional): Airtable base ID. Overrides env variable if provided
        
    Returns:
        Dict[str, Any]: Upload results from send_to_airtable()
        
    Example:
        >>> # Upload scraped DataFrame
        >>> df = pd.read_csv('planetbid/planetbids_data.csv')
        >>> results = upload_dataframe_to_airtable(df)
        >>> print(f"Upload success rate: {results['success_count']}/{results['total_count']}")
    """
    if df.empty:
        print("⚠️  DataFrame is empty - nothing to upload to Airtable")
        return {
            'total_count': 0,
            'success_count': 0,
            'failure_count': 0,
            'successful_records': [],
            'failed_records': [],
            'errors': []
        }
    print(f"📊 Preparing {len(df)} records for Airtable upload...")
    # Convert DataFrame to list of dictionaries
    records = df.to_dict('records')
    # Do NOT add scraped_date or any extra metadata
    return send_to_airtable(records, table_name, base_id=base_id)


# Example integration function for your scraper
def save_to_airtable_and_csv(
    df: pd.DataFrame, 
    csv_path: str,
    table_name: Optional[str] = None
) -> None:
    """
    Save scraping results to both CSV file and Airtable.
    
    Dual-save function that maintains local CSV backup while also
    uploading to Airtable for cloud access and collaboration.
    
    Args:
        df (pd.DataFrame): Scraped bid data
        csv_path (str): Local CSV file path
        table_name (str, optional): Airtable table name
        
    Example:
        >>> # In your main scraper function
        >>> df, stats = scrape_all(URLS)
        >>> save_to_airtable_and_csv(df, "planetbid/planetbids_data.csv")
    """
    # Save to CSV first (local backup)
    df.to_csv(csv_path, index=False)
    print(f"✅ Local CSV saved: {csv_path}")
    
    # Try to upload to Airtable
    try:
        results = upload_dataframe_to_airtable(df, table_name)
        
        if results['success_count'] == results['total_count']:
            print(f"✅ All {results['total_count']} records uploaded to Airtable successfully!")
        else:
            print(f"⚠️  Partial upload: {results['success_count']}/{results['total_count']} records uploaded")
            
    except Exception as e:
        print(f"❌ Airtable upload failed: {e}")
        print(f"📁 Data is safely stored in CSV: {csv_path}")


def save_failed_url_to_txt(url: str, source: str = "", reason: str = "",
                          city_name: str = "", project_title: str = "",
                          filename: str = "failed_urls.txt"):
    """
    Append a failed URL to the failed_urls.txt file (one URL per line).
    """
    if not url:
        return
    try:
        with open(filename, 'a', encoding='utf-8') as f:
            f.write(f"{url}\n")
    except Exception as e:
        print(f"⚠️  Warning: Could not save failed URL to {filename}: {e}")


def save_failed_pages_batch(failed_pages: List[Dict], source: str = "", filename: str = "failed_urls.txt"):
    """
    Save multiple failed page URLs to failed_urls.txt (one URL per line).
    """
    if not failed_pages:
        return

    urls = []
    for page in failed_pages:
        url = page.get('detail_url', page.get('url', ''))
        if url:
            urls.append(url)

    if not urls:
        return

    try:
        with open(filename, 'a', encoding='utf-8') as f:
            for url in urls:
                f.write(f"{url}\n")
        print(f"💾 {len(urls)} failed URLs saved to {filename}")
    except Exception as e:
        print(f"⚠️  Warning: Could not save failed URLs to {filename}: {e}")


def clear_failed_urls_file(filename: str = "failed_urls.txt"):
    """
    Clear the failed URLs file and add a header.
    
    Args:
        filename (str): Filename to clear (default: failed_urls.txt)
    """
    from datetime import datetime
    
    header = f"""# Failed URLs - Last scraper run: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
# One URL per line - these need to be manually checked
"""
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(header)
    except Exception as e:
        print(f"⚠️  Warning: Could not clear {filename}: {e}")


def save_airtable_format_csv(items: List[Dict], filename: str, source_name: str) -> None:
    """
    Save bid records in Airtable-compatible CSV format (5 columns, no Date Scraped).
    
    Args:
        items (List[Dict]): List of bid records (in Airtable format)
        filename (str): Output CSV filename (with path)
        source_name (str): Name of the scraper/source for logging
        
    Example:
        save_airtable_format_csv(airtable_data, "opengov/opengov.csv", "OpenGov")
    """
    import csv
    import os
    if not items:
        print(f"✗ No {source_name} items to save")
        return
    print(f"💾 Saving {source_name} data to {filename}...")
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    headers = ["Project Name", "Summary", "Published Date", "Due Date", "Link"]
    try:
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for item in items:
                row = [
                    item.get("Project Name", ""),
                    item.get("Summary", ""),
                    item.get("Published Date", ""),
                    item.get("Due Date", ""),
                    item.get("Link", "")
                ]
                writer.writerow(row)
        print(f"✓ Successfully saved {len(items)} {source_name} records to {filename}")
    except Exception as e:
        print(f"✗ Failed to save {source_name} data to {filename}: {e}")


# =============================================================================
# PREDEFINED FIELD MAPPINGS FOR COMMON SCRAPERS
# =============================================================================

# PlanetBids field mapping
PLANETBIDS_FIELD_MAPPING = {
    "city_name": "City",
    "portal_id": "Portal ID", 
    "project_title": "Project Title",
    "invitation_num": "Invitation #",
    "bid_posting_date": "Posted Date",
    "project_stage": "Stage",
    "bid_due_date": "Due Date",
    "response_format": "Response Format",
    "project_type": "Project Type",
    "response_types": "Response Types",
    "type_of_award": "Type of Award",
    "categories": "Categories",
    "license_requirements": "License Requirements",
    "department": "Department",
    "address": "Address",
    "county": "County",
    "bid_valid": "Bid Valid",
    "liquidated_damages": "Liquidated Damages",
    "estimated_bid_value": "Estimated Value",
    "start_delivery_date": "Start/Delivery Date",
    "project_duration": "Project Duration",
    "bid_bond": "Bid Bond",
    "payment_bond": "Payment Bond",
    "performance_bond": "Performance Bond",
    "pre-bid_meeting": "Pre-Bid Meeting",
    "online_qa": "Online Q&A",
    "contact_info": "Contact Info",
    "bids_to": "Bids To",
    "owners_agent": "Owner's Agent",
    "scope_of_services": "Scope of Services",
    "other_details": "Other Details",
    "notes": "Notes",
    "special_notices": "Special Notices",
    "local_programs_policies": "Local Programs & Policies",
    "qa_deadline": "Q&A Deadline",
    "ai_category": "AI Category",
    "source_url": "Source URL",
    "detail_url": "Detail URL"
}

# OpenGov field mapping
OPENGOV_FIELD_MAPPING = {
    "portal_code": "Portal Code",
    "city_name": "City",
    "project_title": "Project Title",
    "Project Title": "Project Title",  # Handle both formats
    "status": "Status",
    "addenda": "Addenda",
    "release_date": "Release Date",
    "due_date": "Due Date",
    "sealed_bid_process": "Sealed Bid Process",
    "private_bid": "Private Bid",
    "summary": "Summary",
    "Summary": "Summary",  # Handle both formats
    "release_project_date": "Release Project Date",
    "question_submission_deadline": "Question Submission Deadline",
    "proposal_submission_deadline": "Proposal Submission Deadline",
    "Release Date": "Published Date",  # Airtable-compatible
    "Due Date": "Due Date",  # Airtable-compatible
    "ai_category": "AI Category",
    "is_flooring_related": "Is Flooring Related",
    "source_url": "Source URL",
    "detail_url": "Detail URL"
}

# Generic minimal mapping for new scrapers
GENERIC_FIELD_MAPPING = {
    "project_title": "Project Title",
    "summary": "Summary", 
    "published_date": "Published Date",
    "due_date": "Due Date",
    "source_url": "Source URL",
    "detail_url": "Detail URL"
}

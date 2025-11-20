# New Scraper Template Guide

This document provides a step-by-step guide for creating a new government bid scraper using the provided template (`new_city_scraper.py`).

## Quick Start

1. **Copy the template file:**
   ```bash
   cp new_city_scraper.py your_city_scraper.py
   ```

2. **Update the configuration section**
3. **Analyze the target website structure**
4. **Update the CSS selectors**
5. **Test and refine**
6. **Integrate with main.py**

## Step-by-Step Instructions

### 1. Basic Configuration

Update these constants at the top of the file:

```python
# =============================================================================
# CONFIGURATION
# =============================================================================

BASE_URL = "https://your-city.gov/bids"  # Replace with actual URL
OUTPUT_CSV = "your_city/your_city_bids.csv"  # Update folder name

# Update the docstring
"""
Your City Government Bids Scraper

Scrapes government bid opportunities from [Your City] portal.
...
"""
```

### 2. Analyze Target Website

Before updating selectors, you need to understand the target website structure:

1. **Visit the target URL in your browser**
2. **Right-click and "Inspect Element"**
3. **Identify the HTML structure for:**
   - Bid listing containers
   - Bid titles and links
   - Published dates
   - Due dates
   - Detail page content

### 3. Update CSS Selectors

#### In `extract_summary_table()` function:

```python
# Replace these example selectors with actual ones from the website
bid_containers = soup.find_all('div', class_='bid-item')  # Main containers

# Title and link extraction
title_elem = container.find('a', class_='bid-title')  # Title selector

# Date extraction
date_elem = container.find('span', class_='published-date')  # Published date
due_elem = container.find('span', class_='due-date')  # Due date
```

#### In `extract_bid_detail()` function:

```python
# Update these selectors for the detail page
summary_selectors = [
    'div.bid-description',    # Main description container
    'div.summary',           # Alternative summary container
    'div.content',           # Generic content container
    'p.description',         # Paragraph-based description
    'div#description'        # ID-based description
]
```

### 4. Common HTML Patterns

Here are common patterns you might encounter:

#### Table-based listings:
```python
# For table rows
table = soup.find('table', class_='bids-table')
rows = table.find_all('tr')[1:]  # Skip header row

for row in rows:
    cells = row.find_all('td')
    title = cells[0].get_text(strip=True)
    published = cells[1].get_text(strip=True)
    due = cells[2].get_text(strip=True)
```

#### Card-based listings:
```python
# For card/div containers
cards = soup.find_all('div', class_='bid-card')

for card in cards:
    title = card.find('h3', class_='title').get_text(strip=True)
    date = card.find('span', class_='date').get_text(strip=True)
```

#### List-based structure:
```python
# For list items
items = soup.find_all('li', class_='bid-item')

for item in items:
    link = item.find('a')
    title = link.get_text(strip=True)
    url = link.get('href')
```

### 5. Date Format Handling

The template uses `parse_mmddyyyy()` from utils, but you may need to handle different date formats:

```python
# For different date formats, you can add custom parsing
def parse_custom_date(date_str):
    """Parse dates in format like 'January 15, 2025'"""
    try:
        return datetime.strptime(date_str, '%B %d, %Y')
    except:
        try:
            return datetime.strptime(date_str, '%m/%d/%Y')
        except:
            return None

# Use in your scraper:
published_date = parse_custom_date(detailed_bid['published_date'])
```

### 6. Handling Pagination

If the website has multiple pages of bids:

```python
def scrape_all_pages(driver, base_url):
    """Scrape all pages of bids"""
    all_bids = []
    page = 1
    
    while True:
        url = f"{base_url}?page={page}"  # Adjust URL pattern
        driver.get(url)
        
        bids = extract_summary_table(driver)
        if not bids:
            break  # No more bids found
            
        all_bids.extend(bids)
        page += 1
        
        # Check for "next page" button
        try:
            next_button = driver.find_element(By.CLASS_NAME, "next-page")
            if not next_button.is_enabled():
                break
        except:
            break
    
    return all_bids
```

### 7. Error Handling Patterns

The template includes basic error handling, but you may need specific handling:

```python
# Handle specific website quirks
try:
    # Wait for specific elements
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CLASS_NAME, "bid-container"))
    )
except TimeoutException:
    print("⚠️  Bid container not found, trying alternative selector")
    # Try alternative approach

# Handle missing elements gracefully
title_elem = container.find('h3', class_='title')
title = title_elem.get_text(strip=True) if title_elem else "Title not found"
```

### 8. Testing Your Scraper

1. **Run the scraper in isolation:**
   ```bash
   python your_city_scraper.py
   ```

2. **Check the output:**
   - Verify CSV files are created
   - Check that data looks correct
   - Ensure dates are parsed properly

3. **Test with different scenarios:**
   - No bids available
   - Network timeouts
   - Missing detail pages

### 9. Integration with main.py

Once your scraper works, integrate it with the main pipeline:

```python
# In main.py, add import
from your_city_scraper import scrape_your_city

# Add to the scraping section
try:
    your_city_bids, your_city_failed = scrape_your_city(cutoff_date)
    if your_city_bids:
        all_airtable_data.extend(prepare_airtable_data(your_city_bids))
        scraping_summary['your_city'] = len(your_city_bids)
    failed_urls.extend(your_city_failed)
except Exception as e:
    print(f"❌ Your City scraping failed: {e}")
    scraping_summary['your_city'] = 0
```

### 10. Common Troubleshooting

#### Problem: No bids found
- Check CSS selectors with browser inspector
- Verify the page loads completely
- Check if there's a loading delay

#### Problem: Dates not parsing
- Print raw date strings to see format
- Update date parsing logic
- Handle multiple date formats

#### Problem: Detail pages not loading
- Add longer waits
- Check for redirects
- Verify URL construction

#### Problem: Bot detection
- Add random delays: `time.sleep(random.uniform(1, 3))`
- Use different user agents
- Add cookie handling

## Example: Updating for a Real Website

Let's say you're scraping `https://example-city.gov/procurement/bids`:

1. **Update configuration:**
   ```python
   BASE_URL = "https://example-city.gov/procurement/bids"
   OUTPUT_CSV = "example_city/example_city_bids.csv"
   ```

2. **Analyze the HTML structure** (example):
   ```html
   <div class="procurement-list">
     <div class="procurement-item">
       <h4><a href="/bid/123">Road Maintenance Project</a></h4>
       <p class="dates">Posted: 01/15/2025 | Due: 02/15/2025</p>
       <p class="description">Summary of the project...</p>
     </div>
   </div>
   ```

3. **Update selectors:**
   ```python
   # In extract_summary_table()
   bid_containers = soup.find_all('div', class_='procurement-item')
   
   title_elem = container.find('h4').find('a')
   title = title_elem.get_text(strip=True)
   detail_url = urljoin(BASE_URL, title_elem.get('href'))
   
   # Parse dates from the dates paragraph
   dates_text = container.find('p', class_='dates').get_text()
   # Use regex to extract dates: "Posted: 01/15/2025 | Due: 02/15/2025"
   ```

This template provides a solid foundation that follows the same patterns as your existing scrapers. Customize the selectors and error handling based on the specific website structure you're targeting.

# Coding Standards and Documentation Guidelines

This document establishes the coding standards, documentation requirements, and conventions for the Government Bid Scraping project.

## Table of Contents
1. [Code Organization](#code-organization)
2. [Naming Conventions](#naming-conventions)
3. [Documentation Standards](#documentation-standards)
4. [Docstring Standards](#docstring-standards)
5. [Code Comments](#code-comments)
6. [Type Hints](#type-hints)
7. [Error Handling](#error-handling)
8. [Constants and Configuration](#constants-and-configuration)

## Code Organization

### File Structure
- **Main entry points**: `main.py` - application entry point
- **Scrapers**: `planet_bids.py`, `opengov.py` - portal-specific scrapers
- **Utilities**: `utils.py` - shared utility functions
- **Configuration**: Constants and configuration at the top of each file
- **Output**: Organized in subdirectories (`planetbid/`, `opengov/`)

### Import Organization
1. Standard library imports
2. Third-party imports (grouped alphabetically)
3. Local imports
4. Blank line between each group

```python
# Standard library
import csv
import time
from typing import List, Dict

# Third-party
import pandas as pd
from selenium import webdriver

# Local
from utils import parse_date
```

## Naming Conventions

### Variables and Functions
- Use `snake_case` for variables and functions
- Use descriptive names that clearly indicate purpose
- Avoid abbreviations unless widely understood

```python
# Good
bid_posting_date = "01/01/2025"
def extract_project_details(driver, project_id):

# Avoid
bd = "01/01/2025"
def get_proj_dets(d, pid):
```

### Constants
- Use `UPPER_SNAKE_CASE` for constants
- Group related constants together
- Document complex constants

```python
# Configuration constants
BID_POSTING_DATE_FILTER = "06/01/2025"
MAX_RETRIES = 3
TIMEOUT_SECONDS = 30

# URL mapping
PORTAL_CITY_MAP = {
    "39478": "agoura_hills",
    "55389": "baldwin_park",
}
```

### Classes
- Use `PascalCase` for class names
- Use descriptive names that indicate the class purpose

## Documentation Standards

### Module-Level Documentation
Every Python file must start with a module docstring that includes:
- Brief description of the module's purpose
- Author information
- Creation/modification dates
- Usage examples (if applicable)

### Function Documentation
All functions must have docstrings that include:
- Purpose and behavior description
- Parameters with types and descriptions
- Return value with type and description
- Exceptions that may be raised
- Usage examples for complex functions

### Variable Documentation
- Document complex variables and data structures
- Use inline comments for non-obvious logic
- Document configuration variables and their impact

## Docstring Standards

### Format
Use Google-style docstrings for consistency:

```python
def scrape_detail_page(driver, portal_code: str, project_id: str, source_url: str = None) -> tuple:
    """Extract detailed information from a project's detail page.
    
    Navigates to the project detail page and extracts all required fields
    including project description, contact information, and bidding details.
    
    Args:
        driver: Selenium WebDriver instance for browser automation
        portal_code (str): Portal identifier (e.g., 'redondo', 'cityofbell')
        project_id (str): Unique project identifier from the summary table
        source_url (str, optional): Original URL where project was found
        
    Returns:
        tuple: A tuple containing (detail_dict, detail_url) where:
            - detail_dict (dict): Extracted project details
            - detail_url (str): Full URL of the detail page
            
    Raises:
        TimeoutException: If page fails to load within timeout period
        WebDriverException: If browser automation fails
        
    Example:
        >>> details, url = scrape_detail_page(driver, "redondo", "12345")
        >>> print(details['project_description'])
    """
```

### Required Sections
- **Args**: All parameters with types and descriptions
- **Returns**: Return value type and description
- **Raises**: Exceptions that may be raised
- **Example**: Usage example for complex functions

## Code Comments

### When to Comment
- Explain **why**, not **what** the code does
- Document business logic and complex algorithms
- Explain non-obvious workarounds or hacks
- Document external dependencies and their quirks

### Comment Style
```python
# Single line comments use hash symbol
# Multiple related comments can be grouped

"""
Multi-line comments for complex explanations
or when documenting algorithm steps.
"""

# TODO: Implement retry logic for failed requests
# FIXME: Handle edge case where project_id is None
# NOTE: This workaround is needed due to OpenGov's dynamic loading
```

### Avoid Over-commenting
```python
# Bad - obvious comment
x = x + 1  # Increment x by 1

# Good - explains business logic
x = x + 1  # Account for zero-based indexing in API response
```

## Type Hints

### Required Usage
- All function parameters and return values
- Class methods and properties
- Complex data structures

```python
from typing import List, Dict, Optional, Union

def extract_bid_data(driver, min_date: str) -> List[Dict[str, str]]:
    """Extract bid data with proper type hints."""
    pass

def parse_date(date_str: str) -> Optional[datetime.date]:
    """Return None if parsing fails."""
    pass
```

### Complex Types
```python
from typing import Dict, List, Tuple, Union

# Type aliases for complex structures
BidData = Dict[str, Union[str, int, float]]
ScrapingResult = Tuple[List[BidData], str]

def process_bids(data: List[BidData]) -> ScrapingResult:
    """Process bid data with clear type definitions."""
    pass
```

## Error Handling

### Exception Handling
- Use specific exception types when possible
- Always log errors with context
- Provide meaningful error messages
- Clean up resources in finally blocks

```python
def scrape_with_retry(driver, url: str, max_retries: int = 3) -> bool:
    """Scrape URL with retry logic and proper error handling."""
    for attempt in range(max_retries):
        try:
            driver.get(url)
            wait_for_page_load(driver)
            return True
        except TimeoutException as e:
            print(f"Attempt {attempt + 1} failed: Timeout loading {url}")
            if attempt == max_retries - 1:
                print(f"✗ Failed to load {url} after {max_retries} attempts")
                raise
        except WebDriverException as e:
            print(f"✗ WebDriver error on {url}: {e}")
            raise
        finally:
            # Clean up any temporary resources
            pass
    return False
```

### Logging Best Practices
- Use consistent prefixes: `✓` for success, `✗` for errors, `⚠` for warnings
- Include relevant context in error messages
- Log progress for long-running operations

## Constants and Configuration

### Organization
- Group related constants together
- Document the purpose and impact of each constant
- Use descriptive names that indicate units or format

```python
# Scraping Configuration
BID_POSTING_DATE_FILTER = "06/01/2025"  # Format: mm/dd/yyyy
MAX_RETRIES = 3                          # Number of retry attempts
TIMEOUT_SECONDS = 30                     # Page load timeout in seconds
WAIT_BETWEEN_REQUESTS = 2                # Seconds to wait between requests

# Output Configuration
OUTPUT_COLUMNS = [
    "project_title",
    "bid_posting_date", 
    "source_url",
    "detail_url"
]

# Portal Mapping - Maps portal IDs to human-readable city names
PORTAL_CITY_MAP = {
    "39478": "agoura_hills",      # Agoura Hills, CA
    "55389": "baldwin_park",      # Baldwin Park, CA
}
```

### Configuration Comments
- Explain format requirements
- Document valid values or ranges
- Note dependencies between configuration values

## Implementation Guidelines

### Function Length
- Keep functions focused on a single responsibility
- Aim for functions under 50 lines
- Extract complex logic into helper functions

### Code Reusability
- Extract common patterns into utility functions
- Use configuration over hardcoded values
- Design for extensibility to new portals

### Testing Considerations
- Write functions that are easy to test
- Minimize dependencies between components
- Use dependency injection for external services

This document should be followed for all new code and existing code should be gradually updated to meet these standards.

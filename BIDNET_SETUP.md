# BidNet Direct Environment Setup

To use the BidNet Direct scraper, you need to set up your login credentials as environment variables.

## Step 1: Create/Update .env file

In your project root directory (`/Users/leonardo/Desktop/Python/scraping_bids/`), add these lines to your `.env` file:

```bash
# BidNet Direct Credentials
BIDNET_USERNAME=your_username_here
BIDNET_PASSWORD=your_password_here
```

## Step 2: Set Environment Variables (Alternative)

You can also set them directly in your terminal:

```bash
export BIDNET_USERNAME="your_username_here"
export BIDNET_PASSWORD="your_password_here"
```

## Step 3: Test the Scraper

Run the BidNet Direct scraper:

```bash
python bidnet_scraper.py
```

## What the Scraper Does:

1. **Handles SAML Login**: Automatically logs into BidNet Direct
2. **Extracts Summary Data**: Gets all bid listings from Santa Clarita page
3. **Scrapes Detailed Descriptions**: Visits each individual bid page to get the description
4. **Applies Date Filtering**: Only scrapes recent bids (configurable)
5. **Saves to CSV**: Outputs data in Airtable-compatible format

## Extracted Data Fields:

- **Solicitation Number**: Bid reference number
- **Project Title**: Name/title of the project
- **Summary/Description**: Detailed description from individual bid pages
- **Published Date**: When the bid was published
- **Closing Date**: When bids are due
- **Link**: Direct URL to the bid detail page
- **Region**: Geographic area (California)

## Integration with Main Pipeline:

The scraper is designed to integrate with your existing pipeline:
- Uses same date filtering system
- Outputs Airtable-compatible format
- Handles failed page logging
- Provides detailed statistics

## Security Notes:

- Credentials are stored securely in environment variables
- Never commit credentials to git
- The scraper includes manual fallback if automated login fails
- Uses undetected Chrome to avoid bot detection

## Troubleshooting:

If automated login fails:
1. The scraper will pause and ask for manual intervention
2. Complete the login manually in the browser
3. Navigate to the bid listing page
4. Press ENTER to continue automated scraping

This approach ensures the scraper works even if SAML authentication changes.

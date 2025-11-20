# 🗃️ Airtable Integration Setup Guide

This guide shows you how to set up Airtable integration for your government bid scraper to automatically upload scraped data to your Airtable base.

## 📋 Prerequisites

1. **Airtable Account**: Sign up at [airtable.com](https://airtable.com)
2. **Personal Access Token**: Generate from Airtable account settings
3. **Airtable Base**: Create a base for storing government bid data

## 🚀 Step-by-Step Setup

### Step 1: Create Your Airtable Base

1. Go to [airtable.com](https://airtable.com) and sign in
2. Click "Create a base" 
3. Choose "Start from scratch"
4. Name your base: "Government Bids"
5. Create a table called "Government Bids" (or your preferred name)

### Step 2: Get Your Personal Access Token

1. Click your profile picture → "Account"
2. Go to "Tokens" section
3. Click "Create new token"
4. Name it: "Government Bid Scraper"
5. Select these scopes:
   - `data.records:read`
   - `data.records:write`
6. Select your "Government Bids" base
7. Click "Create token" and copy it

### Step 3: Get Your Base ID

1. Go to your "Government Bids" base
2. Click "Help" → "API documentation"
3. Your Base ID will be shown at the top (starts with `app...`)
4. Copy the Base ID

### Step 4: Update Your .env File

Open your `.env` file and add your credentials:

```properties
# Airtable API Configuration
AIRTABLE_ACCESS_TOKEN=your_personal_access_token_here
AIRTABLE_BASE_ID=appXXXXXXXXXXXXXX
AIRTABLE_TABLE_NAME=Government Bids
```

### Step 5: Test the Connection

Run the test script to verify everything works:

```bash
python airtable_example.py
```

## 📊 Recommended Table Schema

Create these fields in your Airtable table for optimal data structure:

| Field Name | Field Type | Notes |
|------------|------------|-------|
| Project Title | Single line text | Primary field |
| City Name | Single line text | |
| Portal ID | Single line text | |
| Detail Url | URL | |
| Bid Posting Date | Date | |
| Bid Due Date | Date | |
| Project Type | Single line text | |
| Department | Single line text | |
| Estimated Bid Value | Single line text | |
| Project Duration | Single line text | |
| Contact Name | Single line text | |
| Contact Email | Email | |
| Contact Phone | Phone number | |
| Project Description | Long text | |
| AI Category | Single select | Options: Construction, IT Services, Professional Services, etc. |
| AI Risk Level | Single select | Options: Low, Medium, High |
| Status | Single select | Options: New, Reviewing, Bidding, Won, Lost, Passed |
| Notes | Long text | |
| Source Portal | Single line text | |
| Scraped Date | Date and time | |

## 🔄 Usage

### Automatic Upload After Scraping

When you run your main scraper:

```bash
python main.py
```

After scraping completes, you'll see:
```
📤 Airtable integration available!
Upload data to Airtable? (y/n): y
```

### Manual Upload from CSV

Upload existing CSV files:

```python
from utils import upload_dataframe_to_airtable
import pandas as pd

# Load and upload CSV data
df = pd.read_csv('planetbid/planetbids_data.csv')
results = upload_dataframe_to_airtable(df)
print(f"Uploaded: {results['success_count']}/{results['total_count']}")
```

### Dual Save (CSV + Airtable)

In your custom scripts:

```python
from utils import save_to_airtable_and_csv

# This saves to both CSV and Airtable
save_to_airtable_and_csv(df, "output.csv")
```

## 🛠️ Advanced Usage

### Custom Table Name

```python
results = upload_dataframe_to_airtable(df, table_name="PlanetBids_Data")
```

### Batch Upload Control

```python
results = send_to_airtable(records, batch_size=5)  # Smaller batches
```

### Error Handling

```python
results = upload_dataframe_to_airtable(df)

if results['failure_count'] > 0:
    print("Some records failed:")
    for error in results['errors']:
        print(f"  - {error}")
```

## ❓ Troubleshooting

### "Access token invalid"
- Check your token in .env file
- Ensure no extra quotes or spaces
- Verify token has correct scopes

### "Table not found"
- Check your AIRTABLE_TABLE_NAME in .env
- Ensure table name matches exactly (case-sensitive)
- Try with table name in quotes if it has spaces

### "Rate limit exceeded"
- The scraper automatically handles rate limiting
- If issues persist, use smaller batch_size

### "Field validation error"
- Check that your Airtable fields match the data being uploaded
- Some fields may need to be created in Airtable first

## 🔐 Security Notes

1. **Never commit .env to git** - it contains your API tokens
2. **Use Personal Access Tokens** - more secure than API keys
3. **Limit token scopes** - only give necessary permissions
4. **Rotate tokens regularly** - especially if shared or compromised

## 💡 Tips

1. **Start with test data** - run `airtable_example.py` first
2. **Check rate limits** - Airtable has API call limits
3. **Use views** - create filtered views in Airtable for different use cases
4. **Automate with filters** - only upload bids meeting certain criteria
5. **Backup strategy** - CSV files serve as local backup if Airtable fails

## 📞 Support

If you encounter issues:

1. Check the [Airtable API documentation](https://airtable.com/developers)
2. Review error messages in the console output
3. Test with the provided `airtable_example.py` script
4. Ensure your .env file is properly configured

Happy scraping! 🎉

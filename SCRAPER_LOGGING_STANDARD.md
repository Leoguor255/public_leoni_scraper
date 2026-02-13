# Scraper Logging & Terminal Output Standards

This document describes the standard for logging and terminal output for the government bid scraping pipeline. The goal is to make the output clear, concise, and easily readable for non-technical users, focusing on high-level progress and summary information for each website/portal.

## Principles
- **Clarity:** Use plain language and clear section headers.
- **Progress:** Show what the scraper is doing at each major step (starting, scraping, mapping, uploading).
- **Summary:** For each portal (e.g., PlanetBids, OpenGov, El Segundo), print a summary of how many RFPs/bids were scraped, and any errors.
- **Minimal Detail:** Do **not** print every RFP/bid scraped. Only print per-portal/city summaries.
- **Highlight Issues:** Clearly show if a portal failed, found no RFPs, or had upload errors.
- **Visual Cues:** Use emojis and simple formatting for readability (e.g., ✅, ❌, 📊, ➡️, etc.).

## Example Terminal Output

```
==================================================
🚀 Starting Government Bid Scraping Application
==================================================

📅 Date filter: Only bids posted after 11/06/2025 (last 7 days)

➡️  [PlanetBids] Scraping 5 cities...
   - City of Pasadena: 3 RFPs scraped
   - City of Santa Monica: 2 RFPs scraped
   - City of Redondo Beach: 0 RFPs found
   - City of Manhattan Beach: 1 RFP scraped
   - City of Glendale: 0 RFPs found
✅  [PlanetBids] Total: 6 RFPs scraped

➡️  [OpenGov] Scraping 2 cities...
   - City of Pasadena: 1 RFP scraped
   - City of Santa Monica: 0 RFPs found
✅  [OpenGov] Total: 1 RFP scraped

➡️  [El Segundo] Scraping...
✅  [El Segundo] 2 RFPs scraped

➡️  [Compton] Scraping...
❌  [Compton] Failed to scrape (site unreachable)

➡️  [QuestCDN] Scraping 3 cities...
   - Monterey Park: 2 RFPs scraped
   - Glendora: 0 RFPs found
   - Other: 1 RFP scraped
✅  [QuestCDN] Total: 3 RFPs scraped

==================================================
📤 Uploading 12 RFPs to Airtable...
✅  Upload successful!

==================================================
📊 FINAL SUMMARY
==================================================
✅  PlanetBids: 6 RFPs
✅  OpenGov: 1 RFP
✅  El Segundo: 2 RFPs
❌  Compton: 0 RFPs (error)
✅  QuestCDN: 3 RFPs

📝  Note: E-ARC scraper is available but disabled pending client input
==================================================
✅  Application completed successfully
```

## Implementation Guidelines
- **Section Headers:** Use lines of `=` or `-` to separate major sections.
- **Portal Start:** Print a line when starting each portal, e.g., `➡️  [PlanetBids] Scraping...`
- **Per-City/Agency:** For multi-city portals, print a line for each city/agency with the number of RFPs scraped or a message if none found.
- **Portal Summary:** At the end of each portal, print a summary line with a check or cross.
- **Errors:** Print a clear error line if a portal fails, e.g., `❌  [Compton] Failed to scrape (site unreachable)`
- **Upload:** Print a summary before and after uploading to Airtable.
- **Final Summary:** Print a concise summary table at the end.

## What **Not** To Print
- Do **not** print every RFP/bid title or details.
- Do **not** print raw HTML, stack traces, or debug info unless in debug mode.
- Do **not** print internal function calls or variable dumps.

## For Developers
- Use the `log_status(site, step, message, level)` function for all log lines.
- Add a `city_summaries` or similar structure in each multi-city scraper to collect per-city results for summary printing.
- Ensure all errors are caught and reported in a user-friendly way.

---

This standard ensures the scraping pipeline is transparent and easy to follow for all users, regardless of technical background.

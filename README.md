# AI-driven autonomous mobile price hunter & cart optimizer

An autonomous, mobile-native AI agent that finds the true lowest price across major Indian e-commerce platforms—then adds the cheapest valid variant to cart—using Google Gemini Vision and Android automation.

---

## Problem

Online shoppers in India struggle to identify the real lowest price across platforms. Prices vary by seller, variant, and hidden “similar products” sections, making manual comparison slow and error-prone.

---

## Solution

A Python agent that searches top marketplaces, opens live product pages on a real Android device, analyzes screenshots with Vision AI, navigates similar/related sections, detects exact matches and cheaper variants, validates stock, and automatically adds the lowest-priced item to cart.

---

## Features

- **Cross-market search:** Scans top 25 listings across 7 Indian marketplaces via Serper API.
- **Vision AI detection:** Uses Gemini Vision to identify product cards and price regions from screenshots.
- **Smart scrolling:** Navigates long pages and “Similar/Related” sections to uncover cheaper exact matches.
- **Variant optimization:** Detects cheaper seller/variant options and switches automatically.
- **Stock validation:** Avoids out-of-stock or unavailable items.
- **Global lowest tracking:** Maintains the cheapest valid price across visited pages.
- **Cart automation:** Clicks Add-to-Cart once the minimum price is confirmed.
- **Cleanup:** Automatically removes temporary screenshots.
- **Android automation:** Controls Chrome via ADB + UIAutomator2 for real-device reliability.

---

## How it works

1. **Search:** Queries Amazon, Flipkart, JioMart, Tata Cliq, Croma, Myntra, and Nykaa using Serper API.
2. **Rank:** Extracts and compares price data from search results.
3. **Open on device:** Launches the best candidates directly on an Android device via ADB.
4. **Read price:** Captures screenshots and reads current product price using Gemini Vision.
5. **Explore variants:** Scrolls through Similar/Related sections and seller/variant widgets.
6. **Match product:** Uses title similarity to confirm exact product matches.
7. **Optimize:** Identifies and switches to lower-priced seller/variant options.
8. **Loop:** Repeats until the minimum valid price is reached.
9. **Validate:** Confirms stock availability and page integrity.
10. **Cart:** Clicks Add-to-Cart automatically.

---

## Tech stack

- **Python**
- **ADB (Android Debug Bridge)**
- **UIAutomator2**
- **Serper Search API**
- **Google Gemini Vision API**
- **Regex-based price extraction**
- **Title/product similarity matching**

---

## Prerequisites

- **Android phone** with USB Debugging enabled
- **Chrome** installed on the device
- **ADB** (Android SDK Platform Tools) installed on your computer
- **Python 3.8+** on your computer

> Verify ADB connection:
```bash
adb devices
```
Must show **exactly one** device as `device`.

---

## Installation

```bash
git clone https://github.com/<your-username>/ai-product-price-finder
cd ai-product-price-finder
python -m venv venv
```

### Activate virtual environment (Windows)
```bash
venv\Scripts\activate
```

### Install dependencies
```bash
pip install -r requirements.txt
```

---

## Configuration

Create a `.env` file (use `.env.example` as a template):

```env
GEMINI_API_KEY=your_google_key
SERPER_API_KEY=your_serper_key
```

- **GEMINI_API_KEY:** Google Gemini API key for Vision analysis.
- **SERPER_API_KEY:** Serper API key for marketplace search.

---

## Usage

```bash
python price_finder.py
```

- **Enter a product name** when prompted (e.g., “Samsung Galaxy M34 5G”).
- The agent will:
  - **Search** listings across supported marketplaces
  - **Open** promising results on your Android device
  - **Analyze** screenshots to detect exact matches and prices
  - **Scroll** intelligently to find cheaper variants/sellers
  - **Validate** stock and page integrity
  - **Add to cart** the cheapest valid option

---

## Architecture

- **Search layer:** Serper API fetches top results per marketplace.
- **Device control:** ADB + UIAutomator2 open URLs, scroll, and interact with Chrome UI.
- **Vision layer:** Gemini Vision processes screenshots to detect product cards, price regions, and stock cues.
- **Matching & pricing:** Title similarity + regex price extraction confirm exact matches and compute the global lowest.
- **Decision loop:** Iteratively explores variants/sellers until the minimum valid price is reached, then carts.

---

## Troubleshooting

- **Multiple devices listed:** Disconnect extras; ensure only one device shows as `device` in `adb devices`.
- **No Chrome on device:** Install/update Chrome and set it as default browser.
- **ADB not found:** Install Android SDK Platform Tools and add them to your system PATH.
- **Blank screenshots:** Ensure the device screen is on and unlocked; disable battery optimizations for Chrome.
- **Rate limits (search/vision):** Add backoff/retry logic or reduce query frequency.

---

## Limitations

- **UI variability:** Marketplace UI changes can affect selectors and detection.
- **Vision accuracy:** Complex layouts or overlapping elements may reduce precision.
- **Network/device state:** Slow connections or background restrictions can interrupt flows.
- **Regional differences:** Prices, availability, and seller options vary by location.

---

## FAQ

- **Does it buy automatically?**  
  It adds the cheapest valid variant to cart; checkout is intentionally left manual.

- **Can it handle coupons or bank offers?**  
  It focuses on base prices and visible seller/variant differences; offer stacking is out of scope.

- **Is desktop supported?**  
  This agent is mobile-native and optimized for Android Chrome via ADB.

- **Can I add more marketplaces?**  
  Yes—extend the search layer and add marketplace-specific parsing/matching rules.

---

## Hackathon

Built for **Droidrun DevSprint 2026**—demonstrating agentic automation on live mobile workflows.

---

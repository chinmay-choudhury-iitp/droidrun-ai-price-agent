# AI-Driven Autonomous Mobile Price Hunter & Cart Optimizer

## Problem  
Online shoppers in India struggle to identify the true lowest price across multiple e-commerce platforms. Prices vary between sellers, variants, and hidden similar product sections, making manual comparison inefficient and unreliable.  

## Solution  
This project implements an autonomous mobile AI agent that searches products across major Indian e-commerce platforms, navigates live mobile product pages on an Android device, detects cheaper variants of the same product, and automatically adds the lowest-priced valid item to the cart.  

## How It Works  
1. Searches products across Amazon, Flipkart, JioMart, Tata Cliq, Croma, Myntra, and Nykaa using Serper API.  
2. Extracts and compares price data from search results.  
3. Opens the best deal directly on a real Android device using ADB.  
4. Reads current product price from mobile Chrome UI.  
5. Scrolls through Similar / Related product sections.  
6. Detects same product using title similarity matching.  
7. Identifies cheaper seller/variant options.  
8. Automatically switches to lower priced variants.  
9. Repeats optimization loop until minimum price is reached.  
10. Validates stock availability and page integrity.  
11. Clicks Add-to-Cart automatically.  

## Tech Stack  
1. Python  
2. ADB (Android Debug Bridge)  
3. UIAutomator2  
4. Serper Search API  
5. Regex-based price extraction  
6. Product similarity matching  

## Outcome  
A mobile-native AI shopping agent capable of autonomously discovering and carting the cheapest available variant of a product across Indian e-commerce platforms using real device interaction.  

## Hackathon  
Built for Droidrun DevSprint 2026 — demonstrating agentic automation on live mobile workflows.

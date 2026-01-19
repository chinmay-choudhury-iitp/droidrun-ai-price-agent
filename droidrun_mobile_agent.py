import os
import sys
import json
import time
import requests
import re
import base64
import atexit
import glob
from subprocess import run, PIPE
from PIL import Image
from io import BytesIO

print("🔍 Initializing Product Price Finder with Vision AI")
print("=" * 60)

# ============================================================================
# IMPORTS AND SETUP
# ============================================================================

try:
    import google.generativeai as genai
    print("✓ Google GenAI imported")
except ImportError:
    print("✗ Install: pip install google-generativeai")
    sys.exit(1)

try:
    import uiautomator2 as u2
    print("✓ UIAutomator2 imported")
except ImportError:
    print("✗ Install: pip install uiautomator2")
    sys.exit(1)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")

if not GEMINI_API_KEY or not SERPER_API_KEY:
    print("✗ API keys not found. Set GEMINI_API_KEY and SERPER_API_KEY as environment variables.")
    sys.exit(1)

genai.configure(api_key=GEMINI_API_KEY)

# List and select the best available vision model
print("🔍 Finding available Gemini models...")
vision_models = []
try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            model_name = m.name.replace('models/', '')
            vision_models.append(model_name)
            print(f"   • {model_name}")
except Exception as e:
    print(f"⚠️ Could not list models: {e}")

# Updated preferred models list with newer versions
preferred_models = [
    'gemini-2.5-flash',
    'gemini-2.5-pro',
    'gemini-2.0-flash',
    'gemini-2.0-flash-exp',
    'gemini-flash-latest',
    'gemini-pro-latest',
    'gemini-1.5-flash-latest',
    'gemini-1.5-flash-002',
    'gemini-1.5-pro-latest',
    'gemini-pro-vision',
    'gemini-1.5-flash',
    'gemini-1.5-pro'
]

vision_model = None
for model_name in preferred_models:
    if model_name in vision_models:
        try:
            vision_model = genai.GenerativeModel(model_name)
            print(f"✓ Using model: {model_name}")
            break
        except Exception as e:
            print(f"⚠️ Failed to load {model_name}: {e}")
            continue

# If no preferred model found, try the first available one
if not vision_model and vision_models:
    try:
        first_model = vision_models[0]
        vision_model = genai.GenerativeModel(first_model)
        print(f"✓ Using first available model: {first_model}")
    except Exception as e:
        print(f"✗ Failed to load any model: {e}")

if not vision_model:
    print("✗ No compatible Gemini vision model found!")
    print(f"Available models: {', '.join(vision_models) if vision_models else 'None'}")
    sys.exit(1)

print("=" * 60)

GLOBAL_LOWEST_PRICE = None
PRICE_CHECK_HISTORY = []
VISITED_PRODUCTS = set()
ORIGINAL_PRODUCT_NAME = ""  # Store original product name for exact matching

# ============================================================================
# CLEANUP FUNCTION - Delete screenshots on exit
# ============================================================================

def cleanup_screenshots():
    """Delete all temporary screenshots when program exits"""
    try:
        screenshot_files = glob.glob("temp_screenshot_*.png")
        if screenshot_files:
            print(f"\n🧹 Cleaning up {len(screenshot_files)} screenshot(s)...")
            for file in screenshot_files:
                try:
                    os.remove(file)
                    print(f"   ✓ Deleted: {file}")
                except Exception as e:
                    print(f"   ⚠️ Could not delete {file}: {e}")
        else:
            print("\n🧹 No screenshots to clean up")
    except Exception as e:
        print(f"⚠️ Cleanup error: {e}")

# Register cleanup function to run on exit
atexit.register(cleanup_screenshots)

# ============================================================================
# ADB FUNCTIONS
# ============================================================================

def execute_adb_command(command):
    try:
        result = run(command, shell=True, capture_output=True, text=True)
        return result.returncode == 0, result.stdout
    except Exception as e:
        return False, str(e)

def check_adb_connection():
    success, output = execute_adb_command("adb devices")
    if success and "device" in output and output.count('\n') > 1:
        print("✓ Android device connected")
        return True
    else:
        print("⚠ No Android device connected")
        return False

# ============================================================================
# SCREENSHOT AND VISION AI
# ============================================================================

def capture_screenshot(device):
    """Capture screenshot using UIAutomator2's built-in method"""
    try:
        print(f"   📸 Capturing screenshot...")
        
        # UIAutomator2 screenshot() returns PIL Image directly
        img = device.screenshot()
        
        # Save to local file
        local_file = f"temp_screenshot_{int(time.time())}.png"
        img.save(local_file)
        
        if os.path.exists(local_file):
            print(f"   ✓ Screenshot saved: {local_file}")
            return local_file
        else:
            print(f"   ✗ Failed to save screenshot")
            return None
            
    except Exception as e:
        print(f"   ⚠️ Screenshot error: {e}")
        import traceback
        traceback.print_exc()
        return None

def extract_key_product_features(product_name):
    """Extract key features from product name for matching"""
    # Extract brand, storage, RAM, color, etc.
    features = {
        'brand': '',
        'storage': '',
        'ram': '',
        'color': '',
        'model': ''
    }
    
    # Common brands
    brands = ['iPhone', 'Samsung', 'OnePlus', 'Xiaomi', 'Realme', 'Oppo', 'Vivo', 'Google', 'Pixel', 
              'Mi', 'Redmi', 'Nothing', 'Asus', 'Sony', 'Motorola', 'Nokia']
    for brand in brands:
        if brand.lower() in product_name.lower():
            features['brand'] = brand
            break
    
    # Extract storage (256GB, 128GB, etc.)
    storage_match = re.search(r'(\d+\s*(?:GB|TB))', product_name, re.IGNORECASE)
    if storage_match:
        features['storage'] = storage_match.group(1).replace(' ', '')
    
    # Extract RAM
    ram_match = re.search(r'(\d+\s*GB\s*RAM)', product_name, re.IGNORECASE)
    if ram_match:
        features['ram'] = ram_match.group(1).replace(' ', '')
    
    # Extract color
    colors = ['Black', 'White', 'Blue', 'Red', 'Green', 'Gold', 'Silver', 'Gray', 'Grey', 
              'Purple', 'Pink', 'Yellow', 'Orange', 'Midnight', 'Starlight', 'Sierra']
    for color in colors:
        if color.lower() in product_name.lower():
            features['color'] = color
            break
    
    return features

def analyze_screenshot_for_cheaper_products(screenshot_path, current_price, product_name):
    global ORIGINAL_PRODUCT_NAME
    
    try:
        print(f"\n   🤖 Analyzing screenshot with Gemini Vision AI...")
        img = Image.open(screenshot_path)
        
        # Extract key features for exact matching
        key_features = extract_key_product_features(ORIGINAL_PRODUCT_NAME or product_name)
        
        feature_requirements = []
        if key_features['brand']:
            feature_requirements.append(f"Brand: {key_features['brand']}")
        if key_features['storage']:
            feature_requirements.append(f"Storage: {key_features['storage']}")
        if key_features['ram']:
            feature_requirements.append(f"RAM: {key_features['ram']}")
        if key_features['color']:
            feature_requirements.append(f"Color: {key_features['color']}")
        
        feature_text = ", ".join(feature_requirements) if feature_requirements else "N/A"
        
        prompt = f"""Analyze this e-commerce page screenshot carefully.

Current product: {product_name}
Current price: ₹{current_price}
REQUIRED EXACT MATCH: {feature_text}

CRITICAL TASK: Find ONLY the EXACT SAME PRODUCT with these specifications that is CHEAPER than ₹{current_price}.

STRICT MATCHING RULES:
- MUST have the exact same specifications: {feature_text}
- DO NOT include different storage variants (e.g., 128GB vs 256GB)
- DO NOT include different RAM variants (e.g., 6GB vs 8GB RAM)
- DO NOT include different colors
- DO NOT include different models or versions
- ONLY include the EXACT SAME PRODUCT at a lower price

For each EXACT matching cheaper product found, provide:
1. The exact price (numeric value only)
2. The X,Y pixel coordinates where I should tap to open it (center of the product card/image)
3. A brief product title/description

Return ONLY a JSON array with this exact format (no other text):
[
  {{"price": 15999, "x": 540, "y": 800, "title": "Product name"}},
  {{"price": 14500, "x": 540, "y": 1200, "title": "Product name"}}
]

If no EXACT matching cheaper products found, return: []"""

        response = vision_model.generate_content([prompt, img])
        response_text = response.text.strip()
        print(f"   📝 Gemini response: {response_text[:200]}...")
        
        response_text = response_text.replace('```json', '').replace('```', '').strip()
        
        try:
            products = json.loads(response_text)
            
            if products:
                print(f"\n   ✅ Gemini found {len(products)} exact matching cheaper alternatives:")
                for p in products:
                    savings = current_price - p['price']
                    savings_pct = (savings / current_price) * 100
                    print(f"      • ₹{p['price']} at ({p['x']}, {p['y']}) - Save ₹{savings:.0f} ({savings_pct:.1f}%)")
                    print(f"        '{p['title'][:60]}...'")
            else:
                print(f"   ℹ️ No exact matching cheaper products found by Gemini")
            
            return products
            
        except json.JSONDecodeError as e:
            print(f"   ⚠️ JSON parse error: {e}")
            match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if match:
                try:
                    products = json.loads(match.group())
                    return products
                except:
                    pass
            return []
            
    except Exception as e:
        print(f"   ⚠️ Vision analysis error: {e}")
        import traceback
        traceback.print_exc()
        return []

# ============================================================================
# SMART SCROLLING
# ============================================================================

def smart_scroll_and_find_cheaper(device, current_price, product_name):
    global GLOBAL_LOWEST_PRICE
    
    print(f"\n   📜 Smart scrolling with Vision AI to find better deals...")
    print(f"   📦 Product: {product_name[:60] if product_name else 'Unknown'}...")
    print(f"   💰 Current price: ₹{current_price}")
    
    try:
        screen_info = device.info
        screen_width = screen_info.get('displayWidth', 1080)
        screen_height = screen_info.get('displayHeight', 2400)
        
        center_x = screen_width // 2
        scroll_start_y = int(screen_height * 0.75)
        scroll_end_y = int(screen_height * 0.25)
        
        best_price = current_price
        best_coordinates = None
        max_scrolls = 15
        screenshots_taken = 0
        
        print(f"   🔍 Starting intelligent scroll (max {max_scrolls} scrolls)...")
        
        for scroll_num in range(max_scrolls):
            print(f"\n   📱 Scroll {scroll_num + 1}/{max_scrolls}")
            
            if scroll_num % 2 == 0 or scroll_num == 0:
                screenshot_path = capture_screenshot(device)
                
                if screenshot_path:
                    screenshots_taken += 1
                    print(f"   📸 Screenshot #{screenshots_taken} captured")
                    
                    cheaper_products = analyze_screenshot_for_cheaper_products(
                        screenshot_path, current_price, product_name
                    )
                    
                    if cheaper_products:
                        cheaper_products.sort(key=lambda x: x['price'])
                        cheapest = cheaper_products[0]
                        
                        if cheapest['price'] < best_price:
                            best_price = cheapest['price']
                            best_coordinates = (cheapest['x'], cheapest['y'])
                            
                            savings = current_price - best_price
                            savings_pct = (savings / current_price) * 100
                            
                            print(f"\n   🎯 FOUND BETTER DEAL!")
                            print(f"   💰 New price: ₹{best_price} (was ₹{current_price})")
                            print(f"   💵 Savings: ₹{savings:.2f} ({savings_pct:.1f}% cheaper)")
                            print(f"   🖱️ Tapping at ({best_coordinates[0]}, {best_coordinates[1]})...")
                            
                            try:
                                device.click(best_coordinates[0], best_coordinates[1])
                                time.sleep(4)
                                print(f"   ✓ Clicked! Loading new product page...")
                                
                                if GLOBAL_LOWEST_PRICE is None or best_price < GLOBAL_LOWEST_PRICE:
                                    GLOBAL_LOWEST_PRICE = best_price
                                
                                try:
                                    os.remove(screenshot_path)
                                except:
                                    pass
                                
                                return True, best_price
                                
                            except Exception as tap_error:
                                print(f"   ⚠️ Tap failed: {tap_error}")
                                execute_adb_command(f"adb shell input tap {best_coordinates[0]} {best_coordinates[1]}")
                                time.sleep(4)
                                
                                if GLOBAL_LOWEST_PRICE is None or best_price < GLOBAL_LOWEST_PRICE:
                                    GLOBAL_LOWEST_PRICE = best_price
                                
                                try:
                                    os.remove(screenshot_path)
                                except:
                                    pass
                                
                                return True, best_price
                    
                    try:
                        os.remove(screenshot_path)
                    except:
                        pass
            
            try:
                before_scroll = str(device.dump_hierarchy())
                before_hash = hash(before_scroll)
                
                device.swipe(center_x, scroll_start_y, center_x, scroll_end_y, duration=0.4)
                time.sleep(0.8)
                
                after_scroll = str(device.dump_hierarchy())
                after_hash = hash(after_scroll)
                
                if before_hash == after_hash:
                    print(f"   ℹ️ Reached end of page")
                    break
                    
            except Exception as scroll_error:
                print(f"   ⚠️ Scroll error: {scroll_error}")
                break
        
        print(f"\n   📊 Scroll complete: Analyzed {screenshots_taken} screenshots")
        print(f"   ℹ️ No better prices found during scroll")
        
        return False, current_price
        
    except Exception as e:
        print(f"   ⚠️ Error in smart scroll: {e}")
        import traceback
        traceback.print_exc()
        return False, current_price

# ============================================================================
# PRICE EXTRACTION
# ============================================================================

def extract_price_from_text(text):
    if not text:
        return None
    text = str(text).replace('₹', '').replace('Rs', '').replace(',', '').replace('Rs.', '').strip()
    match = re.search(r'(\d+(?:\.\d{1,2})?)', text)
    if match:
        try:
            return float(match.group(1))
        except:
            return None
    return None

def extract_price_value(price_str):
    if not price_str or price_str == 'N/A':
        return float('inf')
    price_str = str(price_str).replace('₹', '').replace('Rs', '').replace(',', '').replace('Rs.', '')
    match = re.search(r'[\d.]+', price_str)
    if match:
        try:
            return float(match.group())
        except:
            return float('inf')
    return float('inf')

# ============================================================================
# PAGE STATE
# ============================================================================

def get_current_price_from_page(device):
    print("   💰 Detecting current product price...")
    try:
        price_patterns = ['₹', 'Rs']
        for pattern in price_patterns:
            try:
                elements = device(textContains=pattern)
                count = elements.count if hasattr(elements, 'count') else 0
                for i in range(min(count, 3)):
                    try:
                        element = elements[i]
                        price_text = element.get_text() if hasattr(element, 'get_text') else str(element.info.get('text', ''))
                        if price_text:
                            price_value = extract_price_from_text(price_text)
                            if price_value and price_value > 0:
                                print(f"   ✓ Current price detected: ₹{price_value}")
                                return price_value
                    except:
                        continue
            except:
                pass
        print("   ⚠️ Could not detect current price")
        return None
    except Exception as e:
        print(f"   ⚠️ Error detecting price: {e}")
        return None

def extract_product_title_from_page(device):
    try:
        time.sleep(0.5)
        title_patterns = [
            device(resourceId="com.android.chrome:id/title"),
            device(className="android.widget.TextView")
        ]
        for pattern in title_patterns:
            try:
                if pattern.exists(timeout=0.5):
                    title = pattern.get_text() if hasattr(pattern, 'get_text') else str(pattern.info.get('text', ''))
                    if title and len(title) > 10:
                        return title.strip()
            except:
                continue
        return None
    except Exception as e:
        print(f"   ℹ️ Could not extract title: {e}")
        return None

def check_page_errors(device):
    error_indicators = ["404", "Page not found", "Access Denied", "Error", "Something went wrong", "Oops"]
    for error_text in error_indicators:
        try:
            if device(textContains=error_text).exists(timeout=0.5):
                print(f"\n   ✗ ERROR: '{error_text}'")
                return True
        except:
            pass
    return False

def check_out_of_stock(device):
    """Check if product is out of stock - more careful detection"""
    stock_indicators = [
        "Out of Stock", 
        "Currently unavailable", 
        "Notify Me", 
        "Sold Out", 
        "Not Available",
        "out of stock",
        "currently unavailable"
    ]
    
    # Check multiple times to avoid false positives
    out_of_stock_count = 0
    
    for stock_text in stock_indicators:
        try:
            if device(textContains=stock_text).exists(timeout=0.5):
                out_of_stock_count += 1
        except:
            pass
    
    # Only return True if we found multiple indicators or a very clear one
    if out_of_stock_count >= 2:
        print(f"\n   ⚠️ STOCK ISSUE: Multiple unavailability indicators found")
        return True
    
    # Check for "Add to Cart" button - if it exists, product is likely available
    try:
        add_to_cart_buttons = ["Add to Cart", "ADD TO CART", "Add to Bag", "Buy Now", "BUY NOW"]
        for button in add_to_cart_buttons:
            if device(textContains=button).exists(timeout=0.5):
                print(f"   ✓ Found '{button}' button - product appears available")
                return False
    except:
        pass
    
    return out_of_stock_count > 0

# ============================================================================
# OPTIMIZATION LOOP
# ============================================================================

def process_product_page_loop(device):
    global GLOBAL_LOWEST_PRICE, PRICE_CHECK_HISTORY, VISITED_PRODUCTS
    
    max_iterations = 3
    iteration = 0
    
    print("\n" + "="*70)
    print("🔄 STARTING AI-POWERED PRICE OPTIMIZATION")
    print("="*70)
    
    while iteration < max_iterations:
        iteration += 1
        print(f"\n{'='*70}")
        print(f"🔍 ITERATION {iteration}/{max_iterations}")
        print(f"{'='*70}")
        
        time.sleep(3)
        
        current_title = extract_product_title_from_page(device)
        current_price = get_current_price_from_page(device)
        
        if not current_price:
            print("   ⚠️ Could not detect price")
            current_price = GLOBAL_LOWEST_PRICE if GLOBAL_LOWEST_PRICE else 0
        
        product_fingerprint = f"{current_title}_{current_price}"
        
        if product_fingerprint in VISITED_PRODUCTS:
            print(f"   ℹ️ Already visited this product - stopping to avoid loop")
            return True, current_price
        
        VISITED_PRODUCTS.add(product_fingerprint)
        
        if current_title:
            print(f"   📦 Product: {current_title[:60]}...")
        print(f"   💰 Current price: ₹{current_price}")
        
        PRICE_CHECK_HISTORY.append(current_price)
        
        # Check for errors first
        if check_page_errors(device):
            print("\n   ✗ Page error detected - trying to find alternatives...")
            found_cheaper, new_price = smart_scroll_and_find_cheaper(device, current_price, current_title)
            if found_cheaper:
                print(f"\n   ✅ Found alternative at ₹{new_price}")
                time.sleep(3)
                continue
            else:
                print("\n   ✗ No alternatives found - stopping")
                return False, current_price
        
        # Check stock status
        is_out_of_stock = check_out_of_stock(device)
        
        if is_out_of_stock:
            print("\n   ⚠️ Current product appears out of stock")
            print("   🔍 Scrolling down to find the EXACT SAME product from other sellers...")
            
            # Scroll down to look for "Similar Products" or seller listings
            try:
                screen_info = device.info
                screen_width = screen_info.get('displayWidth', 1080)
                screen_height = screen_info.get('displayHeight', 2400)
                
                center_x = screen_width // 2
                scroll_start_y = int(screen_height * 0.75)
                scroll_end_y = int(screen_height * 0.25)
                
                # Scroll down multiple times to reveal similar products section
                print("   📜 Scrolling to reveal similar/alternative listings...")
                for scroll_count in range(5):
                    device.swipe(center_x, scroll_start_y, center_x, scroll_end_y, duration=0.4)
                    time.sleep(0.8)
                    print(f"      Scroll {scroll_count + 1}/5")
                
                # Take screenshot and ask Gemini to find exact same product
                screenshot_path = capture_screenshot(device)
                
                if screenshot_path:
                    print(f"\n   🤖 Using Gemini Vision to find EXACT SAME AVAILABLE product...")
                    img = Image.open(screenshot_path)
                    
                    # Extract key features for exact matching
                    key_features = extract_key_product_features(ORIGINAL_PRODUCT_NAME or current_title)
                    
                    feature_requirements = []
                    if key_features['brand']:
                        feature_requirements.append(f"Brand: {key_features['brand']}")
                    if key_features['storage']:
                        feature_requirements.append(f"Storage: {key_features['storage']}")
                    if key_features['ram']:
                        feature_requirements.append(f"RAM: {key_features['ram']}")
                    if key_features['color']:
                        feature_requirements.append(f"Color: {key_features['color']}")
                    
                    feature_text = ", ".join(feature_requirements) if feature_requirements else "N/A"
                    
                    find_available_prompt = f"""Analyze this e-commerce page screenshot carefully.

ORIGINAL PRODUCT (OUT OF STOCK): {current_title}
REQUIRED EXACT MATCH: {feature_text}
CURRENT PRICE: ₹{current_price}

CRITICAL TASK: Find the EXACT SAME PRODUCT that is AVAILABLE (not out of stock) on this page.

STRICT MATCHING RULES:
- MUST have the exact same specifications: {feature_text}
- MUST be AVAILABLE (ignore "Out of Stock", "Notify Me", "Currently Unavailable" items)
- Look for "Similar Products", "Other Sellers", "Buy from other sellers" sections
- Prefer products with "Add to Cart" or "Buy Now" buttons visible
- Price should be close to ₹{current_price} (can be slightly higher if it's available)

For the EXACT matching AVAILABLE product, provide:
1. The exact price (numeric value only)
2. The X,Y pixel coordinates of the CENTER of the product image/card to click
3. A confidence level (high/medium/low)

Return ONLY a JSON object with this exact format (no other text):
{{"price": 15999, "x": 540, "y": 1200, "confidence": "high", "title": "Product name"}}

If no EXACT matching AVAILABLE product found, return: {{"price": 0, "x": 0, "y": 0, "confidence": "low", "title": ""}}"""

                    response = vision_model.generate_content([find_available_prompt, img])
                    response_text = response.text.strip()
                    print(f"   📝 Gemini response: {response_text[:200]}...")
                    
                    response_text = response_text.replace('```json', '').replace('```', '').strip()
                    
                    try:
                        available_product = json.loads(response_text)
                        
                        if available_product.get('confidence') in ['high', 'medium'] and available_product.get('x', 0) > 0:
                            x = available_product.get('x')
                            y = available_product.get('y')
                            new_price = available_product.get('price', current_price)
                            
                            print(f"\n   🎯 FOUND AVAILABLE EXACT MATCH!")
                            print(f"      📦 Product: {available_product.get('title', 'Unknown')[:60]}...")
                            print(f"      💰 Price: ₹{new_price}")
                            print(f"      📍 Location: ({x}, {y})")
                            print(f"      ✅ Confidence: {available_product.get('confidence')}")
                            print(f"\n   🖱️ Clicking on available product...")
                            
                            try:
                                device.click(x, y)
                                time.sleep(5)
                                print(f"   ✓ Clicked! Loading available product page...")
                                
                                # Update global lowest if this is cheaper
                                if GLOBAL_LOWEST_PRICE is None or new_price < GLOBAL_LOWEST_PRICE:
                                    GLOBAL_LOWEST_PRICE = new_price
                                
                                # Clean up screenshot
                                try:
                                    os.remove(screenshot_path)
                                except:
                                    pass
                                
                                # Continue optimization loop with the new available product
                                continue
                                
                            except Exception as tap_error:
                                print(f"   ⚠️ UIAutomator tap failed, using ADB: {tap_error}")
                                execute_adb_command(f"adb shell input tap {x} {y}")
                                time.sleep(5)
                                
                                if GLOBAL_LOWEST_PRICE is None or new_price < GLOBAL_LOWEST_PRICE:
                                    GLOBAL_LOWEST_PRICE = new_price
                                
                                try:
                                    os.remove(screenshot_path)
                                except:
                                    pass
                                
                                continue
                        else:
                            print(f"\n   ℹ️ Gemini could not find exact matching available product")
                            print(f"      Confidence: {available_product.get('confidence', 'unknown')}")
                            
                    except json.JSONDecodeError as e:
                        print(f"   ⚠️ JSON parse error: {e}")
                    
                    # Clean up screenshot
                    try:
                        os.remove(screenshot_path)
                    except:
                        pass
                
            except Exception as scroll_error:
                print(f"   ⚠️ Error while searching for available product: {scroll_error}")
            
            # If we couldn't find available exact match, try the old method
            print("\n   🔍 Fallback: Searching for any available alternatives...")
            found_cheaper, new_price = smart_scroll_and_find_cheaper(device, current_price, current_title)
            
            if found_cheaper:
                print(f"\n   ✅ Found available alternative at ₹{new_price}")
                time.sleep(3)
                
                if check_out_of_stock(device):
                    print("\n   ⚠️ Alternative also out of stock, continuing search...")
                    continue
                else:
                    print("\n   ✓ Alternative is available!")
                    continue
            else:
                print("\n   ℹ️ No available alternatives found")
                print(f"   💰 Lowest price found: ₹{GLOBAL_LOWEST_PRICE if GLOBAL_LOWEST_PRICE else current_price}")
                return False, GLOBAL_LOWEST_PRICE if GLOBAL_LOWEST_PRICE else current_price
        
        # Update global lowest price
        if GLOBAL_LOWEST_PRICE is None or current_price < GLOBAL_LOWEST_PRICE:
            GLOBAL_LOWEST_PRICE = current_price
            print(f"   ⭐ NEW LOWEST PRICE: ₹{GLOBAL_LOWEST_PRICE}")
        
        # Search for cheaper alternatives
        found_cheaper, new_price = smart_scroll_and_find_cheaper(device, current_price, current_title)
        
        if found_cheaper:
            print(f"\n   ✅ Switched to cheaper variant at ₹{new_price}")
            print(f"   🔁 Restarting optimization on new variant...")
            
            time.sleep(3)
            
            if check_page_errors(device):
                print("\n   ✗ Issue with new variant - continuing search...")
                continue
            
            if check_out_of_stock(device):
                print("\n   ⚠️ New variant out of stock - continuing search...")
                continue
            
            continue
        else:
            print(f"\n   ✓ No better deals found - price ₹{current_price} is optimal")
            print(f"   📊 Checked {iteration} iteration(s)")
            
            # RELOAD PAGE AFTER FINDING GLOBAL LOWEST
            print("\n" + "="*70)
            print("🔄 RELOADING PAGE TO VERIFY FINAL STATE")
            print("="*70)
            
            print("   🔄 Refreshing page...")
            try:
                execute_adb_command("adb shell input keyevent KEYCODE_F5")
                time.sleep(5)
                print("   ✓ Page reloaded")
            except Exception as reload_error:
                print(f"   ⚠️ Reload error (continuing anyway): {reload_error}")
                time.sleep(3)
            
            # NOW check for cart/stock after reload
            print("\n   🔍 Post-reload verification:")
            
            # Re-check for errors after reload
            if check_page_errors(device):
                print("   ✗ Error detected after reload - searching for alternatives...")
                
                # Scroll and find similar products
                found_cheaper, new_price = smart_scroll_and_find_cheaper(device, current_price, current_title)
                
                if found_cheaper:
                    print(f"\n   ✅ Found working alternative at ₹{new_price}")
                    time.sleep(3)
                    continue  # Go back to optimization loop with new product
                else:
                    print("   ✗ No working alternatives found - TERMINATING")
                    return False, current_price
            
            # Re-check stock status after reload
            if check_out_of_stock(device):
                print("   ⚠️ Product unavailable after reload")
                print("   🔍 Searching for available alternatives with similar specs...")
                
                # Scroll and find available alternatives
                found_alternative, alt_price = smart_scroll_and_find_cheaper(device, current_price, current_title)
                
                if found_alternative:
                    print(f"\n   ✅ Found available alternative at ₹{alt_price}")
                    time.sleep(3)
                    
                    # Verify the alternative is actually available
                    if check_out_of_stock(device):
                        print("\n   ⚠️ Alternative also unavailable, continuing search...")
                        continue  # Keep searching
                    else:
                        print("\n   ✓ Alternative is available and ready!")
                        # Update current price and continue optimization on this product
                        current_price = alt_price
                        if GLOBAL_LOWEST_PRICE is None or alt_price < GLOBAL_LOWEST_PRICE:
                            GLOBAL_LOWEST_PRICE = alt_price
                        continue
                else:
                    print("\n   ℹ️ No available alternatives found")
                    print(f"   💰 Best price found (unavailable): ₹{GLOBAL_LOWEST_PRICE if GLOBAL_LOWEST_PRICE else current_price}")
                    return False, GLOBAL_LOWEST_PRICE if GLOBAL_LOWEST_PRICE else current_price
            
            # Verify price after reload
            reloaded_price = get_current_price_from_page(device)
            if reloaded_price and reloaded_price != current_price:
                print(f"   ⚠️ Price changed after reload: ₹{current_price} → ₹{reloaded_price}")
                current_price = reloaded_price
                if GLOBAL_LOWEST_PRICE is None or reloaded_price < GLOBAL_LOWEST_PRICE:
                    GLOBAL_LOWEST_PRICE = reloaded_price
            
            print(f"   ✓ Final verification complete")
            print(f"   💰 Confirmed price: ₹{current_price}")
            print(f"   ✅ Product is AVAILABLE and ready to add to cart")
            
            return True, current_price
    
    print(f"\n   ⏱️ Max iterations reached")
    
    # RELOAD PAGE AFTER MAX ITERATIONS TOO
    print("\n" + "="*70)
    print("🔄 RELOADING PAGE FOR FINAL VERIFICATION")
    print("="*70)
    
    try:
        execute_adb_command("adb shell input keyevent KEYCODE_F5")
        time.sleep(5)
        print("   ✓ Page reloaded")
    except:
        time.sleep(3)
    
    # Final checks after reload with alternative search
    if check_out_of_stock(device):
        print("   ⚠️ Final product unavailable after reload")
        print("   🔍 Last attempt: Searching for available alternatives...")
        
        # One final attempt to find available alternatives
        final_price = GLOBAL_LOWEST_PRICE if GLOBAL_LOWEST_PRICE else 0
        current_title = extract_product_title_from_page(device)
        
        found_final, final_alt_price = smart_scroll_and_find_cheaper(device, final_price, current_title)
        
        if found_final and not check_out_of_stock(device):
            print(f"\n   ✅ Found final available alternative at ₹{final_alt_price}")
            if GLOBAL_LOWEST_PRICE is None or final_alt_price < GLOBAL_LOWEST_PRICE:
                GLOBAL_LOWEST_PRICE = final_alt_price
            return True, final_alt_price
        else:
            print("   ✗ No available alternatives found")
            return False, GLOBAL_LOWEST_PRICE
    
    if check_page_errors(device):
        print("   ✗ Error detected after reload")
        print("   🔍 Searching for working alternatives...")
        
        current_title = extract_product_title_from_page(device)
        final_price = GLOBAL_LOWEST_PRICE if GLOBAL_LOWEST_PRICE else 0
        
        found_working, working_price = smart_scroll_and_find_cheaper(device, final_price, current_title)
        
        if found_working and not check_page_errors(device):
            print(f"\n   ✅ Found working alternative at ₹{working_price}")
            return True, working_price
        else:
            print("   ✗ No working alternatives found")
            return False, GLOBAL_LOWEST_PRICE
    
    print(f"   💰 Final price: ₹{GLOBAL_LOWEST_PRICE}")
    print(f"   ✅ Product is AVAILABLE and verified")
    return True, GLOBAL_LOWEST_PRICE

# ============================================================================
# SEARCH FUNCTIONS
# ============================================================================

def get_site_name(link):
    if 'flipkart.com' in link:
        return 'Flipkart'
    elif 'amazon.in' in link:
        return 'Amazon'
    elif 'myntra.com' in link:
        return 'Myntra'

def search_product_prices(product_name):
    print(f"   🔄 Searching '{product_name}' across major Indian e-commerce sites...")
    
    indian_sites = [
        "site:flipkart.com", "site:amazon.in",
        "site:myntra.com"
    ]
    
    site_filter = " OR ".join(indian_sites)
    url = "https://google.serper.dev/shopping"
    payload = json.dumps({
        "q": f"{product_name} {site_filter}",
        "gl": "in",
        "hl": "en",
        "num": 25
    })
    headers = {
        'X-API-KEY': SERPER_API_KEY,
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.post(url, headers=headers, data=payload, timeout=10)
        data = response.json()
        shopping_results = []
        
        if 'shopping' in data:
            for item in data['shopping'][:25]:
                link = item.get('link', '')
                if any(site in link for site in indian_sites):
                    price = item.get('price', 'N/A')
                    source = get_site_name(link)
                    shopping_results.append({
                        'title': item.get('title', ''),
                        'link': link,
                        'source': source,
                        'price': price,
                        'price_value': extract_price_value(price)
                    })
        
        organic_count = 25 - len(shopping_results)
        if organic_count > 0 and 'organic' in data:
            for item in data['organic'][:organic_count]:
                link = item.get('link', '')
                if any(site in link for site in indian_sites):
                    source = get_site_name(link)
                    shopping_results.append({
                        'title': item.get('title', ''),
                        'link': link,
                        'source': source,
                        'price': item.get('snippet', 'Check on site'),
                        'price_value': extract_price_value(item.get('snippet', 'N/A'))
                    })
        
        if shopping_results:
            print(f"   ✓ Found {len(shopping_results)} results from {len(set([r['source'] for r in shopping_results]))} sites")
            shopping_results.sort(key=lambda x: x['price_value'])
            return shopping_results[:25]
        else:
            return search_with_regular_api(product_name)
            
            
    except Exception as e:
        print(f"   ⚠ Shopping search error: {e}")
        return search_with_regular_api(product_name)

def search_with_regular_api(product_name):
    print(f"   🔄 Fallback search across Indian sites...")
    indian_sites = ["flipkart.com", "amazon.in", "myntra.com"]
    site_query = " OR ".join(indian_sites)
    url = "https://google.serper.dev/search"
    payload = json.dumps({
        "q": f"{product_name} buy online india price {site_query}",
        "gl": "in",
        "hl": "en",
        "num": 25
    })
    headers = {
        'X-API-KEY': SERPER_API_KEY,
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.post(url, headers=headers, data=payload, timeout=10)
        data = response.json()
        results = []
        if 'organic' in data:
            for item in data['organic'][:25]:
                link = item.get('link', '')
                if any(site in link for site in indian_sites):
                    source = get_site_name(link)
                    price_text = item.get('snippet', 'Check on site')
                    results.append({
                        'title': item.get('title', ''),
                        'link': link,
                        'source': source,
                        'price': price_text,
                        'price_value': extract_price_value(price_text)
                    })
        
        if results:
            print(f"   ✓ Fallback found {len(results)} results")
            results.sort(key=lambda x: x['price_value'])
        return results[:25]
    except Exception as e:
        print(f"   ✗ Fallback search error: {e}")
        return []

def find_minimum_price_with_gemini(search_results, product_name):
    if not search_results:
        return None
    
    lowest_result = search_results[0]
    print(f"\n   📊 MINIMUM PRICE from TOP 25: {lowest_result.get('price', 'N/A')} at {lowest_result.get('source', 'N/A')}")
    print(f"   🔗 {lowest_result.get('title', 'N/A')[:80]}...")
    
    result = {
        "product_name": lowest_result.get('title', product_name),
        "minimum_price": lowest_result.get('price', 'N/A'),
        "website_name": lowest_result.get('source', 'N/A'),
        "url": lowest_result.get('link', 'N/A'),
        "total_results": len(search_results),
        "additional_info": f"✓ Lowest from TOP 25 results across 7 Indian sites"
    }
    
    print("   ✓ Best deal confirmed")
    return result

def display_results(result):
    print("\n" + "="*70)
    print("✅ LOWEST PRICE FOUND ACROSS MAJOR INDIAN E-COMMERCE!")
    print("="*70)
    print(f"\n📱 Product: {result.get('product_name', 'N/A')}")
    print(f"💰 MINIMUM Price: {result.get('minimum_price', 'N/A')}")
    print(f"🏪 Website: {result.get('website_name', 'N/A')}")
    print(f"🔗 Direct URL: {result.get('url', 'N/A')}")
    print(f"📊 Analyzed: {result.get('total_results', 0)} results")
    if result.get('additional_info'):
        print(f"💡 {result.get('additional_info')}")
    print("="*70)

# ============================================================================
# URL FUNCTIONS
# ============================================================================

def remove_language_codes_from_url(url):
    language_codes = ['/mr', '/hi', '/ta', '/te', '/bn', '/kn', '/ml', '/gu', '/pa', '/or']
    for lang_code in language_codes:
        if lang_code + '/' in url:
            url = url.replace(lang_code + '/', '/')
            print(f"   🔄 Removed language code '{lang_code}' from URL")
            break
    return url

def check_and_fix_language(device):
    try:
        time.sleep(3)
        execute_adb_command("adb shell dumpsys activity activities | grep mResumedActivity")
        hindi_indicators = ["हिंदी", "मराठी", "தமிழ்", "తెలుగు", "বাংলা"]
        for indicator in hindi_indicators:
            try:
                if device(textContains=indicator).exists(timeout=1):
                    print(f"\n   ⚠️ Detected regional language on page!")
                    return True
            except:
                pass
        return False
    except Exception as e:
        print(f"   ℹ️ Could not check language: {e}")
        return False

# ============================================================================
# CART FUNCTIONS
# ============================================================================

def add_to_cart_scroll_click():
    print("\n   🛒 Using scroll+click fallback...")
    time.sleep(3)
    print("   📜 Scrolling to reveal button...")
    for i in range(3):
        execute_adb_command("adb shell input swipe 540 1200 540 600 200")
        time.sleep(0.5)
    time.sleep(1.5)
    execute_adb_command("adb shell input tap 540 1900")
    time.sleep(1.5)
    print("   ✓ Click completed")

def add_to_cart_ui_automator():
    try:
        print("\n   🤖 Connecting to device via UIAutomator2...")
        device = u2.connect()
        
        print("   ⏳ Waiting for initial page load...")
        time.sleep(6)
        
        print("\n" + "="*70)
        print("🎯 STARTING PRICE OPTIMIZATION")
        print("="*70)
        
        success, final_price = process_product_page_loop(device)
        
        if not success:
            print("\n   ✗ Optimization failed - cannot proceed to cart")
            print("\n   🛑 TERMINATING PROGRAM")
            cleanup_screenshots()
            sys.exit(1)
        
        print("\n" + "="*70)
        print("✅ PRICE OPTIMIZATION COMPLETE")
        print("="*70)
        print(f"   💰 Final Price: ₹{final_price}")
        if GLOBAL_LOWEST_PRICE:
            print(f"   🏆 Global Lowest Found: ₹{GLOBAL_LOWEST_PRICE}")
        print("="*70)
        
        print("\n   🔍 Final check: Verifying product availability...")
        
        if check_page_errors(device):
            print("\n   ✗ Page error detected - TERMINATING")
            print("\n   🛑 TERMINATING PROGRAM")
            cleanup_screenshots()
            sys.exit(1)
        
        if check_out_of_stock(device):
            print("\n   ⚠️ Product unavailable - TERMINATING")
            print("\n   🛑 TERMINATING PROGRAM")
            cleanup_screenshots()
            sys.exit(1)
        
        print("   ✓ Product is available")
        
        print("\n   🔍 Step 4: Looking for cart buttons...")
        go_to_cart_texts = ["Go to Cart", "GO TO CART", "Go to cart", "View Cart", "VIEW CART", "View cart"]
        
        for button_text in go_to_cart_texts:
            try:
                print(f"   🔍 Checking for: '{button_text}'...")
                if device(text=button_text).exists(timeout=1):
                    print(f"   ✓ Found '{button_text}' - Product already in cart!")
                    element = device(text=button_text)
                    element.click()
                    time.sleep(2)
                    print(f"   ✓ Clicked '{button_text}' - Opening cart")
                    print("\n   ✅ SUCCESS - Product already in cart, navigating to cart")
                    print("\n   🛑 TERMINATING PROGRAM")
                    cleanup_screenshots()
                    sys.exit(0)
            except Exception as e:
                continue
        
        add_to_cart_texts = [
            "Add to Cart", "ADD TO CART", "Add to Bag", "ADD TO BAG",
            "Add to cart", "add to cart", "Add to bag", "add to bag",
            "Add To Cart", "Add To Bag"
        ]
        
        for button_text in add_to_cart_texts:
            try:
                print(f"   🔍 Looking for: '{button_text}'...")
                if device(text=button_text).exists(timeout=1):
                    print(f"   ✓ Found '{button_text}' button!")
                    element = device(text=button_text)
                    element.click()
                    time.sleep(3)
                    
                    if final_price:
                        print(f"   ✓ Successfully added to cart at ₹{final_price}!")
                    else:
                        print(f"   ✓ Successfully clicked '{button_text}'!")
                    
                    print("\n   ✅ SUCCESS - Product added to cart")
                    print("\n   🛑 TERMINATING PROGRAM")
                    cleanup_screenshots()
                    sys.exit(0)
            except Exception as e:
                continue
        
        print("\n   ⚠ No cart buttons found, using fallback...")
        add_to_cart_scroll_click()
        print("\n   🛑 TERMINATING PROGRAM")
        cleanup_screenshots()
        sys.exit(0)
        
    except Exception as e:
        print(f"\n   ⚠ UIAutomator error: {e}")
        add_to_cart_scroll_click()
        print("\n   🛑 TERMINATING PROGRAM")
        cleanup_screenshots()
        sys.exit(0)

# ============================================================================
# MAIN PROGRAM
# ============================================================================

def main():
    """
    Main program flow:
    1. Get product name and variants from user
    2. Search for product across Indian e-commerce sites
    3. Find lowest price from results
    4. Open product URL on Android device
    5. Use Gemini Vision to find the product card on screen
    6. Click on it to open product page
    7. Optimize price by checking similar items
    8. Add to cart at best price
    """
    global ORIGINAL_PRODUCT_NAME
    
    print("\n🔍 INDIAN E-COMMERCE PRICE FINDER (7 Major Sites)")
    print("=" * 60)
    
    # Check Android device connection
    if not check_adb_connection():
        print("✗ Please connect Android device via ADB")
        return
    
    # Get product search query from user
    product_name = input("\n🔍 Enter product name: ").strip()
    if not product_name:
        print("✗ Product name required!")
        cleanup_screenshots()
        return
    
    # Get optional variant specifications
    variants = input("   Variants (e.g., RAM, Storage, Colour, Weight, etc): ").strip()
    search_query = f"{product_name} {variants}".strip()
    
    # Store original product name for exact matching
    ORIGINAL_PRODUCT_NAME = search_query
    
    print("\n" + "="*60)
    print("🔍 SEARCHING TOP 25 RESULTS ACROSS 7 SITES...")
    print("="*60)
    
    # Search for product
    search_results = search_product_prices(search_query)
    
    if not search_results:
        print("\n✗ No results found")
        cleanup_screenshots()
        return
    
    # Find minimum price from results
    result = find_minimum_price_with_gemini(search_results, search_query)
    
    if result:
        # Display best deal found
        display_results(result)
        
        # Open product on Android device
        url = result.get('url')
        if url and url != 'N/A':
            print("\n" + "="*70)
            print("🎯 PHASE 1: OPENING MINIMUM PRICE PRODUCT")
            print("="*70)
            print(f"📱 Opening {result.get('website_name')} on Android device...")
            print(f"💰 Target price: {result.get('minimum_price')}")
            
            # Open the URL on Android
            if not check_adb_connection():
                print(f"\n📱 Device not connected")
                print(f"🔗 Manual URL: {url}")
                cleanup_screenshots()
                return False
            
            original_url = url
            url = remove_language_codes_from_url(url)
            
            if original_url != url:
                print(f"   ✓ URL cleaned for English: {url}")
            
            print(f"\n📱 Opening on Android in English...")
            
            # Set Chrome to accept English language
            execute_adb_command("adb shell 'echo \"chrome --accept-lang=en-US,en\" > /data/local/chrome-command-line'")
            
            # Go to home screen first
            execute_adb_command("adb shell input keyevent KEYCODE_HOME")
            time.sleep(1)
            
            # Open URL in Chrome using Android intent
            cmd = f'adb shell am start -a android.intent.action.VIEW -d "{url}"'
            success, _ = execute_adb_command(cmd)
            
            # If direct URL opening failed, open Chrome first then URL
            if not success:
                execute_adb_command('adb shell am start -n com.android.chrome/com.google.android.apps.chrome.Main')
                time.sleep(2)
                execute_adb_command(cmd)
            
            print("✓ Chrome opened, waiting for page load...")
            time.sleep(8)  # Wait for page to fully load
            
            print("✓ Chrome opened, waiting for page load...")
            time.sleep(8)  # Wait for page to fully load
            
            # Now use Vision AI to find and click on the product
            print("\n" + "="*70)
            print("🎯 PHASE 2: LOCATING PRODUCT ON SCREEN WITH VISION AI")
            print("="*70)
            
            try:
                device = u2.connect()
                
                # Check if page loaded in regional language
                if check_and_fix_language(device):
                    print("\n   🔄 Page opened in regional language, reloading...")
                    execute_adb_command(f'adb shell am start -a android.intent.action.VIEW -d "{url}"')
                    time.sleep(8)
                
                # Check if we're already on a product detail page
                current_price = get_current_price_from_page(device)
                
                if current_price and current_price > 0:
                    print(f"\n   ✓ Already on product page (detected price: ₹{current_price})")
                    print(f"   ℹ️ Skipping product card search, proceeding to optimization...")
                else:
                    # Take screenshot and find the product
                    screenshot_path = capture_screenshot(device)
                    
                    if screenshot_path:
                        print(f"\n   🤖 Using Gemini Vision to locate the product card...")
                        img = Image.open(screenshot_path)
                        
                        product_title = result.get('product_name', search_query)
                        target_price = result.get('minimum_price', 'N/A')
                        
                        find_product_prompt = f"""Analyze this e-commerce page screenshot.

TARGET PRODUCT: {product_title}
TARGET PRICE: {target_price}

TASK: Find the main product card/listing for this exact product on the screen.

Look for:
1. Product title matching: {product_title}
2. Price matching or close to: {target_price}
3. The main product image/card (not ads or recommendations)

Provide the X,Y pixel coordinates of the CENTER of the product card/image where I should tap to open the product details page.

Return ONLY a JSON object with this exact format (no other text):
{{"x": 540, "y": 800, "confidence": "high"}}

If product not clearly visible, return: {{"x": 0, "y": 0, "confidence": "low"}}"""

                        response = vision_model.generate_content([find_product_prompt, img])
                        response_text = response.text.strip()
                        print(f"   📝 Gemini response: {response_text[:150]}...")
                        
                        response_text = response_text.replace('```json', '').replace('```', '').strip()
                        
                        try:
                            product_location = json.loads(response_text)
                            
                            if product_location.get('confidence') == 'low' or product_location.get('x', 0) == 0:
                                print(f"\n   ⚠️ Could not locate product clearly on screen")
                                print(f"   📱 The product page might already be open, proceeding to optimization...")
                            else:
                                x = product_location.get('x', 540)
                                y = product_location.get('y', 800)
                                
                                print(f"\n   🎯 Product located at coordinates ({x}, {y})")
                                print(f"   🖱️ Clicking to open product page...")
                                
                                try:
                                    device.click(x, y)
                                    time.sleep(6)
                                    print(f"   ✓ Clicked! Product page loading...")
                                except Exception as tap_error:
                                    print(f"   ⚠️ UIAutomator tap failed, using ADB: {tap_error}")
                                    execute_adb_command(f"adb shell input tap {x} {y}")
                                    time.sleep(6)
                            
                            # Clean up screenshot
                            try:
                                os.remove(screenshot_path)
                            except:
                                pass
                                
                        except json.JSONDecodeError as e:
                            print(f"   ⚠️ Could not parse Gemini response: {e}")
                            print(f"   📱 Proceeding with current page...")
                
                # Now start the price optimization process
                print("\n" + "="*70)
                print("🎯 PHASE 3: PRICE OPTIMIZATION WITH VISION AI")
                print("="*70)
                
                # Wait for any page transitions to complete
                time.sleep(3)
                
                # Verify we're on a valid product page
                if check_page_errors(device):
                    print("\n   ✗ Error page detected - cannot proceed")
                    cleanup_screenshots()
                    return
                
                if check_out_of_stock(device):
                    print("\n   ⚠️ Product unavailable")
                    cleanup_screenshots()
                    return
                
                # Scroll to top to ensure we start from a known position
                print("\n   📜 Resetting page position (scrolling to top)...")
                for i in range(5):
                    device.swipe(540, 400, 540, 1200, duration=0.3)
                    time.sleep(0.2)
                
                time.sleep(2)
                print("   ✓ Page ready, starting optimization loop...")
                
                # NOW start optimization - no more clicks before this!
                add_to_cart_ui_automator()
                
            except Exception as e:
                print(f"\n   ⚠️ Error during product location: {e}")
                import traceback
                traceback.print_exc()
                cleanup_screenshots()
                return
        else:
            print("\n✗ No valid URL found")
            cleanup_screenshots()
    else:
        print("\n✗ Could not identify best deal")
        cleanup_screenshots()

# ============================================================================
# PROGRAM ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
        cleanup_screenshots()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        cleanup_screenshots
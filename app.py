import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import json
import time
from urllib.parse import urljoin, urlparse
import re

# Configure page
st.set_page_config(
    page_title="Shopify Product Scraper",
    page_icon="🛍️",
    layout="wide"
)

# Custom CSS for better styling
st.markdown("""
<style>
.main-header {
    font-size: 2.5rem;
    font-weight: bold;
    text-align: center;
    margin-bottom: 2rem;
    color: #1f77b4;
}
.stAlert {
    margin-top: 1rem;
}
</style>
""", unsafe_allow_html=True)

def is_shopify_store(url):
    """Check if a URL is a Shopify store"""
    try:
        response = requests.get(url, timeout=10)
        return 'shopify' in response.text.lower() or 'cdn.shopify.com' in response.text
    except:
        return False

def get_products_json(store_url, limit=250):
    """Get products from Shopify's products.json endpoint with pagination"""
    try:
        # Clean and format the URL
        if not store_url.startswith(('http://', 'https://')):
            store_url = 'https://' + store_url
        
        base_url = store_url.rstrip('/')
        all_products = []
        page = 1
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        while True:
            # Try pagination with limit and page parameters
            products_url = f"{base_url}/products.json?limit={limit}&page={page}"
            
            response = requests.get(products_url, headers=headers, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            products = data.get('products', [])
            
            if not products:  # No more products
                break
                
            all_products.extend(products)
            
            # If we got fewer products than the limit, we're done
            if len(products) < limit:
                break
                
            page += 1
            time.sleep(0.5)  # Be respectful with pagination
            
            # Safety check to prevent infinite loops
            if page > 50:  # Max 50 pages
                st.warning("Reached maximum pagination limit (50 pages)")
                break
        
        return all_products
    
    except requests.exceptions.RequestException as e:
        st.error(f"Network error: {str(e)}")
        return None
    except json.JSONDecodeError:
        st.error("Invalid JSON response - store might not be Shopify or has restricted access")
        return None
    except Exception as e:
        st.error(f"Error fetching products: {str(e)}")
        return None

def get_collections_and_products(store_url):
    """Get products by scraping through collections"""
    try:
        if not store_url.startswith(('http://', 'https://')):
            store_url = 'https://' + store_url
        
        base_url = store_url.rstrip('/')
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # First, try to get collections
        collections_url = f"{base_url}/collections.json"
        response = requests.get(collections_url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            collections_data = response.json()
            collections = collections_data.get('collections', [])
            
            all_products = []
            collection_products = {}
            
            for collection in collections:
                collection_handle = collection.get('handle')
                if collection_handle:
                    # Get products from each collection
                    collection_url = f"{base_url}/collections/{collection_handle}/products.json"
                    
                    try:
                        coll_response = requests.get(collection_url, headers=headers, timeout=10)
                        if coll_response.status_code == 200:
                            coll_data = coll_response.json()
                            products = coll_data.get('products', [])
                            collection_products[collection.get('title', collection_handle)] = len(products)
                            
                            # Add collection info to products
                            for product in products:
                                product['collection'] = collection.get('title', collection_handle)
                            
                            all_products.extend(products)
                            time.sleep(0.3)  # Be respectful
                    except:
                        continue
            
            # Remove duplicates based on product ID
            seen_ids = set()
            unique_products = []
            for product in all_products:
                product_id = product.get('id')
                if product_id not in seen_ids:
                    seen_ids.add(product_id)
                    unique_products.append(product)
            
            return unique_products, collection_products
        
        return [], {}
    
    except Exception as e:
        st.error(f"Error fetching collections: {str(e)}")
        return [], {}

def clean_text_for_dataframe(text):
    """Clean text to prevent Unicode encoding errors in dataframes"""
    if not text:
        return ""
    
    # Convert to string if not already
    text = str(text)
    
    # Remove or replace problematic Unicode characters
    text = text.encode('utf-8', errors='ignore').decode('utf-8')
    
    # Remove control characters
    text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\r\t')
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Limit length to prevent huge cells
    if len(text) > 2000:
        text = text[:2000] + "..."
    
    return text

def get_detailed_product_info(store_url, product_handle, delay=1.0):
    """Get detailed product information by scraping the individual product page"""
    try:
        if not store_url.startswith(('http://', 'https://')):
            store_url = 'https://' + store_url
        
        base_url = store_url.rstrip('/')
        product_url = f"{base_url}/products/{product_handle}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        time.sleep(delay)  # Respect rate limiting
        response = requests.get(product_url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            return {'Debug_Error': f'HTTP {response.status_code} for {product_url}'}
        
        soup = BeautifulSoup(response.content, 'html.parser')
        detailed_info = {'Debug_URL': clean_text_for_dataframe(product_url)}  # Always include URL for debugging
        
        # Debug: Check if we can find any product-tabs at all
        product_tabs_container = soup.select_one('.product-tabs')
        if product_tabs_container:
            detailed_info['Debug_Found_Container'] = 'Yes - product-tabs found'
            
            # Look for individual product-tab elements
            product_tabs = soup.select('.product-tabs .product-tab')
            detailed_info['Debug_Tab_Count'] = str(len(product_tabs))
            
            if product_tabs:
                for i, tab in enumerate(product_tabs):
                    # Get tab title - try multiple selectors
                    title_elem = tab.select_one('.product-tab__title')
                    if not title_elem:
                        title_elem = tab.select_one('button[data-collapsible-trigger]')
                    if not title_elem:
                        title_elem = tab.select_one('button')
                    
                    # Get content - try multiple selectors
                    content_elem = tab.select_one('.product-tab__content .product-tab__inner')
                    if not content_elem:
                        content_elem = tab.select_one('.product-tab__inner')
                    if not content_elem:
                        content_elem = tab.select_one('.product-tab__content')
                    
                    if title_elem:
                        title = clean_text_for_dataframe(title_elem.get_text(strip=True))
                        detailed_info[f'Debug_Tab_{i}_Title'] = title
                        
                        if content_elem:
                            content = clean_text_for_dataframe(content_elem.get_text(strip=True))
                            detailed_info[f'Debug_Tab_{i}_Content_Length'] = str(len(content))
                            
                            if title and content and len(content) > 5:
                                # Clean title for column name
                                clean_title = re.sub(r'[^a-zA-Z0-9\s]', '', title).strip().replace(' ', '_')
                                detailed_info[f'Tab_{clean_title}'] = content
                        else:
                            detailed_info[f'Debug_Tab_{i}_Content'] = 'No content found'
                    else:
                        detailed_info[f'Debug_Tab_{i}'] = 'No title found'
        else:
            detailed_info['Debug_Found_Container'] = 'No - product-tabs not found'
            
            # Try alternative selectors
            alt_selectors = ['.tabs', '.product-info-tabs', '.accordion', '[data-tabs]']
            for selector in alt_selectors:
                if soup.select_one(selector):
                    detailed_info[f'Debug_Found_{selector.replace(".", "").replace("[", "").replace("]", "")}'] = 'Yes'
        
        # Try a broader approach - look for any collapsible content
        collapsible_triggers = soup.select('[data-collapsible-trigger]')
        detailed_info['Debug_Collapsible_Count'] = str(len(collapsible_triggers))
        
        for i, trigger in enumerate(collapsible_triggers):
            title = clean_text_for_dataframe(trigger.get_text(strip=True))
            
            # Find corresponding content using aria-controls
            aria_controls = trigger.get('aria-controls')
            if aria_controls:
                content_elem = soup.find(id=aria_controls)
                if content_elem:
                    content = clean_text_for_dataframe(content_elem.get_text(strip=True))
                    
                    if title and content and len(content) > 10:
                        clean_title = re.sub(r'[^a-zA-Z0-9\s]', '', title).strip().replace(' ', '_')
                        detailed_info[f'Collapsible_{clean_title}'] = content
        
        # Look for any elements with common tab-related classes
        tab_elements = soup.select('.tab, .accordion-item, .collapsible, .product-tab')
        detailed_info['Debug_Total_Tab_Elements'] = str(len(tab_elements))
        
        # Try to extract any visible text from common content areas
        content_areas = soup.select('.rte, .product-description, .tab-content, .tab-pane')
        for i, area in enumerate(content_areas):
            content = clean_text_for_dataframe(area.get_text(strip=True))
            if content and len(content) > 50:  # Only substantial content
                detailed_info[f'Content_Area_{i+1}'] = content[:500] + '...' if len(content) > 500 else content
        
        # Add some page structure info for debugging
        page_title = soup.find('title')
        detailed_info['Debug_Page_Title'] = clean_text_for_dataframe(page_title.get_text(strip=True) if page_title else 'No title')
        detailed_info['Debug_Has_Product_Form'] = 'Yes' if soup.select_one('form[action*="cart"]') else 'No'
        
        # Clean all values to ensure they're safe for dataframe
        cleaned_info = {}
        for key, value in detailed_info.items():
            cleaned_key = clean_text_for_dataframe(str(key))
            cleaned_value = clean_text_for_dataframe(str(value))
            if cleaned_key and cleaned_value:
                cleaned_info[cleaned_key] = cleaned_value
        
        return cleaned_info
    
    except Exception as e:
        return {'Debug_Exception': f'Error: {clean_text_for_dataframe(str(e))}'}

def parse_product_data(products, fetch_detailed=False, store_url='', delay=1.0):
    """Parse product data into a structured format with optional detailed scraping"""
    parsed_products = []
    
    for i, product in enumerate(products):
        # Get all variants for this product
        variants = product.get('variants', [{}])
        
        # Get all images
        images = product.get('images', [])
        first_image = images[0].get('src', '') if images else ''
        
        # Create list of all image URLs (excluding the main image to avoid duplication)
        all_image_urls = [img.get('src', '') for img in images if img.get('src')]
        additional_images = all_image_urls[1:] if len(all_image_urls) > 1 else []  # Skip first image
        
        # Get variant images (images specific to variants) with better handling
        variant_images = []
        variant_image_details = []
        
        for variant in variants:
            variant_image_id = variant.get('image_id')
            if variant_image_id:
                # Find the image that matches this variant
                variant_img = next((img for img in images if img.get('id') == variant_image_id), None)
                if variant_img and variant_img.get('src'):
                    variant_info = {
                        'variant_title': variant.get('title', 'Default'),
                        'variant_sku': variant.get('sku', ''),
                        'variant_price': variant.get('price', ''),
                        'image_url': variant_img.get('src', ''),
                        'image_alt': variant_img.get('alt', ''),
                        'image_position': variant_img.get('position', 0)
                    }
                    variant_image_details.append(variant_info)
                    
                    # Also add to simple list for display
                    if variant_img.get('src') not in variant_images:
                        variant_images.append(variant_img.get('src'))
        
        # Create formatted variant info for display
        variant_display = []
        for var_info in variant_image_details:
            display_text = f"{var_info['variant_title']}: {var_info['image_url']}"
            if var_info['variant_sku']:
                display_text += f" (SKU: {var_info['variant_sku']})"
            variant_display.append(display_text)
        
        # Get collection info - check multiple possible sources
        collection_name = ''
        if 'collection' in product:
            collection_name = product['collection']
        elif 'collections' in product and product['collections']:
            # If there are multiple collections, take the first one
            if isinstance(product['collections'], list):
                collection_name = product['collections'][0] if product['collections'] else ''
            else:
                collection_name = str(product['collections'])
        elif 'product_type' in product and product['product_type']:
            # Fallback to product type if no collection found
            collection_name = f"Type: {product['product_type']}"
        
        # Use first variant for main product data
        first_variant = variants[0] if variants else {}
        
        # Create main product record
        parsed_product = {
            # Shopify CSV compatible fields
            'Handle': product.get('handle', ''),
            'Title': product.get('title', ''),
            'Body (HTML)': product.get('body_html', ''),
            'Vendor': product.get('vendor', ''),
            'Product Category': collection_name,  # Map collection to Product Category
            'Type': product.get('product_type', ''),
            'Tags': ', '.join(product.get('tags', [])),
            'Published': 'TRUE' if product.get('published_at') else 'FALSE',
            
            # Variant information (first variant)
            'Variant SKU': first_variant.get('sku', ''),
            'Variant Grams': first_variant.get('grams', 0),
            'Variant Inventory Qty': first_variant.get('inventory_quantity', 0),
            'Variant Price': first_variant.get('price', '0'),
            'Variant Compare At Price': first_variant.get('compare_at_price', ''),
            'Variant Requires Shipping': 'TRUE' if first_variant.get('requires_shipping', True) else 'FALSE',
            'Variant Taxable': 'TRUE' if first_variant.get('taxable', True) else 'FALSE',
            'Variant Weight Unit': first_variant.get('weight_unit', 'kg'),
            
            # Image information
            'Image Src': first_image,
            'Image Position': 1,
            
            # Additional custom fields for analysis
            'Collection': collection_name,  # Keep this for filtering
            'Available': first_variant.get('available', False),
            'Created At': product.get('created_at', ''),
            'Updated At': product.get('updated_at', ''),
            'Main Image': first_image,
            'Additional Images': ' | '.join(additional_images) if additional_images else '',
            'Variant Images': ' | '.join(variant_images) if variant_images else '',
            'Variant Details': ' | '.join(variant_display) if variant_display else '',
            'Total Images': len(all_image_urls),
            'Variants Count': len(variants),
            'All Variants': json.dumps([{
                'title': v.get('title', ''),
                'sku': v.get('sku', ''),
                'price': v.get('price', ''),
                'available': v.get('available', False),
                'inventory_quantity': v.get('inventory_quantity', 0)
            } for v in variants]) if len(variants) > 1 else '',
            'Description': clean_text_for_dataframe(BeautifulSoup(product.get('body_html', ''), 'html.parser').get_text().strip()) if product.get('body_html') else ''
        }
        
        # Add variant option information if available
        if first_variant.get('option1'):
            parsed_product['Option1 Name'] = 'Title'  # Default option name
            parsed_product['Option1 Value'] = first_variant.get('option1', '')
        if first_variant.get('option2'):
            parsed_product['Option2 Name'] = 'Option2'
            parsed_product['Option2 Value'] = first_variant.get('option2', '')
        if first_variant.get('option3'):
            parsed_product['Option3 Name'] = 'Option3'
            parsed_product['Option3 Value'] = first_variant.get('option3', '')
        
        # Fetch detailed information if requested
        if fetch_detailed and product.get('handle') and store_url:
            if (i + 1) % 5 == 0:  # Progress update every 5 products
                st.write(f"Fetching detailed info for product {i + 1}/{len(products)}...")
            
            detailed_info = get_detailed_product_info(store_url, product.get('handle'), delay)
            
            # Add detailed information to the product data with proper text cleaning
            for key, value in detailed_info.items():
                clean_key = clean_text_for_dataframe(str(key))
                clean_value = clean_text_for_dataframe(str(value))
                if clean_key and clean_value:
                    parsed_product[f'Detail_{clean_key}'] = clean_value
        
        parsed_products.append(parsed_product)
    
    return parsed_products

def main():
    # Header
    st.markdown('<h1 class="main-header">🛍️ Shopify Product Scraper</h1>', unsafe_allow_html=True)
    st.markdown("Extract product data from Shopify stores using their products.json endpoint")
    
    # Sidebar for settings
    with st.sidebar:
        st.header("⚙️ Settings")
        
        # Detailed scraping option
        st.subheader("📄 Detailed Scraping")
        fetch_detailed = st.checkbox(
            "Fetch detailed product information",
            help="Scrape individual product pages for tabbed content, specifications, etc. (slower)",
            value=False
        )
        
        if fetch_detailed:
            st.warning("⚠️ This will be significantly slower as it visits each product page individually")
            detailed_delay = st.slider(
                "Delay between detailed requests (seconds)", 
                min_value=1.0, 
                max_value=10.0, 
                value=2.0, 
                step=0.5,
                help="Higher delay is more respectful but slower"
            )
        else:
            detailed_delay = 1.0
        
        # Rate limiting
        delay_between_requests = st.slider(
            "Delay between requests (seconds)", 
            min_value=0.5, 
            max_value=5.0, 
            value=1.0, 
            step=0.5,
            help="Add delay to be respectful to the server"
        )
        
        # Export options
        st.header("📊 Export Options")
        export_format = st.selectbox("Export Format", ["CSV", "JSON", "Excel"])
    
    # Main input section
    col1, col2 = st.columns([3, 1])
    
    with col1:
        store_url = st.text_input(
            "Enter Shopify Store URL:",
            placeholder="e.g., https://example.myshopify.com or example.com",
            help="Enter the main URL of a Shopify store"
        )
    
    with col2:
        st.write("")  # Add some spacing
        st.write("")  # Add some spacing
        scrape_button = st.button("🔍 Scrape Products", type="primary")
    
    # Scraping method selection
    st.subheader("🔧 Scraping Method")
    scraping_method = st.radio(
        "Choose scraping approach:",
        ["Standard JSON API", "Paginated JSON API", "Collections-based Scraping", "All Methods Combined"],
        help="Different methods to extract more comprehensive product data"
    )

    # Information section
    with st.expander("ℹ️ How it works", expanded=False):
        st.markdown("""
        **This tool offers multiple scraping approaches:**
        
        **1. Standard JSON API** - Uses `/products.json` (fastest, but may miss products)
        **2. Paginated JSON API** - Goes through multiple pages of products
        **3. Collections-based** - Scrapes products from each collection separately
        **4. All Methods Combined** - Uses all approaches for maximum coverage
        
        **Data extracted includes:**
        - Product titles, descriptions, and handles
        - Pricing and inventory information
        - Product images and variants
        - Tags, vendor information, and more
        - Collection information (when available)
        - **Optional: Detailed tabbed content** (specifications, care instructions, etc.)
        
        **Detailed Scraping (when enabled):**
        - Visits individual product pages to extract tabbed content
        - Gets specifications, ingredients, care instructions
        - Extracts accordion content and additional product details
        - Significantly slower but provides comprehensive data
        
        **Note:** Different methods may return different amounts of data. Some stores restrict access to certain endpoints.
        """)
    
    # Scraping logic
    if scrape_button and store_url:
        all_products = []
        collection_info = {}
        
        with st.spinner("Scraping products... Please wait"):
            # Validate if it's a Shopify store
            with st.status("Validating Shopify store...", expanded=True) as status:
                if not is_shopify_store(store_url):
                    st.warning("⚠️ This doesn't appear to be a Shopify store or the store is not accessible.")
                status.update(label="Shopify store validated ✅", state="complete")
            
            # Execute scraping based on selected method
            if scraping_method == "Standard JSON API":
                with st.status("Fetching products via standard API...", expanded=True) as status:
                    products = get_products_json(store_url, limit=50)  # Standard limit
                    if products:
                        all_products = products
                    status.update(label=f"Standard API: {len(all_products)} products ✅", state="complete")
                    
            elif scraping_method == "Paginated JSON API":
                with st.status("Fetching products via paginated API...", expanded=True) as status:
                    products = get_products_json(store_url, limit=250)  # Higher limit with pagination
                    if products:
                        all_products = products
                    status.update(label=f"Paginated API: {len(all_products)} products ✅", state="complete")
                    
            elif scraping_method == "Collections-based Scraping":
                with st.status("Fetching products via collections...", expanded=True) as status:
                    products, collections = get_collections_and_products(store_url)
                    if products:
                        all_products = products
                        collection_info = collections
                    status.update(label=f"Collections method: {len(all_products)} products from {len(collection_info)} collections ✅", state="complete")
                    
            elif scraping_method == "All Methods Combined":
                # Method 1: Standard JSON
                with st.status("Method 1: Standard JSON API...", expanded=True) as status:
                    products1 = get_products_json(store_url, limit=50)
                    if products1:
                        all_products.extend(products1)
                    status.update(label=f"Standard API: {len(products1) if products1 else 0} products ✅", state="complete")
                
                # Method 2: Paginated JSON
                with st.status("Method 2: Paginated JSON API...", expanded=True) as status:
                    products2 = get_products_json(store_url, limit=250)
                    if products2:
                        # Add any new products not already found
                        existing_ids = {p.get('id') for p in all_products}
                        new_products = [p for p in products2 if p.get('id') not in existing_ids]
                        all_products.extend(new_products)
                    status.update(label=f"Paginated API: {len(products2) if products2 else 0} products ✅", state="complete")
                
                # Method 3: Collections
                with st.status("Method 3: Collections-based scraping...", expanded=True) as status:
                    products3, collections = get_collections_and_products(store_url)
                    if products3:
                        # Add any new products not already found
                        existing_ids = {p.get('id') for p in all_products}
                        new_products = [p for p in products3 if p.get('id') not in existing_ids]
                        all_products.extend(new_products)
                        collection_info = collections
                    status.update(label=f"Collections: {len(products3) if products3 else 0} products from {len(collection_info)} collections ✅", state="complete")
            
            if not all_products:
                st.warning("No products found. The store might be empty or have restricted access.")
                st.stop()
        
        # Parse and display data
        with st.status("Processing product data...", expanded=True) as status:
            parsed_products = parse_product_data(all_products, fetch_detailed, store_url, detailed_delay)
            df = pd.DataFrame(parsed_products)
            status.update(label="Data processing complete ✅", state="complete")
        
        # Display results
        st.success(f"✅ Successfully scraped {len(parsed_products)} products!")
        
        # Show collection information if available
        if collection_info:
            st.info(f"📂 Found products across {len(collection_info)} collections:")
            cols = st.columns(min(4, len(collection_info)))
            for i, (collection_name, count) in enumerate(collection_info.items()):
                with cols[i % len(cols)]:
                    st.metric(collection_name, f"{count} products")
        
        # Metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Products", len(parsed_products))
        with col2:
            available_products = sum(1 for p in parsed_products if p['Available'])
            st.metric("Available Products", available_products)
        with col3:
            unique_vendors = len(set(p['Vendor'] for p in parsed_products if p['Vendor']))
            st.metric("Unique Vendors", unique_vendors)
        with col4:
            prices = [float(p['Price']) for p in parsed_products if p['Price'] and str(p['Price']).replace('.', '').isdigit()]
            avg_price = sum(prices) / len(prices) if prices else 0
            st.metric("Average Price", f"${avg_price:.2f}")
        
        # Data table
        st.subheader("📋 Product Data")
        
        # Filters
        col1, col2 = st.columns(2)
        with col1:
            vendor_filter = st.multiselect(
                "Filter by Vendor:",
                options=sorted(list(set(p['Vendor'] for p in parsed_products if p['Vendor']))),
                default=[]
            )
        with col2:
            product_type_filter = st.multiselect(
                "Filter by Product Type:",
                options=sorted(list(set(p['Product Type'] for p in parsed_products if p['Product Type']))),
                default=[]
            )
        
        # Apply filters
        filtered_df = df.copy()
        if vendor_filter:
            filtered_df = filtered_df[filtered_df['Vendor'].isin(vendor_filter)]
        if product_type_filter:
            filtered_df = filtered_df[filtered_df['Product Type'].isin(product_type_filter)]
        
        # Display filtered data with improved column settings
        st.dataframe(
            filtered_df, 
            use_container_width=True,
            column_config={
                "Body (HTML)": st.column_config.TextColumn(
                    "Description (HTML)",
                    help="Full product description in HTML format",
                    max_chars=None,
                    width="large"
                ),
                "Description": st.column_config.TextColumn(
                    "Description (Text)",
                    help="Product description as plain text",
                    max_chars=None,
                    width="large"
                ),
                "Additional Images": st.column_config.TextColumn(
                    "Additional Images", 
                    help="Additional product image URLs (excluding main image)",
                    width="medium"
                ),
                "Image Src": st.column_config.ImageColumn(
                    "Main Image",
                    help="Primary product image"
                ),
                "Main Image": st.column_config.ImageColumn(
                    "Main Image Preview",
                    help="Primary product image preview"
                ),
                "Variant Images": st.column_config.TextColumn(
                    "Variant Images",
                    help="Images specific to product variants",
                    width="medium"
                ),
                "Variant Details": st.column_config.TextColumn(
                    "Variant Details", 
                    help="Variant names with their corresponding image URLs",
                    width="large"
                ),
                "All Variants": st.column_config.TextColumn(
                    "All Variants",
                    help="JSON data of all product variants",
                    width="medium"
                )
            }
        )
        
        # Image gallery section
        if len(filtered_df) > 0:
            st.subheader("🖼️ Product Image Gallery")
            
            # Select product for image viewing
            product_titles = filtered_df['Title'].tolist()
            selected_product = st.selectbox(
                "Select a product to view all images:",
                options=product_titles,
                help="Choose a product to see all its images"
            )
            
            if selected_product:
                product_row = filtered_df[filtered_df['Title'] == selected_product].iloc[0]
                main_image = product_row.get('Main Image', '') or product_row.get('Image Src', '')
                additional_images = product_row.get('Additional Images', '')
                variant_images = product_row.get('Variant Images', '')
                variant_details = product_row.get('Variant Details', '')
                
                # Display main image
                if main_image:
                    st.write("**Main Product Image:**")
                    try:
                        st.image(main_image, caption="Main Image", width=300)
                    except:
                        st.text(f"❌ Failed to load main image: {main_image}")
                
                # Display additional images
                if additional_images:
                    st.write("**Additional Product Images:**")
                    additional_urls = [url.strip() for url in additional_images.split('|') if url.strip()]
                    
                    # Display images in columns
                    cols_per_row = 3
                    for i in range(0, len(additional_urls), cols_per_row):
                        cols = st.columns(cols_per_row)
                        for j, url in enumerate(additional_urls[i:i+cols_per_row]):
                            with cols[j]:
                                try:
                                    st.image(url, caption=f"Additional Image {i+j+1}", use_container_width=True)
                                except:
                                    st.text(f"❌ Failed to load: {url[:50]}...")
                
                # Display variant images
                if variant_images:
                    st.write("**Variant-Specific Images:**")
                    variant_urls = [url.strip() for url in variant_images.split('|') if url.strip()]
                    
                    cols_per_row = 3
                    for i in range(0, len(variant_urls), cols_per_row):
                        cols = st.columns(cols_per_row)
                        for j, url in enumerate(variant_urls[i:i+cols_per_row]):
                            with cols[j]:
                                try:
                                    st.image(url, caption=f"Variant Image {i+j+1}", use_container_width=True)
                                except:
                                    st.text(f"❌ Failed to load: {url[:50]}...")
                
                # Display variant details
                if variant_details:
                    st.write("**Variant Details:**")
                    variant_detail_list = [detail.strip() for detail in variant_details.split('|') if detail.strip()]
                    for detail in variant_detail_list:
                        st.write(f"• {detail}")
                
                if not any([main_image, additional_images, variant_images]):
                    st.info("No images found for this product.")
        
        # Download section
        st.subheader("💾 Download Data")
        
        if export_format == "CSV":
            csv_data = filtered_df.to_csv(index=False)
            st.download_button(
                label="📄 Download CSV",
                data=csv_data,
                file_name=f"shopify_products_{int(time.time())}.csv",
                mime="text/csv"
            )
        elif export_format == "JSON":
            json_data = filtered_df.to_json(orient='records', indent=2)
            st.download_button(
                label="📄 Download JSON",
                data=json_data,
                file_name=f"shopify_products_{int(time.time())}.json",
                mime="application/json"
            )
        elif export_format == "Excel":
            # For Excel, we'll use CSV format as it's more universally supported
            csv_data = filtered_df.to_csv(index=False)
            st.download_button(
                label="📄 Download Excel (CSV format)",
                data=csv_data,
                file_name=f"shopify_products_{int(time.time())}.csv",
                mime="text/csv"
            )
    
    # Footer
    st.markdown("---")
    st.markdown(
        "**⚠️ Disclaimer:** Please respect the terms of service of the websites you scrape. "
        "This tool is for educational and research purposes. Always ensure you have permission "
        "to scrape data from websites."
    )

if __name__ == "__main__":
    main()

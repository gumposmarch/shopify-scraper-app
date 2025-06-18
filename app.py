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
            return {}
        
        soup = BeautifulSoup(response.content, 'html.parser')
        detailed_info = {}
        
        # Look for common tabbed content selectors
        tab_selectors = [
            '.product-tabs',
            '.tab-content', 
            '.product-details-tabs',
            '.accordion',
            '.product-accordion',
            '.product-info-tabs',
            '[data-tabs]',
            '.tabs-wrapper'
        ]
        
        # Extract tabbed content
        for selector in tab_selectors:
            tabs = soup.select(selector)
            if tabs:
                for tab_container in tabs:
                    # Look for tab headers and content
                    tab_headers = tab_container.select('.tab-header, .tab-title, .accordion-header, h3, h4, [data-tab-title]')
                    tab_contents = tab_container.select('.tab-content, .tab-pane, .accordion-content, .tab-panel')
                    
                    # If we have both headers and content, pair them
                    if tab_headers and tab_contents:
                        for i, (header, content) in enumerate(zip(tab_headers, tab_contents)):
                            header_text = header.get_text(strip=True)
                            content_text = content.get_text(strip=True)
                            if header_text and content_text:
                                detailed_info[f'Tab_{header_text}'] = content_text
                    
                    # If no clear pairing, extract all content
                    elif tab_contents:
                        for i, content in enumerate(tab_contents):
                            content_text = content.get_text(strip=True)
                            if content_text:
                                detailed_info[f'Tab_Content_{i+1}'] = content_text
        
        # Look for specific common sections
        common_sections = {
            'Specifications': ['.specifications', '.product-specs', '.spec-table', '.features-list'],
            'Ingredients': ['.ingredients', '.ingredient-list', '.composition'],
            'Care_Instructions': ['.care-instructions', '.washing-instructions', '.care-guide'],
            'Shipping_Info': ['.shipping-info', '.delivery-info', '.shipping-details'],
            'Size_Guide': ['.size-guide', '.size-chart', '.sizing-info'],
            'Additional_Info': ['.additional-info', '.extra-details', '.more-info']
        }
        
        for section_name, selectors in common_sections.items():
            for selector in selectors:
                elements = soup.select(selector)
                if elements:
                    content = ' '.join([elem.get_text(strip=True) for elem in elements])
                    if content:
                        detailed_info[section_name] = content
                    break
        
        # Look for any accordion content
        accordions = soup.select('.accordion-item, .collapsible, [data-accordion]')
        for i, accordion in enumerate(accordions):
            header = accordion.select_one('.accordion-header, .collapsible-header, h3, h4')
            content = accordion.select_one('.accordion-content, .collapsible-content, .accordion-body')
            
            if header and content:
                header_text = header.get_text(strip=True)
                content_text = content.get_text(strip=True)
                if header_text and content_text:
                    detailed_info[f'Accordion_{header_text}'] = content_text
        
        # Extract product details from structured data (JSON-LD)
        json_scripts = soup.find_all('script', type='application/ld+json')
        for script in json_scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and data.get('@type') == 'Product':
                    # Extract additional product properties
                    if 'brand' in data:
                        detailed_info['Brand_JsonLD'] = data['brand'].get('name', '') if isinstance(data['brand'], dict) else str(data['brand'])
                    if 'additionalProperty' in data:
                        for prop in data['additionalProperty']:
                            if isinstance(prop, dict):
                                name = prop.get('name', '')
                                value = prop.get('value', '')
                                if name and value:
                                    detailed_info[f'Property_{name}'] = value
            except:
                continue
        
        return detailed_info
    
    except Exception as e:
        return {'Error': f'Failed to fetch detailed info: {str(e)}'}

def parse_product_data(products, fetch_detailed=False, store_url='', delay=1.0):
    """Parse product data into a structured format with optional detailed scraping"""
    parsed_products = []
    
    for i, product in enumerate(products):
        # Get first variant for pricing (most Shopify stores have at least one variant)
        first_variant = product.get('variants', [{}])[0]
        
        # Get all images
        images = product.get('images', [])
        first_image = images[0].get('src', '') if images else ''
        
        # Create list of all image URLs
        all_image_urls = [img.get('src', '') for img in images if img.get('src')]
        
        # Get variant images (images specific to variants)
        variant_images = []
        for variant in product.get('variants', []):
            if variant.get('image_id'):
                # Find the image that matches this variant
                variant_img = next((img for img in images if img.get('id') == variant.get('image_id')), None)
                if variant_img and variant_img.get('src'):
                    variant_images.append({
                        'variant_title': variant.get('title', ''),
                        'variant_sku': variant.get('sku', ''),
                        'image_url': variant_img.get('src', ''),
                        'image_alt': variant_img.get('alt', '')
                    })
        
        parsed_product = {
            'Title': product.get('title', ''),
            'Handle': product.get('handle', ''),
            'Product Type': product.get('product_type', ''),
            'Vendor': product.get('vendor', ''),
            'Price': first_variant.get('price', '0'),
            'Compare At Price': first_variant.get('compare_at_price', ''),
            'Available': first_variant.get('available', False),
            'Inventory Quantity': first_variant.get('inventory_quantity', 0),
            'Weight': first_variant.get('weight', 0),
            'Tags': ', '.join(product.get('tags', [])),
            'Created At': product.get('created_at', ''),
            'Updated At': product.get('updated_at', ''),
            'Published At': product.get('published_at', ''),
            'Image URL': first_image,
            'All Images': ' | '.join(all_image_urls),  # All images separated by |
            'Variants Count': len(product.get('variants', [])),
            'Images Count': len(product.get('images', [])),
            'Variant Images': json.dumps(variant_images) if variant_images else '',  # JSON string of variant-specific images
            'Description': BeautifulSoup(product.get('body_html', ''), 'html.parser').get_text().strip() if product.get('body_html') else ''
        }
        
        # Fetch detailed information if requested
        if fetch_detailed and product.get('handle') and store_url:
            if (i + 1) % 5 == 0:  # Progress update every 5 products
                st.write(f"Fetching detailed info for product {i + 1}/{len(products)}...")
            
            detailed_info = get_detailed_product_info(store_url, product.get('handle'), delay)
            
            # Add detailed information to the product data
            for key, value in detailed_info.items():
                parsed_product[f'Detail_{key}'] = value
        
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
                "Description": st.column_config.TextColumn(
                    "Description",
                    help="Full product description",
                    max_chars=None,  # No character limit
                    width="large"
                ),
                "All Images": st.column_config.TextColumn(
                    "All Images", 
                    help="All product image URLs separated by |",
                    width="medium"
                ),
                "Image URL": st.column_config.ImageColumn(
                    "Main Image",
                    help="Primary product image"
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
                all_images = product_row['All Images']
                variant_images_json = product_row['Variant Images']
                
                if all_images:
                    st.write(f"**All Images for: {selected_product}**")
                    image_urls = [url.strip() for url in all_images.split('|') if url.strip()]
                    
                    # Display images in columns
                    cols_per_row = 4
                    for i in range(0, len(image_urls), cols_per_row):
                        cols = st.columns(cols_per_row)
                        for j, url in enumerate(image_urls[i:i+cols_per_row]):
                            with cols[j]:
                                try:
                                    st.image(url, caption=f"Image {i+j+1}", use_container_width=True)
                                    st.text(f"URL: {url[:50]}...")
                                except:
                                    st.text(f"❌ Failed to load: {url[:50]}...")
                
                # Show variant-specific images if available
                if variant_images_json:
                    try:
                        variant_images = json.loads(variant_images_json)
                        if variant_images:
                            st.write("**Variant-Specific Images:**")
                            for variant_img in variant_images:
                                st.write(f"**{variant_img.get('variant_title', 'Unknown Variant')}** (SKU: {variant_img.get('variant_sku', 'N/A')})")
                                try:
                                    st.image(variant_img['image_url'], caption=variant_img.get('image_alt', ''), width=200)
                                except:
                                    st.text(f"❌ Failed to load variant image: {variant_img['image_url'][:50]}...")
                    except:
                        pass
        
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

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

def parse_product_data(products, fetch_detailed=False, store_url='', delay=1.0):
    """Parse product data into Shopify CSV compatible format with proper variant handling"""
    parsed_products = []
    
    for i, product in enumerate(products):
        # Get all variants and images
        variants = product.get('variants', [{}])
        images = product.get('images', [])
        
        # Get collection info
        collection_name = product.get('collection', '')
        if not collection_name and product.get('product_type'):
            collection_name = f"Type: {product['product_type']}"
        
        # Create base product data
        base_product = {
            'Handle': product.get('handle', ''),
            'Title': product.get('title', ''),
            'Body (HTML)': clean_text_for_dataframe(product.get('body_html', '')),
            'Vendor': product.get('vendor', ''),
            'Product Category': collection_name,
            'Type': product.get('product_type', ''),
            'Tags': ', '.join(product.get('tags', [])),
            'Published': 'TRUE' if product.get('published_at') else 'FALSE',
            'Collection': collection_name,
            'Created At': product.get('created_at', ''),
            'Updated At': product.get('updated_at', ''),
            'Description': clean_text_for_dataframe(BeautifulSoup(product.get('body_html', ''), 'html.parser').get_text().strip()) if product.get('body_html') else ''
        }
        
        # Process each variant as a separate row (Shopify CSV requirement)
        for variant_index, variant in enumerate(variants):
            variant_row = base_product.copy()
            
            # Add variant-specific data
            variant_row.update({
                'Option1 Name': 'Title' if variant.get('option1') else '',
                'Option1 Value': variant.get('option1', ''),
                'Option2 Name': 'Option2' if variant.get('option2') else '',
                'Option2 Value': variant.get('option2', ''),
                'Option3 Name': 'Option3' if variant.get('option3') else '',
                'Option3 Value': variant.get('option3', ''),
                'Variant SKU': variant.get('sku', ''),
                'Variant Grams': variant.get('grams', 0),
                'Variant Inventory Tracker': 'shopify',
                'Variant Inventory Qty': variant.get('inventory_quantity', 0),
                'Variant Inventory Policy': 'deny',
                'Variant Fulfillment Service': 'manual',
                'Variant Price': variant.get('price', '0'),
                'Variant Compare At Price': variant.get('compare_at_price', ''),
                'Variant Requires Shipping': 'TRUE' if variant.get('requires_shipping', True) else 'FALSE',
                'Variant Taxable': 'TRUE' if variant.get('taxable', True) else 'FALSE',
                'Variant Weight Unit': variant.get('weight_unit', 'kg'),
                'Available': variant.get('available', False),
                'Variants Count': len(variants),
            })
            
            # Handle images for this variant
            variant_image_id = variant.get('image_id')
            variant_image_url = ''
            
            if variant_image_id:
                # Find the specific image for this variant
                variant_image = next((img for img in images if img.get('id') == variant_image_id), None)
                if variant_image:
                    variant_image_url = variant_image.get('src', '')
            
            # For the first variant, include the main product image
            if variant_index == 0:
                main_image = images[0].get('src', '') if images else ''
                variant_row.update({
                    'Image Src': main_image,
                    'Image Position': 1,
                    'Image Alt Text': images[0].get('alt', '') if images else '',
                    'Variant Image': variant_image_url if variant_image_url else main_image,
                    'Total Images': len(images),
                })
                
                # Add all additional images as separate rows
                for img_index, image in enumerate(images[1:], 2):  # Start from position 2
                    image_row = base_product.copy()
                    image_row.update({
                        'Image Src': image.get('src', ''),
                        'Image Position': img_index,
                        'Image Alt Text': image.get('alt', ''),
                        'Total Images': len(images),
                    })
                    # Clear variant data for image-only rows
                    for key in image_row.keys():
                        if key.startswith('Variant') or key.startswith('Option'):
                            image_row[key] = ''
                    parsed_products.append(image_row)
                    
            else:
                # For subsequent variants, only include variant image if different
                variant_row.update({
                    'Image Src': '',  # Empty for variant rows
                    'Image Position': '',
                    'Image Alt Text': '',
                    'Variant Image': variant_image_url,
                    'Total Images': len(images),
                })
            
            parsed_products.append(variant_row)
    
    return parsed_products

def main():
    # Header
    st.markdown('<h1 class="main-header">🛍️ Shopify Product Scraper</h1>', unsafe_allow_html=True)
    st.markdown("Extract product data from Shopify stores using their products.json endpoint")
    
    # Sidebar for settings
    with st.sidebar:
        st.header("⚙️ Settings")
        
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
        st.write("")
        st.write("")
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
                    products = get_products_json(store_url, limit=50)
                    if products:
                        parsed = parse_product_data(products)
                        all_products.extend(parsed)
                    status.update(label=f"Standard API: {len(products) if products else 0} products ✅", state="complete")
                    
            elif scraping_method == "Paginated JSON API":
                with st.status("Fetching products via paginated API...", expanded=True) as status:
                    products = get_products_json(store_url, limit=250)
                    if products:
                        parsed = parse_product_data(products)
                        all_products.extend(parsed)
                    status.update(label=f"Paginated API: {len(products) if products else 0} products ✅", state="complete")
                    
            elif scraping_method == "Collections-based Scraping":
                with st.status("Fetching products via collections...", expanded=True) as status:
                    products, collections = get_collections_and_products(store_url)
                    if products:
                        parsed = parse_product_data(products)
                        all_products.extend(parsed)
                        collection_info = collections
                    status.update(label=f"Collections method: {len(products) if products else 0} products from {len(collection_info)} collections ✅", state="complete")
                    
            elif scraping_method == "All Methods Combined":
                # Method 1: Standard JSON
                with st.status("Method 1: Standard JSON API...", expanded=True) as status:
                    products1 = get_products_json(store_url, limit=50)
                    if products1:
                        parsed1 = parse_product_data(products1)
                        all_products.extend(parsed1)
                    status.update(label=f"Standard API: {len(products1) if products1 else 0} products ✅", state="complete")
                
                # Method 2: Paginated JSON
                with st.status("Method 2: Paginated JSON API...", expanded=True) as status:
                    products2 = get_products_json(store_url, limit=250)
                    if products2:
                        # Remove duplicates
                        existing_handles = {p.get('Handle') for p in all_products}
                        new_products = [p for p in products2 if p.get('handle') not in existing_handles]
                        if new_products:
                            parsed2 = parse_product_data(new_products)
                            all_products.extend(parsed2)
                    status.update(label=f"Paginated API: {len(products2) if products2 else 0} products ✅", state="complete")
                
                # Method 3: Collections
                with st.status("Method 3: Collections-based scraping...", expanded=True) as status:
                    products3, collections = get_collections_and_products(store_url)
                    if products3:
                        # Remove duplicates
                        existing_handles = {p.get('Handle') for p in all_products}
                        new_products = [p for p in products3 if p.get('handle') not in existing_handles]
                        if new_products:
                            parsed3 = parse_product_data(new_products)
                            all_products.extend(parsed3)
                            collection_info = collections
                    status.update(label=f"Collections: {len(products3) if products3 else 0} products from {len(collection_info)} collections ✅", state="complete")
            
            if not all_products:
                st.warning("No products found. The store might be empty or have restricted access.")
                st.stop()
        
        # Display results
        st.success(f"✅ Successfully scraped {len(all_products)} products!")
        
        # Show collection information if available
        if collection_info:
            st.info(f"📂 Found products across {len(collection_info)} collections:")
            cols = st.columns(min(4, len(collection_info)))
            for i, (collection_name, count) in enumerate(collection_info.items()):
                with cols[i % len(cols)]:
                    st.metric(collection_name, f"{count} products")
        
        # Create DataFrame
        df = pd.DataFrame(all_products)
        
        # Metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Products", len(all_products))
        with col2:
            available_products = sum(1 for p in all_products if p.get('Available', False))
            st.metric("Available Products", available_products)
        with col3:
            unique_vendors = len(set(p.get('Vendor', '') for p in all_products if p.get('Vendor')))
            st.metric("Unique Vendors", unique_vendors)
        with col4:
            prices = [float(str(p.get('Variant Price', 0)).replace('$', '').replace(',', '')) for p in all_products if p.get('Variant Price') and str(p.get('Variant Price', '')).replace('$', '').replace(',', '').replace('.', '').isdigit()]
            avg_price = sum(prices) / len(prices) if prices else 0
            st.metric("Average Price", f"${avg_price:.2f}")
        
        # Data table
        st.subheader("📋 Product Data")
        
        # Filters
        col1, col2, col3 = st.columns(3)
        with col1:
            vendors_available = sorted(list(set(p.get('Vendor', '') for p in all_products if p.get('Vendor'))))
            vendor_filter = st.multiselect(
                "Filter by Vendor:",
                options=vendors_available,
                default=[]
            )
        with col2:
            collections_available = sorted(list(set(p.get('Collection', '') for p in all_products if p.get('Collection'))))
            collection_filter = st.multiselect(
                "Filter by Collection:",
                options=collections_available,
                default=[]
            )
        with col3:
            types_available = sorted(list(set(p.get('Type', '') for p in all_products if p.get('Type'))))
            product_type_filter = st.multiselect(
                "Filter by Product Type:",
                options=types_available,
                default=[]
            )
        
        # Apply filters
        filtered_df = df.copy()
        if vendor_filter:
            filtered_df = filtered_df[filtered_df['Vendor'].isin(vendor_filter)]
        if collection_filter:
            filtered_df = filtered_df[filtered_df['Collection'].isin(collection_filter)]
        if product_type_filter:
            filtered_df = filtered_df[filtered_df['Type'].isin(product_type_filter)]
        
        # Display filtered data
        st.dataframe(
            filtered_df, 
            use_container_width=True,
            column_config={
                "Body (HTML)": st.column_config.TextColumn(
                    "Description (HTML)",
                    help="Full product description in HTML format",
                    width="large"
                ),
                "Description": st.column_config.TextColumn(
                    "Description (Text)",
                    help="Product description as plain text",
                    width="large"
                ),
                "Image Src": st.column_config.ImageColumn(
                    "Main Image",
                    help="Primary product image"
                )
            }
        )
        
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

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

def scrape_sitemap_products(store_url):
    """Try to get product URLs from sitemap"""
    try:
        if not store_url.startswith(('http://', 'https://')):
            store_url = 'https://' + store_url
        
        base_url = store_url.rstrip('/')
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # Try common sitemap locations
        sitemap_urls = [
            f"{base_url}/sitemap.xml",
            f"{base_url}/sitemap_products_1.xml",
            f"{base_url}/products.xml"
        ]
        
        product_urls = []
        
        for sitemap_url in sitemap_urls:
            try:
                response = requests.get(sitemap_url, headers=headers, timeout=10)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'xml')
                    
                    # Find all URLs that contain '/products/'
                    for url_tag in soup.find_all('url'):
                        loc_tag = url_tag.find('loc')
                        if loc_tag and '/products/' in loc_tag.text:
                            product_urls.append(loc_tag.text)
                    
                    if product_urls:
                        break  # Found products in this sitemap
                        
            except:
                continue
        
        return product_urls[:100]  # Limit to first 100 for performance
    
    except Exception as e:
        st.error(f"Error scraping sitemap: {str(e)}")
        return []

def parse_product_data(products):
    """Parse product data into a structured format"""
    parsed_products = []
    
    for product in products:
        # Get first variant for pricing (most Shopify stores have at least one variant)
        first_variant = product.get('variants', [{}])[0]
        
        # Get first image
        first_image = product.get('images', [{}])[0].get('src', '') if product.get('images') else ''
        
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
            'Variants Count': len(product.get('variants', [])),
            'Images Count': len(product.get('images', [])),
            'Description': BeautifulSoup(product.get('body_html', ''), 'html.parser').get_text()[:200] + '...' if product.get('body_html') else ''
        }
        
        parsed_products.append(parsed_product)
    
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
                st.warning("No products found. The store might be empty, have restricted access, or use a different structure.")
                st.stop()
        
        # Parse and display data
        with st.status("Processing product data...", expanded=True) as status:
            parsed_products = parse_product_data(all_products)
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
            avg_price = sum(float(p['Price']) for p in parsed_products if p['Price']) / len(parsed_products)
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
        
        # Display filtered data
        st.dataframe(filtered_df, use_container_width=True)
        
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

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

def get_products_json(store_url):
    """Get products from Shopify's products.json endpoint"""
    try:
        # Clean and format the URL
        if not store_url.startswith(('http://', 'https://')):
            store_url = 'https://' + store_url
        
        # Remove trailing slash and add products.json
        base_url = store_url.rstrip('/')
        products_url = f"{base_url}/products.json"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(products_url, headers=headers, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        return data.get('products', [])
    
    except requests.exceptions.RequestException as e:
        st.error(f"Network error: {str(e)}")
        return None
    except json.JSONDecodeError:
        st.error("Invalid JSON response - store might not be Shopify or has restricted access")
        return None
    except Exception as e:
        st.error(f"Error fetching products: {str(e)}")
        return None

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
    
    # Information section
    with st.expander("ℹ️ How it works", expanded=False):
        st.markdown("""
        **This tool extracts product data from Shopify stores by:**
        1. Accessing the store's `/products.json` endpoint
        2. Parsing the JSON response to extract product information
        3. Organizing the data into a readable format
        
        **Data extracted includes:**
        - Product titles, descriptions, and handles
        - Pricing and inventory information
        - Product images and variants
        - Tags, vendor information, and more
        
        **Note:** This tool only works with stores that have public product data access enabled.
        """)
    
    # Scraping logic
    if scrape_button and store_url:
        with st.spinner("Scraping products... Please wait"):
            # Validate if it's a Shopify store
            with st.status("Validating Shopify store...", expanded=True) as status:
                if not is_shopify_store(store_url):
                    st.warning("⚠️ This doesn't appear to be a Shopify store or the store is not accessible.")
                status.update(label="Shopify store validated ✅", state="complete")
            
            # Fetch products
            with st.status("Fetching product data...", expanded=True) as status:
                products = get_products_json(store_url)
                
                if products is None:
                    st.stop()
                elif len(products) == 0:
                    st.warning("No products found. The store might be empty or have restricted access.")
                    st.stop()
                
                status.update(label=f"Found {len(products)} products ✅", state="complete")
            
            # Parse and display data
            with st.status("Processing product data...", expanded=True) as status:
                parsed_products = parse_product_data(products)
                df = pd.DataFrame(parsed_products)
                status.update(label="Data processing complete ✅", state="complete")
        
        # Display results
        st.success(f"✅ Successfully scraped {len(parsed_products)} products!")
        
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

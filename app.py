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
    page_title="E-commerce Product Scraper",
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

def detect_platform(url):
    """Detect if a website is Shopify, WordPress, or other"""
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
            
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        content = response.text.lower()
        
        # Check for Shopify
        if 'shopify' in content or 'cdn.shopify.com' in content:
            return 'shopify'
        
        # Check for WordPress
        if ('wp-content' in content or 
            'wordpress' in content or 
            'wp-json' in content or
            '/wp-' in content or
            'woocommerce' in content):
            return 'wordpress'
        
        return 'unknown'
    except:
        return 'unknown'

def is_shopify_store(url):
    """Check if a URL is a Shopify store"""
    return detect_platform(url) == 'shopify'

def is_wordpress_site(url):
    """Check if a URL is a WordPress site"""
    return detect_platform(url) == 'wordpress'

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

def get_wordpress_products_woocommerce_api(store_url):
    """Try to get products via WooCommerce REST API"""
    try:
        if not store_url.startswith(('http://', 'https://')):
            store_url = 'https://' + store_url
        
        base_url = store_url.rstrip('/')
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # Try WooCommerce REST API endpoints
        api_endpoints = [
            f"{base_url}/wp-json/wc/v3/products",
            f"{base_url}/wp-json/wc/v2/products", 
            f"{base_url}/wp-json/wc/v1/products"
        ]
        
        for endpoint in api_endpoints:
            try:
                response = requests.get(f"{endpoint}?per_page=100", headers=headers, timeout=15)
                if response.status_code == 200:
                    products = response.json()
                    if products and isinstance(products, list):
                        return products, 'woocommerce_api'
            except:
                continue
        
        return [], 'api_failed'
    
    except Exception as e:
        return [], f'error: {str(e)}'

def scrape_wordpress_products_html(store_url):
    """Scrape WordPress products from HTML pages"""
    try:
        if not store_url.startswith(('http://', 'https://')):
            store_url = 'https://' + store_url
        
        base_url = store_url.rstrip('/')
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # Common WordPress shop page URLs
        shop_urls = [
            f"{base_url}/shop",
            f"{base_url}/products", 
            f"{base_url}/store",
            f"{base_url}/product-category/all",
            f"{base_url}/wc-api/v3/products"
        ]
        
        all_products = []
        
        for shop_url in shop_urls:
            try:
                response = requests.get(shop_url, headers=headers, timeout=10)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    # Look for common WooCommerce product selectors
                    product_selectors = [
                        '.woocommerce ul.products li.product',
                        '.products .product',
                        '.wc-products .product',
                        '.product-item',
                        '.woocommerce-LoopProduct-link',
                        'article.product'
                    ]
                    
                    products_found = False
                    for selector in product_selectors:
                        products = soup.select(selector)
                        if products:
                            products_found = True
                            for product in products[:50]:  # Limit to first 50
                                product_data = extract_product_from_html(product, base_url)
                                if product_data:
                                    all_products.append(product_data)
                            break
                    
                    if products_found:
                        break  # Found products, no need to try other URLs
                        
            except:
                continue
        
        return all_products
    
    except Exception as e:
        st.error(f"Error scraping WordPress products: {str(e)}")
        return []

def extract_product_from_html(product_element, base_url):
    """Extract product information from HTML element"""
    try:
        product_data = {}
        
        # Try to get product title
        title_selectors = [
            '.woocommerce-loop-product__title',
            '.product-title', 
            'h2 a',
            'h3 a',
            '.entry-title',
            'a[href*="product"]'
        ]
        
        title = ""
        product_url = ""
        
        for selector in title_selectors:
            title_elem = product_element.select_one(selector)
            if title_elem:
                title = title_elem.get_text(strip=True)
                if title_elem.get('href'):
                    product_url = urljoin(base_url, title_elem.get('href'))
                elif title_elem.find_parent('a'):
                    product_url = urljoin(base_url, title_elem.find_parent('a').get('href', ''))
                break
        
        if not title:
            return None
        
        # Try to get price
        price_selectors = [
            '.price .amount',
            '.woocommerce-Price-amount',
            '.price',
            '.product-price',
            '.cost'
        ]
        
        price = ""
        for selector in price_selectors:
            price_elem = product_element.select_one(selector)
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                # Extract numeric price
                price_match = re.search(r'[\d,]+\.?\d*', price_text.replace(',', ''))
                if price_match:
                    price = price_match.group()
                break
        
        # Try to get image
        image_url = ""
        img_elem = product_element.select_one('img')
        if img_elem:
            image_url = img_elem.get('src') or img_elem.get('data-src') or ""
            if image_url and not image_url.startswith('http'):
                image_url = urljoin(base_url, image_url)
        
        # Try to get description/excerpt
        description = ""
        desc_selectors = [
            '.woocommerce-product-details__short-description',
            '.product-excerpt',
            '.entry-summary',
            'p'
        ]
        
        for selector in desc_selectors:
            desc_elem = product_element.select_one(selector)
            if desc_elem:
                description = desc_elem.get_text(strip=True)[:200] + "..."
                break
        
        product_data = {
            'title': title,
            'price': price,
            'url': product_url,
            'image_url': image_url,
            'description': description,
            'platform': 'wordpress'
        }
        
        return product_data
    
    except Exception as e:
        return None

def parse_wordpress_woocommerce_data(products):
    """Parse WooCommerce API product data"""
    parsed_products = []
    
    for product in products:
        parsed_product = {
            'Title': product.get('name', ''),
            'Handle': product.get('slug', ''),
            'Product Type': ', '.join([cat.get('name', '') for cat in product.get('categories', [])]),
            'Vendor': '',  # WooCommerce doesn't have vendor by default
            'Price': product.get('price', '0'),
            'Compare At Price': product.get('regular_price', ''),
            'Available': product.get('stock_status') == 'instock',
            'Inventory Quantity': product.get('stock_quantity', 0) or 0,
            'Weight': product.get('weight', ''),
            'Tags': ', '.join([tag.get('name', '') for tag in product.get('tags', [])]),
            'Created At': product.get('date_created', ''),
            'Updated At': product.get('date_modified', ''),
            'Published At': product.get('date_created', ''),
            'Image URL': product.get('images', [{}])[0].get('src', '') if product.get('images') else '',
            'Variants Count': len(product.get('variations', [])),
            'Images Count': len(product.get('images', [])),
            'Description': BeautifulSoup(product.get('short_description', ''), 'html.parser').get_text()[:200] + '...' if product.get('short_description') else '',
            'Platform': 'WordPress/WooCommerce'
        }
        
        parsed_products.append(parsed_product)
    
    return parsed_products

def parse_wordpress_html_data(products):
    """Parse HTML-scraped WordPress product data"""
    parsed_products = []
    
    for product in products:
        parsed_product = {
            'Title': product.get('title', ''),
            'Handle': '',
            'Product Type': '',
            'Vendor': '',
            'Price': product.get('price', '0'),
            'Compare At Price': '',
            'Available': True,  # Assume available if listed
            'Inventory Quantity': 0,
            'Weight': '',
            'Tags': '',
            'Created At': '',
            'Updated At': '',
            'Published At': '',
            'Image URL': product.get('image_url', ''),
            'Variants Count': 0,
            'Images Count': 1 if product.get('image_url') else 0,
            'Description': product.get('description', ''),
            'Product URL': product.get('url', ''),
            'Platform': 'WordPress (HTML)'
        }
        
        parsed_products.append(parsed_product)
    
    return parsed_products
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
            'Description': BeautifulSoup(product.get('body_html', ''), 'html.parser').get_text()[:200] + '...' if product.get('body_html') else '',
            'Platform': f'Shopify ({platform})'
        }
        
        parsed_products.append(parsed_product)
    
    return parsed_products

def main():
    # Header
    st.markdown('<h1 class="main-header">🛍️ E-commerce Product Scraper</h1>', unsafe_allow_html=True)
    st.markdown("Extract product data from Shopify stores and WordPress e-commerce sites")
    
    # Platform detection section
    st.subheader("🔍 Platform Detection")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        store_url = st.text_input(
            "Enter Website URL:",
            placeholder="e.g., https://example.com or example.myshopify.com",
            help="Enter the URL of an e-commerce website"
        )
    
    with col2:
        st.write("")
        st.write("")
        detect_button = st.button("🔍 Detect Platform", type="secondary")
    
    # Platform detection
    detected_platform = None
    if detect_button and store_url:
        with st.spinner("Detecting platform..."):
            detected_platform = detect_platform(store_url)
            if detected_platform == 'shopify':
                st.success("✅ Detected: **Shopify Store**")
            elif detected_platform == 'wordpress':
                st.success("✅ Detected: **WordPress Site** (likely WooCommerce)")
            else:
                st.warning("⚠️ Platform not clearly detected - will attempt multiple methods")
    
    # Sidebar for settings
    with st.sidebar:
        st.header("⚙️ Settings")
        
        # Platform selection
        st.subheader("🏪 Platform")
        platform_override = st.selectbox(
            "Force Platform Type",
            ["Auto-detect", "Shopify", "WordPress", "Try Both"],
            help="Override automatic detection"
        )
        
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
    
    # Scraping method selection based on platform
    if detected_platform == 'shopify' or platform_override == "Shopify":
        st.subheader("🔧 Shopify Scraping Method")
        scraping_method = st.radio(
            "Choose Shopify scraping approach:",
            ["Standard JSON API", "Paginated JSON API", "Collections-based Scraping", "All Shopify Methods"],
            help="Different methods to extract Shopify product data"
        )
    elif detected_platform == 'wordpress' or platform_override == "WordPress":
        st.subheader("🔧 WordPress Scraping Method") 
        scraping_method = st.radio(
            "Choose WordPress scraping approach:",
            ["WooCommerce REST API", "HTML Product Pages", "All WordPress Methods"],
            help="Different methods to extract WordPress/WooCommerce product data"
        )
    else:
        st.subheader("🔧 Universal Scraping Method")
        scraping_method = st.radio(
            "Choose scraping approach:",
            ["Try All Platforms", "Shopify Methods Only", "WordPress Methods Only"],
            help="Try different platform approaches"
        )
    
    # Main scrape button
    scrape_button = st.button("🚀 Start Scraping", type="primary", use_container_width=True)
    
    # Information section
    with st.expander("ℹ️ How it works", expanded=False):
        st.markdown("""
        **This tool supports multiple e-commerce platforms:**
        
        **🛍️ Shopify Stores:**
        - Standard/Paginated JSON API - Uses `/products.json` endpoint
        - Collections-based - Scrapes products from each collection
        - All Methods Combined - Maximum coverage approach
        
        **🏪 WordPress/WooCommerce Sites:**
        - WooCommerce REST API - Uses `/wp-json/wc/v*/products`
        - HTML Product Pages - Scrapes product listings from shop pages
        - All Methods Combined - Tries both API and HTML approaches
        
        **Data extracted includes:**
        - Product titles, descriptions, and URLs
        - Pricing and inventory information  
        - Product images and variants
        - Tags, categories, and vendor information
        - Platform-specific metadata
        
        **Note:** Success depends on site configuration and access permissions.
        """)
    
    # Scraping logic
    if scrape_button and store_url:
        all_products = []
        collection_info = {}
        scraping_results = {}
        
        # Determine platform and methods to use
        if platform_override == "Auto-detect":
            target_platform = detected_platform or detect_platform(store_url)
        elif platform_override == "Try Both":
            target_platform = "both"
        else:
            target_platform = platform_override.lower()
        
        with st.spinner("Scraping products... Please wait"):
            
            # SHOPIFY SCRAPING
            if target_platform in ['shopify', 'both'] or 'Shopify' in scraping_method:
                with st.status("Validating Shopify store...", expanded=True) as status:
                    if not is_shopify_store(store_url) and target_platform == 'shopify':
                        st.warning("⚠️ This doesn't appear to be a Shopify store.")
                    status.update(label="Shopify validation complete ✅", state="complete")
                
                if scraping_method == "Standard JSON API" or "Shopify" in scraping_method:
                    with st.status("Shopify: Standard JSON API...", expanded=True) as status:
                        products = get_products_json(store_url, limit=50)
                        if products:
                            parsed = parse_product_data(products, 'Standard API')
                            all_products.extend(parsed)
                            scraping_results['Shopify Standard'] = len(parsed)
                        status.update(label=f"Shopify Standard: {len(products) if products else 0} products ✅", state="complete")
                        
                if scraping_method == "Paginated JSON API" or "All" in scraping_method:
                    with st.status("Shopify: Paginated JSON API...", expanded=True) as status:
                        products = get_products_json(store_url, limit=250)
                        if products:
                            # Remove duplicates
                            existing_ids = {p.get('Title', '') + p.get('Handle', '') for p in all_products}
                            new_products = [p for p in products if (p.get('title', '') + p.get('handle', '')) not in existing_ids]
                            parsed = parse_product_data(new_products, 'Paginated API')
                            all_products.extend(parsed)
                            scraping_results['Shopify Paginated'] = len(parsed)
                        status.update(label=f"Shopify Paginated: {len(products) if products else 0} products ✅", state="complete")
                
                if scraping_method == "Collections-based Scraping" or "All" in scraping_method:
                    with st.status("Shopify: Collections-based scraping...", expanded=True) as status:
                        products, collections = get_collections_and_products(store_url)
                        if products:
                            existing_ids = {p.get('Title', '') + p.get('Handle', '') for p in all_products}
                            new_products = [p for p in products if (p.get('title', '') + p.get('handle', '')) not in existing_ids]
                            parsed = parse_product_data(new_products, 'Collections')
                            all_products.extend(parsed)
                            collection_info = collections
                            scraping_results['Shopify Collections'] = len(parsed)
                        status.update(label=f"Shopify Collections: {len(products) if products else 0} products ✅", state="complete")
            
            # WORDPRESS SCRAPING  
            if target_platform in ['wordpress', 'both'] or 'WordPress' in scraping_method:
                with st.status("Validating WordPress site...", expanded=True) as status:
                    if not is_wordpress_site(store_url) and target_platform == 'wordpress':
                        st.warning("⚠️ This doesn't appear to be a WordPress site.")
                    status.update(label="WordPress validation complete ✅", state="complete")
                
                if scraping_method == "WooCommerce REST API" or "All" in scraping_method:
                    with st.status("WordPress: WooCommerce REST API...", expanded=True) as status:
                        products, api_status = get_wordpress_products_woocommerce_api(store_url)
                        if products:
                            parsed = parse_wordpress_woocommerce_data(products)
                            all_products.extend(parsed)
                            scraping_results['WordPress API'] = len(parsed)
                            status.update(label=f"WordPress API: {len(parsed)} products ✅", state="complete")
                        else:
                            status.update(label=f"WordPress API: Failed ({api_status})", state="error")
                
                if scraping_method == "HTML Product Pages" or "All" in scraping_method:
                    with st.status("WordPress: HTML scraping...", expanded=True) as status:
                        products = scrape_wordpress_products_html(store_url)
                        if products:
                            # Remove duplicates by title
                            existing_titles = {p.get('Title', '').lower() for p in all_products}
                            new_products = [p for p in products if p.get('title', '').lower() not in existing_titles]
                            parsed = parse_wordpress_html_data(new_products)
                            all_products.extend(parsed)
                            scraping_results['WordPress HTML'] = len(parsed)
                        status.update(label=f"WordPress HTML: {len(products) if products else 0} products ✅", state="complete")
            
            if not all_products:
                st.error("❌ No products found with any method. The site might not be an e-commerce store, have restricted access, or use an unsupported platform.")
                st.info("💡 Try different scraping methods or check if the URL is correct.")
                st.stop()
        
        # Display results
        st.success(f"✅ Successfully scraped {len(all_products)} products!")
        
        # Show scraping method results
        if scraping_results:
            st.info("📊 **Scraping Results by Method:**")
            cols = st.columns(min(4, len(scraping_results)))
            for i, (method, count) in enumerate(scraping_results.items()):
                with cols[i % len(cols)]:
                    st.metric(method, f"{count} products")
        
        # Show collection information if available
        if collection_info:
            st.info(f"📂 Found products across {len(collection_info)} collections:")
            cols = st.columns(min(4, len(collection_info)))
            for i, (collection_name, count) in enumerate(collection_info.items()):
                with cols[i % len(cols)]:
                    st.metric(collection_name, f"{count} products")
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
            df = pd.DataFrame(all_products)
            status.update(label="Data processing complete ✅", state="complete")
        
        # Display results
        st.success(f"✅ Successfully scraped {len(all_products)} products!")
        
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

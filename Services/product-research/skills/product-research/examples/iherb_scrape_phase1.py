import json, re, time
from scrapling import StealthyFetcher
from urllib import request

BACKEND = 'http://127.0.0.1:5001'
CID = 'f96ce000'

def post_record(record):
    data = json.dumps({'record': record}).encode('utf-8')
    req = request.Request(f'{BACKEND}/api/subagent/record/{CID}',
                          data=data,
                          headers={'Content-Type': 'application/json'},
                          method='POST')
    try:
        resp = request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except Exception as e:
        return {'error': str(e)}

CATEGORIES = [
    'https://cn.iherb.com/c/menopause',
    'https://cn.iherb.com/c/women-s-health',
    'https://cn.iherb.com/c/hormonal-balance',
    'https://cn.iherb.com/c/bone-health',
]

fetcher = StealthyFetcher()
all_products = []
source_html_path = '/tmp/iherb_peri_phase1.html'

for cat_url in CATEGORIES:
    print(f"\n🔍 Scraping category: {cat_url}")
    try:
        page = fetcher.fetch(
            cat_url,
            timeout=60000,
            wait_selector='.product-cell-container',
            wait_selector_state='attached',
            solve_cloudflare=True,
        )
    except Exception as e:
        print(f"  ❌ Failed: {e}")
        continue

    html = page.html_content
    with open(source_html_path, 'w') as f:
        f.write(html)
    print(f"  HTML saved: {len(html)} bytes")

    cells = page.css('.product-cell-container')
    print(f"  Found {len(cells)} product cells")

    for i, cell in enumerate(cells):
        a = cell.css('a.absolute-link.product-link')
        if not a:
            continue
        a = a[0]

        product_name = a.attrib.get('title', 'unknown')
        brand = a.attrib.get('data-ga-brand-name', 'unknown')
        href = a.attrib.get('href', '')
        sku = a.attrib.get('data-part-number', 'unknown')
        out_of_stock = a.attrib.get('data-ga-is-out-of-stock', 'unknown')

        price_bdi = cell.css('span.price bdi')
        price = price_bdi[0].get_all_text(strip=True) if price_bdi else 'unknown'

        stars_link = cell.css('.stars.scroll-to')
        heat = stars_link[0].attrib.get('title', 'unknown') if stars_link else 'unknown'

        if out_of_stock.lower() == 'true':
            continue

        if 'unknown' in product_name or not product_name or product_name == 'unknown':
            continue

        all_products.append({
            'product_name': product_name,
            'brand': brand,
            'product_url': href,
            'price': price,
            'public_heat_signal': heat,
            'sku': sku,
        })
        print(f"  [{len(all_products)}] {brand} | {product_name[:80]} | {price} | {heat}")

    print(f"  Category done. Total so far: {len(all_products)}")

with open('/tmp/peri_products_phase1.json', 'w') as f:
    json.dump(all_products, f, ensure_ascii=False, indent=2)

print(f"\n✅ Phase 1 complete: {len(all_products)} products collected")

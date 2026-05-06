import json, re, time, os
from scrapling.fetchers import StealthySession
from urllib import request

BACKEND = 'http://127.0.0.1:5001'
CID = 'f96ce000'

def post_record(record):
    data = json.dumps({'record': record}, ensure_ascii=False).encode('utf-8')
    req = request.Request(f'{BACKEND}/api/subagent/record/{CID}',
                          data=data, headers={'Content-Type': 'application/json'}, method='POST')
    try:
        resp = request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        return result
    except Exception as e:
        return {'error': str(e)}

# Load Phase 1 products
with open('/tmp/peri_products_phase1.json') as f:
    all_products = json.load(f)

# Filter: only oral products relevant to perimenopause
# Exclude creams, balms, topical products
CREAM_KEYWORDS = ['cream', 'balm', 'lotion', 'topical', 'gel', 'suppository', 'vaginal']
SKIP_BRANDS = set()  # optional

oral_products = []
for p in all_products:
    name = p['product_name'].lower()
    # Skip creams/balms/topicals
    if any(kw in name for kw in CREAM_KEYWORDS):
        continue
    # Skip products clearly not perimenopause (pregnancy, prenatal, baby)
    if any(kw in name for kw in ['prenatal', 'pregnancy', 'baby', 'kids', 'children']):
        continue
    oral_products.append(p)

print(f"Filtered to {len(oral_products)} oral products")

# Select top products for detail scraping (focus on menopause-direct products first)
# Prioritize products from menopause category (first 44)
menopause_oral = [p for p in oral_products if p in all_products[:44]]
other_oral = [p for p in oral_products if p not in all_products[:44]]

print(f"Menopause-category oral: {len(menopause_oral)}")
print(f"Other oral: {len(other_oral)}")

# Combine: menopause oral first, then relevant others
target_products = menopause_oral[:20] + other_oral[:10]

print(f"\nWill scrape detail pages for {len(target_products)} products")

# Scrape detail pages
source_dir = '/tmp/peri_detail_pages'
os.makedirs(source_dir, exist_ok=True)

submitted = 0
with StealthySession(headless=True, disable_resources=False, timeout=90000) as session:
    for idx, p in enumerate(target_products):
        url = p['product_url']
        if not url or url == 'unknown':
            continue

        print(f"\n[{idx+1}/{len(target_products)}] {p['brand']} - {p['product_name'][:60]}...")

        try:
            page = session.fetch(url)
        except Exception as e:
            print(f"  ❌ Fetch failed: {e}")
            continue

        if page.status != 200:
            print(f"  ⚠️ Status {page.status}, skipping")
            continue

        html = page.body.decode('utf-8', errors='replace')
        if len(html) < 5000:
            print(f"  ⚠️ HTML too short ({len(html)} bytes), skipping")
            continue

        # Save HTML
        html_path = f'{source_dir}/product_{idx}.html'
        with open(html_path, 'w') as f:
            f.write(html)

        # Extract JSON-LD
        description = 'unknown'
        category = 'unknown'
        for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL):
            try:
                data = json.loads(m.group(1))
                if isinstance(data, dict) and data.get('@type') == 'Product':
                    desc = data.get('description', '')
                    if desc:
                        description = desc[:500]  # trim
                    cat = data.get('category', {})
                    if isinstance(cat, dict):
                        category = cat.get('name', 'unknown')
                    elif isinstance(cat, str):
                        category = cat
                    break
            except (json.JSONDecodeError, KeyError):
                pass

        # Extract Supplement Facts from table
        supplement_facts = 'unknown'
        for t in page.css('table'):
            text = t.get_all_text(strip=True)
            if any(kw in text.lower() for kw in ['supplement', 'serving', 'amount per']):
                supplement_facts = text[:1000]
                break

        # Determine dosage_form from product name
        name_lower = p['product_name'].lower()
        if 'capsule' in name_lower or 'veggie cap' in name_lower or 'veg cap' in name_lower:
            dosage_form = 'Capsules'
        elif 'tablet' in name_lower or 'caplet' in name_lower:
            dosage_form = 'Tablets'
        elif 'softgel' in name_lower or 'soft gel' in name_lower:
            dosage_form = 'Softgels'
        elif 'powder' in name_lower:
            dosage_form = 'Powder'
        elif 'gumm' in name_lower:
            dosage_form = 'Gummies'
        elif 'liquid' in name_lower or 'drop' in name_lower:
            dosage_form = 'Liquid'
        else:
            dosage_form = 'unknown'

        # Extract pack_size from product name (e.g., "60 Capsules", "30 Tablets")
        pack_match = re.search(r'(\d+)\s*(Capsules?|Tablets?|Caplets?|Softgels?|Veg(?:gie)?\s*Caps?|Gummies?|fl\s*oz|oz)', p['product_name'], re.IGNORECASE)
        pack_size = pack_match.group(0) if pack_match else 'unknown'

        # Build record
        record = {
            'product_name': p['product_name'],
            'brand': p['brand'],
            'source_platform': 'iHerb',
            'product_url': url,
            'source_html_path': html_path,
            'dosage_form': dosage_form,
            'pack_size': pack_size,
            'price': p['price'],
            'core_selling_points': description,  # JSON-LD description often contains selling points
            'core_ingredients': supplement_facts,
            'claim_direction': category,
            'public_heat_signal': p['public_heat_signal'],
            'target_population': 'Perimenopausal / Menopausal Women',
        }

        # Check unknown count
        _content_fields = ['product_name','brand','dosage_form','pack_size','price',
                           'core_selling_points','core_ingredients','claim_direction',
                           'public_heat_signal','target_population']
        unknown_cnt = sum(1 for f in _content_fields if record.get(f) in ['unknown','',None])
        if unknown_cnt >= 7:
            print(f"  ⏭️ Skipping: {unknown_cnt}/10 fields unknown")
            continue

        # Submit
        result = post_record(record)
        if 'error' in result:
            print(f"  ❌ Submit error: {result['error']}")
        else:
            submitted += 1
            print(f"  ✅ Submitted (#{result.get('count', '?')}) | unknown_fields={unknown_cnt}")
            print(f"     dosage_form={dosage_form} | pack_size={pack_size}")
            print(f"     supp_facts_len={len(supplement_facts)} | desc_len={len(description)}")

        if submitted >= 30:
            break

        # Small delay between pages
        time.sleep(2)

print(f"\n✅ Phase 2 complete: {submitted} records submitted")

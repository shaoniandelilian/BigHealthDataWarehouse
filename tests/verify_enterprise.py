# -*- coding: utf-8 -*-
import requests
import time

API_URL = "http://127.0.0.1:8001/api/v1/ingest/sync"
METRICS_URL = "http://127.0.0.1:8001/metrics"

def test_cache():
    payload = {
        "id": "cache-test-01",
        "name": "Menthol",
        "metadata": {"raw_smiles": "CC1CCC(C(C1)O)C(C)C"},
        "raw_data": "A menthol test."
    }
    
    print("🚀 Sending first request (should call AI)...")
    start = time.time()
    resp1 = requests.post(API_URL, json=payload)
    print(f"First request took: {time.time() - start:.2f}s")
    print(resp1.json().get("status"))
    
    print("\n🚀 Sending second request (should HIT REDIS CACHE)...")
    start = time.time()
    resp2 = requests.post(API_URL, json=payload)
    print(f"Second request took: {time.time() - start:.2f}s")
    print(resp2.json().get("status"))
    
    if "is_cached" in resp2.json().get("metadata_snapshot", {}):
        print("✅ SUCCESS: Cache HIT detected in response metadata!")
    else:
        print("❌ FAILURE: Cache hit NOT detected.")

    print("\n📊 Checking Metrics...")
    metrics_resp = requests.get(METRICS_URL)
    if metrics_resp.status_code == 200:
        print("✅ SUCCESS: Metrics endpoint active.")
        if "chemrag_pipeline_processed_total" in metrics_resp.text:
            print("✅ SUCCESS: Found pipeline counters in metrics.")
    else:
        print("❌ FAILURE: Metrics endpoint not found.")

if __name__ == "__main__":
    test_cache()

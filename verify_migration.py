#!/usr/bin/env python3
"""
Verification script to check that the migrated endpoints are working correctly.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app

def test_endpoints():
    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()

    print("Testing migrated endpoints...")

    # Test /api/breadth-latest (moved to blueprint)
    print("\n1. Testing /api/breadth-latest:")
    response = client.get('/api/v1/breadth-latest')
    print(f"   Status Code: {response.status_code}")
    if response.status_code == 200:
        print("   PASS: Breadth latest endpoint working")
    else:
        print(f"   FAIL: Breadth latest endpoint failed: {response.get_json()}")

    # Test /api/watchlist (moved to blueprint)
    print("\n2. Testing /api/watchlist:")
    response = client.get('/api/v1/watchlist')
    print(f"   Status Code: {response.status_code}")
    if response.status_code == 200:
        print("   PASS: Watchlist endpoint working")
    else:
        print(f"   FAIL: Watchlist endpoint failed: {response.get_json()}")

    # Test /api/journal (moved to blueprint)
    print("\n3. Testing /api/journal:")
    response = client.get('/api/v1/journal')
    print(f"   Status Code: {response.status_code}")
    if response.status_code == 200:
        print("   PASS: Journal endpoint working")
    else:
        print(f"   FAIL: Journal endpoint failed: {response.get_json()}")

    # Test /api/migrate-local-data (still in app.py, not in blueprint)
    print("\n4. Testing /api/migrate-local-data:")
    migrate_data = {
        "watchlist_sections": [],
        "journal": []
    }
    response = client.post('/api/migrate-local-data', json=migrate_data)
    print(f"   Status Code: {response.status_code}")
    if response.status_code == 200:
        print("   PASS: Local data migration endpoint working")
    else:
        print(f"   FAIL: Local data migration endpoint failed: {response.get_json()}")

    print("\nMigration verification complete!")

if __name__ == "__main__":
    test_endpoints()
from app import create_app

app = create_app()
app.testing = True
client = app.test_client()

if __name__ == '__main__':
    print("Testing Watchlist API...")

    # Test 1: Get empty watchlist
    print("\n1. Getting initial watchlist (should be empty):")
    response = client.get('/api/v1/watchlist')
    print('Status Code:', response.status_code)
    data = response.get_json()
    print('Response:', data)

    # Test 2: Create a section
    print("\n2. Creating a watchlist section:")
    section_data = {
        "id": 1,
        "name": "Tech Stocks"
    }
    response = client.post('/api/v1/watchlist/sections', json=section_data)
    print('Status Code:', response.status_code)
    data = response.get_json()
    print('Response:', data)

    # Test 3: Get watchlist to see the section
    print("\n3. Getting watchlist after creating section:")
    response = client.get('/api/v1/watchlist')
    print('Status Code:', response.status_code)
    data = response.get_json()
    print('Response:', data)

    # Test 4: Add an item to the section
    print("\n4. Adding an item to the section:")
    item_data = {
        "section_id": 1,
        "ticker": "AAPL"
    }
    response = client.post('/api/v1/watchlist/items', json=item_data)
    print('Status Code:', response.status_code)
    data = response.get_json()
    print('Response:', data)

    # Test 5: Get watchlist to see the item
    print("\n5. Getting watchlist after adding item:")
    response = client.get('/api/v1/watchlist')
    print('Status Code:', response.status_code)
    data = response.get_json()
    print('Response:', data)

    # Test 6: Rename the section
    print("\n6. Renaming the section:")
    rename_data = {
        "name": "Technology Stocks"
    }
    response = client.put('/api/v1/watchlist/sections/1', json=rename_data)
    print('Status Code:', response.status_code)
    data = response.get_json()
    print('Response:', data)

    # Test 7: Get watchlist to see the renamed section
    print("\n7. Getting watchlist after renaming section:")
    response = client.get('/api/v1/watchlist')
    print('Status Code:', response.status_code)
    data = response.get_json()
    print('Response:', data)

    # Test 8: Remove the item
    print("\n8. Removing the item:")
    remove_item_data = {
        "section_id": 1,
        "ticker": "AAPL"
    }
    response = client.delete('/api/v1/watchlist/items', json=remove_item_data)
    print('Status Code:', response.status_code)
    data = response.get_json()
    print('Response:', data)

    # Test 9: Get watchlist to see the item removed
    print("\n9. Getting watchlist after removing item:")
    response = client.get('/api/v1/watchlist')
    print('Status Code:', response.status_code)
    data = response.get_json()
    print('Response:', data)

    # Test 10: Delete the section
    print("\n10. Deleting the section:")
    response = client.delete('/api/v1/watchlist/sections/1')
    print('Status Code:', response.status_code)
    data = response.get_json()
    print('Response:', data)

    # Test 11: Get watchlist to see the section deleted
    print("\n11. Getting watchlist after deleting section:")
    response = client.get('/api/v1/watchlist')
    print('Status Code:', response.status_code)
    data = response.get_json()
    print('Response:', data)

    # Test 11: Get watchlist to see the section deleted
    print("\n11. Getting watchlist after deleting section:")
    response = client.get('/api/v1/watchlist')
    print('Status Code:', response.status_code)
    data = response.get_json()
    print('Response:', data)

    # Test 12: Create two sections for reordering test
    print("\n12. Creating two sections for reordering test:")
    section1_data = {"id": 10, "name": "Section A"}
    section2_data = {"id": 20, "name": "Section B"}
    response = client.post('/api/v1/watchlist/sections', json=section1_data)
    print('Section A creation:', response.status_code, response.get_json())
    response = client.post('/api/v1/watchlist/sections', json=section2_data)
    print('Section B creation:', response.status_code, response.get_json())

    # Test 13: Get watchlist to see the initial order
    print("\n13. Getting watchlist to see initial order:")
    response = client.get('/api/v1/watchlist')
    print('Status Code:', response.status_code)
    data = response.get_json()
    print('Response:', data)

    # Test 14: Reorder sections (reverse the order)
    print("\n14. Reordering sections (B, A):")
    reorder_data = {"order": [20, 10]}
    response = client.put('/api/v1/watchlist/sections/reorder', json=reorder_data)
    print('Status Code:', response.status_code)
    print('Response:', response.get_json())

    # Test 15: Get watchlist to see the new order
    print("\n15. Getting watchlist after reordering sections:")
    response = client.get('/api/v1/watchlist')
    print('Status Code:', response.status_code)
    data = response.get_json()
    print('Response:', data)

    # Test 16: Add items to section A for item reordering test
    print("\n16. Adding items to section A for item reordering test:")
    item_aapl = {"section_id": 10, "ticker": "AAPL"}
    item_goog = {"section_id": 10, "ticker": "GOOG"}
    item_msft = {"section_id": 10, "ticker": "MSFT"}
    response = client.post('/api/v1/watchlist/items', json=item_aapl)
    print('AAPL added:', response.status_code, response.get_json())
    response = client.post('/api/v1/watchlist/items', json=item_goog)
    print('GOOG added:', response.status_code, response.get_json())
    response = client.post('/api/v1/watchlist/items', json=item_msft)
    print('MSFT added:', response.status_code, response.get_json())

    # Test 17: Get section A to see initial item order
    print("\n17. Getting section A to see initial item order:")
    response = client.get('/api/v1/watchlist')
    print('Status Code:', response.status_code)
    data = response.get_json()
    # Find section A
    section_a = None
    for section in data['data']:
        if section['id'] == '10':
            section_a = section
            break
    print('Section A items:', section_a['items'] if section_a else "Not found")

    # Test 18: Reorder items in section A (MSFT, GOOG, AAPL)
    print("\n18. Reordering items in section A (MSFT, GOOG, AAPL):")
    reorder_items_data = {"stocks": ["MSFT", "GOOG", "AAPL"]}
    response = client.put('/api/v1/watchlist/sections/10/reorder', json=reorder_items_data)
    print('Status Code:', response.status_code)
    print('Response:', response.get_json())

    # Test 19: Get section A to see new item order
    print("\n19. Getting section A after reordering items:")
    response = client.get('/api/v1/watchlist')
    print('Status Code:', response.status_code)
    data = response.get_json()
    section_a = None
    for section in data['data']:
        if section['id'] == '10':
            section_a = section
            break
    print('Section A items:', section_a['items'] if section_a else "Not found")

    print("\nWatchlist API test completed.")
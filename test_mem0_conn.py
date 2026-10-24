from mem0 import MemoryClient

client = MemoryClient(api_key="m0sk_3opeYe7dV6J4vhxDmtjCDz_zl781vaZ--eghUOCkKs4", host="http://localhost:8888")
try:
    # Try add
    res = client.add([{"role": "user", "content": "I like coffee"}], user_id="test_user")
    print("ADD:", res)
    
    # Try search
    res = client.search("coffee", filters={"user_id": "test_user"})
    print("SEARCH:", res)
    
    # Try get_all
    res = client.get_all(filters={"user_id": "test_user"})
    print("GET_ALL:", res)
except Exception as e:
    print("ERR:", type(e).__name__, e)
    import traceback
    traceback.print_exc()

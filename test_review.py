from core.review_store import ReviewStore
store = ReviewStore()
records = store.get_pending_records(1)
if records:
    print(records[0]['id'])
else:
    print("NO_RECORDS")

import urllib.request
import json

try:
    with urllib.request.urlopen('https://raw.githubusercontent.com/timothycarambat/senate-stock-watcher-data/master/aggregate/all_transactions.json') as response:
        data = json.loads(response.read().decode())
        import datetime
        def safe_parse(d):
            try: return datetime.datetime.strptime(d['transaction_date'], '%m/%d/%Y')
            except: return datetime.datetime.min
        data.sort(key=safe_parse, reverse=True)
        print('Total:', len(data))
        print('Latest date:', data[0]['transaction_date'] if data else 'None')
except Exception as e:
    print(e)

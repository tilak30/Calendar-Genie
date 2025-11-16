import os
import time
import requests
from agents.smart_fetcher import SmartFetcherAgent
import main
from main import SearchRequest

# Monkeypatch requests.post to call main.search_local_context directly
original_post = requests.post

def fake_post(url, json=None, timeout=None):
    # Emulate the HTTP POST body -> call the FastAPI function directly
    req = SearchRequest(**json)
    resp = main.search_local_context(req)
    class FakeResp:
        def __init__(self, data):
            self._data = data
            self.status_code = 200
        def json(self):
            return self._data
    return FakeResp(resp)

requests.post = fake_post

# Run the agent
agent = SmartFetcherAgent()
meeting = {
    'title': 'Test Meeting',
    'description': 'A short test meeting',
    'start_time': '2025-11-16T10:00:00Z',
    'location': 'Zoom',
    'participants': []
}

print('Calling SmartFetcherAgent.fetch_all (local, no HTTP)...')
result = agent.fetch_all('What is this meeting about?', meeting)
print('Result:')
print(result)

# Restore requests.post just in case
requests.post = original_post

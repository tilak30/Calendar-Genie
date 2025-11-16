import os
import time
from agents.smart_fetcher import SmartFetcherAgent

# Ensure the fetcher points to local RAG server we started on port 5002
os.environ['RAG_SERVER_URL'] = 'http://127.0.0.1:5002'

# Small delay to ensure server is up
time.sleep(1)

agent = SmartFetcherAgent()
meeting = {
    'title': 'Test Meeting',
    'description': 'A short test meeting',
    'start_time': '2025-11-16T10:00:00Z',
    'location': 'Zoom',
    'participants': []
}

print('Calling SmartFetcherAgent.fetch_all...')
result = agent.fetch_all('What is this meeting about?', meeting)
print('Result:')
print(result)

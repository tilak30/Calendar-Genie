import os
import json
import requests
from openai import OpenAI

class SmartFetcherAgent:
    """
    Agent that decides:
    1. Do we need THEORY from RAG?
    2. Do we need PRACTICE/EXAMPLES from web?
    3. Or MEETINGS data from meeting.json?
    
    Then fetches from appropriate sources
    """
    
    def __init__(self, rag_server_url: str | None = None):
        # Allow explicit injection of the RAG server URL (useful for tests
        # and to avoid relying on global env side-effects).
        self.rag_server_url = rag_server_url or os.getenv("RAG_SERVER_URL", "http://localhost:5002")

        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY")
        )
        self.model = "anthropic/claude-3-5-sonnet"
        self.meetings = self._load_meetings()
    
    def _load_meetings(self) -> list:
        """Load all meetings from meeting.json"""
        try:
            with open('meeting.json', 'r') as f:
                data = json.load(f)
                return data.get('meetings', [])
        except Exception as e:
            print(f"Error loading meetings: {e}")
            return []
    
    def decide_what_to_fetch(self, query: str, meeting: dict) -> dict:
        """Agent decides: theory? practice? both?"""
        
        prompt = f"""Meeting: {meeting['title']}
Query: "{query}"

Agent decides what to fetch:
- "theory": Get underlying concepts/theory
- "practice": Get examples/exercises/how-to
- "both": Need both theory and practice

Respond JSON:
{{"fetch_type": "theory|practice|both"}}"""
        
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}]
        )
        
        import json
        response = json.loads(completion.choices[0].message.content)
        return response
    
    def fetch_all(self, query: str, meeting: dict) -> dict:
        """Fetch content based on agent's decision"""
        
        # Step 1: Agent decides what to fetch
        # fetch_plan = self.decide_what_to_fetch(query, meeting)
        # fetch_type = fetch_plan.get("fetch_type", "both")
        
        # Step 2: Fetch from appropriate sources
        content = {}
        
        # Check if query is asking about meetings
        meetings_content = self._fetch_from_meetings(query)
        if meetings_content:
            content["meetings"] = meetings_content
        
        # if fetch_type in ["theory", "both"]:
            # Fetch from Person 3 RAG
        rag_content = self._fetch_from_rag(query, meeting)
        content["rag"] = rag_content
        
        # if fetch_type in ["practice", "both"]:
            # Fetch from Web
        web_content = self._fetch_from_web(query)
        content["web"] = web_content
        
        return content
    
    def _fetch_from_meetings(self, query: str) -> str:
        """Search meeting.json for relevant meetings"""
        if not self.meetings:
            return ""
        
        # Keywords that indicate meeting-related queries
        meeting_keywords = ['meeting', 'upcoming', 'schedule', 'calendar', 'events', 'next', 'attend', 'class', 'office hours']
        query_lower = query.lower()
        
        is_meeting_query = any(kw in query_lower for kw in meeting_keywords)
        
        if not is_meeting_query:
            return ""
        
        # Build list of meetings with timestamps for sorting
        from datetime import datetime
        
        try:
            meetings_with_time = [
                (meeting, datetime.fromisoformat(meeting['start_time'].replace('Z', '+00:00')))
                for meeting in self.meetings
            ]
            # Sort by start time
            meetings_with_time.sort(key=lambda x: x[1])
        except Exception as e:
            print(f"Error parsing meeting times: {e}")
            meetings_with_time = [(m, None) for m in self.meetings]
        
        # Extract count if user asked for "next N"
        import re
        match = re.search(r'next\s+(\d+)', query_lower)
        count = int(match.group(1)) if match else 3  # Default to next 3
        
        # Get upcoming meetings
        upcoming = meetings_with_time[:count]
        
        meetings_text = "UPCOMING MEETINGS:\n"
        for meeting, _ in upcoming:
            meetings_text += f"""
- Title: {meeting['title']}
  Date/Time: {meeting['start_time']}
  Location: {meeting['location']}
  Description: {meeting['description']}
  Participants: {', '.join([p['name'] for p in meeting.get('participants', [])])}
"""
        
        return meetings_text
    
    def _fetch_from_rag(self, query: str, meeting: dict) -> str:
        """
        Call the local RAG API server (main.py).
        """
        try:
            # The RAG server expects meeting_name and meeting_description
            payload = {
                "meeting_name": meeting.get("title", query),
                "meeting_description": meeting.get("description", "")
            }
            # Use the instance's configured RAG server URL
            endpoint = f"{self.rag_server_url.rstrip('/')}/api/search"
            response = requests.post(endpoint, json=payload, timeout=10)

            if response.status_code == 200:
                data = response.json()
                return data.get("answer", "")
            else:
                print(f"RAG error: {response.status_code} - {response.text}")
                return ""

        except Exception as e:
            print(f"Error calling RAG server: {e}")
            return ""
    
    def _fetch_from_web(self, query: str) -> str:
        # """
        # Search web using Tavily API
        
        # Request:
        # POST https://api.tavily.com/search
        # JSON: {"api_key": "...", "query": "...", "max_results": 5}
        
        # Response:
        # {"results": [{"content": "..."}, ...]}
        # """
        # try:
        #     response = requests.post(
        #         "https://api.tavily.com/search",
        #         json={
        #             "api_key": os.getenv("TAVILY_API_KEY"),
        #             "query": query,
        #             "max_results": 3
        #         },
        #         timeout=10
        #     )
            
        #     if response.status_code == 200:
        #         data = response.json()
        #         # Extract content from all results
        #         content = "\n\n".join([
        #             result.get("content", "")
        #             for result in data.get("results", [])
        #         ])
        #         return content
        #     else:
        #         return ""
        
        # except Exception as e:
        #     print(f"Error calling Tavily: {e}")
        #     # Fallback hardcoded content
            return """Best practices for studying data structures:
1. Start with fundamentals and visualizations
2. Implement from scratch multiple times
3. Practice with different test cases
4. Study time/space complexity
5. Review common interview questions"""

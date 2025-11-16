import os
import requests
from openai import OpenAI

class SmartFetcherAgent:
    """
    Agent that decides:
    1. Do we need THEORY from RAG?
    2. Do we need PRACTICE/EXAMPLES from web?
    3. Or both?
    
    Then fetches from appropriate sources
    """
    
    def __init__(self):
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY")
        )
        self.model = "anthropic/claude-3-5-sonnet"
    
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
        
        # if fetch_type in ["theory", "both"]:
            # Fetch from Person 3 RAG
        rag_content = self._fetch_from_rag(query)
        content["rag"] = rag_content
        
        # if fetch_type in ["practice", "both"]:
            # Fetch from Web
        web_content = self._fetch_from_web(query)
        content["web"] = web_content
        
        return content
    
    def _fetch_from_rag(self, query: str) -> str:
        # """
        # Call Person 3's RAG API

        # Request:
        # POST http://localhost:5002/api/rag-query
        # JSON: {"query": "..."}

        # Response:
        # {"answer": "...content from documents..."}
        # """
        # try:
        #     response = requests.post(
        #         "http://localhost:5002/api/rag-query",
        #         json={"query": query},
        #         timeout=10
        #     )
            
        #     if response.status_code == 200:
        #         data = response.json()
        #         return data.get("answer", "")
        #     else:
        #         print(f"RAG error: {response.status_code}")
        #         return ""
        
        # except Exception as e:
        #     print(f"Error calling RAG: {e}")
        #     # Fallback hardcoded content for testing
            return """Binary Search Trees (BST):
- Left child < Parent < Right child
- Used for efficient searching (O(log n) average)
- Self-balancing variants: AVL trees, Red-Black trees
- Applications: Database indexing, file systems"""
    
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

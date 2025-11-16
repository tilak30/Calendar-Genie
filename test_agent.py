#!/usr/bin/env python3
"""
Test script for enhanced SmartFetcherAgent.
Shows the agent's planning, execution, and reflection phases.
"""

import sys
import json
from agents.smart_fetcher import SmartFetcherAgent

def test_agent():
    """Test the agent with different query types."""
    
    agent = SmartFetcherAgent()
    
    # Mock meeting context
    meeting = {
        "title": "Data Structures - Review Session",
        "description": "AVL trees & rotation walkthrough",
        "start_time": "2025-11-15T12:00:00Z",
        "location": "Room 301"
    }
    
    test_queries = [
        "What meetings do I have tomorrow?",
        "Explain AVL tree rotations in detail",
        "What is Project Alpha about?",
        "Who is attending the cloud computing meeting?",
        "Tell me about upcoming meetings this week"
    ]
    
    print("=" * 70)
    print("SmartFetcherAgent - Enhanced ReAct Agent Test")
    print("=" * 70)
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n\n{'─' * 70}")
        print(f"Test {i}: {query}")
        print('─' * 70)
        
        try:
            result = agent.fetch_all(query, meeting)
            
            # Show execution trace
            print("\n" + agent.get_execution_summary())
            
            # Show results
            print("\n📊 Results:")
            print(f"  • Meetings found: {len(result.get('meetings_structured', []))}")
            print(f"  • RAG content: {len(result.get('rag', ''))} chars")
            print(f"  • Success: {result.get('success', False)}")
            
            if result.get('meetings'):
                print(f"\n📅 Meetings Preview:")
                preview = result['meetings'][:200]
                print(f"  {preview}...")
            
            if result.get('rag'):
                print(f"\n📚 RAG Preview:")
                preview = result['rag'][:200]
                print(f"  {preview}...")
                
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n\n" + "=" * 70)
    print("Query History Summary:")
    print("=" * 70)
    for i, h in enumerate(agent.query_history, 1):
        print(f"{i}. {h['query'][:50]}")
        print(f"   Strategy: {h['plan'].get('strategy')} | Success: {h.get('success')}")

if __name__ == "__main__":
    test_agent()

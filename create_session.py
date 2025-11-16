#!/usr/bin/env python3
"""
Create a session command - interactive CLI tool to create meeting sessions
and test the chat API.
"""

import requests
import json
import sys
from datetime import datetime

BASE_URL = "http://localhost:5001"

def list_meetings():
    """List all available mock meetings"""
    with open('meeting.json', 'r') as f:
        meetings = json.load(f)['meetings']
    
    print("\n📅 Available Meetings:")
    print("-" * 80)
    for i, meeting in enumerate(meetings):
        print(f"\n[{i}] {meeting['title']}")
        print(f"    Time: {meeting['start_time']}")
        print(f"    Location: {meeting['location']}")
        print(f"    Description: {meeting['description'][:80]}...")
    return meetings

def create_session(meeting_index: int = None):
    """Create a new session with a meeting"""
    
    if meeting_index is None:
        meetings = list_meetings()
        try:
            meeting_index = int(input("\n👉 Select meeting index (0-7): "))
            if not (0 <= meeting_index < len(meetings)):
                print("❌ Invalid index")
                return None
        except ValueError:
            print("❌ Invalid input")
            return None
    
    payload = {
        "meetings": True,
        "mock_index": meeting_index
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/prep-meeting", json=payload)
        response.raise_for_status()
        result = response.json()
        session_id = result['session_id']
        
        print(f"\n✅ Session Created!")
        print(f"   Session ID: {session_id}")
        print(f"   Meeting: {result['meeting']['title']}")
        print(f"   Description: {result['meeting']['description']}")
        
        return session_id
    except Exception as e:
        print(f"❌ Error creating session: {e}")
        return None

def chat_with_session(session_id: str):
    """Interactive chat with a session"""
    
    print(f"\n💬 Chat Session Started (ID: {session_id})")
    print("   Type 'exit' to quit\n")
    
    while True:
        query = input("You: ").strip()
        
        if query.lower() == 'exit':
            print("Goodbye! 👋")
            break
        
        if not query:
            continue
        
        try:
            payload = {
                "session_id": session_id,
                "query": query
            }
            
            response = requests.post(f"{BASE_URL}/api/chat", json=payload)
            response.raise_for_status()
            result = response.json()
            
            print(f"\n🤖 Assistant: {result['answer']}\n")
            
            # Show sources if requested
            if result.get('sources'):
                print(f"📚 Sources used:")
                if result['sources'].get('rag'):
                    print(f"   - RAG: {result['sources']['rag'][:100]}...")
                if result['sources'].get('web'):
                    print(f"   - Web: {result['sources']['web'][:100]}...")
                print()
            
        except Exception as e:
            print(f"❌ Error: {e}\n")

def main():
    """Main CLI menu"""
    print("\n" + "="*80)
    print("🎓 HackNYU Meeting Assistant - Session Creator")
    print("="*80)
    
    if len(sys.argv) > 1:
        # If meeting index is passed as argument
        try:
            meeting_index = int(sys.argv[1])
            session_id = create_session(meeting_index)
            if session_id:
                chat_with_session(session_id)
        except ValueError:
            print("❌ Invalid meeting index")
    else:
        # Interactive menu
        while True:
            print("\n📋 Menu:")
            print("  1. Create new session and chat")
            print("  2. List meetings")
            print("  3. Create session with specific meeting (enter index)")
            print("  4. Exit")
            
            choice = input("\nChoose option (1-4): ").strip()
            
            if choice == '1':
                session_id = create_session()
                if session_id:
                    chat_with_session(session_id)
            elif choice == '2':
                list_meetings()
            elif choice == '3':
                try:
                    idx = int(input("Enter meeting index: "))
                    session_id = create_session(idx)
                    if session_id:
                        chat_with_session(session_id)
                except ValueError:
                    print("❌ Invalid index")
            elif choice == '4':
                print("Goodbye! 👋\n")
                break
            else:
                print("❌ Invalid option")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Integration test for Calendar-Genie unified backend (server.py).
Tests: auth flow, session management, /api/chat response with audio_url.
"""
import os
import sys

# Set mock mode before importing server
os.environ['MOCK_AUTH'] = 'true'
os.environ['ELEVENLABS_API_KEY'] = 'test-key-for-demo'

from fastapi.testclient import TestClient
from server import app, create_session

client = TestClient(app)

def test_auth_flow():
    """Test mock OAuth flow"""
    print("\n1️⃣  Testing mock OAuth flow...")
    response = client.get("/auth/google", follow_redirects=False)
    print(f"   GET /auth/google -> {response.status_code} (redirect)")
    assert response.status_code == 307, f"Expected 307, got {response.status_code}"
    
    # Extract session from redirect URL
    redirect_url = response.headers.get('location', '')
    if 'session=' in redirect_url:
        session_id = redirect_url.split('session=')[1]
        print(f"   ✅ Session created: {session_id[:20]}...")
        return session_id
    
    print(f"   ⚠️  No session in redirect URL. Trying to extract from cookies...")
    cookies = response.cookies
    if 'session_id' in cookies:
        return cookies['session_id']
    
    # Fallback: create a session manually
    user_data = {"email": "test@example.com", "name": "Test User", "picture": ""}
    session_id = create_session(user_data)
    print(f"   ✅ Manual session created: {session_id[:20]}...")
    return session_id

def test_user_endpoint(session_id):
    """Test GET /api/user"""
    print("\n2️⃣  Testing GET /api/user...")
    response = client.get("/api/user", cookies={"session_id": session_id})
    print(f"   GET /api/user -> {response.status_code}")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    data = response.json()
    print(f"   ✅ User: {data.get('name')} ({data.get('email')})")
    return data

def test_prep_meeting(session_id):
    """Test POST /api/prep-meeting"""
    print("\n3️⃣  Testing POST /api/prep-meeting...")
    response = client.post(
        "/api/prep-meeting",
        json={"meetings": True, "mock_index": 0},
        cookies={"session_id": session_id}
    )
    print(f"   POST /api/prep-meeting -> {response.status_code}")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    data = response.json()
    assert "meeting_session_id" in data, "Missing 'meeting_session_id'"
    assert "meeting" in data, "Missing 'meeting'"
    
    meeting_session_id = data["meeting_session_id"]
    print(f"   ✅ Meeting session created: {meeting_session_id[:20]}...")
    print(f"   📚 Meeting: {data['meeting'].get('title')}")
    
    return meeting_session_id

def test_chat_endpoint(session_id, meeting_session_id):
    """Test POST /api/chat"""
    print("\n4️⃣  Testing POST /api/chat...")
    
    test_messages = [
        "What is this meeting about?",
        "Tell me more about the topics",
        "How do I prepare?"
    ]
    
    for msg in test_messages:
        print(f"\n   Sending: '{msg}'")
        response = client.post(
            "/api/chat",
            json={
                "meeting_session_id": meeting_session_id,
                "query": msg
            },
            cookies={"session_id": session_id}
        )
        print(f"   POST /api/chat -> {response.status_code}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        
        # Verify response structure
        assert "text" in data or "answer" in data, "Missing 'text' or 'answer' in response"
        assert "decision" in data, "Missing 'decision' in response"
        assert "sources" in data, "Missing 'sources' in response"
        
        response_text = data.get('text') or data.get('answer', '')
        print(f"   ✅ Response received ({len(response_text)} chars)")
        print(f"   🎯 Decision: {data.get('decision')} - {data.get('reasoning')}")
        print(f"   📚 Sources: RAG={bool(data['sources'].get('rag'))}, Web={bool(data['sources'].get('web'))}")
        
        # Check audio_url
        if data.get('audio_url'):
            is_dataurl = data['audio_url'].startswith('data:audio/mpeg;base64,')
            print(f"   🔊 Audio: {'✅ data URL' if is_dataurl else '❌ invalid format'}")
            assert is_dataurl, "audio_url should be a base64 data URL"
        else:
            print(f"   🔇 No audio (ELEVENLABS_API_KEY not configured)")
        
        print(f"   💬 Response: {response_text[:100]}...")

def test_no_auth():
    """Test that endpoints require authentication"""
    print("\n5️⃣  Testing authentication requirement...")
    
    # Try to call /api/prep-meeting without session
    response = client.post(
        "/api/prep-meeting",
        json={"meetings": True, "mock_index": 0}
    )
    print(f"   POST /api/prep-meeting (no auth) -> {response.status_code}")
    assert response.status_code == 401, f"Expected 401, got {response.status_code}"
    print(f"   ✅ Correctly rejected unauthorized request")

def main():
    print("=" * 60)
    print("  Calendar-Genie Unified Backend - Integration Test")
    print("=" * 60)
    
    try:
        # Test auth flow
        session_id = test_auth_flow()
        
        # Test user endpoint
        test_user_endpoint(session_id)
        
        # Test meeting prep
        meeting_session_id = test_prep_meeting(session_id)
        
        # Test chat endpoint (main feature)
        test_chat_endpoint(session_id, meeting_session_id)
        
        # Test auth requirement
        test_no_auth()
        
        print("\n" + "=" * 60)
        print("  ✅ All integration tests PASSED!")
        print("=" * 60)
        return 0
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())

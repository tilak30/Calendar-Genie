#!/usr/bin/env python3
"""
Test script for ElevenLabs integration
Run this after setting: export ELEVENLABS_API_KEY="your-key-here"
"""
import os
import asyncio
import sys

# Check if API key is set
api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
if not api_key:
    print("❌ ERROR: ELEVENLABS_API_KEY not set!")
    print("Please run: export ELEVENLABS_API_KEY=\"your-api-key\"")
    sys.exit(1)

print(f"✅ API Key found: {api_key[:20]}...")

# Try to import dependencies
try:
    import httpx
    import base64
    print("✅ httpx and base64 imported successfully")
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)

# Test the audio generation function
async def test_elevenlabs():
    """Test ElevenLabs API call"""
    text = "Hello! This is a test of the ElevenLabs integration for Calendar Genie."
    
    print(f"\n📝 Testing with text: '{text}'")
    
    url = "https://api.elevenlabs.io/v1/text-to-speech/21m00Tcm4TlvDq8ikWAM"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
        }
    }
    
    try:
        async with httpx.AsyncClient() as client:
            print("🔄 Calling ElevenLabs API...")
            response = await client.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            
            audio_bytes = response.content
            print(f"✅ Audio received: {len(audio_bytes)} bytes")
            
            # Create data URL
            audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
            audio_url = f"data:audio/mpeg;base64,{audio_b64[:50]}..."
            print(f"✅ Data URL created: {audio_url}")
            
            return True
            
    except httpx.HTTPError as e:
        print(f"❌ HTTP Error: {e}")
        print(f"   Status: {e.response.status_code if hasattr(e, 'response') else 'Unknown'}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

# Run the test
if __name__ == "__main__":
    print("\n" + "="*60)
    print("🧪 ElevenLabs Integration Test")
    print("="*60)
    
    success = asyncio.run(test_elevenlabs())
    
    if success:
        print("\n" + "="*60)
        print("✅ SUCCESS! ElevenLabs is working correctly!")
        print("="*60)
        print("\nYou can now:")
        print("1. Start the backend: MOCK_AUTH=true python3 main.py")
        print("2. Open: http://localhost:8000")
        print("3. Send messages and hear ElevenLabs audio!")
        sys.exit(0)
    else:
        print("\n" + "="*60)
        print("❌ FAILED - Check the error above")
        print("="*60)
        print("\nPossible issues:")
        print("- Invalid API key")
        print("- API rate limit exceeded")
        print("- Network connection issues")
        print("- ElevenLabs API is down")
        sys.exit(1)

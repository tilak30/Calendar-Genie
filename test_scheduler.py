#!/usr/bin/env python3
"""
Test the SchedulerAgent with various scheduling scenarios.
"""

import json
import copy
from dotenv import load_dotenv
from datetime import datetime
from agents.scheduler_agent import SchedulerAgent

def test_scheduler():
    """Test the scheduler agent with different requests."""
    load_dotenv()
    agent = SchedulerAgent()
    
    # Monkeypatch LLM calls for offline testing
    def stub_analyze(query: str, ctx: dict):
        q = query.lower()
        def iso(year, month, day, hour, minute=0):
            return datetime(year, month, day, hour, minute).strftime("%Y-%m-%dT%H:%M:%SZ")
        # Default 1h
        if "november 19" in q and "8am" in q:
            return {"is_scheduling": True, "time_slot": {"start_time": iso(2025,11,19,8), "end_time": iso(2025,11,19,9)}, "mentioned_details": {}}
        if "nov 19" in q and "9am" in q and "30" in q:
            return {"is_scheduling": True, "time_slot": {"start_time": iso(2025,11,19,9), "end_time": iso(2025,11,19,9,30)}, "mentioned_details": {"title": "Team standup", "location":"Room 201"}}
        if "november 20" in q and "10am" in q:
            return {"is_scheduling": True, "time_slot": {"start_time": iso(2025,11,20,10), "end_time": iso(2025,11,20,11)}, "mentioned_details": {"title": "Review Meeting"}}
        if "nov 15" in q and "3:15" in q:
            return {"is_scheduling": True, "time_slot": {"start_time": iso(2025,11,15,15,15), "end_time": iso(2025,11,15,15,45)}, "mentioned_details": {"title": "Calibration Sync"}}
        return {"is_scheduling": False, "reasoning": "stub default"}

    def stub_gather(query: str, intent: dict, ctx: dict):
        ts = intent.get("time_slot", {})
        return {
            "complete": True,
            "meeting_id": f"meeting_stub_{ts.get('start_time','now').replace(':','').replace('-','')}",
            "title": intent.get("mentioned_details", {}).get("title", "New Meeting"),
            "description": "Stubbed details",
            "location": intent.get("mentioned_details", {}).get("location", "TBD"),
            "start_time": ts.get("start_time"),
            "end_time": ts.get("end_time"),
            "participants": [{"email": "you@nyu.edu", "name": "You", "is_organizer": True}]
        }

    agent._analyze_scheduling_intent = stub_analyze  # type: ignore
    agent._gather_meeting_details = stub_gather      # type: ignore
    
    context = {
        "current_meeting": {
            "title": "Test Context",
            "description": "For testing"
        },
        "user": {
            "email": "you@nyu.edu",
            "name": "You"
        }
    }
    
    print("=" * 70)
    print("SchedulerAgent Test Suite")
    print("=" * 70)
    
    # Test 1: Simple scheduling request
    print("\n\n📅 Test 1: Simple scheduling request")
    print("─" * 70)
    query1 = "Schedule a meeting on November 19 at 8am"
    result1 = agent.handle_scheduling_request(query1, context)
    print(f"Query: {query1}")
    print(f"Action: {result1['action']}")
    print(f"Message:\n{result1['message']}")
    if result1.get('trace'):
        print(f"\n{result1['trace']}")
    
    # Test 2: Detailed scheduling request
    print("\n\n📅 Test 2: Detailed scheduling request")
    print("─" * 70)
    query2 = "Book a team standup meeting on Nov 19 at 9am for 30 minutes in Room 201 with Alice and Bob"
    result2 = agent.handle_scheduling_request(query2, context)
    print(f"Query: {query2}")
    print(f"Action: {result2['action']}")
    print(f"Message:\n{result2['message']}")
    if result2.get('trace'):
        print(f"\n{result2['trace']}")
    
    # Test 3: Confirm scheduling (if pending)
    if agent.pending_confirmation:
        print("\n\n✅ Test 3: Confirming schedule")
        print("─" * 70)
        confirm_result = agent.confirm_and_schedule("yes")
        print(f"Confirmation: yes")
        print(f"Action: {confirm_result['action']}")
        print(f"Message:\n{confirm_result['message']}")
        if confirm_result.get('trace'):
            print(f"\n{confirm_result['trace']}")
    
    # Test 4: Conflict detection
    print("\n\n⚠️  Test 4: Conflict detection")
    print("─" * 70)
    query4 = "Schedule a review meeting on November 20 at 10am"
    result4 = agent.handle_scheduling_request(query4, context)
    print(f"Query: {query4}")
    print(f"Action: {result4['action']}")
    print(f"Message:\n{result4['message']}")
    if result4.get('conflicts'):
        print(f"Conflicts found: {len(result4['conflicts'])}")
    if result4.get('trace'):
        print(f"\n{result4['trace']}")
    
    # Test 5: Non-scheduling query
    print("\n\n❌ Test 5: Non-scheduling query")
    print("─" * 70)
    query5 = "What meetings do I have tomorrow?"
    result5 = agent.handle_scheduling_request(query5, context)
    print(f"Query: {query5}")
    print(f"Action: {result5['action']}")
    print(f"Message:\n{result5['message']}")
    
    print("\n\n" + "=" * 70)
    print("Test Suite Complete")
    print("=" * 70)


def test_replacement_flow():
    """End-to-end replacement flow: conflict → replace → confirm → verify → restore file."""
    load_dotenv()
    agent = SchedulerAgent()
    # Monkeypatch for offline
    def stub_analyze(query: str, ctx: dict):
        q = query.lower()
        def iso(year, month, day, hour, minute=0):
            return datetime(year, month, day, hour, minute).strftime("%Y-%m-%dT%H:%M:%SZ")
        if "nov 15" in q and "3:15" in q:
            return {"is_scheduling": True, "time_slot": {"start_time": iso(2025,11,15,15,15), "end_time": iso(2025,11,15,15,45)}, "mentioned_details": {"title": "Calibration Sync"}}
        return {"is_scheduling": False}
    def stub_gather(query: str, intent: dict, ctx: dict):
        ts = intent.get("time_slot", {})
        return {
            "complete": True,
            "meeting_id": f"meeting_stub_replace_{ts.get('start_time','now').replace(':','').replace('-','')}",
            "title": intent.get("mentioned_details", {}).get("title", "Replacement Meeting"),
            "description": "Stubbed replacement",
            "location": "TBD",
            "start_time": ts.get("start_time"),
            "end_time": ts.get("end_time"),
            "participants": [{"email": "you@nyu.edu", "name": "You", "is_organizer": True}]
        }
    agent._analyze_scheduling_intent = stub_analyze  # type: ignore
    agent._gather_meeting_details = stub_gather      # type: ignore

    context = {
        "current_meeting": {"title": "Test Context", "description": "For testing"},
        "user": {"email": "you@nyu.edu", "name": "You"}
    }

    # Backup meetings file
    with open(agent.meetings_file, "r") as f:
        orig = json.load(f)

    try:
        print("\n\n🧪 Replacement Flow Test")
        print("-" * 70)
        # This time overlaps the existing Network Security meeting (2025-11-15 15:00-16:00Z)
        query = "Schedule calibration sync on Nov 15 at 3:15pm for 30 minutes"
        res1 = agent.handle_scheduling_request(query, context)
        print(f"Initial Action: {res1.get('action')}")
        print(res1.get('message', ''))

        # Proceed with replacement if conflict and not organizer
        res2 = agent.process_followup("replace", context)
        if res2:
            print(f"Follow-up Action: {res2.get('action')}")
            print(res2.get('message', ''))

        # If pending confirmation, confirm replacement
        if agent.pending_confirmation:
            res3 = agent.confirm_and_schedule("yes")
            print(f"Confirm Action: {res3.get('action')}")
            print(res3.get('message', ''))

            # Verify that replaced meeting id is gone if one was targeted
            new_data = None
            with open(agent.meetings_file, "r") as f:
                new_data = json.load(f)
            old_ids = {m.get('meeting_id') for m in orig.get('meetings', [])}
            new_ids = {m.get('meeting_id') for m in new_data.get('meetings', [])}
            removed = list(old_ids - new_ids)
            added = list(new_ids - old_ids)
            print(f"Removed meeting IDs (due to replacement): {removed}")
            print(f"Added meeting IDs: {added}")

        # Also check the 'another time' branch quickly
        res4 = agent.handle_scheduling_request(query, context)
        res5 = agent.process_followup("another time", context)
        if res5:
            print(f"Another-time Action: {res5.get('action')}")
            print(res5.get('message', ''))

    finally:
        # Restore original meetings file to avoid side effects
        with open(agent.meetings_file, "w") as f:
            json.dump(orig, f, indent=2)
        print("\n(Restored meeting.json to original state)")

if __name__ == "__main__":
    test_scheduler()
    test_replacement_flow()

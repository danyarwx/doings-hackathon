"""
simulate_meeting.py
===================
Simulates a real-time product planning meeting by replaying a realistic
transcript — segment by segment — into the extraction server, exactly as
whisper.cpp would do it during a live call.

Usage
-----
    python simulate_meeting.py                          # default server
    python simulate_meeting.py --api-url http://localhost:8000
    python simulate_meeting.py --speed 2.0              # 2× faster replay
    python simulate_meeting.py --session my-meeting-01  # custom session id

Requires
--------
    pip install httpx
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import datetime

import httpx

# ---------------------------------------------------------------------------
# Simulated meeting transcript
# ---------------------------------------------------------------------------
# Scenario: "Nova" mobile app — sprint planning + requirements meeting
# Attendees: Sarah (PM), Marcus (Backend), Priya (Frontend), Dev (QA)
# The transcript is split into segments as whisper.cpp would produce them.
# ---------------------------------------------------------------------------

MEETING_SEGMENTS = [
    # --- Opening ---
    {
        "text": "Alright everyone, let's get started. Sarah here, I'll be facilitating today's sprint planning for the Nova app.",
        "speaker": "Sarah",
        "gap_after": 1.8,
    },
    {
        "text": "Quick heads up — we have a hard deadline of June 30th for the beta launch, so today we need to lock in requirements for the authentication and onboarding flows.",
        "speaker": "Sarah",
        "gap_after": 2.1,
    },
    # --- Auth discussion ---
    {
        "text": "Marcus, can you walk us through the backend status for user authentication?",
        "speaker": "Sarah",
        "gap_after": 1.2,
    },
    {
        "text": "Sure. The OAuth 2.0 integration with Google and Apple is about 60% done. The main blocker right now is the JWT refresh token rotation — I need a decision on the expiry window.",
        "speaker": "Marcus",
        "gap_after": 2.0,
    },
    {
        "text": "What are the options? Give us the tradeoffs.",
        "speaker": "Sarah",
        "gap_after": 1.0,
    },
    {
        "text": "Option A is 15-minute access tokens with 30-day refresh. That's the most secure but means more round-trips. Option B is 1-hour access tokens — simpler but a bigger window if a token is stolen.",
        "speaker": "Marcus",
        "gap_after": 2.5,
    },
    {
        "text": "Given our users are mostly on mobile networks, I'd vote for Option A. Priya, does that cause any issues on the frontend?",
        "speaker": "Dev",
        "gap_after": 1.5,
    },
    {
        "text": "It adds a bit of complexity to the token refresh logic, but nothing we can't handle with a proper interceptor. I can build that into the API client layer.",
        "speaker": "Priya",
        "gap_after": 2.0,
    },
    {
        "text": "Okay, we'll go with Option A — 15-minute access tokens. Marcus, please document the token schema and share it with the team by Friday.",
        "speaker": "Sarah",
        "gap_after": 1.8,
    },
    # --- Onboarding flow ---
    {
        "text": "Now let's talk onboarding. The current design has 4 screens — welcome, permissions, profile setup, and the first-run tutorial. Priya, where are we?",
        "speaker": "Sarah",
        "gap_after": 1.5,
    },
    {
        "text": "Welcome and permissions screens are done and tested. Profile setup is blocked waiting on the avatar upload API from Marcus. The tutorial isn't started yet.",
        "speaker": "Priya",
        "gap_after": 2.2,
    },
    {
        "text": "The avatar upload endpoint — I can have that ready by Wednesday. It'll support JPEG and PNG, max 5 megabytes, and I'll return a CDN URL.",
        "speaker": "Marcus",
        "gap_after": 1.8,
    },
    {
        "text": "We should also support WebP. A lot of modern phones default to WebP for camera output.",
        "speaker": "Dev",
        "gap_after": 1.2,
    },
    {
        "text": "Good catch. Adding WebP to the spec. Marcus, can you include that?",
        "speaker": "Sarah",
        "gap_after": 0.9,
    },
    {
        "text": "Yeah, no problem. JPEG, PNG, and WebP all under 5 MB.",
        "speaker": "Marcus",
        "gap_after": 1.5,
    },
    # --- Push notifications ---
    {
        "text": "Let's move to push notifications. This one is high priority — marketing is asking for it from day one of beta.",
        "speaker": "Sarah",
        "gap_after": 1.6,
    },
    {
        "text": "We need to integrate Firebase Cloud Messaging. I haven't started this yet but I'd estimate 3 days of work on the backend. I also need the notification payload schema agreed before I start.",
        "speaker": "Marcus",
        "gap_after": 2.3,
    },
    {
        "text": "The permissions screen already asks for notification access, so we're covered on the iOS and Android side. But we need a preference screen so users can opt out of specific notification types.",
        "speaker": "Priya",
        "gap_after": 2.0,
    },
    {
        "text": "Agreed. Users must be able to turn off promotional notifications independently from transactional ones — that's a GDPR requirement actually.",
        "speaker": "Dev",
        "gap_after": 1.8,
    },
    {
        "text": "Good point Dev. Let's call that a hard requirement — granular notification preferences, with promotional and transactional as separate toggles, before beta launch.",
        "speaker": "Sarah",
        "gap_after": 2.2,
    },
    # --- Performance + QA ---
    {
        "text": "I want to raise a performance concern. The feed screen is currently loading in about 2.8 seconds on a 4G connection in our test environment. That's too slow.",
        "speaker": "Dev",
        "gap_after": 2.1,
    },
    {
        "text": "What's the target? I was assuming under 2 seconds.",
        "speaker": "Priya",
        "gap_after": 0.9,
    },
    {
        "text": "We should target under 1.5 seconds for the initial load, with skeleton screens while content loads. That matches what users expect from comparable apps.",
        "speaker": "Dev",
        "gap_after": 2.0,
    },
    {
        "text": "The main issue is the feed API — it's returning too much data. I'll add server-side pagination with a default page size of 20 items. That should cut the payload by 70 percent.",
        "speaker": "Marcus",
        "gap_after": 2.5,
    },
    {
        "text": "Perfect. Priya, can you add skeleton loaders to the feed screen while we wait for Marcus's pagination fix?",
        "speaker": "Sarah",
        "gap_after": 1.3,
    },
    {
        "text": "Yes, I'll do that. I'll also add an offline empty state so the app doesn't crash with no connection.",
        "speaker": "Priya",
        "gap_after": 1.8,
    },
    # --- Wrap up ---
    {
        "text": "Okay, let's summarize. We've decided on 15-minute JWT access tokens. Marcus is delivering the avatar upload API Wednesday and will add WebP support. Push notifications need FCM integration and a preference screen with granular toggles.",
        "speaker": "Sarah",
        "gap_after": 2.0,
    },
    {
        "text": "Feed performance target is 1.5 seconds — Marcus is adding pagination, Priya is adding skeleton loaders. Dev, please write regression tests for the auth flow and feed performance by end of next week.",
        "speaker": "Sarah",
        "gap_after": 2.0,
    },
    {
        "text": "Will do. I'll also set up a performance baseline in CI so we catch regressions automatically.",
        "speaker": "Dev",
        "gap_after": 1.5,
    },
    {
        "text": "Great. Next sync is Thursday 10am. Any blockers before then, ping the #nova-sprint channel. Thanks everyone.",
        "speaker": "Sarah",
        "gap_after": 0.0,
    },
]

# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------

async def simulate(api_url: str, session_id: str, speed: float) -> None:
    """Stream transcript segments to the extraction server."""

    print(f"\n🎙  Nova App — Sprint Planning Meeting Simulation")
    print(f"   Session  : {session_id}")
    print(f"   Server   : {api_url}")
    print(f"   Segments : {len(MEETING_SEGMENTS)}")
    print(f"   Speed    : {speed}×\n")
    print("─" * 60)

    start_real   = time.time()
    current_ts   = 0.0          # simulated meeting clock (seconds)

    async with httpx.AsyncClient(timeout=30.0) as client:
        for idx, seg_def in enumerate(MEETING_SEGMENTS):
            seg_id     = f"seg-{idx+1:03d}"
            duration   = len(seg_def["text"]) / 15.0   # rough 15 chars/sec speaking rate
            end_ts     = current_ts + duration

            payload = {
                "id":         seg_id,
                "session_id": session_id,
                "text":       seg_def["text"],
                "start_s":    round(current_ts, 2),
                "end_s":      round(end_ts, 2),
                "lang":       "en",
            }

            # --- Print the "live subtitle" line ---
            elapsed_real = time.time() - start_real
            print(f"[{current_ts:6.1f}s]  {seg_def['speaker']:8s}  {seg_def['text'][:80]}")

            # --- POST to server ---
            try:
                resp = await client.post(f"{api_url}/segments", json=payload)
                resp.raise_for_status()
                result = resp.json()

                # Show extraction result if it fired
                if "data" in result:
                    _print_extraction(result)

            except httpx.HTTPStatusError as e:
                print(f"           ⚠  HTTP {e.response.status_code}: {e.response.text[:120]}")
            except httpx.RequestError as e:
                print(f"           ⚠  Connection error: {e}")
                print(f"           Is the server running at {api_url}?")
                return

            # Advance simulated clock
            current_ts = end_ts + seg_def["gap_after"]

            # Pace the replay by gap_after / speed
            delay = seg_def["gap_after"] / speed
            if delay > 0:
                await asyncio.sleep(delay)

        # --- Flush remaining buffer ---
        print("\n─" * 60)
        print("📤  Flushing remaining buffer (meeting ended)…")
        try:
            resp = await client.post(f"{api_url}/sessions/{session_id}/flush")
            resp.raise_for_status()
            result = resp.json()
            if "data" in result:
                _print_extraction(result)
            else:
                print(f"   {result}")
        except httpx.RequestError as e:
            print(f"⚠  Flush failed: {e}")

    print("\n✅  Simulation complete.")
    print(f"   View live dashboard → {api_url}/")
    print(f"   Full context        → {api_url}/sessions/{session_id}/context\n")


def _print_extraction(result: dict) -> None:
    """Pretty-print an extraction result to the console."""
    data = result.get("data", {})
    model = result.get("model", "?").split("/")[-1]
    ts    = result.get("extracted_at", "")[-9:-1]
    segs  = ", ".join(result.get("segment_ids", []))

    print(f"\n   ┌─ 🤖 Extraction [{ts}] model={model} segs=[{segs}]")

    items = data.get("action_items", [])
    if items:
        print(f"   │  ✅ Action Items ({len(items)})")
        for i in items:
            owner    = f" → {i['owner']}"   if i.get("owner")    else ""
            deadline = f" by {i['deadline']}" if i.get("deadline") else ""
            prio     = i.get("priority", "medium")
            marker   = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(prio, "•")
            print(f"   │    {marker} {i['task']}{owner}{deadline}")

    reqs = data.get("requirements", [])
    if reqs:
        print(f"   │  📋 Requirements ({len(reqs)})")
        for r in reqs:
            labels = " ".join(f"[{l}]" for l in r.get("labels", []))
            prio   = r.get("priority", "medium")
            marker = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(prio, "•")
            print(f"   │    {marker} {r['spec']} {labels}")

    decisions = data.get("decisions", [])
    if decisions:
        print(f"   │  🔷 Decisions ({len(decisions)})")
        for d in decisions:
            print(f"   │    • {d['summary']}")

    topics = data.get("topics", [])
    if topics:
        print(f"   │  🏷  Topics: {', '.join(topics)}")

    if data.get("parse_error"):
        print(f"   │  ⚠  Parse error: {data['parse_error']}")
        print(f"   │  Raw: {data.get('raw', '')[:200]}")

    print("   └─")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Stream a simulated meeting transcript to extraction_server.py"
    )
    parser.add_argument(
        "--api-url", default="http://localhost:8000",
        help="Base URL of the extraction server (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--session", default=f"sess-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        help="Session ID to use (default: timestamp-based)"
    )
    parser.add_argument(
        "--speed", type=float, default=1.0,
        help="Replay speed multiplier (default: 1.0, try 3.0 for quick testing)"
    )
    args = parser.parse_args()

    asyncio.run(simulate(args.api_url, args.session, args.speed))


if __name__ == "__main__":
    main()
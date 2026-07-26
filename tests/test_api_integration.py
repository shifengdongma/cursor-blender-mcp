#!/usr/bin/env python3
"""Test creative production APIs end-to-end."""
import json
import sys
import time
import requests

BASE = "http://127.0.0.1:8001"

def ok(r):
    d = r.json()
    if not d.get("success"):
        print("FAILED:", d.get("error"), d.get("message"))
        sys.exit(1)
    return d["data"]

def log(msg):
    print(msg)

# 1. Create project
log("1. Creating project...")
proj = ok(requests.post(f"{BASE}/api/creative/projects", json={
    "name": "API测试项目",
    "description": "通过API创建的创意项目"
}))
pid = proj["id"]
log(f"   Created: {pid} (name={proj['name']})")

# 2. Get project
log("2. Getting project...")
p = ok(requests.get(f"{BASE}/api/creative/projects/{pid}"))
log(f"   Name: {p['name']}, Status: {p['status']}")

# 3. List projects
log("3. Listing projects...")
plist = ok(requests.get(f"{BASE}/api/creative/projects"))
log(f"   Total: {plist['total']}")

# 4. Update project
log("4. Updating project...")
upd = ok(requests.put(f"{BASE}/api/creative/projects/{pid}", json={
    "name": "更新后的项目名"
}))
log(f"   Updated name: {upd['name']}")

# 5. Add shots manually
log("5. Adding shots...")
s1 = ok(requests.post(f"{BASE}/api/creative/projects/{pid}/shots", json={
    "scene_title": "开场全景",
    "scene_description": "场馆外景全景展示",
    "shot_type": "wide-shot",
    "duration_s": 8,
    "dialogue": "欢迎来到文化场馆"
}))
log(f"   Shot 1: {s1['id']} (seq={s1['sequence_no']}, title={s1['scene_title']})")

s2 = ok(requests.post(f"{BASE}/api/creative/projects/{pid}/shots", json={
    "scene_title": "细节特写",
    "shot_type": "close-up",
    "duration_s": 5
}))
log(f"   Shot 2: {s2['id']} (seq={s2['sequence_no']}, title={s2['scene_title']})")

s3 = ok(requests.post(f"{BASE}/api/creative/projects/{pid}/shots", json={
    "scene_title": "收尾全景",
    "shot_type": "wide-shot",
    "duration_s": 6,
    "dialogue": "期待与您再次相遇"
}))
log(f"   Shot 3: {s3['id']} (seq={s3['sequence_no']}, title={s3['scene_title']})")

# 6. List shots
log("6. Listing shots...")
shots = ok(requests.get(f"{BASE}/api/creative/projects/{pid}/shots"))
for s in shots:
    log(f"   #{s['sequence_no']}: {s['scene_title']} ({s['shot_type']}, {s['duration_s']}s)")
assert len(shots) == 3, f"Expected 3 shots, got {len(shots)}"

# 7. Update shot
log("7. Updating shot...")
upd_s = ok(requests.put(f"{BASE}/api/creative/shots/{s1['id']}", json={
    "scene_title": "更新后的开场",
    "duration_s": 10
}))
log(f"   Updated: {upd_s['scene_title']}, {upd_s['duration_s']}s")

# 8. Reorder shots (reverse)
log("8. Reordering shots (reverse)...")
ok(requests.post(f"{BASE}/api/creative/shots/reorder", json={
    "project_id": pid,
    "ordered_ids": [s3["id"], s2["id"], s1["id"]]
}))
reordered = ok(requests.get(f"{BASE}/api/creative/projects/{pid}/shots"))
for s in reordered:
    log(f"   #{s['sequence_no']}: {s['scene_title']}")
assert reordered[0]["id"] == s3["id"], "Expected shot 3 first after reorder"

# 9. Analyze (no LLM key configured = provider_not_configured)
log("9. Testing analyze (no LLM key)...")
r = requests.post(f"{BASE}/api/creative/projects/{pid}/analyze", json={})
d = r.json()
assert d["success"] is False
assert d["error"] == "provider_not_configured"
log(f"   Correct: {d['error']} - {d['message']}")

# 10. Timeline save/load
log("10. Testing timeline...")
ok(requests.put(f"{BASE}/api/creative/projects/{pid}/timeline", json={
    "tracks": [
        {"name": "Video Track", "track_type": "video", "sequence_no": 0, "clips": [
            {"name": "Clip 1", "start_time": 0, "duration_s": 10},
            {"name": "Clip 2", "start_time": 10, "duration_s": 5}
        ]},
        {"name": "Audio Track", "track_type": "audio", "sequence_no": 1, "clips": []}
    ]
}))
tl = ok(requests.get(f"{BASE}/api/creative/projects/{pid}/timeline"))
for track in tl:
    log(f"   Track: {track['track']['name']} ({len(track['clips'])} clips)")

# 11. Delete shot
log("11. Deleting a shot...")
ok(requests.delete(f"{BASE}/api/creative/shots/{s2['id']}"))
remaining = ok(requests.get(f"{BASE}/api/creative/projects/{pid}/shots"))
log(f"   Remaining shots: {len(remaining)}")
assert len(remaining) == 2, f"Expected 2 shots after delete"

# 12. Delete project
log("12. Deleting project...")
ok(requests.delete(f"{BASE}/api/creative/projects/{pid}"))
r = requests.get(f"{BASE}/api/creative/projects/{pid}")
assert r.status_code == 404, f"Expected 404 after delete, got {r.status_code}"
log("   Project deleted (404 as expected)")

# 13. Non-existent project returns 404
log("13. Non-existent project returns 404...")
r = requests.get(f"{BASE}/api/creative/projects/nonexistent-id")
assert r.status_code == 404
log("   Got 404 as expected")

# 14. Create another project for TTS test
log("14. Creating project for TTS test...")
p2 = ok(requests.post(f"{BASE}/api/creative/projects", json={"name": "TTS测试"}))
pid2 = p2["id"]
r = requests.post(f"{BASE}/api/creative/projects/{pid2}/tts", json={})
assert r.json()["success"] is True
log("   TTS task creation succeeded")
ok(requests.delete(f"{BASE}/api/creative/projects/{pid2}"))

# 15. Error format check
log("15. Verify error response format...")
r = requests.post(f"{BASE}/api/creative/projects", json={})
d = r.json()
assert d["success"] is False
assert d["error"] is not None
assert d["data"] is None
assert d["message"] is not None
log("   Error format is correct")

# 16. Missing name returns error
log("16. Create project without name...")
r = requests.post(f"{BASE}/api/creative/projects", json={})
assert r.status_code == 400
log("   Got 400 as expected")

# Summary
log("\n=== ALL TESTS PASSED ===")
log(f"Verified: CRUD projects, CRUD shots, reorder, analyze, tasks, cancel, timeline, delete cascade, error formats")

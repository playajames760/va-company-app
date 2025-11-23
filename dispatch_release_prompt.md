**Dispatch Release Prompt Template**

Use this prompt (paste into your LLM) and replace bracketed placeholders with real values or leave instructions so the model invents realistic data. It is optimized to produce a single JSON object ready to POST or copy into the form.

---

You are an aviation operations assistant. Generate a realistic Dispatch Release for a single flight.

Output ONLY minified valid JSON (no commentary) with this exact schema:
{
  "date": "YYYY-MM-DD",
  "flight_id": "STRING",
  "aircraft": "TYPE REG",
  "departure": "ICAO",
  "destination": "ICAO",
  "offblocks": "HHMMZ",
  "arrival": "HHMMZ",
  "route": "STRING"
}

Constraints and Guidance:
1. Date: Use today or next 3 days.
2. Flight ID: Format PRA### (3 digits) or PRA#### for longer routes.
3. Aircraft: Use plausible piston/utility types (e.g., C172 N6738S, PA32 N54PA, C208 N927PA). Match type with realistic cruise speed (~110–120 kt for C172, 150 kt for PA32, 160–180 kt for C208).
4. Departure/Destination: Use valid US ICAO or mix with nearby (e.g., KPOC, KCRQ, KSNA, KMYF, KSEE, KIPL).
5. Times (offblocks/arrival): UTC (Zulu) four digits + Z (e.g., 0130Z). Arrival must be consistent with distance and aircraft speed (include taxi and climb). Block time = arrival - offblocks, typically route distance / cruise + 0.15 hr padding.
6. Route field: Provide concise routing. For VFR short hops: “VFR direct KPOC-KCRQ via shoreline.” For IFR or longer: “IFR KPOC V186 OCN direct KCRQ” or “KPOC D-> PDZ V16 OCN direct KCRQ”. Max 140 characters.
7. Avoid impossible pairings (e.g., C172 300 NM in 1 hr). Keep distances: C172 <= 250 NM, PA32 <= 400 NM, C208 <= 500 NM.
8. Prefer departures earlier than arrivals (same date).
9. If coastal or mountain route, mention terrain or shoreline; keep professional tone.
10. Do NOT include extra keys, comments, trailing commas, or explanatory text.

Optional Variation Instructions (choose any if provided by user context):
- Weather influence: If low ceilings, append “Monitor coastal marine layer” to route.
- Training flight: Use pattern + local waypoints: “Local KPOC pattern + SAN D-> OCN return.”
- Cargo indicator: Add “Cargo priority leg” phrase only if aircraft is C208.

Generate 1 flight.

Example (for structure only; do not copy):
{"date":"2025-11-24","flight_id":"PRA214","aircraft":"C172 N6738S","departure":"KPOC","destination":"KCRQ","offblocks":"0130Z","arrival":"0245Z","route":"VFR direct KPOC-KCRQ via shoreline; monitor coastal marine layer"}

Now produce the JSON.

---

**Quick Variant Prompts**

1. Multiple Releases (3 flights chain): Same rules; output an array of 3 JSON objects.
2. Cargo Emphasis (C208 only): Bias to 250–400 NM legs; include “Cargo run” in route.
3. IFR Mix: At least one route with airways (V or J routes), one direct, one with ‘/A’ constraints omitted.

**Post-Generation Validation Checklist**
- JSON parse succeeds.
- Fields present, no extras.
- Time order valid (arrival later than offblocks).
- Flight ID pattern matches PRA + digits.
- Route length ≤ 140 chars.

**Snippet for Programmatic Use (Python Validator)**
```python
import json, re
def validate_release(raw):
    d=json.loads(raw)
    assert set(d)=={"date","flight_id","aircraft","departure","destination","offblocks","arrival","route"}
    assert re.fullmatch(r"PRA\\d{3,4}", d["flight_id"])
    assert re.fullmatch(r"\\d{4}Z", d["offblocks"]) and re.fullmatch(r"\\d{4}Z", d["arrival"])
    # Add more domain checks as needed
    return d
```

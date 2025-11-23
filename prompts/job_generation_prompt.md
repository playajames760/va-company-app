# Palm Route Air – Random Flight Job Generation Prompt

Use this prompt with an LLM to generate a single realistic flight / cargo job for Palm Route Air. The model should output ONLY the completed markdown document (no explanations of how it was generated). Follow all structure and constraints below.

## INSTRUCTIONS TO MODEL
Generate a new, self-consistent flight job scenario with realistic but fictional operational data. Randomize values each time while respecting aircraft capabilities, geography, and weight limits.

### Output Format (Markdown)
```
# Flight Job: <CALLSIGN / FLIGHT ID>

**Date (UTC):** <YYYY-MM-DD>
**Generation Timestamp (UTC):** <ISO8601>

## Summary
Short narrative (2–4 sentences) describing purpose of flight, cargo nature, and any special considerations.

## Dispatch Release
- Flight ID / Callsign: <ID>
- Aircraft: <Type + Registration>
- Departure (ICAO): <Origin>
- Destination (ICAO): <Destination>
- Planned Off-Blocks (Z): <HHMMZ>
- Planned Arrival (Z): <HHMMZ>
- Route: <Condensed planned routing or VFR remarks>
- Alternate Airports: <Comma-separated list>
- Weather Brief (Summary): <Key winds/ceilings/visibility/hazards>
- Special Notes: <Concise bullet list or sentence>
- Planned Payload (lbs): <Number>
- Planned Fuel (gal or lbs): <Number>

## Cargo Manifest (Planned)
| Item | Description | Weight (lbs) | Special Handling |
|------|-------------|--------------|------------------|
| ...  |             |              |                  |

**Total Pieces:** <Count>
**Total Cargo Weight (lbs):** <Sum matches table>

## Crew Log (Forecast Data)
- Pilot in Command: <Name>
- Second Crew / Observer: <Name or N/A>
- Estimated Block Time (hh:mm): <Duration>
- Estimated Air Time (hh:mm): <Duration>

## Weather Detail
Provide one METAR-like string for departure and destination, plus any SIGMET/AIRMET-style line if relevant.

## Risk Assessment
| Factor | Rating (Low/Med/High) | Rationale |
|--------|-----------------------|-----------|
| Weather |  |  |
| Fatigue |  |  |
| Terrain / Route |  |  |
| Cargo Hazards |  |  |
| Operational Complexity |  |  |

**Overall Risk Level:** <Low/Medium/High> (justify briefly)

## NOTAM / Advisory Considerations
List 1–3 synthesized, relevant company NOTAM-style advisories (e.g., ramp works, equipment limitations).

## Fleet & Performance Check
- Aircraft Type: <Type>
- Registration: <Reg>
- MTOW (lbs): <Value>
- Useful Load (lbs): <Value>
- Planned Payload + Fuel (lbs): <Calculated> (Ensure <= Useful Load)
- Payload Margin (lbs): <Useful Load - (Payload+Fuel)>

## Data Integrity Crosscheck
- Cargo Table Sum == Total Cargo Weight: <Yes/No>
- Total Cargo Weight <= Planned Payload: <Yes/No>
- Planned Payload + Fuel <= Useful Load: <Yes/No>
- Departure ≠ Destination: <Yes/No>

## Suggested Next Actions
Numbered list of 3–5 operations steps (e.g., finalize dispatch, verify weight & balance, obtain updated METAR, brief crew).
```

### Randomization & Constraint Rules
1. **Aircraft Selection:** Choose from: C172, PA34, BE58, C208, PC12, B350. Pair with a plausible US registration (e.g., N57PR). Ensure payload/fuel ranges match scale (e.g., C172 useful load ~900 lbs; PC12 ~3000 lbs; adjust realistically).
2. **Airports:** Use valid US ICAO codes (mix of GA + regional). Ensure route plausibility (e.g., no oceanic crossing for C172). Departure ≠ Destination.
3. **Times:** Off-blocks within next 36h UTC; arrival after off-blocks (reasonable duration for distance). Block time aligns with route distance and aircraft cruise speed (e.g., C172 ~110 KTAS, PC12 ~270 KTAS).
4. **Cargo Items:** 3–8 rows. Individual weights sum exactly to total cargo weight. Include varied descriptions (e.g., "Medical Supplies", "Frozen Samples", "Survey Equipment"). Mark special handling for sensitive or fragile items occasionally.
5. **Weight Logic:** Planned Payload ≥ Total Cargo Weight. Payload+Fuel must not exceed useful load; maintain ≥10% margin unless risk is High (then margin may drop to 5–10%).
6. **Weather:** Generate plausible VFR or marginal IFR conditions consistent with risk and route (e.g., coastal morning IFR, inland afternoon VFR). If High weather risk, justify with visibility, ceilings, or convective remarks.
7. **Risk Ratings:** At least one Medium; High only if justified. Overall risk not High unless ≥2 factors are High.
8. **Alternates:** 1–3 valid ICAO codes reasonably near destination.
9. **NOTAMs:** Fabricate internally relevant advisories (NOT FAA official). Keep concise.
10. **Integrity Checks:** They must logically result in "Yes" unless deliberately introducing a scenario risk—never produce contradictory payload math.
11. **No Explanatory Preface:** Output starts with the markdown header; do not say "Here is" or similar.
12. **Data Consistency:** All numeric cross references align (cargo sum, margins).

### Style Guidelines
- Keep narrative concise and professional.
- Use consistent units (lbs for weight unless fuel plausibly in gallons for piston aircraft; may still convert logically).
- Avoid over-optimistic times; reflect realistic cruise speeds.
- No confidential or real customer data—purely fictional.

### Rejection Avoidance
If constraints conflict, adjust payload downward first, then adjust fuel, then adjust alternates.

### Completion
Return only the finished markdown document following the template. Do not include the instruction text.

---
**Prompt Usage Tip:** Provide this entire file content as the system or user message to the LLM and request: "Generate one new Palm Route Air flight job." Each invocation should yield a different scenario.

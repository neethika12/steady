# Local AI evaluation

Model: **phi4-mini** via ollama · runs per feature: 3 · date: 2026-10-14


## 1. Break down a task / inbox item

- Valid proposals: 3/3 (rejected after validation + 1 retry: 0)
- Latency: median 3.5 s, max 3.6 s
- task: Gather Q3 spending data (30 min); Compare spending to Q3 budget (30 min); Identify top two variances (20 min); Summarize findings in report (40 min); Flag variances in report (10 min); Review and finalize report (30 min)
- inbox: Choose a date for the picnic (15 min); Find a suitable location (30 min); Send invitations to friends (20 min); Plan the menu and snacks (45 min); Organize entertainment and activities (60 min); Prepare a birthday card for Sam (30 min)
- task: Gather Q3 spending data (30 min); Compare spending with Q3 plan (30 min); Identify top two variances (20 min); Summarize spending vs plan (20 min); Flag top two variances (20 min); Compile the quarterly budget report (30 min)

## 2. Suggest a daily plan

- Valid proposals: 3/3 (rejected after validation + 1 retry: 0)
- Latency: median 2.7 s, max 4.3 s
- Model respected the time budget on its own in 3/3 runs; the app enforces it either way.
- budget 120 min → model chose 115 min (within budget); app kept 115 min: Prepare slides for Monday review, Reply to landlord about repairs, Call the dentist
- budget 60 min → model chose 25 min (within budget); app kept 25 min: Reply to landlord about repairs, Call the dentist
- budget 240 min → model chose 160 min (within budget); app kept 160 min: Prepare slides for Monday review, Renew passport application, Reply to landlord about repairs, Call the dentist

## 3. Summarise non-completion reasons

- Valid proposals: 2/3 (rejected after validation + 1 retry: 1)
- Latency: median 10.4 s, max 18.0 s
- Observation: Not enough time was recorded for 14 tasks. (refs: R1, R2, R3, R8, R9, R10, R15, R16, R20, R21, R22, R26)
- Observation: Task was too large was recorded for 4 tasks. (refs: R5, R11, R17, R23)
- Suggestion: Break down larger tasks into smaller, manageable parts.
- Suggestion: Schedule tasks with waiting dependencies earlier in the day.
- Observation: Not enough time was recorded for 14 tasks. (refs: R1, R2, R3, R8, R9, R10, R14, R15, R16, R20, R21, R22, R26)
- Observation: Task was too large was recorded for 4 tasks. (refs: R5, R11, R17, R23)
- Suggestion: Break down larger tasks into smaller, manageable parts.
- Suggestion: Prioritize tasks and allocate specific time slots for them.
- REJECTED: The local model's answer was rejected (it stated the number 9, which is not in the supplied data), so nothing is shown. You can try again; nothing was changed.

## 4. Review habit consistency

- Valid proposals: 3/3 (rejected after validation + 1 retry: 0)
- Latency: median 14.6 s, max 15.0 s
- Observation: You have completed stretching exercises “Stretch mv8a5vpc”, “Stretch mv8a5xky”, “Stretch mv8a6722”, and “Stretch mv8a6a0r” on all scheduled days with 100% consistency. These habits are well-maintained and consistent.
- Suggestion (Evening walk): Consider reducing the frequency of your evening walks to once a week to improve consistency.
- Suggestion (Evening walk): Consider reducing the frequency of your evening walks to once a week to improve consistency.
- Observation: Stretch mv8a5vpc (“Stretch mv8a5vpc”) has 100% consistency, completed on 1 of 1 scheduled days.
- Suggestion (Evening walk): Consider reducing the number of scheduled days for Evening walk [92972] (“Evening walk [92972]”) to improve consistency.
- Suggestion (Evening walk): Consider reducing the number of scheduled days for Evening walk [93001] (“Evening walk [93001]”) to improve consistency.
- Observation: You have completed stretching exercises “Stretch mv8a5vpc”, “Stretch mv8a5xky”, “Stretch mv8a6722”, and “Stretch mv8a6a0r” on all scheduled days with 100% consistency. Great job maintaining this routine consistently.
- Suggestion (Evening walk): Consider reducing the number of scheduled days for evening walks to 7 days a week to improve consistency.
- Suggestion (Evening walk): Consider reducing the number of scheduled days for evening walks to 7 days a week to improve consistency.

## 5a. Journal prompts (no journal content sent)

- Valid proposals: 3/3 (rejected after validation + 1 retry: 0)
- Latency: median 1.3 s, max 1.4 s
- How did you feel when you accomplished something today? | What was a moment today that made you smile? | Can you think of a small thing you did today that felt good?
- How did you feel when you accomplished something big today? | What was a moment today that made you smile? | Can you think of a small act of kindness you did today?
- How did you feel when you accomplished something you set out to do today? | What was a moment today that brought you joy or peace? | Can you think of a small change you could make tomorrow to feel more at ease?

## 5b. Summarise selected journal entries

- Valid proposals: 3/3 (rejected after validation + 1 retry: 0)
- Latency: median 2.9 s, max 3.3 s
- You wrote about spending the afternoon packing boxes and calling your Mum, feeling excited but also a bit tired. You also mentioned having a long day at work and taking a walk home in the rain, which helped you think about the move.
- You wrote about spending the afternoon packing boxes and calling your Mum, feeling excited but a bit tired. You also wrote about having a long day at work and taking a walk home in the rain, which helped you think about the move.
- You wrote about spending the afternoon packing boxes and calling your Mum, feeling excited but a bit tired. You also wrote about having a long day at work and finding solace in a walk home in the rain while thinking about the move.

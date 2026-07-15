# Seedance 2.0 official documentation snapshot

Verified from Volcengine official documentation on 2026-07-15. This is a working snapshot, not a substitute for checking the live pages immediately before a billable request.

## Source map

- `2298881`: general Seedance SDK examples and model/output overview.
- `2222480`: Seedance 2.0 prompt guide, including multimodal reference syntax, ordered-shot guidance, action wording, failure patterns, and mitigations.
- `2291680`: Seedance 2.0-specific SDK tutorial and model comparison.
- `1520757`: create-task API reference and current request-field support.
- `1521309`: get-task API reference, task lifecycle, retention, and result URL lifetime.

The previously supplied `1099504` page is a language-model experience-center page and is intentionally excluded. The old `1520758` URL is a video-generation API landing page, not the current get-task reference.

## Models and output contract

| Variant | Model ID | Resolutions | Duration | Fixed ratios | Output |
|---|---|---|---|---|---|
| Seedance 2.0 | `doubao-seedance-2-0-260128` | 480p, 720p, 1080p, 4k (10-bit) | 4–15 s | 21:9, 16:9, 4:3, 1:1, 3:4, 9:16 | MP4, 24 FPS |
| Seedance 2.0 Fast | `doubao-seedance-2-0-fast-260128` | 480p, 720p | 4–15 s | same | MP4, 24 FPS |
| Seedance 2.0 Mini | `doubao-seedance-2-0-mini-260615` | 480p, 720p | 4–15 s | same | MP4, 24 FPS |

For the lowest-cost Mini test, request 480p and 4 seconds explicitly. This produces a nominal 96 source frames at 24 FPS, but extraction must still use presentation timestamps.

## API contract

- Create: `POST https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks`
- Query: `GET https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/{id}`
- Authentication: `Authorization: Bearer $ARK_API_KEY`
- Inputs: text plus 0–9 images, 0–3 videos, and 0–3 audios. `text + audio` and audio-only input are unsupported; audio must accompany image or video input.
- Seedance 2.0 can generate a new video, edit a video, or extend/connect up to three video segments.
- Use request-body parameters rather than legacy prompt suffix parameters because request-body validation is stronger.
- `duration`: integer 4–15 seconds, or `-1` for smart duration where supported; default is 5 seconds.
- `resolution`: Seedance 2.0 defaults to 720p. Mini and Fast support only 480p/720p.
- `ratio`: the 2.0 create API defaults to adaptive; use an explicit fixed ratio for sprite planning.
- `generate_audio`: defaults to `true`; set `false` for sprite-motion acquisition.
- `watermark`: defaults to `false`; still set it explicitly in auditable requests.
- `return_last_frame`: optional; returns a no-watermark final image matching the video size.
- `frames`, `seed`, and `camera_fixed` are currently documented as unsupported by the Seedance 2.0 series. Use `duration`, express camera lock in the prompt, and record returned timing metadata.
- Draft/sample mode is for Seedance 1.5 Pro, not Seedance 2.0. Seedance 2.0 also does not support the general `service_tier: flex` path, so neither can be used to discount a 2.0 Mini probe.
- `priority` is available for 2.0 online tasks, 0–9, and orders tasks within the same endpoint; it does not reduce cost.

## Async lifecycle and retention

- Create returns a task ID. Poll the get-task endpoint or configure `callback_url`.
- States include `queued`, `running`, `succeeded`, `failed`, `expired`, and, for eligible queued tasks, `cancelled`.
- Task records are queryable for only the latest 7 days.
- A successful `content.video_url` is valid for 24 hours. Download and hash the MP4 immediately.
- A callback can report state changes; the service retries callback delivery up to three times when it receives no response within five seconds.
- Default task execution expiry is 172800 seconds; the documented configurable range is 3600–259200 seconds.

## Prompt rules relevant to sprite motion

- Define a subject with two or three stable static traits and reuse the same label every time it is mentioned.
- Use ordered shots/action beats: who, where, what action, and what camera behavior. The official guide says exact time constraints such as `0–3 秒` are unstable; do not depend on exact prompt timestamps for extraction.
- Describe body parts, direction, amplitude, speed, and force. Include transition/inertia wording between actions.
- Prefer one camera instruction per shot. For sprite extraction request a fixed camera and reinforce no pan, zoom, cuts, or scale change in text because `camera_fixed` is unsupported.
- The guide says low, continuous motions are more stable than running, large jumps, or rolls. Treat jump and attack as higher-risk beats and provide extra spatial margin.
- Avoid verbose, conflicting prompts. Add explicit exclusions for subtitles, logos, watermarks, duplicate subjects, motion blur, VFX, shadows, and background changes as needed.

## Multi-subject and reference warnings

- The prompt guide reports lower stability when more than four reference people are involved. Keep a same-character grid to four subjects or fewer unless a paid probe proves a denser layout.
- Multi-view/turnaround character references can trigger duplicate “twin” people. Prefer a clean single-character reference for generation, bind each subject explicitly, and add a no-duplicate constraint.
- If a reference video expresses an exact action or effect better than text, use it as motion reference; keep identity/reference roles unambiguous.

## Cost-safe sprite request baseline

Use this only after a dry run and explicit authorization:

```json
{
  "model": "doubao-seedance-2-0-mini-260615",
  "resolution": "480p",
  "duration": 4,
  "ratio": "4:3",
  "generate_audio": false,
  "watermark": false,
  "return_last_frame": true
}
```

When repeats are prohibited, fill the minimum clip with sequential complete actions, for example `idle -> walk -> jump/land -> attack -> end hold`. Phrase them as ordered beats rather than exact second ranges, then detect their real boundaries after download. Do not add repeated filler.

## Project-measured cost anchor

This is project evidence, not an official fixed token formula:

- a Seedance 2.0 Mini image-reference task at 720p, 4:3, 4 seconds, 24 FPS, audio off returned `usage.total_tokens = 87850`;
- at the 2026-07-15 no-video-input list price of ¥23 per million tokens, that task is approximately ¥2.0206;
- two matching 480p tasks each returned `usage.total_tokens = 39891`, or ¥0.9175 each at the same list price; the provisional area estimate of 39,044 tokens was 2.12% low;
- the returned files were 97 decoded frames over about 4.0417 seconds: 1112×834 for the 720p route and 752×560 for the 480p route. Treat provider resolution labels as pricing/output tiers and always probe the coded dimensions;
- in the filled same-character experiment, one 720p 2×2 clip yielded eight readable action propositions at ¥0.2526/readable action, while two 480p two-cell clips yielded the same eight propositions at ¥0.2294/readable action;
- strict canonical-idle endpoint QA passed 2/8 actions at 720p and 5/8 at 480p, making the corresponding cost ¥1.0103 and ¥0.3670 per immediately reusable idle-enveloped action. This is one project sample, not a general model-quality ranking.

## Official links

- https://docs.volcengine.com/docs/82379/2298881?redirect=1&lang=zh
- https://docs.volcengine.com/docs/82379/2222480?lang=zh
- https://docs.volcengine.com/docs/82379/2291680?lang=zh
- https://docs.volcengine.com/docs/82379/1520757?lang=zh
- https://docs.volcengine.com/docs/82379/1521309?lang=zh

# Provider adapters

## Adapter contract

Implement every provider behind the same stages:

1. `build_request`: prompt, model, input images/video, duration, aspect, resolution, seed, audio, watermark.
2. `dry_run`: serialize a redacted request preview with local file hashes and byte sizes.
3. `submit`: create one billable task and persist the task ID.
4. `poll`: record queued/running/succeeded/failed/cancelled states with bounded backoff.
5. `download`: copy the result locally before the provider URL expires.
6. `cancel`: expose cancellation when the provider supports it.
7. `report`: persist model/version, request parameters, output FPS/duration, usage/cost data, and response hash.

Never log bearer tokens, API keys, base64 payloads, or signed URLs. Prefer environment variables; allow an ignored local secret file only as a deliberate fallback.

## Capability manifest

Record these fields per provider and verify them against current official documentation before each integration:

```json
{
  "provider": "name",
  "verifiedAt": "YYYY-MM-DD",
  "createEndpoint": "...",
  "queryEndpoint": ".../{task_id}",
  "auth": "bearer|signed|sdk",
  "models": [],
  "inputRoles": ["first_frame", "last_frame", "reference_image", "reference_video"],
  "durationSeconds": {"min": 0, "max": 0},
  "ratios": [],
  "resolutions": [],
  "outputFps": null,
  "supportsSeed": false,
  "supportsLockedCamera": false,
  "supportsAudioOff": false,
  "supportsWatermarkOff": false,
  "resultUrlExpires": "unknown"
}
```

If a field is unknown, leave it unknown and design a probe. Do not infer API support from the consumer UI.

## Seedance / Volcengine Ark snapshot

Verified against official Seedance 2.0 documentation on 2026-07-15. Read [seedance-2-official.md](seedance-2-official.md) and re-check the live pages before use:

- Create task: `POST https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks`
- Query task: `GET https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/{id}`
- Authentication: `Authorization: Bearer $ARK_API_KEY`
- Models: `doubao-seedance-2-0-260128`, `doubao-seedance-2-0-fast-260128`, and `doubao-seedance-2-0-mini-260615`.
- Seedance 2.0 Mini supports 480p and 720p, the six documented fixed ratios, 4–15 second MP4 output, and 24 FPS output. For the cheapest probe use explicit `resolution: "480p"`, `duration: 4`, `generate_audio: false`, and `watermark: false`.
- Request `content` can combine text with 0–9 reference images, 0–3 reference videos, and 0–3 reference audios. Audio cannot be the only non-text input.
- Use `duration` for Seedance 2.0. The current create API documents `frames`, `seed`, and `camera_fixed` as unsupported for the 2.0 series; lock the camera through the prompt and verify the returned FPS/duration instead of assuming frame control.
- Seedance 2.0 does not support the general `flex` service tier or draft/sample generation parameters. Do not plan cost around them.
- Store `id`, `status`, `duration`, `framespersecond`, `usage`, model, ratio, and resolution from the response when present. Preserve any extra response fields without assuming they were request-controllable.
- Query only recent tasks and download successful output immediately: task records are retained for 7 days and returned video URLs are valid for 24 hours.
- Keep one billable-submission receipt per output directory and refuse a duplicate submit when a task ID or downloaded video already exists. Polling, downloading, extraction, and local re-keying are safe resumable stages; task creation is not.
- Treat background compliance as model-specific. In the tested Mini route, a scenic or dark reference board overrode a text-only green-screen request; rebuilding the single merged reference on exact `#00FF00` produced a keyable result. Do not assume prompt parity between full and Mini models.
- Save full and Mini outputs in separate directories and compare their accepted keyed sequences, not only raw videos. A cheaper model may reduce compressed runtime bytes while requiring a stricter chroma profile.

Official references:

- https://docs.volcengine.com/docs/82379/2298881?redirect=1&lang=zh
- https://docs.volcengine.com/docs/82379/2222480?lang=zh
- https://docs.volcengine.com/docs/82379/2291680?lang=zh
- https://docs.volcengine.com/docs/82379/1520757?lang=zh
- https://docs.volcengine.com/docs/82379/1521309?lang=zh

## Other providers

Add a provider only from its official API documentation. Keep provider-specific request code separate from extraction and normalization. The downstream sequence contract must not change when swapping Seedance, Runway, Kling, Luma, Veo, or a local video model.

Before comparing providers, run the same reference assets, action brief, aspect ratio, duration window, and QA gates. Compare accepted seconds or accepted takes per billable request, not only headline price or resolution.

# Production smoke matrix

This matrix is the canonical RELEASE-001 production smoke contract. It must be
run against the exact Railway deployment bound in `.production-review.json`.
Repository CI, private-alpha evidence, or a different deployment cannot satisfy
these checks.

The local `.production-smoke.json` records operator observations only. It does
not inspect Telegram on its own and it must not be committed.

## Initialize

After the production review exists on the exact deployed commit:

```bash
python scripts/production_smoke.py init \
  --review .production-review.json \
  --output .production-smoke.json
```

The smoke manifest copies the exact commit, provider, deployment ID, and runtime
identity from the production review. A stale checkout is rejected.

Mark one check only after the corresponding behavior has actually been observed:

```bash
python scripts/production_smoke.py mark \
  --input .production-smoke.json \
  --check image.to_jpeg \
  --status pass
```

There is intentionally no bulk `all` shortcut.

## Navigation

- `navigation.ru_en` — verify `/start`, `/tools`, `/help`, and `/settings`
  in Russian and English, including Back navigation and file-send guidance.

## Image operations

Use decoded output/content properties rather than filename extensions as the
acceptance signal.

- `image.to_jpeg` — valid JPEG result.
- `image.to_png` — valid PNG result.
- `image.to_webp` — valid WebP result.
- `image.compress_best` — valid source-format-preserving result using Best
  quality.
- `image.compress_balanced` — valid source-format-preserving Balanced result.
- `image.compress_smallest` — valid source-format-preserving Smallest result.
- `image.resize_25` — dimensions are 25% of the decoded source dimensions.
- `image.resize_50` — dimensions are 50% of the decoded source dimensions.
- `image.resize_720` — maximum side is at most 720 px and a smaller source is
  not upscaled.
- `image.resize_1080` — maximum side is at most 1080 px and a smaller source
  is not upscaled.
- `image.info` — reported format/dimensions come from decoded content. Include
  an image sent as a Telegram document with misleading filename/MIME metadata.

The legacy registry identity `image.compress` is compatibility-only and is not
advertised by the current Telegram UI, so it is intentionally excluded.

## PDF operations

- `pdf.to_images` — PDF pages return valid PNG images in source page order.
- `pdf.to_jpeg_images` — PDF pages return valid JPEG images in source page
  order.
- `pdf.from_images` — start Images → PDF with at least three images, remove
  the last one, add/finalize as needed, and verify the resulting PDF preserves
  the remaining image order.
- `pdf.merge` — start Merge PDFs with at least three PDFs, remove the last one,
  finalize, and verify the remaining file/page order.
- `pdf.extract_pages` — Split returns one valid PDF per source page in order;
  use a source within the Telegram fan-out limit.
- `pdf.extract_first` — result contains exactly the first source page.
- `pdf.extract_first_5` — result contains pages 1 through
  `min(5, page_count)` in order.
- `pdf.extract_last` — result contains exactly the last decoded source page.
- `pdf.compress` — use a prepared structurally compressible PDF; result is
  valid, page count is unchanged, and output is smaller. This operation is
  lossless and does not promise every arbitrary PDF will shrink.
- `pdf.info` — reported page count, file size, and PDF version match inspected
  content.

## Audio operations

Use representative supported inputs and verify the returned file can be decoded.

- `audio.to_mp3`
- `audio.to_m4a`
- `audio.to_wav`

## Video operations

Use a short representative supported video and verify the returned file can be
decoded/played.

- `video.to_mp3` — audio extraction result is valid MP3.
- `video.mute` — valid video result without an audio track.
- `video.to_gif` — valid bounded GIF result.
- `video.compress_best`
- `video.compress_balanced`
- `video.compress_smallest`

The legacy registry identity `video.compress` is compatibility-only and is not
advertised by the current Telegram UI, so it is intentionally excluded.

## Failure, cleanup, and handoff behavior

- `error.unsupported_input` — unsupported input receives the bounded,
  actionable unsupported-format response.
- `error.oversized_transport` — a >20 MiB standard Bot API input fails before
  provider download/conversion with the bounded oversized response.
- `cleanup.after_success` — temporary workspace cleanup is observed after a
  successful real production operation.
- `cleanup.after_failure` — temporary workspace cleanup is observed after a
  failed real production operation.
- `runtime.controlled_redeploy_handoff` — one controlled Railway redeploy
  transfers singleton lease ownership without concurrent polling or
  `TelegramConflictError`, and processing resumes on the new deployment.
- `runtime.healthy_after_smoke` — dependency health, retention/cleanup,
  diagnostics, queue worker, and Telegram polling remain healthy after the
  complete smoke run.

## Gate and apply

Inspect progress:

```bash
python scripts/production_smoke.py show --input .production-smoke.json
```

Require every smoke check to be PASS:

```bash
python scripts/production_smoke.py show \
  --input .production-smoke.json \
  --require-ready

echo $?
```

Exit `0` means all checks are PASS on the exact bound commit/deployment. Exit
`2` means at least one check is pending, failed, or stale.

Only after the smoke manifest is ready, apply its bounded conclusions to the
production review:

```bash
python scripts/production_smoke.py apply-review \
  --input .production-smoke.json \
  --review .production-review.json
```

This explicit apply step can mark only:

- `production_smoke_completed`;
- `cleanup_success_failure_verified`;
- `oversized_transport_verified`;
- `advertised_operations_observed`.

It cannot approve backup policy, provider alerts, BotFather/profile state,
rollback, privacy review, Security Release Gate status, unexplained failure
classes, or final operator approval.

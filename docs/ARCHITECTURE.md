# Architecture

## Design goals

- simple user flow
- deterministic operations
- bounded resource usage
- replaceable Telegram transport
- horizontally scalable workers
- idempotent update and job handling
- explicit job states
- temporary storage
- security isolation between untrusted files and the bot control plane

## Logical components

Telegram -> Bot Gateway -> Job Service -> Queue -> Worker -> Temporary Storage -> Telegram

Supporting services:

- PostgreSQL for durable metadata and job state
- Redis for queueing, locks, short-lived coordination, and rate limits
- structured logging and metrics
- cleanup/reaper process

## Bot Gateway

Responsibilities:

- receive Telegram updates
- deduplicate updates
- identify message/file candidates
- preserve only necessary Telegram metadata
- request file download through a transport abstraction
- create or continue a multi-file session
- present valid operations
- initiate a job
- render user-visible state

The gateway does not implement conversion algorithms.

## Telegram transport abstraction

The conversion system should not depend directly on official-API size assumptions.

Transport interface responsibilities include:

- fetch file metadata
- materialize an input file
- upload/send an output file
- expose transport capability limits

Phase 1 implementation: official Telegram Bot API.

Later implementation: Local Bot API server.

As of Telegram Bot API 10.3, official documentation states:

- official max download: 20 MB
- official multipart upload for general files: 50 MB
- Local Bot API download: no Bot API size limit
- Local Bot API upload: up to 2000 MB

Reference: https://core.telegram.org/bots/api

These values must be configuration/capability data, not scattered constants.

## Job model

Minimum durable fields:

- job_id
- user/chat identity references required for delivery
- operation_id
- operation_version
- state
- input object references
- output object reference when present
- created_at
- updated_at
- deadline/expiry
- attempt identifier
- stable error_code
- resource/usage measurements that contain no file contents

Original sensitive filenames should not be used as analytics identifiers.

## State machine

Nominal path:

RECEIVED -> VALIDATING -> QUEUED -> PROCESSING -> UPLOADING -> COMPLETED

Terminal alternatives:

- REJECTED
- FAILED
- CANCELLED
- EXPIRED

Rules:

- COMPLETED requires successful output delivery or a precisely defined delivery receipt
- retries must not create a second logical job
- worker restart must not convert unknown state into success
- transitions must be monotonic unless a specific recovery transition is designed
- terminal jobs are immutable except for cleanup metadata

## Operation registry

All conversions are fixed registered operations.

Each operation definition includes:

- stable operation_id
- version
- accepted detected input types
- produced type
- allowed parameter schema
- default preset
- maximum input count
- per-input and aggregate limits
- resource class
- timeout
- worker family
- output-size policy
- validation hook

Example identities:

- image.to_jpeg
- image.to_png
- image.to_webp
- image.compress
- image.resize
- pdf.to_images
- pdf.merge
- pdf.extract_pages
- audio.to_mp3
- video.extract_mp3
- video.to_gif
- video.compress

User input selects allowed parameters; it never selects executable paths, binaries, shell fragments, or arbitrary FFmpeg arguments.

## Worker families

Initial logical worker families:

- image
- pdf
- media

Workers receive a validated operation request, materialized input object references, and bounded parameters.

Each worker should run with:

- no unnecessary privileges
- read/write access only to its job workspace
- CPU limit
- memory limit
- disk/output limit
- process timeout
- network disabled unless an operation explicitly requires it

## Temporary storage

Storage API:

- put input
- open input read-only
- create output
- validate output
- mark delivered
- delete job workspace

Policy:

- inputs and outputs have TTLs
- successful Telegram delivery does not imply cleanup can be skipped
- cleanup failures are observable and retried by a reaper
- filenames on disk are generated identifiers, not original names

Object storage can replace local disk later without changing operation logic.

## Multi-file sessions

A collection/session groups inputs before a job is created.

Required properties:

- owner/chat binding
- expiry
- max files
- aggregate byte limit
- deterministic order
- explicit finalization action

Expired collections are cleaned without conversion.

## Idempotency

At least two identities are needed:

- Telegram update identity to prevent reprocessing the same update
- logical job idempotency key to prevent duplicate conversion from repeated callbacks

Callback actions must validate that they refer to the expected user/chat/session/job and current state.

## Observability

Structured events should cover:

- update accepted/deduplicated
- validation passed/rejected
- job queued
- worker started/finished/terminated
- output validation
- upload started/completed/failed
- cleanup completed/failed

Logs must not contain file contents, bot tokens, arbitrary metadata dumps, or full sensitive filenames.

## Deployment progression

Phase A:

- official Telegram Bot API
- one application deployment
- Redis
- PostgreSQL
- bounded worker processes/containers
- local temporary disk

Phase B, only if usage justifies it:

- Local Bot API
- object storage
- separate worker nodes
- autoscaling by queue class

The migration seam is the transport/storage interface, not a rewrite of conversion operations.

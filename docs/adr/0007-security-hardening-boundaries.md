# ADR 0007 — Security hardening boundaries

Status: Accepted

## Context

SimpleConvBot processes hostile public files. Format-level validation alone does not bound parser failure, resource exhaustion, stale temporary data, credential exposure, or container privilege.

The bot is currently deployed as a Railway private-alpha service. Railway uses the repository Dockerfile to build a service container, but Dockerfile syntax alone cannot guarantee runtime CPU/memory/PID/network policy. Railway also maps separate application services to separate containers and private networking.

## Decision

This hardening layer separates controls into three boundaries:

1. Application controls
   - content-based type validation and per-format dimensions/pages/duration/output limits
   - UUID job workspaces with generated basename-only internal paths
   - workspace byte quotas and observable cleanup/reaping
   - secrets excluded from configuration representation
   - durable job admission and request-rate controls (added in the same security workstream)

2. Child-process controls
   - conversion execution may be placed behind the Linux sandbox runner
   - sandbox children receive a minimal environment with no Telegram/DB/Redis secrets
   - wall-clock, CPU, address-space, file-size, open-file and process limits are explicit
   - timeout kills the full child process group
   - unsupported platforms fail closed for this sandbox

3. Container/deployment controls
   - production image runs as an unprivileged user
   - CI verifies a hardened worker invocation with read-only rootfs, dropped capabilities, no-new-privileges, PID/memory/CPU limits, bounded tmpfs and no network
   - the current Railway bot service is not claimed to provide kernel-level egress isolation merely because it uses a Dockerfile

## Public-release consequence

Kernel-level network isolation for the actual conversion worker deployment remains an explicit release condition. Until a production worker is launched with an equivalent isolation profile, the existing Railway deployment is a private-alpha bot/control-plane surface rather than evidence that hostile file execution is fully isolated.

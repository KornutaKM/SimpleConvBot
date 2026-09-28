# Security hardening implementation

This document records what SEC-001 can prove in code/CI and what remains deployment-bound.

## Proven in repository/CI

- production image runs as non-root
- hardened worker profile drops Linux capabilities
- no-new-privileges is enabled
- hardened worker root filesystem is read-only
- only a bounded job tmpfs is writable
- hardened worker network namespace contains loopback only
- hardened worker has explicit PID, memory and CPU limits
- job workspace paths are UUID-scoped
- workspace internal filenames are bounded generated basenames
- symlink workspace tampering fails closed
- workspace usage has an explicit byte quota
- cleanup failures are observable instead of silently ignored
- stale UUID workspaces have a bounded reaper
- sandbox child processes do not inherit Telegram/database/Redis secrets
- sandbox child processes have wall/CPU/address-space/file/open-file/process bounds
- parser/codec-specific input/output bounds remain enforced by Image/PDF/Media engines

## Deliberately not claimed

A Dockerfile cannot by itself enforce the full hardened runtime profile. The private-alpha Railway bot service should not be described as a kernel-isolated conversion worker.

Before public hostile-file execution is enabled, the actual production worker service must demonstrate an equivalent runtime boundary, especially network egress isolation and hard CPU/RAM/PID/workspace limits.

Railway documents services as separate containers and provides private project networking, but that does not by itself prove outbound egress is disabled. Therefore this remains a deployment gate rather than an inferred guarantee.

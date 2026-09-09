# OPENHTPC — Agent Contract

## Role

You are an implementation agent for OPENHTPC.

The existing architecture is authoritative.

Do not silently redesign an established subsystem.

If a requested change conflicts with a frozen rule:
STOP and report the conflict before modifying code.

Prefer the smallest coherent implementation.

Do not broaden scope.


## Authority precedence

Authority precedence is:
1. code / tests / artifacts
2. `OPENHTPC_CURRENT_STATE.json` for current workstream and approved next action
3. current qualification and architecture documents
4. roadmap documents
5. historical conversation only as background.

Canonical project state never overrides code truth.


## Platform

Target:
Fedora 44 KDE / Wayland living-room HTPC.

Principle:
Use what you have.

Fedora owns:
- GPU drivers
- global audio configuration
- global network configuration

OPENHTPC adapts to the correctly configured operating system.

OPENHTPC must not repair or replace Fedora GPU drivers.


## Autopilot guidance

When invoked by OPENHTPC Autopilot:
- obey only the bounded plan
- do not expand scope
- do not commit or push unless explicitly authorized
- return the required structured report
- stop on any safety or policy ambiguity


## Evidence vocabulary

Never treat these as synonyms:

DETECTED
AVAILABLE
SUPPORTED
OBSERVED
PROVEN
PHYSICALLY_QUALIFIED

Never promote evidence without proof.

Examples:

DRM render node available
!= VAAPI qualified.

hwdec=vaapi observed
!= physical decode GPU proven.

Vulkan deviceUUID explicitly selected
= Vulkan render device proven.

It does not prove physical decode-GPU ownership.

`AVAILABLE` means `READY_TO_ATTEMPT`, never guaranteed per-disc decryptability.
Software tests never establish physical optical qualification.


## KEYDB policy

OPENHTPC does not provide, download, update, link to, parse, copy, or modify a user KEYDB.

Metadata-only presence detection is permitted where the current architecture requires it.


## Protected optical and P2 boundary — frozen

The P2 Phase 12 boundary is frozen.

`plugin.bluray` owns:
- Blu-ray / UHD Doctor
- presentation
- capability
- decision
- declarative UI
- classification
- pure libbluray / structural normalization
- static assets

Core intentionally owns:
- device / library / filesystem acquisition
- KEYDB metadata acquisition
- raw-fact merge and canonical publication
- resource validation / rendering
- tokens
- dispatcher / revalidation
- bounded playback execution
- MPV launch
- attempt recording

Do not cross these I/O, security, rendering, or execution boundaries without explicit authorization and qualification planning.


## GPU identity — frozen

Persistent GPU identity is PCI address.

Never use:

card0/card1
renderD128/renderD129
enumeration order
marketing name
discrete-GPU preference

as persistent identity.

Validated persistent DRM path may be:

/dev/dri/by-path/pci-<PCI>-render


## T8.1A — frozen

T8.1A resolves runtime GPU topology.

effective_candidate describes topology.

It does NOT prove:

Vulkan use
VAAPI use
NVDEC use
actual decoder ownership.


## T8.1B1 — frozen

PCI / validated DRM identity maps to VkPhysicalDevice
and opaque Vulkan deviceUUID.

UUID is opaque.

Allowed UUID transformation:
lowercase only.

Never derive PCI identity from UUID.

Evidence states:

ABSENT
VALID
INVALID
CONFLICT

INVALID or CONFLICT fails closed.

AMBIGUOUS means multiple independently valid answers,
not malformed evidence.


## T8.1B2 — frozen

OPENHTPC dynamically binds the Vulkan RENDER GPU.

When runtime display topology and Vulkan identity are proven:

--vulkan-device=<opaque UUID>

may be supplied to MPV.

Do NOT inject --vaapi-device for normal direct hwdec=vaapi.

MPV 0.41 --vaapi-device applies to vaapi-copy semantics.

drm_render_path is topology evidence.
It is not an explicit direct-VAAPI decoder selector.

Render binding and decode policy are separate.

Example:

gpu_render_binding:
    status = RENDER_BOUND

decode_policy:
    hwdec = vaapi / nvdec
    status = OBSERVED
    physical_gpu_binding = NOT_PROVEN


## Render vs decode — frozen distinction

T8.1B2/T8.5 contract:

Vulkan render GPU:
may be explicitly selected and PROVEN.

Decode backend:
may be OBSERVED.

Physical decode GPU:
remains NOT_PROVEN unless independently established.

Do not use render-GPU capability tables to make negative
per-GPU decode decisions while decode-GPU identity is
NOT_PROVEN.


## Effective MPV runtime authority

Effective MPV runtime directory:

~/.config/openhtpc/runtime/mpv/

Relevant generated files:

pure.conf
reference.conf

Do NOT use obsolete:

runtime/pure.conf

A value is OBSERVED only when actually read from the effective
runtime configuration.

If missing/unreadable:

status = UNAVAILABLE
value = null

Never expose a guessed/default value as OBSERVED.


## Runtime GPU configuration

Generated pure.conf/reference.conf must not use a static
machine identity such as:

vaapi-device=/dev/dri/renderD128
vaapi-device=/dev/dri/renderD129

Runtime topology is authoritative.


## Decode backends

Preserve existing backend policy unless the active tranche
explicitly changes it.

Intel/AMD may use:
hwdec=vaapi

NVIDIA may use:
hwdec=nvdec

Never inject VAAPI semantics into an NVDEC path.

Physical decode GPU remains NOT_PROVEN unless separately proven.


## Physical decode GPU — frozen

For the current MPV 0.41 direct VAAPI/NVDEC architecture:

observing the decode backend does NOT prove the physical
decoder PCI identity.

Current contract:

physical_gpu_binding = NOT_PROVEN
physical_gpu_pci = null

Never infer physical decode GPU from:

- Vulkan render GPU
- Vulkan UUID
- Hardware Passport
- GPU marketing name
- codec capability table
- VAAPI/NVDEC backend name
- free-form log marker

A future tranche may promote this only from an independently
trustworthy runtime source.


## Negative hwdec policy — frozen

A per-GPU negative decoding decision such as:

--hwdec=no
codec exclusion
forced software decoding

requires PROVEN physical decode-GPU identity.

RENDER GPU identity is insufficient.

If:

physical_gpu_binding = NOT_PROVEN

GPU-specific capability information may be diagnostic,
but MUST NOT be used to disable hardware decoding.

Hardware Passport codec capabilities are not runtime decode
authority unless identity AND freshness have independently
been proven.

Positive MPV capability enablement is permitted when MPV
retains a safe software fallback.


## Audio — frozen T7

GPU work must not regress:

DEVICE / SYSTEM output selection
PCM / BITSTREAM
PipeWire routing
audio-spdif
Fedora global audio defaults

OPENHTPC may select MPV audio output.

OPENHTPC does not alter Fedora's global audio default.


## Playback ownership

Playback policy is centralized.

Local files, DVD and protected Blu-ray dispatchers consume
policy output.

Dispatchers must not independently rediscover GPUs.


## Playback runtime truth

Keep these truths separate.

RENDER GPU:
PROVEN only from trustworthy MPV Vulkan runtime evidence
associated with the bound Vulkan UUID.

DECODE BACKEND:
OBSERVED only from MPV decode runtime evidence.

HARDWARE/SOFTWARE DECODE:
OBSERVED only from chronological MPV decode transitions.

PHYSICAL DECODE GPU:
NOT_PROVEN unless independently proven.

Never promote one semantic state into another merely because
they are likely to refer to the same hardware.


## MPV log authority

For runtime playback observation:

Render evidence is accepted only from:

[vo/gpu-next/libplacebo]

Decode evidence is accepted only from:

[vd]

Do not treat matching strings from:

[ao]
[cplayer]
[other]
or unrelated components

as render/decode truth.

Parsing must:

- be chronological
- associate evidence to the correct Vulkan device
- fail closed on ambiguity
- never combine evidence from different device blocks


## Post-mortem playback semantics

Current T8.5 observation is POST-MORTEM, not live telemetry.

During playback:

dispatch_status = DISPATCHED
render.status = NOT_PROVEN
decode.status = UNAVAILABLE

After the matching MPV process completes:

the observation may become PROVEN / OBSERVED according to
actual runtime evidence.

Do not present the previous completed playback as current live
playback truth.


## Current-state ownership rule

Atomic rename protects file integrity.

It does NOT make read/check/write ownership atomic.

Any persisted current-session state shared by multiple
processes must serialize the COMPLETE transaction:

LOCK
READ
VALIDATE OWNER
DECIDE
WRITE / ATOMIC REPLACE
UNLOCK

The ownership comparison must occur while the same lock is held
that protects the replacement.

Never:

READ
CHECK OWNER
UNLOCK / NO LOCK
WRITE LATER

based on a stale ownership decision.


## Playback dispatch ID contract

Every playback dispatch owns a unique opaque dispatch_id.

All completion/failure mutations belonging to that playback
must explicitly carry that dispatch_id.

Missing / None / empty dispatch_id:

MUST NOT mutate current playback state.

Never infer or borrow dispatch_id from the currently persisted
state.

A stale completion/failure must never overwrite a newer
dispatch.


## Inter-process locking

For playback-runtime current-state ownership:

use an inter-process lock around the full transaction.

Current implementation uses:

fcntl.flock(..., LOCK_EX)

on the dedicated runtime lock file.

Lock release and file-descriptor cleanup must occur reliably
even on exception.

Atomic JSON replacement occurs while ownership lock remains
held.


## Persisted JSON is untrusted input

Persistent runtime state must always be validated before use.

Validate exact expected types BEFORE:

- enum membership
- hash/set lookup
- semantic interpretation

Do not assume a value is a string or hashable.

Malformed, partial, wrong-schema, wrong-type or corrupt state
must:

- fail closed
- never crash system-model
- never become PROVEN / OBSERVED truth

Handle Python bool/int distinction explicitly where the schema
requires an exact bool or int.


## Deployment

Repository code is not proof of installed product behavior.

When adding a production payload file, inspect all real
deployment authorities, including when applicable:

PRODUCT_FILES
managed-files.txt
installer
update path

Normal ./update.sh must deploy the implementation.

When deployment matters, distinguish explicitly:

repository state
installed state


## Source file headers

New OPENHTPC source files, where applicable, use:

    Copyright 2026 Steve Dehanne
    SPDX-License-Identifier: Apache-2.0

    Part of the OPENHTPC project.
    Original project by Steve Dehanne.


## Testing

Synthetic tests must be hermetic.

They must not depend accidentally on:

/sys
/dev/dri
Wayland
salon hardware
real vulkaninfo

Real-host tests must be separate and skippable.

Never weaken an unrelated historical assertion to make a new
tranche pass.

If an existing assertion changes, explain which intentional
architectural change invalidated the previous expectation.


## Failure behavior

When hardware identity cannot be proven:

prefer safe fallback.

Never invent:

first GPU
discrete GPU
marketing-name winner
stale render node
UUID-derived PCI identity

Do not convert uncertainty into a plausible claim.


## Working method

Before coding:

1. Read this AGENTS.md.
2. Read .git/OPENHTPC_STATE.md if present.
3. Verify HEAD, status and stash.
4. Identify the actual source of truth.
5. Perform PRE-FLIGHT when semantics or architecture are involved.

During coding:

6. Make the smallest coherent change.
7. Do not refactor unrelated code.
8. Preserve tranche boundaries.
9. Do not weaken unrelated tests.

Before reporting:

10. Run targeted tests first.
11. Perform an adversarial SELF-REVIEW.
12. Run relevant regressions.
13. Run git diff --check.
14. Run git status --short.
15. Run git stash list.


## Mandatory self-review

Before reporting any future tranche as ready, Builder must
actively try to invalidate its own implementation against:

- wrong runtime path
- repository/install mismatch
- stale generated configuration
- guessed/default value reported as OBSERVED
- render/decode identity conflation
- negative hwdec decision without proven decoder identity
- stale playback completion
- stale playback failure
- missing dispatch_id
- borrowed session ownership
- non-atomic read/check/write transaction
- malformed persisted JSON
- bool/int schema confusion
- cross-device Vulkan association
- generic log substring matching
- stale decode fallback reason
- free-form physical decode proof
- Intel/AMD/NVIDIA backend regression
- host-dependent synthetic tests
- unrelated weakened historical assertion
- stale diagnostic state
- tranche contamination

If one is reproduced:
fix it BEFORE reporting.


## Git

Never commit unless explicitly authorized.

Never push unless explicitly authorized.

Protected stash:

RC7 T5 network deferred

Never apply, drop or modify it unless explicitly authorized.

conftest.py is protected unless explicitly authorized.


## Reporting

Report evidence, not confidence.

At minimum:

WHAT changed
WHY
SOURCE OF TRUTH
FILES changed
TARGETED tests
REGRESSIONS
git diff --check
exact git status
stash state

When something is uncertain:
report NOT_PROVEN.

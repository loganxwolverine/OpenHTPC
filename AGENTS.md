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


## Effective MPV runtime

Effective generated runtime directory:

~/.config/openhtpc/runtime/mpv/

Important files:

pure.conf
reference.conf

Do not read obsolete:

runtime/pure.conf

OBSERVED means the value was actually read from the
effective runtime configuration.

If the value cannot be read:

status = UNAVAILABLE
value = null

Never report a default or guess as OBSERVED.


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

Before returning a successful implementation, actively search
for:

- wrong runtime path
- repository/install mismatch
- stale generated configuration
- guessed value labelled OBSERVED
- render/decode semantic confusion
- Intel/AMD/NVIDIA backend regression
- host-dependent synthetic test
- unrelated weakened assertion
- stale diagnostic state
- tranche contamination

Fix discovered issues before reporting.


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

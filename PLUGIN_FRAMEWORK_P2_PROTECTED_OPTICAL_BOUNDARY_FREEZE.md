# Plugin Framework P2 protected-optical architectural boundary freeze

Status: `PHASE 12 — ARCHITECTURE FROZEN / CUTOVER INCOMPLETE`

This document freezes the boundary reached after Phases 1–11. It changes no
runtime behavior. The qualified Core path and every fallback remain present,
and `plugin.bluray` remains disabled by default.

## Ownership reached through Phases 1–11

Phase 1 established registry and manifest validation. Phase 2 established
shadow equivalence. Phases 3–7 transferred the Doctor projection,
presentation descriptor, capability projection, playback-decision projection
and declarative menu contribution. Phase 8 transferred deterministic
Blu-ray/UHD classification. Phases 9 and 10 transferred normalization of
already-acquired libbluray and structural facts. Phase 11 transferred exact
copies of the qualified Blu-ray/UHD static assets.

Accordingly, `plugin.bluray` owns media-specific Doctor projection,
presentation, capability projection, playback decision, declarative UI,
classification, both pure normalization stages and static assets.

Core intentionally owns these platform boundaries:

- physical services: device lifecycle/access, udev, libbluray calls,
  libaacs/libbdplus fact acquisition, mounted BDMV/INDX reads, KEYDB presence
  metadata acquisition, raw-fact validation/merge and canonical publication;
- security: action-token generation and binding, dispatcher/revalidation and
  stale/forged-token rejection;
- execution: generic optical handler infrastructure, bounded `bd://`
  execution, MPV launch and protected-attempt recording;
- rendering: resource validation/loading, Flex layout/composition and
  generated runtime files.

These Core responsibilities are not currently migration failures. Low-level
I/O, security and execution may remain shared platform services requested
through validated plugin/Core contracts.

## Actual behavior matrix before production cutover

This matrix follows the production selectors in `openhtpc-optical.py`,
`openhtpc-core.py`, `openhtpc-disc-view.py` and `openhtpc-play-optical`.

| User-visible function | Plugin absent | Installed, disabled | Enabled, valid | Broken |
|---|---|---|---|---|
| Blu-ray/UHD detection | Core available | Core available | Core acquisition | Core available |
| Classification | Core fallback | Core fallback | Plugin after exact A/B | Core fallback |
| Badge | Core fallback asset/mapping | Core fallback | Plugin descriptor/asset after guards | Core fallback |
| Menu/play button | Core fallback | Core fallback | Plugin contribution, Core rendering/token | Core fallback |
| Protected eligibility | Core fallback | Core fallback | Plugin projection, Core enforcement | Core fallback |
| Feature Doctor rows | Core fallback | Core fallback; registry says `DISABLED` | Plugin projection | Core fallback; registry error reports `BROKEN` |
| Actual playback | Core backend remains available | Core backend remains available | Core securely executes selected policy | Core backend remains available |

Thus registry labels are truthful about plugin installation state, but feature
exposure is not yet optional: absent, disabled and broken states silently use
a second complete media-specific Core path.

## Fallback classification

Migration safety fallbacks duplicate plugin-owned policy and exist for A/B,
rollback and failure isolation:

- Core Blu-ray/UHD classifier;
- Core libbluray and structural normalizers;
- Core protected-optical Doctor row projection;
- Core presentation mapping;
- Core capability and playback-decision projections;
- Core declarative UI/menu builder;
- Core Blu-ray/UHD static assets.

Intended permanent Core services are device lifecycle and bounded acquisition,
canonical publication, generic registry/contract validation, resource
validation/loading, Flex rendering, token security, dispatcher revalidation,
generic execution/MPV service and result recording.

Some remaining Core implementation is media-specific even where its system
calls may intentionally remain Core: libbluray/AACS/BD+ and KEYDB acquisition
adapters, the current Blu-ray-shaped raw-fact merge, `bd://` adapter, and all
migration fallback functions above. Production cutover should hide those
services behind validated plugin requests and retire user-visible fallback
policy; it need not move their system calls into plugin code.

## Fallback retirement readiness

| Migration fallback | Plugin equivalent | Automated A/B | Covered / isolated | Permanent Core service after removal | Default behavior changes | Physical validation |
|---|---|---|---|---|---|---|
| Doctor projection | Yes | Yes | Yes | Generic Doctor engine | Yes | Required with combined cutover |
| Presentation mapping | Yes | Yes | Yes | Generic descriptor validator/renderer | Yes | Required with combined cutover |
| Capability projection | Yes | Yes | Yes | Canonical snapshot service | Yes | Required with combined cutover |
| Playback decision | Yes | Yes | Yes | Core enforcement/revalidation | Yes | Required |
| UI/menu contribution | Yes | Yes | Yes | Flex/token services | Yes | Required |
| Classification | Yes | Yes | Yes | Probe acquisition/publication | Yes | Required |
| libbluray normalization | Yes | Yes | Yes | Core libbluray acquisition | Yes indirectly | Required with classifier cutover |
| Structural normalization | Yes | Yes | Yes | Core filesystem acquisition | Yes indirectly | Required with classifier cutover |
| Static assets | Yes, exact SHA | Yes | Yes | Core validator/loader/renderer | Yes | Badge validation required |

Automated equivalence and isolation are complete, but retirement is not ready
under the current default because the plugin is disabled. A central feature
authority must first define absent/disabled/broken as unavailable rather than
silently selecting media-specific Core behavior. Core fallbacks must remain
until that bounded cutover is deliberately implemented and qualified.

## Desired long-term plugin semantics and cutover status

The target is: absent means `NOT_INSTALLED` with no Blu-ray/UHD feature
exposure; disabled means no active contribution; enabled means plugin policy
with generic Core services; broken means feature unavailable while Core and
generic optical services remain healthy. Current behavior differs in all
negative plugin states because the complete Core media-specific fallback is
still selected.

`PLUGIN_CUTOVER_STATUS=INCOMPLETE`

## Installation model recommendation

Use **Model 2**: ship the maintained first-party plugin locally and enable it
only when the Blu-ray/UHD feature and dependencies are explicitly selected in
the OPENHTPC installer. This preserves offline installation and coordinated
updates while keeping base installations and Doctor truthful. Model 1 leaves
a qualified selected feature unexpectedly inactive; Model 3 requires a mature
separate plugin-package installer and lifecycle that does not yet exist.

## Future physical qualification matrix

No physical validation is required for this documentation phase. A future
production cutover requires:

- ZimaBoard 2, plugin enabled: protected Blu-ray and protected UHD detection,
  classification, exact badge, enabled action, launch, image/audio,
  `OPEN_SUCCESS`, eject/current-state clearing, quit/return, plus DVD
  regression. UHD dropped-frame performance remains a known limitation.
- Ryzen AMD: plugin enabled, at least one practical optical regression,
  normal MEDIA playback and AMD runtime regression.
- NVIDIA: plugin enabled, normal MEDIA/NVDEC runtime regression and an optical
  regression when hardware/media are available.
- Negative matrix on a non-destructive fixture and, where practical, the
  validator: plugin absent, disabled and broken must expose no Blu-ray/UHD
  feature action while generic optical/Core health and DVD remain available.

## Frozen conclusion

No meaningful media-state pure/declarative responsibility remains in Core.
The next useful change is not more raw-I/O migration. It is a bounded feature
cutover that makes `plugin.bluray` required for Blu-ray/UHD policy and feature
exposure while retaining generic Core I/O, security, rendering and execution.

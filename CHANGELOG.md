# Changelog

# OPENHTPC 1.2.0 Release Candidate 8 — 1.2.0-rc8

- Implements Media Foundation persistent SQLite database with schema v3 (WAL mode, transactional consistency).
- Introduces normalized media probe and incremental filesystem scanner.
- Adds heuristic movie matcher and living-room interactive identity resolver within Flex Launcher.
- Implements on-screen manual movie search with full keyboard entry and safe navigation trampoline.
- Adds TMDb provider adapter for localized metadata snapshots and content-addressed poster cache.
- Displays cached movie posters in Flex Launcher via atomic short symlink projections in /tmp.
- Enforces strict zero-network invariant for living-room browsing, poster display, and media playback.
- Hardens runtime graphical context detection and Wayland/X11 socket validation for headless environments.

# OPENHTPC 1.2.0 Release Candidate 7 — 1.2.0-rc7

- Adds automatic display frame-rate matching for local media, DVD, and protected optical playback.
- Ensures hermetic mode switching and exact display mode restoration via KScreen.
- Synchronizes Couch UI display settings (`flex-v1.ini`) dynamically on preference changes without stale labels.
- Preserves HD bitstream across display mode changes with post-resync PipeWire sink re-identification and codec verification before MPV launch.
- Defers native HDR switching (OPENHTPC does not mutate KDE HDR state; HDR→SDR tone mapping remains a separate future image processing concern).
- Passes the complete RC7 physical release qualification on Fedora KDE with Denon AVR.

# OPENHTPC 1.2.0 Release Candidate 6 — 1.2.0-rc6

- Centralizes and shares dynamic PipeWire IEC958 sink preparation helper between Protected Optical and MEDIA playback policy.
- MEDIA BITSTREAM now dynamically prepares HDMI sink for HD codecs (`EAC3`, `TrueHD`, `DTS-HD`) before MPV launch.
- Recovers MEDIA bitstream passthrough after dynamic HDMI sink recreation (e.g. HDMI hotplug / AVR power cycling).
- Leaves MEDIA PCM mode unchanged (skipped preparation, no PipeWire mutation).
- Keeps Protected Optical functionally unchanged and fully compatible.
- Awaits Steve's physical qualification on Fedora KDE with Denon AVR.

# OPENHTPC 1.2.0 Release Candidate 5 — 1.2.0-rc5

- Corrects PipeWire IEC958 state authority to query active SPA parameters via `pw-cli enum-params <node_id> Props`.
- Eliminates false-negative `MUTATION_NOT_EFFECTIVE` diagnostic when HDMI sink node already has 6 effective codecs (`PCM`, `DTS`, `AC3`, `EAC3`, `TrueHD`, `DTS-HD`).
- Implements `ALREADY_COMPATIBLE` idempotent handling without redundant `pw-cli` mutation when effective SPA codecs are already present.
- Preserves distinct reporting of static `iec958_property_codecs` and runtime effective `iec958_codecs_before` / `iec958_codecs_after`.
- Retains exact bitstream MPV invocation contract and PCM pass-through isolation.
- Awaits Steve's physical qualification on Fedora KDE with Denon AVR.

# OPENHTPC 1.2.0 Release Candidate 4 — 1.2.0-rc4

- Implements dynamic PipeWire HDMI sink resolution and deterministic `iec958.codecs` preparation for protected Blu-ray bitstream passthrough.
- Ensures required bitstream HD codecs (`PCM`, `DTS`, `AC3`, `EAC3`, `TrueHD`, `DTS-HD`) are active on the HDMI sink node.
- Verifies preparation post-mutation and enriches atomic diagnostics in `~/.local/state/openhtpc/protected-optical-last-command.json`.
- Preserves PCM mode behavior without bitstream allowlist or PipeWire sink mutation.
- Awaits Steve's physical qualification on Fedora KDE with Denon AVR.

# OPENHTPC 1.2.0 Release Candidate 3 — 1.2.0-rc3

- Made protected Blu-ray bitstream track, channel, and SPDIF audio policy explicit.
- Retained last execution command and diagnostic log evidence.

# OPENHTPC 1.2.0 Release Candidate 2 — 1.2.0-rc2

- Added protected optical stabilization following RC1 physical NO-GO.

# OPENHTPC 1.2.0 Release Candidate 1 — 1.2.0-rc1

- Promotes the physically qualified Dev14 Plugin Framework P2 production-cutover baseline without functional changes.
- Records `plugin.bluray` opt-in Blu-ray/UHD ownership, corrected disabled-plugin UI gating and Core-owned DVD behavior.
- Preserves protected-media `AVAILABLE` as `READY_TO_ATTEMPT`, never guaranteed per-disc decryptability.
- Awaits the separate RC1 physical release gate before any tag or publication.

# OPENHTPC Plugin Framework P2 UI Gating — 1.2.0-dev14

- Prevents protected-optical play actions from remaining visible when `plugin.bluray` is disabled, absent or broken.
- Preserves Core-owned DVD behavior.
- Records multi-platform physical qualification on Intel/ZimaBoard 2, AMD/Ryzen and NVIDIA/RTX 3050; Dev14 is a qualified candidate for a separate RC-preparation step, not an RC.

# OPENHTPC Plugin Framework P2 Production Cutover — 1.2.0-dev13

- Identifies the production plugin cutover software candidate, awaiting physical qualification.

# OPENHTPC Plugin Framework P2 Optical Static Assets — 1.2.0-dev12

- Moves byte-identical qualified Blu-ray and Ultra HD Blu-ray 4K badge resources into the disabled first-party plugin.
- Adds allowlisted, in-root, regular-PNG resource declarations with traversal, URI and symlink-escape rejection.
- Keeps exact Core assets as fallback and retains all asset loading, equivalence checking and Flex rendering in Core.

# OPENHTPC Plugin Framework P2 Structural Fact Normalization — 1.2.0-dev11

- Transfers only deterministic normalization of Core-acquired BDMV/INDX and structural protection primitives to enabled `plugin.bluray`.
- Keeps structural and libbluray fragments distinct until the validated Core raw-fact merge and Phase 8 classifier.
- Retains every mounted-filesystem operation, BDMV/INDX read, fallback and canonical-state publication in Core.

# OPENHTPC Plugin Framework P2 libbluray Fact Normalization — 1.2.0-dev10

- Transfers only deterministic normalization of Core-acquired libbluray primitive facts to enabled `plugin.bluray`.
- Preserves independent AACS/BD+ detected and handled facts plus normalized INDX versions without performing classification.
- Keeps device handles, every libbluray/BDMV call, structural fallback, raw-fact merge and canonical publication in Core with exact fallback.

# OPENHTPC Plugin Framework P2 Optical Classification — 1.2.0-dev9

- Transfers deterministic Blu-ray/UHD classification of normalized Core probe facts to enabled `plugin.bluray`.
- Preserves the INDX0300-only UHD rule, AACS/BD+ detection semantics, source precedence and confidence policy.
- Keeps all physical I/O, library calls, structural reads and canonical-state publication in Core with exact fallback.

# OPENHTPC Plugin Framework P2 Optical UI Contribution — 1.2.0-dev8

- Transfers only the declarative Blu-ray/UHD menu contribution to enabled `plugin.bluray`.
- Consumes validated Phase 4 presentation and Phase 6 decision data without reclassifying or regating media.
- Keeps Flex rendering, asset resolution, action tokens, dispatcher enforcement and playback execution in Core.

# OPENHTPC Plugin Framework P2 Optical Playback Decision — 1.2.0-dev7

- Transfers only the deterministic protected-optical playback-decision projection to enabled `plugin.bluray`.
- Retains exact Core fallback and Core ownership of UI gating, action tokens, dispatcher revalidation and playback execution.
- Preserves `AVAILABLE` as ready-to-attempt and keeps per-disc history outside the decision.

# OPENHTPC Plugin Framework P2 Optical Capability — 1.2.0-dev6

- Transfers only protected-optical capability projection to enabled `plugin.bluray`.
- Keeps all probing and canonical snapshot generation in Core.
- Preserves `AVAILABLE` as ready-to-attempt rather than per-disc success.

# OPENHTPC Plugin Framework P2 Optical Presentation — 1.2.0-dev5

- Transfers only Blu-ray/UHD descriptor selection to enabled `plugin.bluray`.
- Keeps a byte-equivalent Core mapping and requires exact A/B equality.
- Keeps Flex rendering and allowlisted resolution of existing badge assets in Core.

# OPENHTPC Plugin Framework P2 Protected Optical Doctor — 1.2.0-dev4

- Transfers only protected-optical Doctor row projection to enabled `plugin.bluray`.
- Retains exact Core fallback, runtime isolation and Core-owned Overall aggregation.
- Requires live semantic A/B equality before selecting plugin authority.

# OPENHTPC Plugin Framework P2 Protected Optical Shadow — 1.2.0-dev3

- Adds the disabled first-party `plugin.bluray` manifest and bounded loader.
- Adds a side-effect-free Core observation contract and read-only equivalence adapter.
- Preserves all qualified protected-optical, DVD, media and GPU runtime ownership in Core.

# OPENHTPC Plugin Framework P2 Registry Foundation — 1.2.0-dev2

- Replaces the competing legacy manifest model with one strict declarative V2 schema and explicit plugin API compatibility.
- Adds safe, deterministic project/user discovery, enablement state, provider hooks and a canonical registry snapshot without plugin execution or network access.
- Modernizes non-blocking Doctor plugin states while keeping qualified Protected Optical Dev5 temporarily integrated into Core.

# OPENHTPC Protected Optical Provider Phase 5 — 1.1.4-dev5

- Consolidates physical gates for protected Blu-ray, DVD regression and protected UHD opening while recording UHD dropped frames as a deferred limitation.
- Propagates the existing `INDX0300` structural proof through libbluray so protected, unmounted UHD media selects the dedicated Ultra HD Blu-ray 4K badge.
- Documents honest Plugin Registry semantics and the future Plugin Framework P2 ownership boundary without extracting code.

# OPENHTPC Protected Optical Provider Phase 4 — 1.1.4-dev4

- Classifies physical Blu-ray, AACS and BD+ facts from libbluray's public disc-information API, with a structural read-only fallback.
- Keeps exact Blu-ray/UHD identity conservative and accepts `BLURAY_FAMILY` for the generic gated `bd://` attempt.
- Reports classification source, confidence, protection mechanisms and handled status without acquiring or directly reading key material.

# OPENHTPC 1.1.3 Release Candidate 2 — 1.1.3-rc2

- Promotes the physically qualified Dev19 NVIDIA stabilization baseline without additional functional changes.
- Adds bounded native NVIDIA Vulkan/NVDEC support and preserves the qualified Intel/AMD VA-API paths.
- Records physical MPEG-2, H.264, and HEVC Main 10 NVDEC qualification on the Fedora 44 NVIDIA validator.
- Preserves all qualified Dev16/RC1 MEDIA synchronization, update, optical, audio, and desktop-return behavior.

# OPENHTPC NVIDIA NVDEC MPEG-2 whitelist — 1.1.3-dev19

- Preserve mpv 0.41's default hardware-decoder codec whitelist and add `mpeg2video` only for native NVIDIA NVDEC profiles that report MPEG-2 support.
- Keep NVIDIA Vulkan/NVDEC selection and Intel/AMD VAAPI runtime generation unchanged.

# OPENHTPC NVIDIA native backend — 1.1.3-dev18

- Discovers NVDEC through a bounded, PCI-associated NVIDIA software-stack probe without fabricating physical validation.
- Prefers a directly capable display GPU before considering an unqualified multi-GPU offload path.
- Generates native MPV NVDEC PURE and REFERENCE runtimes without a VA-API device option.
- Rebuilds stale or legacy Hardware Passports through a safe, non-interactive product workflow.

# OPENHTPC NVIDIA native foundation — 1.1.3-dev17

- Characterizes the qualified Intel/AMD VA-API and Vulkan runtime paths without changing them.
- Tracks Capability Snapshot provenance in new Hardware Passports and generated runtimes.
- Reports stale and legacy passports without fabricating compatibility.
- Fixes the public initial setup argument contract.

# OPENHTPC 1.1.3 Release Candidate 1 — 1.1.3-rc1

- Promotes the physically qualified Dev16 implementation without functional product changes.
- Records consistent RC identity across source, installer, runtime provenance, validator metadata, and artifact tooling.
- Adds bounded RC1 release notes and completed update/fresh-install qualification evidence.

# OPENHTPC running Flex MEDIA generation synchronization — 1.1.3-dev16

- Synchronizes every cached MEDIA descendant when a committed live source mutation changes the authoritative MEDIA generation.
- Retains the single authoritative Flex process and redirects removed current descendants to MEDIA_ROOT.
- Preserves Dev15 atomic config/Flex/manifest publication and Dev12 optical-only generation preservation.
- Rebuilds and records the shipped Flex ELF from the Dev16 vendor source.

# OPENHTPC MEDIA live refresh manifest activation — 1.1.3-dev15

- Publishes live MEDIA source configuration, Flex graph, candidate manifest, and
  authoritative action manifest as one rollback-safe transaction.
- Propagates publication failures truthfully and restores the exact prior user
  configuration and MEDIA generation without weakening token validation.
- Preserves Dev12 optical-only MEDIA generation binding and all Dev14 runtime behavior.

# OPENHTPC update runtime regeneration — 1.1.3-dev14

- Regenerates version-derived runtime and MPV configuration during updates from
  the preserved Hardware Passport and freshly observed canonical capabilities.
- Preserves user configuration, MEDIA sources, TMDb credentials and confirmed
  disc associations, audio preference, caches, and the valid Hardware Passport.
- Refuses to report a successful update when capability refresh or runtime
  regeneration cannot produce a truthful READY state.
- Uses the same authoritative runtime generator for fresh Builder execution and
  update migration, including the qualified VA-API policy.

# OPENHTPC Optical TMDb search recovery UX — 1.1.3-dev13

- Conservatively removes recognized technical suffixes from TMDb search queries
  while preserving the physical label and optical identity unchanged.
- Adds a generation-bound manual title and optional-year recovery path only after
  a genuine automatic `NO_RESULT`, with explicit confirmation before persistence.
- Reuses the existing physical-disc cache so confirmed DVDs resolve after reinsertion.
- Preserves the qualified automatic ambiguity picker without new entries or layout changes.

## OPENHTPC MEDIA action-token runtime binding — 1.1.3-dev12

- Keeps the authoritative MEDIA generation stable across optical-only menu
  regeneration, so unchanged dynamic `MEDIA_<hash>` pages and their secure
  action manifest retain the same token binding.
- Continues to advance MEDIA generation for genuine MEDIA graph generation;
  stale, unknown, malformed and wrong-page tokens remain rejected.
- The captured `current_page=MEDIA` value was a pending diagnostic default,
  not evidence that Flex published generic MEDIA instead of a hashed page.

## OPENHTPC optical disc auto-open UX — 1.1.3-dev11

- Auto-opens the optical disc sheet only for a new insertion observed while
  HOME is active, using generation-scoped navigation requests.
- Returns to HOME when the active disc sheet observes eject, while SYSTÈME,
  MEDIA, settings and playback retain their current navigation authority.
- Preserves startup with an already-present disc, TMDb enrichment and the
  existing ambiguous-result picker without replaying stale navigation.

## OPENHTPC TMDb picker close and media logo — 1.1.3-dev7

- Extends the existing presentation signature to generation-scoped optical
  metadata, so a successful ambiguous-result commit regenerates the active
  disc menu and removes its candidate entries immediately.
- Restores the official derived Blu-ray media logo for `BLURAY_FAMILY` while
  retaining separate `BLU-RAY / UHD` exact-type-unknown informational truth.

## OPENHTPC optical TMDb selection UI — 1.1.3-dev6

- Presents cached ambiguous TMDb results as couch-readable selectable entries
  and commits the chosen identity only for the current optical generation.
- Keeps canonical optical media identity authoritative and rejects selection
  callbacks after eject or replacement by a newer disc generation.
- Attaches the canonical media badge to fallback or TMDb poster artwork,
  separates year/runtime metadata, and moves optical status out of actions.

## OPENHTPC emergency startup hotfix — 1.1.3-dev5

- Validates the mandatory HOME optical action by its authoritative
  `:submenu DISQUE` destination instead of a finite list of media-dependent
  display-label prefixes.
- Restores startup with EMPTY, DVD_VIDEO and BLURAY_FAMILY while retaining the
  action gate: a matching label without the real optical action is rejected.
- Records `DOCTOR_AUTOSTART_RUNTIME_SEMANTICS` as backlog only; Doctor behavior
  is deliberately unchanged.

## OPENHTPC Optical Media Core O1 Dev4 — 1.1.3-dev4

- Makes optical generation part of the HOME refresh identity and moves
  post-start menu regeneration into a bounded, generation-guarded worker.
- Publishes current live optical identity immediately, cancels obsolete work,
  rejects stale menu publication and emits a same-generation fallback after a
  five-second worker timeout.
- Enables generation-scoped TMDb enrichment for titled `BLURAY_FAMILY` media;
  only a real started lookup may present a searching state, and late results
  remain generation-guarded.
- Cross-checks canonical, disc-sheet and Flex generations in the validator,
  persists observer status, fixes absolute forensic paths and empty-drive udev
  discovery, and records journals plus file hashes/mtimes in captures.

## OPENHTPC Optical Media Core O1 Dev3 — 1.1.3-dev3

- Removes unbounded published `INITIALIZING`: stable canonical detection is now
  published directly, and MMC-confirmed BD media never enters the DVD probe.
- Makes eject a hard presentation invalidation boundary and requires generated
  disc-sheet provenance to match canonical state, optical generation and UI hash.
- Stages render results and rejects late TMDb/render commits from stale optical
  generations, with bounded JSONL lifecycle tracing.
- Adds the user-owned `~/OPENHTPC-VALIDATOR` lab with manifest-driven
  `apply-latest`, pre-change `capture`, and objective `observe optical` failure
  detection. No graphical start, playback, purge, root or stored credential.

## OPENHTPC Optical Media Core O1 Dev2 — 1.1.3-dev2

- Makes `canonical_state` authoritative for every optical media label, icon,
  provider message and fallback poster.
- Presents bounded `BLURAY_FAMILY` as `BLU-RAY / UHD` without selecting either
  playback plugin, even when labels or titles contain UHD/4K text.
- Replaces the hardcoded DVD generic poster with canonical media-aware DVD,
  Blu-ray, UHD, Blu-ray/UHD-family and unknown-optical fallbacks.
- Keeps TMDb as enrichment only: pending/no-result retains the correct fallback;
  a committed poster may replace it without changing optical identity.
- Does not change O1 detection evidence or any playback path.

## OPENHTPC Optical Media Core O1 — 1.1.3-dev1

- Separates canonical physical-medium detection from playback-provider
  availability while preserving the qualified DVD path.
- Adds deterministic drive-empty, DVD-Video, Blu-ray Video, UHD Blu-ray Video,
  ambiguous Blu-ray-family, unknown-media and indeterminate states.
- Requires MMC/udev BD-media evidence plus the unencrypted `INDX0300`
  `BDMV/index.bdmv` header before identifying UHD; labels, capacity, BDXL and
  drive capability are never used as UHD proof.
- Adds a bounded, read-only, title-free optical forensic collector and truthful
  plugin-required couch UI wording. No Blu-ray/UHD playback was added.

## OPENHTPC AMD release metadata consistency — 1.1.2-dev5

- Propagate the root `VERSION` deterministically to payload metadata and the
  installer log version before candidate construction.
- Reject source trees and extracted archives whose version or build metadata
  disagree.
- Preserve Dev4 capability behavior without functional changes.

## OPENHTPC AMD canonical capability refresh — 1.1.2-dev4

- Synchronize current `profile.json` codec mirrors from the same observation
  produced by every successful `openhtpc capabilities --refresh` operation.
- Preserve GPU identity, runtime configuration and bounded per-codec history.
- Run the canonical refresh after installation even when codec dependencies
  are already installed and no package transaction occurs.

## OPENHTPC AMD codec consistency candidate — 1.1.2-dev3

- Keep the qualified Dev2 RPM Fusion Free remediation and accept MPEG-2
  software fallback when the current freeworld VAAPI driver omits MPEG-2.
- Make `media_stack.observed_capabilities` authoritative inside `profile.json`
  and atomically synchronize all existing GPU-topology compatibility mirrors.
- Record VAAPI capability gains and losses individually without fabricating
  playback validation.

## OPENHTPC AMD Base validation candidate — 1.1.2-dev1

- Remove the historical Intel-only runtime-generation veto.
- Generate PURE/REFERENCE candidates only when the existing observed Vulkan,
  VAAPI, render-node, direct-display and MPV capability gates all pass.
- Keep AMD physical validation pending and preserve unvalidated-offload safety.

## OPENHTPC 1.1 audio final semantic corrective — 1.1.1-rc3

- Make requested PCM deterministically report passthrough as inactive,
  immediately and without requiring playback observation.
- Preserve BITSTREAM observation semantics and all forensic history.

## OPENHTPC 1.1 audio corrective — 1.1.1-rc2

- Preserve the physically validated PCM/BITSTREAM MPV and PipeWire policy.
- Refresh the AUDIO page and mode label synchronously after couch selection.
- Capture isolated MPV runtime evidence for DVD and publish the same bounded
  `AUDIO_POLICY_OBSERVED` state as local MEDIA playback.
- Place the AUDIO mode selector in the qualified lower system-page dock.
- Reuse existing lsdvd audio-format metadata when it identifies the DVD codec.

## OPENHTPC 1.1 maintenance candidate — 1.1.1-rc1

- Add one persistent PCM/BITSTREAM output policy, with safe PCM migration and
  codec-bounded MPV passthrough for AC3, E-AC3, DTS/DTS-HD and TrueHD.
- Remove audio-mode and HDR-capability questions from fresh installation.
- Record requested and observed audio policy without treating channel count or
  configured `audio-spdif` as proof of active passthrough.
- Include bounded audio policy, MPV observation and default PipeWire sink data
  in the support bundle.

## OPENHTPC 1.1 RC3 final corrective — 1.1.0-dev38

- Resolve DVD `FR_FULL` from qualified `lsdvd` language inventory through MPV's
  documented DVD language selector, without assuming lsdvd-to-MPV track IDs.
- Refresh an already-loaded DVD detail menu after the global presentation mode
  changes from SYSTÈME → LECTURE.
- Preserve dev37 UI geometry, artwork, OSD, audio and presentation semantics.

## OPENHTPC 1.1 RC3 final UI and optical artwork — 1.1.0-dev37

- Separates the approved playback dock icons vertically from their labels.
- Shows only the active user video-mode preference in the startup OSD.
- Integrates deterministic UI derivatives of Steve's optical-media artwork.
- Leaves playback, DVD detection and all media policies unchanged.

## OPENHTPC 1.1 RC3 playback UX corrective — 1.1.0-dev36

- Keeps LECTURE available when system capabilities are partial or unavailable.
- Restores the approved six first-party icons inside the lower action dock.
- Explains requested policy and resolved profile on separate OSD lines.
- Preserves the global DVD mode shortcut and qualified playback policy.

## OPENHTPC 1.1 RC3 playback UX candidate — 1.1.0-dev35

- Places all playback controls in the real Flex bottom dock below status.
- Applies each playback preference synchronously and reloads its parent view.
- Shows only the effective applied presentation mode in the startup OSD.
- Adds a DVD-sheet shortcut to the same global presentation preference.

## OPENHTPC 1.1 RC3 corrective candidate — 1.1.0-dev34

- Separates the LECTURE status card from its bottom action zone.
- Makes presentation-mode page refresh observable without restarting Flex.
- Sends the startup OSD as literal multiline UTF-8 in one argument.
- Preserves the dev33 icons and qualified audio/subtitle engines.

## OPENHTPC 1.1 RC3 development candidate — 1.1.0-dev33

- Separates the LECTURE page into an informational active-preferences zone and
  a bottom action row with distinct first-party icons.
- Refreshes the active-preferences page immediately after a saved selection.
- Shows the resolved playback policy in a top-left MPV OSD for five seconds.
- Backlog: `FUTURE_MEDIA_LANGUAGE_PREFERENCE` will generalize the currently
  qualified French media-language policy after RC3, without changing dev33.

## Previous candidate — 1.1.0-dev32

- Added persistent couch-native presentation, audio-language and subtitle
  preferences under SYSTÈME → LECTURE.
- Wired qualified PURE/CINÉMA AUTO intent and deterministic language policy
  through local/DVD playback, MPV arguments, temporary OSD and structured logs.
- Added the À PROPOS screen and explicit first-party project provenance.
- Added opt-in OpenSSH Ed25519 release-signing and public verification tools.
- Preserved RC2 runtime, MEDIA dispatcher, DVD, C3/C4 and updater semantics.

## OPENHTPC 1.1 Public Candidate R2 — 1.1.0-dev31

- Refined only the generic DVD, BLU-RAY and UHD badge family and the DVD media
  sheet banner using original OPENHTPC primitives and generic descriptive text.
- No optical detection, playback, metadata or other functional code changed.

## OPENHTPC 1.1 Public Candidate R2 — 1.1.0-dev30

- Replaced the generic optical icon on QUITTER OPENHTPC with an original
  OPENHTPC door-and-exit-arrow symbol.
- Assigned the approved POWER symbol to ÉTEINDRE LE PC and a dedicated return
  arrow to RETOUR.
- Refined the MEDIA folder silhouette and generic DVD/BLU-RAY/UHD disc badges.
- No functional runtime behavior changed from the physically qualified dev29
  baseline.

## OPENHTPC 1.1 Public Candidate R2 — 1.1.0-dev29

- Prevented Flex/inih from truncating MEDIA action tokens when a displayed
  filename makes an INI entry exceed the parser's 200-byte input buffer.
- Kept full media paths exclusively in the action manifest; only the displayed
  label is shortened to fit the proven parser boundary.
- Added regression coverage for the physically failing dotted release name,
  long names, spaces, apostrophes, parentheses, release-group hyphens and UTF-8.

## OPENHTPC 1.1 Public Candidate R2 — 1.1.0-dev28

- Derived the public runtime strictly from physically qualified Media Sources
  dev27 (`core-media-sources-dev4`).
- Added qualified graphical management for zero to multiple filesystem media
  sources, including non-destructive removal and duplicate feedback.
- Simplified the HOME label to `MÉDIA`.
- Added original OPENHTPC POWER, folder and generic DVD/BLU-RAY/UHD artwork.
- Added manifest-based update convergence for obsolete managed files while
  preserving unknown and user-persistent files.
- Retained the qualified five-file benchmark set byte-for-byte and kept
  `filmgrain.glsl` excluded from public distribution.

## OPENHTPC 1.1 Public Candidate R1 — derived from 1.1.0-dev23

Changes since OPENHTPC Basic V1.0.0 Gold Master:

- Added the canonical System and Capability Engine UI integration.
- Added adaptive optical read-ahead with the qualified 12-second target and
  bounded forward/backward memory policy.
- Added local video render benchmarking and the versioned synthetic benchmark
  asset set.
- Added the qualified DVD visual recipe catalogue and real-disc blind-review
  outcomes.
- Added local auto-calibration with signature/event-driven staleness and
  observed-stability criteria.
- Added PURE and CINÉMA AUTO runtime/UI integration, including explicit couch
  recalibration and reliable KDE desktop restoration on quit.
- Added appliance idle/suspend inhibition while OPENHTPC owns the session.
- Added public licensing, third-party notices, provenance documentation and
  original replacement UI artwork for this distribution candidate.

R1 did not claim final `1.1.0` status.

## OPENHTPC Basic V1.0.0 Gold Master

- First qualified OPENHTPC Basic public baseline.

# OPENHTPC Protected Optical Provider Phase 1 — 1.1.4-dev1

- Add a read-only protected optical capability model for externally configured
  `libbluray`, `libaacs`, optional `libbdplus`, and user-provided `KEYDB.cfg`.
- Expose the optional state in Doctor without changing Overall READY when the
  external configuration is unavailable or incomplete.
- Preserve all RC2 playback dispatch, MPV, Hardware Passport, and GPU runtime
  behavior.

# OPENHTPC Protected Optical Provider Phase 2 — 1.1.4-dev2

- Classify Blu-ray/UHD protection independently from media type and external
  capability state.
- Gate the Flex Play action from canonical optical and capability truth, while
  preserving unprotected media and the existing DVD path.
- Revalidate generation, device, media type, and capability in a bounded
  optical dispatcher without implementing protected playback.

# OPENHTPC Protected Optical Provider Phase 3 — 1.1.4-dev3

- Connect authorized Blu-ray/UHD actions to MPV's system libbluray backend.
- Keep provider readiness separate from per-disc `OPEN_SUCCESS` and
  `OPEN_FAILED` results.
- Preserve the existing DVD and GPU runtime paths while rejecting stale,
  forged, removed-device, and no-longer-authorized optical actions.

Bounded contradictory review — OPENHTPC Magnificence GPU matrix
Reviewer: Hermes (read-only snapshot). Mission: AUDIT_MISSION.md. No file was modified; no host was contacted; no physical validation performed or claimed.

================================================================
0. EVIDENCE LIMITS OF THIS SNAPSHOT (read before the verdicts)
================================================================
FACT — The snapshot has no `.git` (verified: `git rev-parse HEAD` fails, "not a git repository"), so HEAD/status/stash could not be independently re-derived here. PROVENANCE.md:6 records HEAD `975402945376618db56e29945074ea30ddcd2cb8`, and the two continuity checkpoints restate the same value (docs/continuity/2026-10-11-it13-strong-dvd-resource-test.md:9, docs/continuity/2026-10-11-it13-system-magnificence-deployment.md:9). This is consistent but not independently re-verified.

FACT — The snapshot is a curated subset. `payload/` contains only 3 files (payload/assets/magnificence_gpu_knowledge.json, payload/assets/magnificence_profiles.json, payload/openhtpc-playback-policy.py). Verified MISSING: payload/assets/shaders/catalog.json, payload/assets/shaders/*.glsl, payload/managed-files.txt, payload/install-openhtpc-fedora.sh, payload/openhtpc-ui.py, payload/openhtpc-capabilities.py, payload/openhtpc-system-action, payload/openhtpc-session-engine.py.

Consequence — `tests/test_magnificence_policy.py` cannot execute in this snapshot: it imports those files (e.g. :141-148, :172-189, :607-623) and `_magnificence_choice` itself requires `install/assets/shaders/<name>.is_file()` (payload/openhtpc-playback-policy.py:321-323, :381-382). I therefore verified selection precedence STATICALLY, by reading the code, not by running the suite. Test PASS/FAIL claims are NOT made.

================================================================
1. WHAT I VERIFIED (FACT)
================================================================
F1. Family-rule inactivity is real. payload/assets/magnificence_gpu_knowledge.json defines exactly 22 `family_rules` (:82-410); all 22 have `"selection_status": "REFERENCE_ONLY"` and `"confidence": "COMMUNITY_DERIVED"`. `community_reference_rules_active` is `false` (:15). The runtime gate honours this: `_magnificence_family_rule` skips any rule whose `selection_status != "ACTIVE"` (payload/openhtpc-playback-policy.py:224). No rule is ACTIVE. → The mission's global claim "all 22 … REFERENCE_ONLY; none is ACTIVE" is CORROBORATED.

F2. Family recipes match the mission table. LIGHT=KrigBilateral (knowledge:27-36), MEDIUM=FSRCNNX-8+Krig (:37-47), STRONG=FSRCNNX-16+Krig+Vibrance (:48-63), HIGH=FSRCNNX-16+Krig+SSim+Vibrance (:64-80). The declared precedence is EXACT → FAMILY → LIGHT baseline → PURE (knowledge:5-10; GPU-EVIDENCE.md:30-38).

F3. Precedence in code. `_magnificence_choice` scans all exact profiles first and returns on match (playback-policy.py:359-397); only if none match does it call `_magnificence_family_choice` (:399), which returns the LIGHT baseline when no ACTIVE rule exists (:303-315) and requires the Vulkan+MPEG-2 capability baseline (:300-301, :251-280). Unknown but capable GPUs therefore get the LIGHT baseline; scope/source/resolution failures fall to PURE (:284-291). → precedence claim CORROBORATED (static).

F4. Frozen-contract hygiene holds. `grep` finds no `vaapi-device=`, no `renderD1xx`, no `card0/card1` anywhere in payload/ (matches AGENTS.md:222, :291-292). Decode policy hard-codes `physical_gpu_binding = "NOT_PROVEN"` (playback-policy.py:1769) and never infers decode identity from the render GPU. The RTX 3050 path uses `bwdif_cuda` + nvdec and injects no VAAPI semantics (magnificence_profiles.json:654-660). → Consistent with AGENTS.md:222-257, :310-353.

F5. The eight rows in AUDIT_MISSION.md map 1:1 to the eight JSON profiles, and every `gpu.hardware_class` equals its `classification.gpu_tier` (verified programmatically). Identity (pci_id), class, and selected shader chain in the matrix all match the repository:
  Intel N150 8086:46d4 LIGHT Krig — profiles:5-136 (:9, :12, :128-130)
  Vega 3 1002:15d8 LIGHT Krig — :137-275 (:141, :143, :260-262)
  Arc A310 8086:56a6 MEDIUM HQDN3D+FSRCNNX-16+Krig+Vibrance — :276-539 (:280, :282, :498-519)
  HD 630 8086:5912 MEDIUM FSRCNNX-8+Krig — :540-608 (:544, :546, :579-585)
  RTX 3050 10de:2507 HIGH HQ32+Krig+SSim+Vibrance — :609-691 (:613, :615, :648-660)
  RX 580 1002:67df STRONG FSRCNNX-16+Krig+SSim+Vibrance — :692-765 (:696, :698, :731-743)
  Meteor Lake-P 8086:7d55 STRONG vaapi-copy+BWDIF+FSRCNNX-16+Krig+Vibrance — :766-874 (:770, :772, :831-843)
  RX 5700 XT 1002:731f HIGH vaapi-copy+BWDIF+HQ32+Krig+SSim+Vibrance — :875-967 (:879, :881, :914-927)

================================================================
2. VERDICT TABLE
================================================================
Legend: CORROBORATED / PARTIALLY_CORROBORATED / NOT_CORROBORATED / INSUFFICIENT_EVIDENCE.

GPU                                        Identity/scope  Class  Recipe+argv  Technical  Visual/phys  Installed  VERDICT
Intel N150 8086:46d4 (LIGHT)               match           match  match        pass       limited      n/a        CORROBORATED
AMD Vega 3 1002:15d8 (LIGHT)               match           match  match        pass       pass*        n/a        CORROBORATED
Intel Arc A310 8086:56a6 (MEDIUM)          match           match  match        note†      pass         n/a        CORROBORATED
Intel HD 630 8086:5912 (MEDIUM)            match           match  match‡       thin       pass         n/a        CORROBORATED
NVIDIA RTX 3050 10de:2507 (HIGH)           match           match  match        thin       pass(hist)   n/a        CORROBORATED
AMD RX 580 1002:67df (STRONG)              match           match  match‡       thin       pass(hist)   n/a        PARTIALLY_CORROBORATED
Intel Meteor Lake-P 8086:7d55 (STRONG)     match           match  match        pass       pass(op)     yes        CORROBORATED
AMD RX 5700 XT 1002:731f (HIGH)            match           match  match        pass       pass         n/a        CORROBORATED
GLOBAL family / selection policy           —               —      —            —          —            —          PARTIALLY_CORROBORATED

  * Vega 3: the blind winner was PURE, Krig was 2nd — see FINDING C3/§5.
  † A310: the 69-minute real DVD session resolved FSRCNNX-8, not the selected FSRCNNX-16 — FINDING C1.
  ‡ HD 630 / RX 580: software lavfi BWDIF with no `--hwdec=vaapi-copy` — FINDING C2 (this is why RX 580 is downgraded).

================================================================
3. CONTRADICTIONS / MATERIAL FINDINGS
================================================================
C1. (FACT) A310 long real-session used the weaker recipe. The Arc A310 profile selects `RECIPE_MAG_SD_FSRCNNX16_KRIG_VIBRANCE_MILD` (magnificence_profiles.json:494) but its one long real-DVD session is recorded as `"presentation_resolved": "RECIPE_MAG_SD_FSRCNNX8_KRIG"` for the 1h09m25s / 8002-sample run (:459-478, esp. :463). The endurance evidence for the selected FSRCNNX-16 chain is a bench (`repeats:8`, :430-456), not the long session. A reader can wrongly infer that the 69-minute physical run validated the selected recipe. Also note the endurance-tested recipe is `RECIPE_MAG_SD_FSRCNNX16_KRIG` (no Vibrance; :418-456) while the selected recipe adds Vibrance Mild, and the profile itself concedes "No separate long-endurance requalification was performed for the color pass" (:532).

C2. (FACT) Software `lavfi` BWDIF without `vaapi-copy` on four code paths. Only three profiles carry `--hwdec=vaapi-copy`: A310 (:517), IT13 (:837), RX5700XT (:921). HD 630 (:584) and RX 580 (:739) use `--vf=lavfi=[bwdif=…]` with NO hwdec override, and ALL FOUR family recipes carry the same software BWDIF with no `--hwdec=vaapi-copy` (knowledge:34, :45, :58, :75). The repository documents that this exact combination fails: with the installed `hwdec=vaapi`, MPV logs "failed to configure the filter graph" and silently disables BWDIF; only `vaapi-copy` fixes it (docs/continuity/2026-10-11-it13-strong-dvd-resource-test.md:62; OPENHTPC-MAGNIFICENCE-ROADMAP.md:153). The authors acknowledge the family gap openly ("la recette de famille STRONG déclarée ne porte actuellement pas --hwdec=vaapi-copy") (it13-strong:64). Tests currently freeze the suspect behaviour rather than guard it: test_magnificence_policy.py:487 asserts `--hwdec=vaapi-copy` is ABSENT for HD 630, and the RX 580 test (:526-540) never asserts it either. → The DECODE FILTER graph on HD 630, RX 580, and every generalized family/baseline path is not proven to be active, contrary to the implied "BWDIF send_frame" intent.

C3. (FACT) The stated promotion gate ("blind visual benefit over the lighter recipe", magnificence_profiles.json:974-978) is not met by two "technically qualified" defaults. N150 visual_basis says "1080p-specific visual confirmation still pending" (:119) yet the profile is the selected default (:115-118). Vega 3's recorded blind result is "PURE winner, KrigBilateral 2nd finalist" (:264) — i.e. the lighter recipe (PURE) won — while Krig is still selected as the default enhancement (:256-263). These are defensible as explicit product decisions, but they are inconsistent with the selection_policy's own required gate.

C4. (FACT) Class label does not predict recipe load (non-monotonic). A310 is class MEDIUM but its exact shader set equals the STRONG family recipe (verified: {FSRCNNX-16, Krig, Vibrance} = knowledge STRONG :48-63) plus HQDN3D. RX 580 is class STRONG but its exact shader set equals the HIGH family recipe (verified: adds SSimSuperRes). This matches the mission's "exact recipe stronger than its family" pattern and is permitted by the exact-overrides-family rule, but it means LIGHT/MEDIUM/STRONG/HIGH no longer bound the realized load per GPU.

C5. (FACT) DVD source-scope is not actually PAL-scoped in code. `_magnificence_source_scope` returns `"DVD_PAL_FILM"` for ANY `kind == "dvd"` (playback-policy.py:65-68) with no resolution/fps/field check, and the exact-profile matcher compares only `source_scope.class` (not the recorded 720x576/25/MPEG-2 facts) (:371-374). An NTSC (720x480/29.97) or otherwise non-PAL DVD would therefore match the "DVD PAL" exact profiles whose own records claim PAL-only scope (e.g. IT13 scope_limit, magnificence_profiles.json:847). The same PAL-only assumption is baked into the family path (:284). → "source/output scope drift" the mission asked about does exist at the DVD branch.

C6. (FACT) Documentation internally inconsistent about IT13 promotion.
  - docs/OPENHTPC_MAGNIFICENCE_QUALIFICATION_PROTOCOL.md:139 states "Le IT13 reste hors des deux fichiers jusqu'à ce gate" (IT13 stays out of BOTH files until the gate). It is now IN magnificence_profiles.json:766-874.
  - OPENHTPC-MAGNIFICENCE-GPU-EVIDENCE.md:25-26 still calls the IT13 "the installed but unqualified GEEKOM IT13 Max", while the same document's own IT13 section (:42-64) records the exact profile and operator physical validation.
  These are stale sentences, not recipe errors, but they contradict the implemented state.

C7. (FACT) Diagnostic mislabel risk for Meteor Lake Arc. `is_intel_dg2` matches on the substring "arc" in model or Vulkan name, or a device id starting "56" (playback-policy.py:1773-1779). Meteor Lake's own record is Vulkan name `Intel(R) Arc(tm) Graphics (MTL)` (GPU-EVIDENCE.md:46), so an IT13 would be tagged with the diagnostic limit `INTEL_DG2_NO_HARDWARE_VC1` (:1781-1782) that describes Alchemist/DG2, not Meteor Lake. Diagnostic-only (does not gate selection), but factually wrong for that device.

================================================================
4. HYPOTHESIS (clearly not proven)
================================================================
H1. The HD 630 and RX 580 concrete-preset `bwdif` stages are probably inert on their direct-VAAPI runtime paths, for the same reason the IT13 record documents (it13-strong:62). I did NOT observe this on those hosts; it is inferred from (a) the shared software-filter + no-vaapi-copy pattern and (b) the documented sibling failure. (Maps to C2.)

H2. Because `deint=interlaced` only acts on interlaced frames and PAL film content is repeatedly described as progressive (magnificence_profiles.json:489, :947), the practical impact of C2 on those specific PAL-film runs may be small — but this would have to be shown, not assumed, and would not apply to genuinely interlaced sources.

H3. C5's NTSC risk is a code-path inference; I did not construct an NTSC probe. An NTSC DVD with a matching PCI and 3840x2160 output would, per the code as written, select the PAL exact profile.

================================================================
5. OPEN QUESTIONS
================================================================
Q1. For HD 630 and RX 580, was the installed runtime `hwdec` direct (`vaapi`) or `vaapi-copy` on the machines actually used? The profiles record `video_backend: "vaapi"` (:553, :705) but the decode filter activation is not recorded. If direct, the C2/H1 concern is live; if copy, the profiles are simply under-specified. This cannot be resolved from the snapshot (no effective pure.conf/reference.conf included).

Q2. Why was RX 580 (STRONG, validated 2026-10-01) never re-run with the corrected path that RX 5700XT received on 2026-10-09 (OPENHTPC-MAGNIFICENCE-ROADMAP.md:153-157)? Same chassis (Core i7-7700), same software-filter lineage.

Q3. Does the intent of `--vf=lavfi=[bwdif=…]` in the family recipes actually require it, given the source class is film/progressive? If the filter is a no-op on progressive material, the family recipes may be carrying dead weight (and a latent direct-VAAPI incompatibility) rather than a benefit.

Q4. Should the A310 profile's long-session record be annotated so `presentation_resolved = RECIPE_MAG_SD_FSRCNNX8_KRIG` is not mistaken for validation of the FSRCNNX-16 selection (C1)?

Q5. Is "unknown capable GPU → LIGHT baseline" intended to include the software BWDIF stage (knowledge:33-35), or should the baseline be KrigBilateral only as the GPU-EVIDENCE "Frozen inferred recipes" table implies ("LIGHT | KrigBilateral", GPU-EVIDENCE.md:66-72)? The JSON family recipe and the prose differ on this point.

================================================================
6. PER-GPU ONE-LINE DISPOSITIONS
================================================================
- Intel N150: CORROBORATED. Identity/class/recipe/technical all match; visual confirmation is correctly described as limited (:119). (Note C3.)
- AMD Vega 3: CORROBORATED. Identity (PCI + CPU match gate) and class match; recipe matches; blind evidence exists, but PURE won it (:264) — see C3.
- Intel Arc A310: CORROBORATED. Exact .229 qualification is corroborated (docs/continuity/2026-10-10-131-reprise-qualification.md:310; docs/OPENHTPC_REFERENCE_PLATFORMS.md:23); see C1 for the FSRCNNX-8 session nuance and :532 for the un-requalified Vibrance pass.
- Intel HD 630: CORROBORATED (claim = "live visual validation", which is recorded, :590-604). Technical evidence is qualitative only (no measurement block); see C2/H1 for the unverified BWDIF stage. Roadmap RC2 physical PASS adds corroboration (ROADMAP.md:95-112).
- NVIDIA RTX 3050: CORROBORATED. HIGH/HQ32 chain, nvdec + bwdif_cuda, no VAAPI injection, historical live validation (:674-690). No quantitative measurement recorded.
- AMD RX 580: PARTIALLY_CORROBORATED. Class/recipe/visual match, but the software BWDIF runs with no `--hwdec=vaapi-copy` while its validated sibling (RX 5700XT) was corrected for exactly that — an unaddressed, untested inconsistency (C2, Q2).
- Intel Meteor Lake-P / IT13: CORROBORATED for the row's claim (operator-qualified bounded run + installed selection software-verified; magnificence_profiles.json:826-869; deployment doc:42-52). Config contradicts elsewhere (C6); the record is otherwise honest (render PROVEN, decode OBSERVED, physical decode NOT_PROVEN, :854-868).
- AMD RX 5700 XT: CORROBORATED. Identity/class/recipe/argv match; corrected vaapi-copy+BWDIF path is documented and revalidated (ROADMAP.md:149-158; 131-reprise:263); .67 physical qualification corroborated (OPENHTPC_REFERENCE_PLATFORMS.md:24).

GLOBAL family/selection policy: PARTIALLY_CORROBORATED. What is claimed and true: 22 REFERENCE_ONLY rules, none ACTIVE (F1); recipe/tier table (F2); precedence EXACT→FAMILY→LIGHT→PURE (F3); frozen-contract hygiene (F4). What weakens it: the generalized family recipes carry a software BWDIF stage with no `--hwdec=vaapi-copy` while the repository documents that exact stage being silently disabled under direct VAAPI (C2), the DVD source class is not truly PAL-scoped (C5), and the selection_policy's own blind-benefit gate is unmet by two shipped defaults (C3).

================================================================
7. RECOMMENDED DOCUMENTATION CORRECTIONS / FUTURE TESTS (no code, no deploy)
================================================================
D1. Fix stale prose: OPENHTPC_MAGNIFICENCE_QUALIFICATION_PROTOCOL.md:139 and OPENHTPC-MAGNIFICENCE-GPU-EVIDENCE.md:25 ("installed but unqualified") vs the now-installed exact IT13 profile (magnificence_profiles.json:766-874). (C6)
D2. Annotate A310 magnificence_profiles.json:459-478 so the FSRCNNX-8 `real_dvd_session` is not read as FSRCNNX-16 validation, and note that the color (Vibrance) pass had no endurance requalification (:532). (C1)
D3. Reconcile the family LIGHT recipe (knowledge:27-36, includes BWDIF) with the prose table (GPU-EVIDENCE.md:66-72, "LIGHT | KrigBilateral") — decide explicitly whether the baseline carries BWDIF. (Q5)
D4. Either add `--hwdec=vaapi-copy` to the family recipes / HD 630 / RX 580 where a software `lavfi` filter is present, or document that those paths intentionally rely on a filter that may be disabled, per AGENTS.md positive/negative-hwdec policy. This is an architecture decision, not a reviewer action. (C2)
D5. Future tests to add (hermetic, static): assert that any profile/family recipe containing `--vf=lavfi=[…]` also carries a compatible `--hwdec`; assert that the DVD scope classifier distinguishes PAL from NTSC (720x576/25 vs 720x480/29.97) rather than mapping every DVD to `DVD_PAL_FILM`; assert that a status beginning `TECHNICALLY_QUALIFIED` but with a pending/limited `visual_basis` is surfaced as such.
D6. Note C7: the `is_intel_dg2` "arc" substring will tag Meteor Lake Arc with a DG2-specific diagnostic; make the predicate architecture-specific if the label is ever shown to a user.

================================================================
8. AUTHORITY / LIMITS OF THIS REPORT
================================================================
This is a bounded read-only review (AGENTS.md: read-only, no `.git` authority, no credentials, no hosts). It does not authorize any code change, commit, merge, push, deployment, release, or physical operation, and it grants no promotion of any family rule. All verdicts are repository-evidence verdicts; nothing here constitutes physical qualification. Where the snapshot could not support a claim (running the test suite, reading effective runtime configs, re-deriving HEAD), I marked it INSUFFICIENT / OPEN rather than promoting it.

# OPENHTPC 1.1.3-dev5 emergency startup hotfix

Root cause: the generated HOME optical entry remained the mandatory Core action
`:submenu DISQUE`, but startup validation inferred that action solely from a
finite label-prefix list. `BLURAY_FAMILY` generates `Blu-ray / UHD - <title>`,
which was absent from the list, causing `UI_ACTION_MISSING:OPENHTPC:LECTEUR`
before Flex started.

Fix: for `OPENHTPC:LECTEUR`, validate the authoritative `:submenu DISQUE`
action. All other action gates remain unchanged, and a Blu-ray-family label
without the real optical action is still rejected.

Focused tests: 15/15 PASS. Full regression: 194/194 PASS.

No optical detection, generation, TMDb, artwork, playback, codec, audio,
plugin, power, observer or Doctor behavior changed.

Backlog retained: `DOCTOR_AUTOSTART_RUNTIME_SEMANTICS`.

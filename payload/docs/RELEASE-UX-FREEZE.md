# OPENHTPC Basic V1 — Release UX Freeze

After RC20, these Basic V1 contracts are frozen. Only demonstrated release blockers may change them before 1.0.0.

## HOME

Order: dynamic optical entry, EJECTER, MEDIA, SYSTEME, ETEINDRE.

- Empty: `LECTEUR` / `Aucun disque`.
- Probe: `LECTEUR` / `Initialisation du disque…`.
- Ready DVD: `DVD - <Titre>`.

Optical state never disables MEDIA, SYSTEME or ETEINDRE.

## DVD sheet

A playable DVD opens the movie sheet with exactly: `LIRE LE DVD`, `CONFIGURER TMDb`, `ÉJECTER`, `RETOUR`. LIRE is the default. TMDb is optional progressive enrichment; local playback never depends on it.

## Back

ESC and BACKSPACE are contextual Back. HOME is non-destructive. DISC, SYSTEME and POWER return HOME. MEDIA returns to its parent, then HOME at its root.

## Appliance continuity

Normal foreground ownership is OPENHTPC or MPV. KDE appears only after explicit Quit. Plasma optical popups remain suppressed only during appliance mode.

## Installer mutation policy

`CHECK → EXPLAIN → ASK → INSTALL → VERIFY`. Every system/repository mutation is explicit and scoped. OPENHTPC never performs a general Fedora upgrade and never hides sudo actions.

# OPENHTPC 1.1.3 Dev16 — Running Flex MEDIA Generation Synchronization

Version: 1.1.3-dev16  
Build: running-flex-media-generation-sync-dev16

Dev16 corrects the physical Dev15 failure in which the authoritative HOME Flex
process retained cached generation-23 MEDIA descendants after a coherent
generation-25 disk publication. A committed MEDIA generation change now reloads
all cached MEDIA-derived sections in the running authoritative Flex process.

Automated qualification:

- Targeted reconciliation: 30/30 PASS
- Focused Dev16 gate: 35/35 PASS
- Full regression: 314/314 PASS, exit 0
- Shipped Flex SHA-256: 351fbe72572fa719fd325899e6ab3703cf42de9a62732904c80555daf236448c
- Shipped Flex build ID: 77862cb627f4f324f99a4c08a5bba5f8d4958901

Physical qualification remains required on Ryzen: cache the MEDIA/Dvd submenu,
remove and re-add `/home/steve/media`, then launch Alerte.mkv immediately without
restarting OPENHTPC.

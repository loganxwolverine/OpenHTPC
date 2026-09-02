# OPENHTPC 1.2.0 RC3

Pre-release: **Yes**  
Physical validation: **PENDING**

## Français

RC3 stabilise uniquement l'audio Blu-ray protégé. La sélection de piste, la
politique de canaux et la liste SPDIF sont désormais explicites, tandis que le
mode PCM désactive explicitement SPDIF. L'argv final, la piste, le décodeur,
AO et le résultat du processus sont conservés après la lecture.

RC2 a physiquement produit STEREO sur l'AVR en mode BITSTREAM. Le défaut de
contrat logiciel est identifié, mais sa causalité physique exacte n'est pas
prouvable rétroactivement faute de traces RC2. RC3 reste non qualifié jusqu'au
test physique de Steve.

## English

RC3 stabilizes protected Blu-ray audio only. Track selection, channel policy
and the SPDIF allowlist are now explicit, while PCM explicitly disables SPDIF.
Final argv, track, decoder, AO and process-result evidence survive playback.

RC2 physically produced AVR STEREO in BITSTREAM mode. The software contract
defect is identified, but exact physical fallback causality is not
retrospectively provable because RC2 retained no evidence. RC3 remains
unqualified until Steve's physical test.

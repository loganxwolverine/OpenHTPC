#!/usr/bin/env bash

set -Eeuo pipefail

readonly OPENHTPC_VERSION="1.1.0-dev31"


readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SOURCE_BUILDER="${SCRIPT_DIR}/openhtpc-builder.sh"
readonly SOURCE_PLAYER="${SCRIPT_DIR}/openhtpc-player-test.sh"
readonly SOURCE_ANALYZER="${SCRIPT_DIR}/openhtpc-playback-analyze.py"
readonly SOURCE_SESSION="${SCRIPT_DIR}/openhtpc-session-start"
readonly SOURCE_SESSION_ENGINE="${SCRIPT_DIR}/openhtpc-session-engine.py"
readonly SOURCE_INITIAL_SETUP="${SCRIPT_DIR}/openhtpc-initial-setup.py"
readonly SOURCE_MEDIA_BROWSER="${SCRIPT_DIR}/openhtpc-media-browser"
readonly SOURCE_MEDIA_BROWSER_ENGINE="${SCRIPT_DIR}/openhtpc-media-browser.py"
readonly SOURCE_PLAY="${SCRIPT_DIR}/openhtpc-play"
readonly SOURCE_OPTICAL="${SCRIPT_DIR}/openhtpc-optical.py"
readonly SOURCE_DVD_DEPENDENCIES="${SCRIPT_DIR}/openhtpc-dvd-dependencies.py"
readonly SOURCE_FEDORA_DEPENDENCIES="${SCRIPT_DIR}/openhtpc-fedora-dependencies.py"
readonly SOURCE_DNF_TRANSACTION="${SCRIPT_DIR}/openhtpc-dnf-transaction.py"
readonly PRODUCT_FILES=(openhtpc openhtpc-core.py openhtpc-capabilities.py openhtpc-readahead.py openhtpc-benchmark.py openhtpc-recipes.py openhtpc-visual-review.py openhtpc-calibrate.py openhtpc-calibrate-ui openhtpc-cinema-auto.py openhtpc-video-profile.py openhtpc-eject-current openhtpc-power-menu openhtpc-tmdb.py openhtpc-fedora-dependencies.py openhtpc-dnf-transaction.py openhtpc-system-page openhtpc-system-model.py openhtpc-system-action openhtpc-system-view openhtpc-ui.py openhtpc-disc-sheet.py openhtpc-disc-view.py openhtpc-configure-tmdb openhtpc-appliance-mode openhtpc-kde-device-popup openhtpc-desktop-restore.py openhtpc-support-bundle.py openhtpc-quit openhtpc-home.py openhtpc-installer-ui.py openhtpc-theme.py openhtpc-runtime.py openhtpc-bind-disc openhtpc-media-sources openhtpc-media-picker openhtpc-media-remove openhtpc-media-sources-action openhtpc-update-managed-files)


readonly SOURCE_FLEX="${SCRIPT_DIR}/flex"
readonly INSTALL_DIR="${HOME}/.local/lib/openhtpc"
readonly BIN_DIR="${HOME}/.local/bin"
readonly INSTALLED_BUILDER="${INSTALL_DIR}/openhtpc-builder.sh"
readonly INSTALLED_PLAYER="${INSTALL_DIR}/openhtpc-player-test.sh"
readonly INSTALLED_ANALYZER="${INSTALL_DIR}/openhtpc-playback-analyze.py"
readonly INSTALLED_SESSION="${INSTALL_DIR}/openhtpc-session-start"
readonly COMMAND_PATH="${BIN_DIR}/openhtpc-builder"
readonly PLAYER_COMMAND_PATH="${BIN_DIR}/openhtpc-player-test"
readonly SESSION_COMMAND_PATH="${BIN_DIR}/openhtpc-session-start"
readonly MEDIA_BROWSER_COMMAND_PATH="${BIN_DIR}/openhtpc-media-browser"
readonly OPENHTPC_COMMAND_PATH="${BIN_DIR}/openhtpc"
readonly AUTOSTART_DIR="${HOME}/.config/autostart"
readonly AUTOSTART_PATH="${AUTOSTART_DIR}/openhtpc.desktop"
TEMP_DIR="$(mktemp -d -t openhtpc-installer.XXXXXX)"
readonly INSTALL_LOG_DIR="${HOME}/.local/state/openhtpc"
readonly INSTALL_LOG="${INSTALL_LOG_DIR}/install.log"
mkdir -p "$INSTALL_LOG_DIR"; touch "$INSTALL_LOG"; chmod 0600 "$INSTALL_LOG"
RUN_ID="$(date +%Y%m%dT%H%M%S)-$$"; RUN_STAGE=BOOTSTRAP; RUN_RESULT=FAIL
TUI_ACTIVE=false
if [[ -t 0 && -t 1 && ${TERM:-dumb} != dumb ]] && [[ $(tput cols 2>/dev/null || echo 0) -ge 72 && $(tput lines 2>/dev/null || echo 0) -ge 20 ]]; then
    TUI_ACTIVE=true; printf '\033[?1049h\033[?25l'
fi
printf '\n==================================================\nOPENHTPC INSTALL RUN\nversion=%s\ntimestamp=%s\nrun_id=%s\n==================================================\n' "$OPENHTPC_VERSION" "$(date --iso-8601=seconds)" "$RUN_ID" >>"$INSTALL_LOG"
finish_run() { local code=$?; [[ $code -eq 0 ]] && RUN_RESULT=PASS; printf 'run_id=%s\nresult=%s\nfailed_stage=%s\n==================================================\n' "$RUN_ID" "$RUN_RESULT" "$([[ $code -eq 0 ]] && printf NONE || printf '%s' "$RUN_STAGE")" >>"$INSTALL_LOG"; $TUI_ACTIVE && printf '\033[?25h\033[?1049l'; rm -rf -- "$TEMP_DIR"; }
trap finish_run EXIT

DRY_RUN=false
if [[ ${1:-} == "--check" ]]; then
    DRY_RUN=true
elif [[ $# -gt 0 ]]; then
    printf 'Usage : %s [--check]\n' "$0" >&2
    exit 2
fi

log() {
    printf '[OPENHTPC] %s\n' "$*" | tee -a "$INSTALL_LOG"
}

die() {
    printf '[OPENHTPC] ERREUR : %s\n[OPENHTPC] Journal détaillé : %s\n' "$*" "$INSTALL_LOG" | tee -a "$INSTALL_LOG" >&2
    exit 1
}

stage() { RUN_STAGE=$1; python3 "$SCRIPT_DIR/openhtpc-installer-ui.py" --stage "$1" 2>/dev/null || true; printf '%s stage=%s\n' "$(date --iso-8601=seconds)" "$1" >>"$INSTALL_LOG"; }

package_available() {
    local package=$1
    rpm -q "$package" >/dev/null 2>&1 ||
        "$DNF" -q repoquery --available "$package" >/dev/null 2>&1
}

repo_enabled() {
    local repo_id=$1
    "$DNF" -q repolist --enabled 2>/dev/null |
        awk '{print $1}' | grep -Fxq "$repo_id"
}

count_updates() {
    local count
    count="$("$DNF" -q repoquery --upgrades --qf '%{name}' 2>/dev/null |
        sed '/^[[:space:]]*$/d' | sort -u | wc -l)" || true
    printf '%s' "${count:-0}"
}

preflight_updates() {
    local update_count
    update_count="$(count_updates)"
    if [[ $update_count =~ ^[0-9]+$ ]] && ((update_count > 0)); then
        log "Information : ${update_count} mise(s) à jour Fedora disponible(s). Fedora conserve la responsabilité de leur installation."
    else
        log "Politique système validée : aucune mise à niveau générale n'est exécutée par OPENHTPC."
    fi
}

collect_media_stack() {
    local output_file=$1 render_node one_file
    : >"$output_file"

    command -v vainfo >/dev/null 2>&1 || return 0
    while IFS= read -r render_node; do
        [[ -c $render_node ]] || continue
        one_file="$TEMP_DIR/vainfo-$(basename "$render_node").txt"
        printf '[%s]\n' "$render_node" >>"$output_file"
        if vainfo --display drm --device "$render_node" >"$one_file" 2>&1; then
            grep -E 'Driver version|VAProfile' "$one_file" >>"$output_file" || true
        else
            printf 'test VA-API échoué ou accès refusé\n' >>"$output_file"
        fi
    done < <(find /dev/dri -maxdepth 1 -type c -name 'renderD*' -print 2>/dev/null | sort)
}

read_media_capabilities() {
    local input_file=$1 ffmpeg_decoders
    VA_MPEG2=false VA_H264=false VA_HEVC=false VA_HEVC10=false VA_VP9=false VA_AV1=false
    grep -Eq 'VAProfileMPEG2.*VAEntrypointVLD' "$input_file" && VA_MPEG2=true
    grep -Eq 'VAProfileH264.*VAEntrypointVLD' "$input_file" && VA_H264=true
    grep -Eq 'VAProfileHEVCMain[[:space:]]*:.*VAEntrypointVLD' "$input_file" && VA_HEVC=true
    grep -Eq 'VAProfileHEVCMain10.*VAEntrypointVLD' "$input_file" && VA_HEVC10=true
    grep -Eq 'VAProfileVP9.*VAEntrypointVLD' "$input_file" && VA_VP9=true
    grep -Eq 'VAProfileAV1.*VAEntrypointVLD' "$input_file" && VA_AV1=true

    FFMPEG_H264=false FFMPEG_HEVC=false FFMPEG_AV1=false
    if command -v ffmpeg >/dev/null 2>&1; then
        ffmpeg_decoders="$(ffmpeg -hide_banner -decoders 2>/dev/null || true)"
        grep -Eq '[[:space:]]h264[[:space:]]' <<<"$ffmpeg_decoders" && FFMPEG_H264=true
        grep -Eq '[[:space:]]hevc[[:space:]]' <<<"$ffmpeg_decoders" && FFMPEG_HEVC=true
        grep -Eq '[[:space:]]av1[[:space:]]' <<<"$ffmpeg_decoders" && FFMPEG_AV1=true
    fi
    return 0
}

mark() {
    if "$1"; then printf '✓ observé'; else printf 'non validé'; fi
}

show_media_stack() {
    local heading=$1
    if $TUI_ACTIVE; then
        { printf '\n--- %s ---\n' "$heading"; cat "$MEDIA_FILE"; } >>"$INSTALL_LOG"
        log "✓ Analyse des capacités graphiques terminée (détails dans install.log)"
        return 0
    fi
    printf '\n------------------------------------------------------------\n'
    printf '%s\n' "$heading"
    printf '%-15s %s\n' 'VA-API MPEG-2' "$(mark "$VA_MPEG2")"
    printf '%-15s %s\n' 'VA-API H.264' "$(mark "$VA_H264")"
    printf '%-15s %s\n' 'VA-API HEVC' "$(mark "$VA_HEVC")"
    printf '%-15s %s\n' 'VA-API HEVC 10' "$(mark "$VA_HEVC10")"
    printf '%-15s %s\n' 'VA-API VP9' "$(mark "$VA_VP9")"
    printf '%-15s %s\n' 'VA-API AV1' "$(mark "$VA_AV1")"
    printf '%-15s %s\n' 'FFmpeg H.264' "$(mark "$FFMPEG_H264")"
    printf '%-15s %s\n' 'FFmpeg HEVC' "$(mark "$FFMPEG_HEVC")"
    printf '%-15s %s\n' 'FFmpeg AV1' "$(mark "$FFMPEG_AV1")"
    if grep -m1 'Driver version' "$MEDIA_FILE" >/dev/null 2>&1; then
        printf 'Pilote : %s\n' "$(grep -m1 'Driver version' "$MEDIA_FILE" | sed 's/^[[:space:]]*//')"
    fi
    printf '%s\n' '------------------------------------------------------------'
}

install_multimedia_extension() {
    local fedora_release answer
    local -a release_urls=() media_packages=()

    printf '\n------------------------------------------------------------\n'
    printf 'Extension multimédia recommandée\n'
    printf '%s\n\n' '------------------------------------------------------------'
    printf "La pile actuelle n'expose pas certains formats importants pour un HTPC :\n\n"
    printf 'H.264 : %s\nHEVC : %s\nHEVC 10 bits : %s\n\n' \
        "$(mark "$VA_H264")" "$(mark "$VA_HEVC")" "$(mark "$VA_HEVC10")"
    printf 'OPENHTPC peut activer RPM Fusion free et nonfree, puis installer\n'
    printf 'les compléments multimédias disponibles pour ce matériel.\n'
    printf 'Cela permettra de vérifier à nouveau les capacités réellement\n'
    printf 'exposées par VA-API et les codecs disponibles dans FFmpeg/MPV.\n\n'
    printf 'Aucune capacité ne peut être garantie avant cette nouvelle mesure.\n'

    if $DRY_RUN; then
        log "Mode --check : extension recommandée, aucune modification effectuée."
        return 0
    fi

    read -r -p "Activer l'extension multimédia ? [O/n] " answer
    case ${answer:-O} in
        O|o|Y|y|oui|Oui|OUI|yes|Yes|YES) ;;
        *)
            log "Extension multimédia refusée. La pile Fedora est conservée."
            return 0
            ;;
    esac

    fedora_release="$(rpm -E %fedora)"
    repo_enabled rpmfusion-free || release_urls+=(
        "https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-${fedora_release}.noarch.rpm"
    )
    repo_enabled rpmfusion-nonfree || release_urls+=(
        "https://mirrors.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-${fedora_release}.noarch.rpm"
    )

    if ((${#release_urls[@]})); then
        log "Activation explicite des dépôts RPM Fusion..."
        sudo "$DNF" install "${release_urls[@]}" ||
            die "L'activation de RPM Fusion a échoué."
    fi

    if { ! $VA_H264 || ! $VA_HEVC || ! $VA_HEVC10; } &&
       "$DNF" -q repoquery --available intel-media-driver >/dev/null 2>&1; then
        media_packages+=(intel-media-driver)
    fi
    if { ! $FFMPEG_H264 || ! $FFMPEG_HEVC; } &&
       "$DNF" -q repoquery --available libavcodec-freeworld >/dev/null 2>&1; then
        media_packages+=(libavcodec-freeworld)
    fi

    ((${#media_packages[@]})) || die "Aucun complément multimédia approprié n'est disponible."
    log "Compléments proposés par DNF : ${media_packages[*]}"
    sudo "$DNF" install --refresh "${media_packages[@]}" ||
        die "L'installation de l'extension multimédia a échoué."

    collect_media_stack "$MEDIA_FILE"
    read_media_capabilities "$MEDIA_FILE"
    show_media_stack "Media Stack observée après extension"
    log "Toute capacité absente reste non validée."
}

[[ ${EUID} -ne 0 ]] || die "Lancez ce script avec votre compte utilisateur, sans sudo."
[[ -r /etc/os-release ]] || die "/etc/os-release est introuvable."
# shellcheck source=/dev/null
source /etc/os-release
[[ ${ID:-} == "fedora" && ${VERSION_ID:-} == "44" ]] || die "OPENHTPC Basic V1 RC1 prend uniquement en charge Fedora 44 KDE."
command -v rpm >/dev/null 2>&1 || die "La commande rpm est requise."

if ! rpm -q plasma-workspace >/dev/null 2>&1 &&
   [[ ${XDG_CURRENT_DESKTOP:-} != *KDE* ]] &&
   [[ ${XDG_CURRENT_DESKTOP:-} != *Plasma* ]]; then
    die "KDE Plasma n'a pas été détecté (paquet plasma-workspace absent)."
fi

if command -v dnf5 >/dev/null 2>&1; then
    DNF=dnf5
elif command -v dnf >/dev/null 2>&1; then
    DNF=dnf
else
    die "DNF est introuvable."
fi

[[ -r $SOURCE_BUILDER ]] || die "openhtpc-builder.sh doit se trouver à côté de l'installateur."
[[ -r $SOURCE_PLAYER ]] || die "openhtpc-player-test.sh doit se trouver à côté de l'installateur."
[[ -r $SOURCE_ANALYZER ]] || die "openhtpc-playback-analyze.py doit se trouver à côté de l'installateur."
[[ -x $SOURCE_SESSION && -r $SOURCE_SESSION_ENGINE && -x $SOURCE_INITIAL_SETUP ]] ||
    die "Les composants de session BUILD A sont incomplets."
[[ -x $SOURCE_FLEX/bin/flex-launcher && -r $SOURCE_FLEX/assets/fonts/OpenSans-Regular.ttf ]] ||
    die "La baseline Flex BUILD A est incomplète."
[[ -x $SOURCE_MEDIA_BROWSER && -r $SOURCE_MEDIA_BROWSER_ENGINE && -x $SOURCE_PLAY ]] ||
    die "Les composants médias BUILD B sont incomplets."
[[ -r $SOURCE_OPTICAL && -x $SCRIPT_DIR/openhtpc-optical-monitor && -x $SCRIPT_DIR/openhtpc-dvd-ui && -x $SCRIPT_DIR/openhtpc-play-dvd && -x $SCRIPT_DIR/openhtpc-eject ]] ||
    die "Les composants DVD BUILD C sont incomplets."
[[ -x $SOURCE_DVD_DEPENDENCIES ]] || die "Le détecteur de dépendances DVD est absent."
[[ -x $SOURCE_FEDORA_DEPENDENCIES ]] || die "Le vérificateur de dépendances Fedora est absent."
[[ -x $SOURCE_DNF_TRANSACTION ]] || die "Le constructeur de transaction DNF est absent."
[[ -r $SCRIPT_DIR/VERSION && -r $SCRIPT_DIR/plugins/README.md ]] || die "Les métadonnées produit RC1 sont incomplètes."
for name in "${PRODUCT_FILES[@]}"; do [[ -r $SCRIPT_DIR/$name ]] || die "Composant produit absent : $name"; done
log "Fedora ${VERSION_ID:-inconnue}, KDE Plasma détecté."
stage SYSTÈME
preflight_updates
stage DÉPENDANCES

packages=(pciutils procps-ng python3 python3-pillow mpv libva-utils vulkan-tools mesa-vulkan-drivers SDL2 SDL2_image SDL2_ttf kdialog)
command -v ffmpeg >/dev/null 2>&1 || packages+=(ffmpeg-free)
gpu_inventory="$(lspci -nn 2>/dev/null | grep -Ei 'VGA compatible|3D controller|Display controller' || true)"
intel_gpu_present=false amd_gpu_present=false nvidia_gpu_present=false
grep -Eqi '\[8086:[0-9a-f]{4}\]' <<<"$gpu_inventory" && intel_gpu_present=true
grep -Eqi '\[1002:[0-9a-f]{4}\]' <<<"$gpu_inventory" && amd_gpu_present=true
grep -Eqi '\[10de:[0-9a-f]{4}\]' <<<"$gpu_inventory" && nvidia_gpu_present=true

if $intel_gpu_present && package_available libva-intel-media-driver; then
    packages+=(libva-intel-media-driver)
fi
if $amd_gpu_present; then
    log "GPU AMD détecté : branche paquet/backend en attente de validation physique."
fi
if $nvidia_gpu_present; then
    log "GPU NVIDIA détecté : aucun pilote ni backend propriétaire installé automatiquement."
fi

missing=()
for package in "${packages[@]}"; do
    if python3 "$SOURCE_FEDORA_DEPENDENCIES" --ready "$package"; then
        continue
    fi
    package_available "$package" || die "Le paquet requis '$package' est introuvable."
    missing+=("$package")
done
log "Paquets Fedora vérifiés : ${packages[*]}"

declare -A dvd_hints=([lsdvd]=lsdvd [eject]=util-linux [udisksctl]=udisks2)
dvd_missing=()
for capability in lsdvd eject udisksctl; do
    if executable="$(command -v "$capability" 2>/dev/null)"; then
        provider="$(rpm -qf "$executable" 2>/dev/null || true)"
        log "Capacité DVD ${capability} : disponible (${provider:-provider RPM inconnu})."
    else
        dvd_missing+=("${dvd_hints[$capability]}")
    fi
done
if ! python3 -c 'import ctypes.util,sys; sys.exit(0 if ctypes.util.find_library("dvdnav") else 1)'; then
    dvd_missing+=(libdvdnav)
else
    log "Capacité DVD libdvdnav : disponible."
fi

if ((${#dvd_missing[@]})); then
    mapfile -t dvd_missing < <(printf '%s\n' "${dvd_missing[@]}" | sort -u)
    log "OpenHTPC a besoin des composants suivants : ${dvd_missing[*]}"
    if $DRY_RUN; then
        log "Mode --check : aucune installation système sans confirmation."
        exit 3
    fi
    python3 "$SCRIPT_DIR/openhtpc-installer-ui.py" --consent dvd-tools --packages "${dvd_missing[@]}" 2>/dev/null || true
    printf '\nSUPPORT DES DVD VIDÉO\nOPENHTPC a besoin de ces composants pour identifier et lire correctement les DVD vidéo :\n'
    for package in "${dvd_missing[@]}"; do
        case $package in
            lsdvd) reason="analyse la structure du DVD et identifie le titre principal" ;;
            util-linux) reason="fournit l'éjection physique sûre du lecteur" ;;
            udisks2) reason="fournit la gestion sûre des volumes optiques" ;;
            libdvdnav) reason="fournit la navigation dans les DVD vidéo" ;;
            *) reason="composant requis par le support DVD" ;;
        esac
        printf '  %s — %s.\n' "$package" "$reason"
    done
    printf 'OPENHTPC utilisera sudo et dnf uniquement pour installer ces composants.\nAucune mise à niveau générale de Fedora ne sera effectuée.\n'
    read -r -p "Installer le support DVD ? [o/N] " answer || answer=N
    case ${answer:-N} in
        O|o|Y|y|oui|Oui|OUI|yes|Yes|YES)
            python3 "$SCRIPT_DIR/openhtpc-installer-ui.py" --dvd-progress check --packages "${dvd_missing[@]}" 2>/dev/null || true
            log "✓ Vérification des dépendances DVD"
            python3 "$SCRIPT_DIR/openhtpc-installer-ui.py" --dvd-progress install --packages "${dvd_missing[@]}" 2>/dev/null || true
            log "→ Installation de ${dvd_missing[*]}"
            log "DNF action : install packages=[${dvd_missing[*]}] assumeyes=yes executable=$(command -v "$DNF")"
            # Python builds a real argv after validating every package against
            # the closed DVD dependency registry. No shell string is executed.
            sudo python3 "$SOURCE_DNF_TRANSACTION" --dnf "$(command -v "$DNF")" "${dvd_missing[@]}" >>"$INSTALL_LOG" 2>&1 || die "Installation de ${dvd_missing[*]} impossible. La commande DNF n'a pas pu être exécutée."
            ;;
        *) die "Installation des composants DVD refusée." ;;
    esac
    python3 "$SCRIPT_DIR/openhtpc-installer-ui.py" --dvd-progress verify --packages "${dvd_missing[@]}" 2>/dev/null || true
    log "→ Vérification du support DVD"
    for capability in lsdvd eject udisksctl; do command -v "$capability" >/dev/null 2>&1 || die "Capacité DVD toujours absente : $capability"; done
    if [[ " ${dvd_missing[*]} " == *" lsdvd "* ]]; then
        rpm -q lsdvd >>"$INSTALL_LOG" 2>&1 || die "lsdvd a été installé sans provenance RPM vérifiable."
        lsdvd -h >>"$INSTALL_LOG" 2>&1 || die "lsdvd est présent mais son exécution de validation a échoué."
        log "✓ lsdvd installé et exécutable"
    fi
    python3 -c 'import ctypes.util,sys; sys.exit(0 if ctypes.util.find_library("dvdnav") else 1)' || die "Capacité DVD toujours absente : libdvdnav"
    python3 "$SCRIPT_DIR/openhtpc-installer-ui.py" --dvd-progress done --packages "${dvd_missing[@]}" 2>/dev/null || true
    log "✓ Support DVD opérationnel"
fi

LIBDVDCSS_STATE= LIBDVDCSS_FREE=false LIBDVDCSS_TAINTED=false LIBDVDCSS_RELEASE=false
LIBDVDCSS_FEDORA_RELEASE= LIBDVDCSS_FREE_URL=
while IFS='=' read -r key value; do
    case $key in
        LIBDVDCSS_STATE) LIBDVDCSS_STATE=$value ;;
        FEDORA_RELEASE) LIBDVDCSS_FEDORA_RELEASE=$value ;;
        RPMFUSION_FREE_ENABLED) LIBDVDCSS_FREE=$value ;;
        RPMFUSION_FREE_BOOTSTRAP_URL) LIBDVDCSS_FREE_URL=$value ;;
        FREE_TAINTED_ENABLED) LIBDVDCSS_TAINTED=$value ;;
        FREE_TAINTED_RELEASE_AVAILABLE) LIBDVDCSS_RELEASE=$value ;;
    esac
done < <(python3 "$SOURCE_DVD_DEPENDENCIES" --shell)

if [[ $LIBDVDCSS_STATE != LIBDVDCSS_READY ]]; then
    [[ $LIBDVDCSS_STATE != LIBDVDCSS_BROKEN ]] || die "libdvdcss est détectée mais ne peut pas être chargée."
    log "libdvdcss est nécessaire à la lecture des DVD commerciaux chiffrés."
    python3 "$SCRIPT_DIR/openhtpc-installer-ui.py" --consent dvd-css 2>/dev/null || true
    if [[ $LIBDVDCSS_FREE != true ]]; then
        [[ $LIBDVDCSS_FEDORA_RELEASE == ${VERSION_ID:-} && -n $LIBDVDCSS_FREE_URL ]] ||
            die "Impossible de déterminer le bootstrap RPM Fusion Free officiel pour Fedora ${VERSION_ID:-inconnue}."
        log "RPM Fusion Free n'est pas actif."
        log "Plan proposé : activer le dépôt officiel RPM Fusion Free pour Fedora ${LIBDVDCSS_FEDORA_RELEASE}."
        log "Source officielle : ${LIBDVDCSS_FREE_URL}"
        $DRY_RUN && { log "Mode --check : aucune modification système sans confirmation."; exit 3; }
        read -r -p "Autoriser l'activation de RPM Fusion Free ? [o/N] " answer || answer=N
        case ${answer:-N} in O|o|Y|y|oui|Oui|OUI|yes|Yes|YES) ;; *) die "Activation de RPM Fusion Free refusée." ;; esac
        log "Activation de RPM Fusion Free en cours…"
        sudo "$DNF" install -y "$LIBDVDCSS_FREE_URL" >>"$INSTALL_LOG" 2>&1 || die "Le téléchargement ou l'activation de RPM Fusion Free a échoué. Vérifiez le réseau et réessayez."
        repo_enabled rpmfusion-free || die "RPM Fusion Free n'est pas actif après installation."
        "$DNF" -q makecache --refresh >/dev/null || die "RPM Fusion Free est actif mais le rafraîchissement des métadonnées a échoué."
        package_available rpmfusion-free-release-tainted || die "RPM Fusion Free est actif mais rpmfusion-free-release-tainted reste indisponible."
        LIBDVDCSS_FREE=true
        LIBDVDCSS_RELEASE=true
    fi
    if [[ $LIBDVDCSS_TAINTED != true ]]; then
        [[ $LIBDVDCSS_RELEASE == true ]] || die "RPM Fusion Free Tainted est inactif et rpmfusion-free-release-tainted est indisponible."
        log "libdvdcss est fournie par RPM Fusion Free Tainted."
        log "Plan proposé : activer rpmfusion-free-tainted, puis installer libdvdcss."
        $DRY_RUN && { log "Mode --check : aucune modification système sans confirmation."; exit 3; }
        read -r -p "Autoriser l'activation de RPM Fusion Free Tainted ? [o/N] " answer || answer=N
        case ${answer:-N} in O|o|Y|y|oui|Oui|OUI|yes|Yes|YES) ;; *) die "Activation de RPM Fusion Free Tainted refusée." ;; esac
        log "Activation de RPM Fusion Free Tainted en cours…"
        sudo "$DNF" install -y rpmfusion-free-release-tainted >>"$INSTALL_LOG" 2>&1 || die "L'activation de RPM Fusion Free Tainted a échoué."
        repo_enabled rpmfusion-free-tainted || die "RPM Fusion Free Tainted n'est pas actif après installation."
    fi
    log "Plan proposé : installer libdvdcss pour les DVD commerciaux chiffrés."
    $DRY_RUN && { log "Mode --check : aucune modification système sans confirmation."; exit 3; }
    read -r -p "Autoriser l'installation de libdvdcss ? [o/N] " answer || answer=N
    case ${answer:-N} in O|o|Y|y|oui|Oui|OUI|yes|Yes|YES) ;; *) die "Installation de libdvdcss refusée." ;; esac
    log "Installation de libdvdcss en cours…"
    sudo "$DNF" install -y libdvdcss >>"$INSTALL_LOG" 2>&1 || die "L'installation de libdvdcss a échoué."
    verify_state="$(python3 "$SOURCE_DVD_DEPENDENCIES" --shell | sed -n 's/^LIBDVDCSS_STATE=//p')"
    [[ $verify_state == LIBDVDCSS_READY ]] || die "libdvdcss n'est pas fonctionnelle après installation (${verify_state:-UNKNOWN})."
fi

if ! $DRY_RUN && ((${#missing[@]})); then
    log "OpenHTPC a besoin des composants Fedora suivants : ${missing[*]}"
    log "Plan proposé : installer uniquement ces paquets avec sudo/DNF, puis vérifier les capacités."
    read -r -p "Installer le socle OPENHTPC avec sudo/DNF ? [o/N] " answer || answer=N
    case ${answer:-N} in
        O|o|Y|y|oui|Oui|OUI|yes|Yes|YES) log "Installation de ${#missing[@]} composants système…"; sudo "$DNF" install -y "${missing[@]}" >>"$INSTALL_LOG" 2>&1 || die "L'installation des composants système a échoué." ;;
        *) die "Installation du socle Fedora refusée." ;;
    esac
    for package in "${missing[@]}"; do
        python3 "$SOURCE_FEDORA_DEPENDENCIES" --ready "$package" ||
            die "Dépendance toujours absente après installation : $package"
    done
elif $DRY_RUN && ((${#missing[@]})); then
    log "Paquets qui seraient installés : ${missing[*]}"
else
    log "Le socle Fedora est déjà présent."
fi

MEDIA_FILE="$TEMP_DIR/media-stack.txt"
collect_media_stack "$MEDIA_FILE"
read_media_capabilities "$MEDIA_FILE"
show_media_stack "Media Stack actuellement observée"

if [[ ${OPENHTPC_UPDATE_MODE:-0} != 1 ]] && $intel_gpu_present &&
   { ! $VA_H264 || ! $VA_HEVC || ! $VA_HEVC10 || ! $FFMPEG_H264 || ! $FFMPEG_HEVC; }; then
    install_multimedia_extension
fi

if $DRY_RUN; then
    log "Mode --check : aucune modification effectuée."
    exit 0
fi

mkdir -p "$INSTALL_DIR" "$BIN_DIR" "${HOME}/.config/openhtpc"
rm -f -- "$INSTALL_DIR/openhtpc-backdrop"
stage INSTALLATION
if [[ -e $INSTALLED_BUILDER ]] && ! cmp -s "$SOURCE_BUILDER" "$INSTALLED_BUILDER"; then
    backup="${INSTALLED_BUILDER}.backup-$(date +%Y%m%d-%H%M%S)"
    cp -a "$INSTALLED_BUILDER" "$backup"
    log "Ancien Builder sauvegardé : $backup"
fi
if [[ -e $INSTALLED_PLAYER ]] && ! cmp -s "$SOURCE_PLAYER" "$INSTALLED_PLAYER"; then
    backup="${INSTALLED_PLAYER}.backup-$(date +%Y%m%d-%H%M%S)"
    cp -a "$INSTALLED_PLAYER" "$backup"
    log "Ancien lanceur de test sauvegardé : $backup"
fi
if [[ -e $INSTALLED_ANALYZER ]] && ! cmp -s "$SOURCE_ANALYZER" "$INSTALLED_ANALYZER"; then
    backup="${INSTALLED_ANALYZER}.backup-$(date +%Y%m%d-%H%M%S)"
    cp -a "$INSTALLED_ANALYZER" "$backup"
    log "Ancien analyseur sauvegardé : $backup"
fi
install -m 0755 "$SOURCE_BUILDER" "$INSTALLED_BUILDER"
install -m 0755 "$SOURCE_PLAYER" "$INSTALLED_PLAYER"
install -m 0755 "$SOURCE_ANALYZER" "$INSTALLED_ANALYZER"
install -m 0755 "$SOURCE_SESSION" "$INSTALLED_SESSION"
install -m 0755 "$SOURCE_SESSION_ENGINE" "$INSTALL_DIR/openhtpc-session-engine.py"
install -m 0755 "$SOURCE_INITIAL_SETUP" "$INSTALL_DIR/openhtpc-initial-setup.py"
install -m 0755 "$SOURCE_MEDIA_BROWSER" "$INSTALL_DIR/openhtpc-media-browser"
install -m 0755 "$SOURCE_MEDIA_BROWSER_ENGINE" "$INSTALL_DIR/openhtpc-media-browser.py"
install -m 0755 "$SOURCE_PLAY" "$INSTALL_DIR/openhtpc-play"
install -m 0755 "$SOURCE_OPTICAL" "$INSTALL_DIR/openhtpc-optical.py"
install -m 0755 "$SCRIPT_DIR/openhtpc-optical-monitor" "$INSTALL_DIR/openhtpc-optical-monitor"
install -m 0755 "$SCRIPT_DIR/openhtpc-dvd-ui" "$INSTALL_DIR/openhtpc-dvd-ui"
install -m 0755 "$SCRIPT_DIR/openhtpc-play-dvd" "$INSTALL_DIR/openhtpc-play-dvd"
install -m 0755 "$SCRIPT_DIR/openhtpc-eject" "$INSTALL_DIR/openhtpc-eject"
install -m 0755 "$SOURCE_DVD_DEPENDENCIES" "$INSTALL_DIR/openhtpc-dvd-dependencies.py"
for name in "${PRODUCT_FILES[@]}"; do install -m 0755 "$SCRIPT_DIR/$name" "$INSTALL_DIR/$name"; done
install -m 0644 "$SCRIPT_DIR/VERSION" "$INSTALL_DIR/VERSION"
install -m 0644 "$SCRIPT_DIR/version.json" "$INSTALL_DIR/version.json"
install -Dm 0644 "$SCRIPT_DIR/plugins/README.md" "$INSTALL_DIR/plugins/README.md"
install -Dm 0755 "$SOURCE_FLEX/bin/flex-launcher" "$INSTALL_DIR/flex/bin/flex-launcher"
install -Dm 0644 "$SOURCE_FLEX/BUILD-METADATA.json" "$INSTALL_DIR/flex/BUILD-METADATA.json"
install -Dm 0644 "$SOURCE_FLEX/assets/fonts/OpenSans-Regular.ttf" "$INSTALL_DIR/flex/assets/fonts/OpenSans-Regular.ttf"
install -Dm 0644 "$SOURCE_FLEX/assets/icons/drive-empty.png" "$INSTALL_DIR/flex/assets/icons/drive-empty.png"
install -Dm 0644 "$SOURCE_FLEX/assets/icons/dvd.png" "$INSTALL_DIR/flex/assets/icons/dvd.png"
install -Dm 0644 "$SCRIPT_DIR/assets/branding/openhtpc-logo.png" "$INSTALL_DIR/assets/branding/openhtpc-logo.png"
install -Dm 0644 "$SCRIPT_DIR/assets/branding/openhtpc-wallpaper.png" "$INSTALL_DIR/assets/branding/openhtpc-wallpaper.png"
for asset_file in "$SCRIPT_DIR"/assets/ui/*.png; do
    [[ -f $asset_file ]] || continue
    install -Dm 0644 "$asset_file" "$INSTALL_DIR/assets/ui/$(basename "$asset_file")"
done
for bench_file in "$SCRIPT_DIR"/assets/benchmark/*; do
    [[ -f $bench_file ]] || continue
    install -Dm 0644 "$bench_file" "$INSTALL_DIR/assets/benchmark/$(basename "$bench_file")"
done
for shader_file in "$SCRIPT_DIR"/assets/shaders/*; do
    [[ -f $shader_file ]] || continue
    install -Dm 0644 "$shader_file" "$INSTALL_DIR/assets/shaders/$(basename "$shader_file")"
done
if [[ -f "$SCRIPT_DIR/assets/c3_calibration_catalog.json" ]]; then
    install -Dm 0644 "$SCRIPT_DIR/assets/c3_calibration_catalog.json" "$INSTALL_DIR/assets/c3_calibration_catalog.json"
fi
install -m 0644 "$SCRIPT_DIR/managed-files.txt" "$INSTALL_DIR/.openhtpc-managed-files"


ln -sfn "$INSTALLED_BUILDER" "$COMMAND_PATH"
ln -sfn "$INSTALLED_PLAYER" "$PLAYER_COMMAND_PATH"
ln -sfn "$INSTALLED_SESSION" "$SESSION_COMMAND_PATH"
ln -sfn "$INSTALL_DIR/openhtpc-media-browser" "$MEDIA_BROWSER_COMMAND_PATH"
ln -sfn "$INSTALL_DIR/openhtpc" "$OPENHTPC_COMMAND_PATH"
mkdir -p "$AUTOSTART_DIR"
if [[ -e $AUTOSTART_PATH ]] && ! grep -Fq 'X-OPENHTPC-Managed=true' "$AUTOSTART_PATH"; then
    die "Refus d'écraser l'autostart externe : $AUTOSTART_PATH"
fi
cat >"$AUTOSTART_PATH" <<EOF
[Desktop Entry]
Type=Application
Name=OPENHTPC Basic
Exec=${BIN_DIR}/openhtpc-session-start
Terminal=false
X-KDE-autostart-after=panel
X-OPENHTPC-Managed=true
EOF
chmod 0644 "$AUTOSTART_PATH"

log "OPENHTPC ${OPENHTPC_VERSION} installé."
if [[ ! -f ${HOME}/.config/openhtpc/profile.json && ${OPENHTPC_UPDATE_MODE:-0} == 1 ]]; then
    log "Hardware Passport absent dans ce profil Builder : mise à jour des fichiers terminée sans lancer l'assistant matériel interactif."
elif [[ ! -f ${HOME}/.config/openhtpc/profile.json ]]; then
    log "Découverte matérielle et génération du runtime OPENHTPC..."
    stage MATÉRIEL
    "$INSTALLED_BUILDER"
    stage RUNTIME
else
    log "Hardware Passport existant conservé. Relancez openhtpc-builder après un changement matériel."
fi
if [[ ! -f ${HOME}/.config/openhtpc/user-config.json && ${OPENHTPC_UPDATE_MODE:-0} != 1 ]]; then
    stage CONFIGURATION
    "$INSTALL_DIR/openhtpc-initial-setup.py" --home "$HOME" --default-empty || die "Configuration initiale interrompue."
fi
if ! OPENHTPC_HOME="$HOME" OPENHTPC_INSTALL_DIR="$INSTALL_DIR" "$INSTALL_DIR/openhtpc-capabilities.py" --refresh >/dev/null; then
    log "Le snapshot de capacités n'a pas pu être généré; il pourra être relancé avec openhtpc capabilities --refresh."
fi
# Safely remove only specific legacy transitional non-disc cache if present
rm -f -- "${HOME}/.local/share/openhtpc/media-cache/dvd/80ebf0f74dc6d50b350636314e91eb3b734527de8d2d69c0674c33e2c492232a/metadata.json" 2>/dev/null || true
rmdir -- "${HOME}/.local/share/openhtpc/media-cache/dvd/80ebf0f74dc6d50b350636314e91eb3b734527de8d2d69c0674c33e2c492232a" 2>/dev/null || true

log "Installation prête. OPENHTPC démarrera à la prochaine ouverture de session."
log "Diagnostic : openhtpc doctor"
stage VALIDATION
if ! "$INSTALL_DIR/openhtpc" doctor >>"$INSTALL_LOG" 2>&1; then
    log "Installation validée ; le diagnostic runtime complet sera disponible après le premier démarrage."
else
    log "Installation validée. Runtime prêt au démarrage."
fi
python3 "$INSTALL_DIR/openhtpc-installer-ui.py" --success 2>/dev/null || true
if [[ :$PATH: != *":${BIN_DIR}:"* ]]; then
    log "Ajoutez ${BIN_DIR} à PATH ou reconnectez-vous à votre session."
fi

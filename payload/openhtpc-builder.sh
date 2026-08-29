#!/usr/bin/env bash

set -u

readonly OPENHTPC_VERSION="4.0.0"
readonly CONFIG_DIR="${HOME}/.config/openhtpc"
readonly PROFILE_FILE="${CONFIG_DIR}/profile.json"
readonly REPORT_FILE="${CONFIG_DIR}/report.txt"
readonly RUNTIME_DIR="${CONFIG_DIR}/runtime"
readonly MPV_RUNTIME_DIR="${RUNTIME_DIR}/mpv"
readonly MPV_PURE_CONFIG="${MPV_RUNTIME_DIR}/pure.conf"
readonly MPV_REFERENCE_CONFIG="${MPV_RUNTIME_DIR}/reference.conf"
readonly DRI_ROOT="${OPENHTPC_DRI_ROOT:-/dev/dri}"
readonly DRM_SYSFS_ROOT="${OPENHTPC_DRM_SYSFS_ROOT:-/sys/class/drm}"
readonly RUNTIME_GENERATOR="${OPENHTPC_RUNTIME_GENERATOR:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/openhtpc-runtime-generator.py}"
readonly VERSION_METADATA="${OPENHTPC_VERSION_METADATA:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/version.json}"
readonly GPU_POLICY="${OPENHTPC_GPU_POLICY:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/openhtpc-gpu-policy.py}"
REGENERATE_RUNTIME=false
REBUILD_PASSPORT=false
if [[ ${1:-} == "--regenerate-runtime" && $# -eq 1 ]]; then
    REGENERATE_RUNTIME=true
elif [[ ${1:-} == "--rebuild-passport" && $# -eq 1 ]]; then
    REBUILD_PASSPORT=true
elif [[ $# -ne 0 ]]; then
    printf 'Usage : %s [--regenerate-runtime|--rebuild-passport]\n' "$0" >&2
    exit 2
fi
WORK_DIR="$(mktemp -d -t openhtpc-builder.XXXXXX)"
trap 'rm -rf -- "$WORK_DIR"' EXIT

if [[ -t 1 ]]; then
    C_TITLE=$'\033[1;36m'
    C_OK=$'\033[1;32m'
    C_WARN=$'\033[1;33m'
    C_RESET=$'\033[0m'
else
    C_TITLE='' C_OK='' C_WARN='' C_RESET=''
fi

title() {
    printf '\n%s============================================================%s\n' "$C_TITLE" "$C_RESET"
    printf '%s%s%s\n' "$C_TITLE" "$1" "$C_RESET"
    printf '%s============================================================%s\n\n' "$C_TITLE" "$C_RESET"
}

command_version() {
    local command_name=$1
    shift
    if command -v "$command_name" >/dev/null 2>&1; then
        "$command_name" "$@" 2>/dev/null | head -n 1
    else
        printf 'absent'
    fi
}

ask_choice() {
    local prompt=$1 variable=$2
    shift 2
    local choices=("$@") answer index
    while true; do
        printf '\n%s\n' "$prompt"
        for index in "${!choices[@]}"; do
            printf '  %d. %s\n' "$((index + 1))" "${choices[index]}"
        done
        if ! read -r -p '> ' answer; then
            printf '\nEntrée interrompue ; aucun profil incomplet ne sera enregistré.\n' >&2
            exit 1
        fi
        if [[ $answer =~ ^[0-9]+$ ]] &&
           ((answer >= 1 && answer <= ${#choices[@]})); then
            printf -v "$variable" '%s' "${choices[answer - 1]}"
            return
        fi
        printf '%sChoix invalide.%s\n' "$C_WARN" "$C_RESET"
    done
}

os_name="Fedora non détectée"
if [[ -r /etc/os-release ]]; then
    # shellcheck source=/dev/null
    source /etc/os-release
    os_name=${PRETTY_NAME:-$os_name}
fi
kernel="$(uname -srmo)"
cpu="$(lscpu 2>/dev/null | awk -F: '/^Model name:/ {sub(/^[[:space:]]+/, "", $2); print $2; exit}')"
ram="$(free -h 2>/dev/null | awk '/^Mem:/ {print $2}')"
mpv_version="$(command_version mpv --no-config --version)"
ffmpeg_version="$(command_version ffmpeg -version)"

: >"$WORK_DIR/mpv-options.txt"
: >"$WORK_DIR/mpv-values.txt"
if command -v mpv >/dev/null 2>&1; then
    mpv --no-config --list-options >"$WORK_DIR/mpv-options.txt" 2>/dev/null || true
    {
        mpv --no-config --vo=help 2>&1 || true
        mpv --no-config --gpu-api=help 2>&1 || true
        mpv --no-config --hwdec=help 2>&1 || true
    } >"$WORK_DIR/mpv-values.txt"
fi

: >"$WORK_DIR/nvidia-smi.csv"
if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=pci.bus_id,name,driver_version --format=csv,noheader,nounits \
        >"$WORK_DIR/nvidia-smi.csv" 2>/dev/null || true
fi

if $REGENERATE_RUNTIME; then
    [[ -r $PROFILE_FILE ]] || { printf 'Hardware Passport absent : %s\n' "$PROFILE_FILE" >&2; exit 1; }
    [[ -x $RUNTIME_GENERATOR && -r $VERSION_METADATA ]] || { printf 'Générateur runtime courant incomplet.\n' >&2; exit 1; }
    mkdir -p "$MPV_RUNTIME_DIR"
    exec "$RUNTIME_GENERATOR" "$PROFILE_FILE" "$MPV_PURE_CONFIG" "$MPV_REFERENCE_CONFIG" \
        "$WORK_DIR/mpv-options.txt" "$WORK_DIR/mpv-values.txt" "$VERSION_METADATA"
fi

rpmfusion_enabled=false
dnf_command=""
command -v dnf5 >/dev/null 2>&1 && dnf_command=dnf5
[[ -z $dnf_command ]] && command -v dnf >/dev/null 2>&1 && dnf_command=dnf
if [[ -n $dnf_command ]]; then
    enabled_repos="$("$dnf_command" -q repolist --enabled 2>/dev/null || true)"
    if awk '{print $1}' <<<"$enabled_repos" | grep -Eq '^rpmfusion-(free|nonfree)(-|$)'; then
        rpmfusion_enabled=true
    fi
fi

media_source="inconnue"
if rpm -q intel-media-driver >/dev/null 2>&1; then
    media_source="RPM Fusion"
elif rpm -q libva-intel-media-driver >/dev/null 2>&1; then
    media_source="Fedora"
fi

if command -v lspci >/dev/null 2>&1; then
    lspci -Dnnk 2>/dev/null | awk '
        /^[0-9a-f]+:[0-9a-f]+:[0-9a-f]+\.[0-9].*(VGA compatible controller|3D controller|Display controller)/ {show=1; print; next}
        show && /^[[:space:]]+Kernel (driver in use|modules):/ {print; next}
        show && !/^[[:space:]]/ {show=0}
    ' >"$WORK_DIR/gpus.txt"
else
    printf 'lspci absent\n' >"$WORK_DIR/gpus.txt"
fi

find "$DRI_ROOT" -maxdepth 1 -type c -name 'renderD*' -print 2>/dev/null | sort >"$WORK_DIR/render-nodes.txt"
[[ -s $WORK_DIR/render-nodes.txt ]] || printf 'aucun render node accessible\n' >"$WORK_DIR/render-nodes.txt"

: >"$WORK_DIR/render-map.txt"
for render_sysfs in "$DRM_SYSFS_ROOT"/renderD*; do
    [[ -e $render_sysfs/device ]] || continue
    render_name="$(basename "$render_sysfs")"
    device_path="$(readlink -f "$render_sysfs/device")"
    pci_slot="$(basename "$device_path")"
    pci_vendor="$(sed 's/^0x//' "$render_sysfs/device/vendor" 2>/dev/null || true)"
    pci_device="$(sed 's/^0x//' "$render_sysfs/device/device" 2>/dev/null || true)"
    kernel_driver="$(basename "$(readlink -f "$render_sysfs/device/driver")")"
    printf '%s|%s|%s|%s|%s\n' \
        "$DRI_ROOT/$render_name" "$pci_slot" "$pci_vendor" "$pci_device" "$kernel_driver" \
        >>"$WORK_DIR/render-map.txt"
done

# Relie les connecteurs DRM aux fonctions PCI sans déduire l'affichage de
# l'ordre des cartes. Une absence de connecteur lisible reste « inconnue ».
: >"$WORK_DIR/drm-topology.txt"
for card_sysfs in "$DRM_SYSFS_ROOT"/card[0-9]*; do
    card_name="$(basename "$card_sysfs")"
    [[ $card_name =~ ^card[0-9]+$ && -e $card_sysfs/device ]] || continue
    device_path="$(readlink -f "$card_sysfs/device")"
    pci_slot="$(basename "$device_path")"
    kernel_driver="$(basename "$(readlink -f "$card_sysfs/device/driver")")"
    printf 'CARD|%s|%s|%s\n' "$card_name" "$pci_slot" "$kernel_driver" \
        >>"$WORK_DIR/drm-topology.txt"
    for connector_sysfs in "$DRM_SYSFS_ROOT"/"$card_name"-*; do
        [[ -r $connector_sysfs/status ]] || continue
        connector_name="$(basename "$connector_sysfs")"
        connector_status="$(<"$connector_sysfs/status")"
        printf 'CONNECTOR|%s|%s|%s\n' \
            "$card_name" "$connector_name" "$connector_status" \
            >>"$WORK_DIR/drm-topology.txt"
    done
done

vulkan_status="non observé"
if command -v vulkaninfo >/dev/null 2>&1; then
    if vulkaninfo --summary >"$WORK_DIR/vulkan-full.txt" 2>&1; then
        grep -E 'Vulkan Instance Version|vendorID|deviceID|deviceName|deviceType|driverName|driverInfo|apiVersion' \
            "$WORK_DIR/vulkan-full.txt" >"$WORK_DIR/vulkan.txt" || true
        vulkan_status="observé par vulkaninfo"
    else
        printf 'vulkaninfo présent, mais le test a échoué dans cette session\n' >"$WORK_DIR/vulkan.txt"
        vulkan_status="outil présent, test échoué"
    fi
else
    printf 'vulkaninfo absent\n' >"$WORK_DIR/vulkan.txt"
fi

vaapi_status="non observé"
: >"$WORK_DIR/vaapi.txt"
if command -v vainfo >/dev/null 2>&1; then
    while IFS= read -r render_node; do
        [[ -c $render_node ]] || continue
        printf '[%s]\n' "$render_node" >>"$WORK_DIR/vaapi.txt"
        if vainfo --display drm --device "$render_node" >"$WORK_DIR/vaapi-one.txt" 2>&1; then
            grep -E 'Driver version|VAProfile' "$WORK_DIR/vaapi-one.txt" >>"$WORK_DIR/vaapi.txt" || true
            vaapi_status="observé sur au moins un render node"
        else
            printf 'test VA-API échoué ou accès refusé\n' >>"$WORK_DIR/vaapi.txt"
        fi
    done <"$WORK_DIR/render-nodes.txt"
    if [[ ! -s $WORK_DIR/vaapi.txt ]]; then
        printf 'vainfo présent, aucun render node testable\n' >"$WORK_DIR/vaapi.txt"
    fi
else
    printf 'vainfo absent\n' >"$WORK_DIR/vaapi.txt"
fi

gpu_count="$(grep -Ec '^[0-9a-f]+:' "$WORK_DIR/gpus.txt" || true)"

title "ÉCRAN 1 — VOTRE MATÉRIEL"
printf 'Fedora       : %s\n' "$os_name"
printf 'Kernel       : %s\n' "$kernel"
printf 'CPU          : %s\n' "${cpu:-inconnu}"
printf 'RAM          : %s\n' "${ram:-inconnue}"
printf '\nGPU et pilotes :\n'
sed 's/^/  /' "$WORK_DIR/gpus.txt"
printf '\nRender nodes :\n'
sed 's/^/  /' "$WORK_DIR/render-nodes.txt"
printf '\nVulkan (%s) :\n' "$vulkan_status"
sed 's/^/  /' "$WORK_DIR/vulkan.txt"
printf '\nVA-API (%s) :\n' "$vaapi_status"
sed 's/^/  /' "$WORK_DIR/vaapi.txt"
printf '\nMPV          : %s\n' "$mpv_version"
printf 'FFmpeg       : %s\n' "$ffmpeg_version"
printf 'Media Stack  : %s (RPM Fusion : %s)\n' "$media_source" "$rpmfusion_enabled"
if ((gpu_count > 1)); then
    printf '\n%sPlusieurs GPU sont présents. Build 2.1 distinguera affichage, traitement et chemin d’offload.%s\n' "$C_WARN" "$C_RESET"
fi

title "ÉCRAN 2 — VOTRE AFFICHAGE"
if $REBUILD_PASSPORT; then
    [[ -r $PROFILE_FILE ]] || { printf 'Hardware Passport absent : reconstruction impossible.\n' >&2; exit 1; }
    mapfile -t saved_display < <(python3 - "$PROFILE_FILE" <<'PYANSWERS'
import json,sys
value=json.load(open(sys.argv[1],encoding="utf-8"));answers=value.get("user_answers",{});display=answers.get("display",{});audio=answers.get("audio",{})
for source,key in ((display,"resolution"),(display,"hdr"),(display,"refresh_rate"),(audio,"destination"),(audio,"mode")):
    item=source.get(key)
    if not isinstance(item,str) or not item:raise SystemExit("Réponses écran absentes ; reconstruction non interactive refusée")
    print(item)
PYANSWERS
    )
    [[ ${#saved_display[@]} -eq 5 ]] || { printf 'Réponses matérielles absentes ; reconstruction non interactive refusée.\n' >&2; exit 1; }
    display_resolution=${saved_display[0]}; display_hdr=${saved_display[1]}; display_refresh=${saved_display[2]}
else
    ask_choice "Résolution de l'écran :" display_resolution \
        "1920x1080" "3840x2160" "Autre"
    display_hdr="Je ne sais pas"
    ask_choice "Fréquence connue :" display_refresh \
        "60 Hz" "120 Hz" "Autre" "Je ne sais pas"
fi

title "ÉCRAN 3 — VOTRE AUDIO"
if $REBUILD_PASSPORT; then
    audio_destination=${saved_display[3]}; audio_mode=${saved_display[4]}
else
    audio_destination="Détection système"; audio_mode="PCM"
fi
printf 'Fondations audio détectées automatiquement. Mode initial sûr : PCM.\n'

has_mpeg2=false has_h264=false has_hevc=false has_hevc10=false has_vp9=false has_av1=false
grep -Eq 'VAProfileMPEG2.*VAEntrypointVLD' "$WORK_DIR/vaapi.txt" && has_mpeg2=true
grep -Eq 'VAProfileH264.*VAEntrypointVLD' "$WORK_DIR/vaapi.txt" && has_h264=true
grep -Eq 'VAProfileHEVCMain[[:space:]]*:.*VAEntrypointVLD' "$WORK_DIR/vaapi.txt" && has_hevc=true
grep -Eq 'VAProfileHEVCMain10.*VAEntrypointVLD' "$WORK_DIR/vaapi.txt" && has_hevc10=true
grep -Eq 'VAProfileVP9.*VAEntrypointVLD' "$WORK_DIR/vaapi.txt" && has_vp9=true
grep -Eq 'VAProfileAV1.*VAEntrypointVLD' "$WORK_DIR/vaapi.txt" && has_av1=true

ffmpeg_h264=false ffmpeg_hevc=false ffmpeg_av1=false
: >"$WORK_DIR/ffmpeg-decoders.txt"
if command -v ffmpeg >/dev/null 2>&1; then
    ffmpeg -hide_banner -decoders >"$WORK_DIR/ffmpeg-decoders.txt" 2>/dev/null || true
    ffmpeg_decoders="$(<"$WORK_DIR/ffmpeg-decoders.txt")"
    grep -Eq '[[:space:]]h264[[:space:]]' <<<"$ffmpeg_decoders" && ffmpeg_h264=true
    grep -Eq '[[:space:]]hevc[[:space:]]' <<<"$ffmpeg_decoders" && ffmpeg_hevc=true
    grep -Eq '[[:space:]]av1[[:space:]]' <<<"$ffmpeg_decoders" && ffmpeg_av1=true
fi
vaapi_driver="$(grep -m1 'Driver version' "$WORK_DIR/vaapi.txt" | sed 's/^[[:space:]]*//' || true)"

python3 - "$WORK_DIR" "$display_resolution" "$display_hdr" "$display_refresh" \
    "$audio_destination" "$audio_mode" "$mpv_version" "$GPU_POLICY" <<'PYGPU'
import importlib.util
import json
import pathlib
import re
import sys

work = pathlib.Path(sys.argv[1])
resolution, hdr, refresh, audio_destination, audio_mode, mpv_version = sys.argv[2:8]
policy_path = pathlib.Path(sys.argv[8])
spec = importlib.util.spec_from_file_location("openhtpc_gpu_policy", policy_path)
policy = importlib.util.module_from_spec(spec); spec.loader.exec_module(policy)

def read_lines(name):
    path = work / name
    return path.read_text(encoding="utf-8", errors="replace").splitlines() if path.exists() else []

def identify_vendor(vendor_id, kernel_driver):
    by_pci = {"8086": "intel", "1002": "amd", "10de": "nvidia"}
    by_driver = {
        "i915": "intel", "xe": "intel",
        "amdgpu": "amd", "radeon": "amd",
        "nvidia": "nvidia", "nouveau": "nvidia",
    }
    return by_pci.get((vendor_id or "").lower(), by_driver.get((kernel_driver or "").lower(), "unknown"))

# PCI inventory and kernel drivers.
gpus = []
current = None
for line in read_lines("gpus.txt"):
    if line and not line[0].isspace():
        match = re.match(r"^(\S+)\s+([^:]+):\s+(.+)$", line)
        if not match:
            continue
        slot, gpu_class, description = match.groups()
        ids = re.findall(r"\[([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\]", description)
        vendor_id, device_id = ids[-1] if ids else (None, None)
        model = re.sub(r"\s*\[[0-9a-fA-F]{4}:[0-9a-fA-F]{4}\].*$", "", description)
        current = {
            "pci_slot": slot.lower(),
            "pci_id": f"{vendor_id.lower()}:{device_id.lower()}" if vendor_id else None,
            "vendor_id": vendor_id.lower() if vendor_id else None,
            "device_id": device_id.lower() if device_id else None,
            "vendor": None,
            "model": model.strip(),
            "kernel_driver": None,
            "drm_card": None,
            "display_connectors": [],
            "display_path_status": "unknown",
            "render_node": None,
            "vulkan_device": None,
            "vaapi_driver": None,
            "vaapi_decode": {name: False for name in ("mpeg2", "h264", "hevc", "hevc_main10", "vp9", "av1")},
            "nvdec_available": False,
            "nvdec_decode": {name: False for name in ("mpeg2", "h264", "hevc", "hevc_main10", "vp9", "av1")},
        }
        gpus.append(current)
    elif current and "Kernel driver in use:" in line:
        current["kernel_driver"] = line.split(":", 1)[1].strip()

for gpu in gpus:
    gpu["vendor"] = identify_vendor(gpu["vendor_id"], gpu["kernel_driver"])

# Render nodes are mapped through sysfs to their PCI function.
for line in read_lines("render-map.txt"):
    parts = line.split("|")
    if len(parts) != 5:
        continue
    node, slot, vendor_id, device_id, driver = parts
    for gpu in gpus:
        if gpu["pci_slot"] == slot.lower():
            gpu["render_node"] = node
            gpu["kernel_driver"] = gpu["kernel_driver"] or driver
            gpu["vendor"] = identify_vendor(gpu["vendor_id"], gpu["kernel_driver"])

# Display evidence comes only from DRM connector state associated with a card.
cards = {}
for line in read_lines("drm-topology.txt"):
    parts = line.split("|")
    if len(parts) != 4:
        continue
    kind, card, value1, value2 = parts
    if kind == "CARD":
        cards[card] = {"pci_slot": value1.lower(), "driver": value2, "connectors": []}
    elif kind == "CONNECTOR" and card in cards:
        cards[card]["connectors"].append({"name": value1, "status": value2})
for card, data in cards.items():
    for gpu in gpus:
        if gpu["pci_slot"] != data["pci_slot"]:
            continue
        gpu["drm_card"] = card
        gpu["display_connectors"] = [item["name"] for item in data["connectors"] if item["status"] == "connected"]
        if gpu["display_connectors"]:
            gpu["display_path_status"] = "connected"
        elif data["connectors"]:
            gpu["display_path_status"] = "disconnected"

# VA-API observations remain attached to the render node that was tested.
va_by_node = {}
node = None
for line in read_lines("vaapi.txt"):
    section = re.match(r"^\[(.+)]$", line)
    if section:
        node = section.group(1)
        va_by_node[node] = {"driver": None, "lines": []}
    elif node:
        va_by_node[node]["lines"].append(line)
        if "Driver version" in line:
            va_by_node[node]["driver"] = line.strip()

patterns = {
    "mpeg2": r"VAProfileMPEG2.*VAEntrypointVLD",
    "h264": r"VAProfileH264.*VAEntrypointVLD",
    "hevc": r"VAProfileHEVCMain\s*:.*VAEntrypointVLD",
    "hevc_main10": r"VAProfileHEVCMain10.*VAEntrypointVLD",
    "vp9": r"VAProfileVP9.*VAEntrypointVLD",
    "av1": r"VAProfileAV1.*VAEntrypointVLD",
}
for gpu in gpus:
    observed = va_by_node.get(gpu["render_node"])
    if not observed:
        continue
    blob = "\n".join(observed["lines"])
    gpu["vaapi_driver"] = observed["driver"]
    gpu["vaapi_decode"] = {name: bool(re.search(pattern, blob)) for name, pattern in patterns.items()}

# Vulkan summary exposes vendor/device IDs. Software renderers are excluded.
vulkan_devices = []
vk = None
for line in read_lines("vulkan-full.txt"):
    if re.match(r"GPU\d+:\s*$", line.strip()):
        if vk:
            vulkan_devices.append(vk)
        vk = {}
        continue
    if vk is None or "=" not in line:
        continue
    key, value = (part.strip() for part in line.split("=", 1))
    if key in {"vendorID", "deviceID", "deviceType", "deviceName", "driverName", "driverInfo", "apiVersion"}:
        vk[key] = value
if vk:
    vulkan_devices.append(vk)

hardware_vulkan = []
for device in vulkan_devices:
    name = device.get("deviceName", "").lower()
    device_type = device.get("deviceType", "")
    if device_type == "PHYSICAL_DEVICE_TYPE_CPU" or "llvmpipe" in name or "lavapipe" in name:
        continue
    hardware_vulkan.append(device)

for gpu in gpus:
    matches = [device for device in hardware_vulkan
               if device.get("vendorID", "").lower().removeprefix("0x") == gpu["vendor_id"]
               and device.get("deviceID", "").lower().removeprefix("0x").zfill(4) == gpu["device_id"]]
    if len(matches) == 1:
        device = matches[0]
        gpu["vulkan_device"] = {
            "name": device.get("deviceName"),
            "type": device.get("deviceType"),
            "driver": device.get("driverName"),
            "api_version": device.get("apiVersion"),
        }

def normalize_pci(value):
    match = re.fullmatch(r"(?:(?:0000|00000000):)?([0-9a-fA-F]{2}):([0-9a-fA-F]{2})\.([0-7])", value.strip())
    return f"0000:{match.group(1).lower()}:{match.group(2).lower()}.{match.group(3)}" if match else None

smi_slots = set()
for line in read_lines("nvidia-smi.csv"):
    parts = [part.strip() for part in line.split(",")]
    if len(parts) == 3 and (slot := normalize_pci(parts[0])):
        smi_slots.add(slot)
mpv_values = "\n".join(read_lines("mpv-values.txt")).lower()
decoder_text = "\n".join(read_lines("ffmpeg-decoders.txt"))
cuvid_names = {"mpeg2":"mpeg2", "h264":"h264", "hevc":"hevc", "hevc_main10":"hevc", "vp9":"vp9", "av1":"av1"}
for gpu in gpus:
    gpu["nvdec_available"] = bool(gpu["vendor_id"] == "10de" and gpu["kernel_driver"] == "nvidia"
                                      and gpu["pci_slot"] in smi_slots and gpu["vulkan_device"] and "nvdec" in mpv_values)
    if gpu["nvdec_available"]:
        gpu["nvdec_decode"] = {name: bool(re.search(rf"\b{decoder}_cuvid\b", decoder_text)) for name, decoder in cuvid_names.items()}

weights = {"mpeg2": 1, "h264": 2, "hevc": 2, "hevc_main10": 2, "vp9": 1, "av1": 2}
for gpu in gpus:
    gpu["selection_score"] = (
        (2 if gpu["vulkan_device"] else 0)
        + (1 if gpu["render_node"] else 0)
        + sum(weights[name] for name, value in gpu["vaapi_decode"].items() if value)
    )

policy_decision = policy.select(gpus)
display_gpu = policy_decision["display_gpu"]
selected = policy_decision["processing_gpu"]
confidence = policy_decision["confidence"]
reason = policy_decision["reason"]
display_candidates = [gpu for gpu in gpus if gpu["display_connectors"]]

def public_gpu(gpu):
    if not gpu:
        return None
    return {key: gpu[key] for key in (
        "vendor", "pci_slot", "pci_id", "vendor_id", "device_id", "model",
        "kernel_driver", "drm_card", "render_node", "vulkan_device",
        "vaapi_driver", "vaapi_decode", "nvdec_available", "nvdec_decode",
        "display_connectors", "display_path_status"
    )}

# Le GPU d'affichage est identifié séparément par les connecteurs DRM actifs.
if len(display_candidates) == 1:
    display_confidence = "high"
elif len(display_candidates) > 1:
    display_confidence = "low"
else:
    display_confidence = "pending"

if display_gpu and selected:
    offload_required = policy_decision["offload_required"]
    topology_confidence = "high" if not offload_required and confidence == "high" else "medium"
else:
    offload_required = None
    topology_confidence = "low" if display_candidates or selected else "pending"

gpu_topology = {
    "display_gpu": public_gpu(display_gpu),
    "processing_gpu": public_gpu(selected),
    "offload_required": offload_required,
    "offload_validated": False,
    "confidence": topology_confidence,
    "display_detection_confidence": display_confidence,
}

evidence = []
if selected:
    evidence.append(f"GPU matériel associé au PCI {selected['pci_slot']} et au pilote {selected['kernel_driver'] or 'inconnu'}")
    if selected["render_node"]:
        evidence.append(f"Render node observé : {selected['render_node']}")
    if selected["vulkan_device"]:
        evidence.append(f"Périphérique Vulkan matériel associé : {selected['vulkan_device']['name']}")
    if any(selected["vaapi_decode"].values()):
        evidence.append("Profils de décodage VA-API observés par vainfo sur ce render node")
    if selected["nvdec_available"] and any(selected["nvdec_decode"].values()):
        evidence.append("NVDEC observé par pile NVIDIA PCI, Vulkan, nvidia-smi, MPV et FFmpeg")

decode_api = None
render_api = None
backend_status = "pending"
if selected:
    render_api = "vulkan" if selected["vulkan_device"] else "pending"
    if any(selected["vaapi_decode"].values()):
        decode_api = "vaapi"
    elif selected["nvdec_available"] and any(selected["nvdec_decode"].values()):
        decode_api = "nvdec"
    else:
        decode_api = "pending"
    backend_status = "observed" if decode_api in {"vaapi", "nvdec"} and render_api == "vulkan" else "proposed"

video_backend = {
    "vendor": selected["vendor"] if selected else "unknown",
    "decode_api": decode_api,
    "render_api": render_api,
    "kernel_driver": selected["kernel_driver"] if selected else None,
    "render_node": selected["render_node"] if selected else None,
    "status": backend_status,
    "evidence": evidence,
}

if hdr == "SDR":
    hdr_policy = "HDR tone mapping required for HDR sources"
elif hdr in {"HDR / HDR10", "HDR + Dolby Vision"}:
    hdr_policy = "HDR passthrough / output path à valider"
else:
    hdr_policy = "pending"

blueprint = {
    "status": "proposed" if selected else "pending",
    "gpu": public_gpu(selected),
    "gpu_selection": {"reason": reason, "confidence": confidence},
    "gpu_topology": gpu_topology,
    "video_backend": video_backend,
    "vo": "gpu-next" if selected and mpv_version != "absent" else None,
    "gpu_api": "vulkan" if render_api == "vulkan" else None,
    "hwdec": decode_api if decode_api in {"vaapi", "nvdec"} else None,
    "render_node": selected["render_node"] if selected else None,
    "offload_path": "direct" if offload_required is False else "pending",
    "display": {"resolution": resolution, "hdr": hdr, "refresh_rate": refresh},
    "hdr_policy": hdr_policy,
    "dolby_vision": "pending",
    "audio_policy": {"mode": audio_mode, "destination": audio_destination, "codecs_certified": False},
    "configuration_applied": False,
}

result = {
    "gpus": [public_gpu(gpu) | {"selection_score": gpu["selection_score"]} for gpu in gpus],
    "selection": {"gpu": public_gpu(selected), "reason": reason, "confidence": confidence},
    "gpu_topology": gpu_topology,
    "video_backend": video_backend,
    "mpv_blueprint": blueprint,
}
(work / "gpu-decision.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PYGPU

title "ÉCRAN 4 — CAPACITÉS DE VOTRE OPENHTPC"
printf '%sCet écran est informatif : il ne configure aucun traitement.%s\n\n' "$C_OK" "$C_RESET"
printf 'SD / DVD\n'
if $has_mpeg2; then
    printf '  - Décodage matériel MPEG-2 observé via VA-API.\n'
else
    printf '  - Décodage MPEG-2 matériel non validé ; décodage logiciel possible via MPV.\n'
fi
printf '  - Upscale et reconstruction chroma pourront être étudiés dans un futur runtime.\n\n'
printf '720p\n'
printf '  - Lecture par MPV ; décodage H.264 matériel %s.\n\n' "$($has_h264 && printf 'observé' || printf 'non validé')"
printf '1080p / Blu-ray\n'
printf '  - Décodage H.264 matériel %s ; HEVC matériel %s.\n' \
    "$($has_h264 && printf 'observé' || printf 'non validé')" \
    "$($has_hevc && printf 'observé' || printf 'non validé')"
printf '  - Les traitements image futurs dépendront des performances mesurées.\n\n'
printf 'UHD / 4K\n'
printf '  - HEVC Main10 : %s ; VP9 : %s ; AV1 : %s.\n' \
    "$($has_hevc10 && printf 'observé' || printf 'non validé')" \
    "$($has_vp9 && printf 'observé' || printf 'non validé')" \
    "$($has_av1 && printf 'observé' || printf 'non validé')"
printf '  - Couche FFmpeg : H.264 %s ; HEVC %s ; AV1 %s.\n' \
    "$($ffmpeg_h264 && printf 'disponible' || printf 'non validé')" \
    "$($ffmpeg_hevc && printf 'disponible' || printf 'non validé')" \
    "$($ffmpeg_av1 && printf 'disponible' || printf 'non validé')"
if [[ $display_resolution == "3840x2160" ]]; then
    printf "  - L'écran déclaré permet une sortie 4K potentielle.\n"
else
    printf '  - Une adaptation à la résolution déclarée sera nécessaire pour les sources 4K.\n'
fi
if [[ $display_hdr == "SDR" ]]; then
    printf '  - Un tone mapping pourra être nécessaire pour les sources HDR.\n'
else
    printf '  - Le comportement HDR devra être validé sur la chaîne d’affichage réelle.\n'
fi

printf '\nProfils disponibles pendant la lecture :\n'
printf '  PURE      : chaîne minimale fidèle ; état déterminé par les validations conservées.\n'
printf '  REFERENCE : rendu fidèle avec fonctions natives MPV/libplacebo ; prêt pour validation.\n'
printf '  ENHANCED  : à venir.\n'
printf '%sAucun profil n’est choisi définitivement par ce Builder.%s\n' "$C_WARN" "$C_RESET"

printf '\nArchitecture vidéo proposée\n'
python3 - "$WORK_DIR/gpu-decision.json" <<'PYDISPLAY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
selection = data["selection"]
blueprint = data["mpv_blueprint"]
topology = data["gpu_topology"]
backend = data["video_backend"]
gpu = selection["gpu"]
display = topology["display_gpu"]
print(f"  GPU d’affichage      : {display['model'] if display else 'à confirmer'}")
print(f"  GPU vidéo recommandé : {gpu['model'] if gpu else 'à confirmer'}")
print(f"  Backend vidéo        : {backend['decode_api'] or 'pending'} + {backend['render_api'] or 'pending'}")
print(f"  Chemin multi-GPU     : {blueprint['offload_path']}")
if gpu:
    print(f"  PCI / render         : {gpu['pci_id']} / {gpu['render_node']}")
print(f"  Raison        : {selection['reason']}")
print(f"  Confiance     : {selection['confidence']}")
print(f"  vo            : {blueprint['vo'] or 'pending'}")
print(f"  gpu-api       : {blueprint['gpu_api'] or 'pending'}")
print(f"  hwdec         : {blueprint['hwdec'] or 'pending'}")
print(f"  HDR           : {blueprint['hdr_policy']}")
print(f"  Audio         : {blueprint['audio_policy']['mode']} — codecs non certifiés")
print("  Application   : aucune (blueprint informatif)")
PYDISPLAY

mkdir -p "$CONFIG_DIR"

python3 - "$PROFILE_FILE" "$WORK_DIR" \
    "$os_name" "$kernel" "${cpu:-inconnu}" "${ram:-inconnue}" \
    "$mpv_version" "$ffmpeg_version" "$vulkan_status" "$vaapi_status" \
    "$display_resolution" "$display_hdr" "$display_refresh" \
    "$audio_destination" "$audio_mode" "$gpu_count" \
    "$media_source" "$rpmfusion_enabled" "$vaapi_driver" \
    "$ffmpeg_h264" "$ffmpeg_hevc" "$ffmpeg_av1" \
    "$has_mpeg2" "$has_h264" "$has_hevc" "$has_hevc10" "$has_vp9" "$has_av1" <<'PY'
import datetime
import hashlib
import json
import pathlib
import platform
import sys

(profile_path, work_dir, os_name, kernel, cpu, ram, mpv, ffmpeg,
 vulkan_status, vaapi_status, resolution, hdr, refresh, audio_destination,
 audio_mode, gpu_count, media_source, rpmfusion_enabled, vaapi_driver,
 ffmpeg_h264, ffmpeg_hevc, ffmpeg_av1, *codec_values) = sys.argv[1:]
work = pathlib.Path(work_dir)
codec_names = ("mpeg2", "h264", "hevc", "hevc_main10", "vp9", "av1")
codecs = dict(zip(codec_names, (value == "true" for value in codec_values)))

def lines(name):
    return (work / name).read_text(encoding="utf-8", errors="replace").splitlines()

decision = json.loads((work / "gpu-decision.json").read_text(encoding="utf-8"))
fingerprint_gpus = decision["gpus"]
fingerprint_data = {
    "gpus": [[gpu.get("vendor_id"), gpu.get("device_id"), gpu.get("kernel_driver")] for gpu in fingerprint_gpus],
    "architecture": platform.machine(),
}
hardware_fingerprint = hashlib.sha256(json.dumps(fingerprint_data, sort_keys=True).encode()).hexdigest()
vaapi_drivers = []
for gpu in fingerprint_gpus:
    driver = gpu.get("vaapi_driver")
    if driver:
        vaapi_drivers.append(driver.split("Driver version:", 1)[-1].strip())
runtime_data = {
    "mpv": mpv.splitlines()[0] if mpv else None,
    "ffmpeg": ffmpeg.splitlines()[0] if ffmpeg else None,
    "vaapi_drivers": sorted(set(vaapi_drivers)),
    "gpu_drivers": [gpu.get("kernel_driver") for gpu in fingerprint_gpus],
    "nvidia_drivers": sorted({parts[2].strip() for line in lines("nvidia-smi.csv") if len(parts := line.split(",")) == 3}),
    "mpv_hwdec_nvdec": "nvdec" in "\n".join(lines("mpv-values.txt")).lower(),
}
runtime_fingerprint = hashlib.sha256(json.dumps(runtime_data, sort_keys=True).encode()).hexdigest()
generated_at = datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat()
optical_drives = []
for entry in sorted(pathlib.Path("/sys/class/block").glob("*")):
    try:
        if (entry / "device/type").read_text().strip() == "5":
            optical_drives.append("/dev/" + entry.name)
    except OSError:
        pass
try:
    audio_devices = pathlib.Path("/proc/asound/cards").read_text(encoding="utf-8", errors="replace").splitlines()
except OSError:
    audio_devices = []
previous_playback_validation = None
existing_profile = pathlib.Path(profile_path)
if existing_profile.exists():
    try:
        previous_playback_validation = json.loads(
            existing_profile.read_text(encoding="utf-8")
        ).get("playback_validation")
    except (json.JSONDecodeError, OSError):
        previous_playback_validation = None

profile = {
    "schema": 1,
    "generator": {"name": "OPENHTPC Builder", "version": "4.0.0"},
    "generated_at": generated_at,
    "capability_source": {
        "hardware_fingerprint": hardware_fingerprint,
        "runtime_fingerprint": runtime_fingerprint,
        "generated_at": generated_at,
    },
    "detected": {
        "os": os_name,
        "kernel": kernel,
        "cpu": cpu,
        "memory": ram,
        "gpus": lines("gpus.txt"),
        "gpu_details": decision["gpus"],
        "gpu_count": int(gpu_count),
        "render_nodes": lines("render-nodes.txt"),
        "vulkan": {"status": vulkan_status, "observations": lines("vulkan.txt")},
        "vaapi": {"status": vaapi_status, "observed_decode_profiles": codecs},
        "mpv": mpv,
        "ffmpeg": ffmpeg,
        "desktop_session": {
            "desktop": __import__("os").environ.get("XDG_CURRENT_DESKTOP"),
            "session_type": __import__("os").environ.get("XDG_SESSION_TYPE"),
        },
        "audio_devices": audio_devices,
        "optical_drives": optical_drives,
    },
    "media_stack": {
        "source": media_source,
        "rpmfusion_enabled": rpmfusion_enabled == "true",
        "vaapi_driver": vaapi_driver or None,
        "observed_capabilities": {
            "vaapi_decode": codecs,
            "ffmpeg_decoders": {
                "h264": ffmpeg_h264 == "true",
                "hevc": ffmpeg_hevc == "true",
                "av1": ffmpeg_av1 == "true",
            },
        },
    },
    "gpu_selection": decision["selection"],
    "gpu_topology": decision["gpu_topology"],
    "video_backend": decision["video_backend"],
    "mpv_blueprint": decision["mpv_blueprint"],
    "user_answers": {
        "display": {"resolution": resolution, "hdr": hdr, "refresh_rate": refresh},
        "audio": {"destination": audio_destination, "mode": audio_mode},
    },
    "pending_validation": [
        "Validation de tout chemin d’offload lorsque GPU d’affichage et GPU vidéo diffèrent",
        "Validation physique des backends AMD et NVIDIA",
        "Chaîne HDR et Dolby Vision",
        "Périphérique et formats audio réellement utilisables",
        "Performances des futurs traitements image",
    ],
    "runtime_profiles": {
        "available": ["PURE", "REFERENCE"],
        "enhanced": "pending",
        "default": "PURE",
        "selection_scope": "playback",
        "selected": None,
    },
    "mpv_configuration_generated": False,
    "flex_independent": True,
}
if previous_playback_validation:
    profile["playback_validation"] = previous_playback_validation
pathlib.Path(profile_path).write_text(
    json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
PY

mkdir -p "$MPV_RUNTIME_DIR"
"$RUNTIME_GENERATOR" "$PROFILE_FILE" "$MPV_PURE_CONFIG" "$MPV_REFERENCE_CONFIG" \
    "$WORK_DIR/mpv-options.txt" "$WORK_DIR/mpv-values.txt" "$VERSION_METADATA"

{
    printf 'OPENHTPC — Rapport Build 4\n'
    printf 'Généré : %s\n\n' "$(date --iso-8601=seconds)"
    printf 'MATÉRIEL DÉTECTÉ\n'
    printf 'OS : %s\nKernel : %s\nCPU : %s\nRAM : %s\n' "$os_name" "$kernel" "${cpu:-inconnu}" "${ram:-inconnue}"
    printf '\nGPU ET PILOTES\n'; cat "$WORK_DIR/gpus.txt"
    printf '\nRENDER NODES\n'; cat "$WORK_DIR/render-nodes.txt"
    printf '\nVULKAN — %s\n' "$vulkan_status"; cat "$WORK_DIR/vulkan.txt"
    printf '\nVA-API — %s\n' "$vaapi_status"; cat "$WORK_DIR/vaapi.txt"
    printf '\nOUTILS\nMPV : %s\nFFmpeg : %s\n' "$mpv_version" "$ffmpeg_version"
    printf '\nMEDIA STACK\nSource : %s\nRPM Fusion : %s\nPilote VA-API : %s\n' \
        "$media_source" "$rpmfusion_enabled" "${vaapi_driver:-non observé}"
    printf 'VA-API : MPEG-2=%s H.264=%s HEVC=%s HEVC10=%s VP9=%s AV1=%s\n' \
        "$has_mpeg2" "$has_h264" "$has_hevc" "$has_hevc10" "$has_vp9" "$has_av1"
    printf 'FFmpeg : H.264=%s HEVC=%s AV1=%s\n' "$ffmpeg_h264" "$ffmpeg_hevc" "$ffmpeg_av1"
    printf '\nTOPOLOGIE GPU / VIDEO BACKEND / MPV BLUEPRINT\n'
    python3 - "$WORK_DIR/gpu-decision.json" <<'PYREPORT'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
s, b, t, v = d["selection"], d["mpv_blueprint"], d["gpu_topology"], d["video_backend"]
print("GPU d’affichage :", t["display_gpu"]["model"] if t["display_gpu"] else "à confirmer")
print("GPU vidéo :", s["gpu"]["model"] if s["gpu"] else "à confirmer")
print("Offload requis :", t["offload_required"])
print("Offload validé : non")
print("Backend :", v["decode_api"] or "pending", "+", v["render_api"] or "pending")
print("Raison :", s["reason"])
print("Confiance :", s["confidence"])
print("vo :", b["vo"] or "pending")
print("gpu-api :", b["gpu_api"] or "pending")
print("hwdec :", b["hwdec"] or "pending")
print("render node :", b["render_node"] or "pending")
print("HDR :", b["hdr_policy"])
print("Audio :", b["audio_policy"]["mode"], "— codecs non certifiés")
print("Configuration appliquée : non")
PYREPORT
    printf '\nRÉPONSES UTILISATEUR\nAffichage : %s, %s, %s\nAudio : %s, %s\n' \
        "$display_resolution" "$display_hdr" "$display_refresh" "$audio_destination" "$audio_mode"
    printf '\nÀ VALIDER\nGPU actif, HDR/Dolby Vision, formats audio, performances des traitements image.\n'
    printf '\nRUNTIME MPV\n'
    python3 - "$PROFILE_FILE" <<'PYRUNTIME_REPORT'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))["runtime"]
print("État :", r["status"])
print("Configuration :", r["config_path"] or "non générée")
print("Chemin vidéo :", r["display_path"])
print("Raison :", r["reason"])
print("Validation lecture : en attente")
print("Configuration globale appliquée : non")
profiles = json.load(open(sys.argv[1], encoding="utf-8"))["runtime_profiles"]["profiles"]
print("PURE :", profiles["PURE"]["generation_status"], "/", profiles["PURE"]["validation_status"])
print("REFERENCE :", profiles["REFERENCE"]["generation_status"], "/", profiles["REFERENCE"]["validation_status"])
print("ENHANCED : pending")
PYRUNTIME_REPORT
    printf '\nAucun shader ni profil ENHANCED n’a été activé. Le profil est choisi à chaque lecture.\n'
} >"$REPORT_FILE"

printf '\n%sProfil créé : %s%s\n' "$C_OK" "$PROFILE_FILE" "$C_RESET"
printf '%sRapport créé : %s%s\n' "$C_OK" "$REPORT_FILE" "$C_RESET"
printf '\nRuntime MPV\n'
python3 - "$PROFILE_FILE" <<'PYRUNTIME_DISPLAY'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))["runtime"]
b = r["backend"]
print("  Configuration candidate :", "prête" if r["status"] == "ready" else "non générée")
print("  Backend                :", (b.get("decode_api") or "pending"), "+", (b.get("render_api") or "pending"))
print("  Chemin vidéo           :", r["display_path"])
print("  Validation lecture     : en attente")
profiles = json.load(open(sys.argv[1], encoding="utf-8"))["runtime_profiles"]["profiles"]
print("  PURE                   :", profiles["PURE"]["generation_status"], "/", profiles["PURE"]["validation_status"])
print("  REFERENCE              :", profiles["REFERENCE"]["generation_status"], "/", profiles["REFERENCE"]["validation_status"])
print("  ENHANCED               : pending")
if r["status"] != "ready":
    print("  Raison                 :", r["reason"])
PYRUNTIME_DISPLAY

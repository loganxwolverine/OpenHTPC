#!/usr/bin/env bash
# Read-only OPENHTPC Phase 2A collector. It writes only its requested report.
set -u
set -o pipefail

timestamp="$(date -u +%Y%m%d-%H%M%S)"
output="${1:-$PWD/openhtpc-amd-codec-forensic-${timestamp}.txt}"
profile="${OPENHTPC_PROFILE:-${HOME}/.config/openhtpc/profile.json}"
pure="${OPENHTPC_PURE_CONF:-${HOME}/.config/openhtpc/runtime/mpv/pure.conf}"
audit_tool="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/openhtpc-codec-capability-audit.py"

section() { printf '\n===== %s =====\n' "$1"; }
run() {
    printf '\n$'
    printf ' %q' "$@"
    printf '\n'
    "$@" 2>&1
    local status=$?
    printf '[exit=%s]\n' "$status"
    return 0
}
available() { command -v "$1" >/dev/null 2>&1; }

render_node=""
if [[ -r $profile ]] && available python3; then
    render_node="$(python3 - "$profile" <<'PY' 2>/dev/null || true
import json, pathlib, sys
try:
    data = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
except (OSError, ValueError):
    raise SystemExit(0)
paths = (
    ("video_backend", "render_node"),
    ("gpu_topology", "processing_gpu", "render_node"),
    ("gpu_topology", "display_gpu", "render_node"),
)
for path in paths:
    value = data
    for key in path:
        value = value.get(key) if isinstance(value, dict) else None
    if isinstance(value, str) and value.startswith("/dev/dri/renderD"):
        print(value)
        break
PY
)"
fi

{
    printf 'OPENHTPC AMD MEDIA CODEC FORENSIC — PHASE 2A\n'
    printf 'collector_version=2\ncollected_utc=%s\n' "$(date -u --iso-8601=seconds)"
    printf 'output=%s\nprofile=%s\npassport_render_node=%s\n' "$output" "$profile" "${render_node:-NOT_FOUND}"

    section 'OPERATING SYSTEM'
    [[ -r /etc/os-release ]] && run sed -n '1,80p' /etc/os-release
    run uname -a

    section 'GPU AND DRM'
    available lspci && run lspci -Dnnk
    if [[ -d /dev/dri ]]; then run ls -l /dev/dri; else printf '/dev/dri: NOT_FOUND\n'; fi
    for node in /sys/class/drm/renderD*; do
        [[ -e $node ]] || continue
        printf '\n[%s]\n' "$node"
        run readlink -f "$node/device"
        [[ -r $node/device/vendor ]] && run sed -n '1p' "$node/device/vendor"
        [[ -r $node/device/device ]] && run sed -n '1p' "$node/device/device"
        [[ -L $node/device/driver ]] && run readlink -f "$node/device/driver"
    done

    section 'INSTALLED MEDIA PACKAGES AND PROVENANCE'
    if available rpm; then
        printf '[filtered media packages]\n'
        rpm -qa --qf '%{NAME}\t%{EPOCHNUM}:%{VERSION}-%{RELEASE}\t%{ARCH}\t%{VENDOR}\t%{PACKAGER}\n' 2>&1 |
            grep -Ei '(^|[-])(mesa|libva|ffmpeg|libavcodec|mpv)([-[:space:]]|$)' | sort || true
        printf '\n[VA driver file owners]\n'
        for driver in /usr/lib64/dri/*_drv_video.so /usr/lib64/dri-freeworld/*_drv_video.so /usr/lib/dri/*_drv_video.so; do
            [[ -e $driver ]] || continue
            printf '%s\t' "$driver"
            rpm -qf --qf '%{NAME} %{EPOCHNUM}:%{VERSION}-%{RELEASE} %{VENDOR} %{PACKAGER}\n' "$driver" 2>&1 || true
        done
        printf '\n[installed package source repositories]\n'
        if available dnf5; then
            dnf5 -q repoquery --installed --qf '%{name}\t%{evr}\t%{arch}\t%{from_repo}' 2>&1 |
                grep -Ei '(^|[-])(mesa|libva|ffmpeg|libavcodec|mpv)([-[:space:]]|$)' | sort || true
        elif available dnf; then
            dnf -q repoquery --installed --qf '%{name}\t%{evr}\t%{arch}\t%{from_repo}' 2>&1 |
                grep -Ei '(^|[-])(mesa|libva|ffmpeg|libavcodec|mpv)([-[:space:]]|$)' | sort || true
        fi
    else
        printf 'rpm: NOT_FOUND\n'
    fi

    section 'ENABLED REPOSITORIES (READ ONLY)'
    if available dnf5; then run dnf5 -q repolist --enabled
    elif available dnf; then run dnf -q repolist --enabled
    else printf 'dnf/dnf5: NOT_FOUND\n'; fi

    section 'LIBVA AND VAAPI'
    available vainfo && run vainfo --version || printf 'vainfo: NOT_FOUND\n'
    if [[ -n $render_node ]]; then
        if [[ -e $render_node ]]; then run vainfo --display drm --device "$render_node"
        else printf 'Passport render node does not exist: %s\n' "$render_node"; fi
    else
        printf 'No render node found in Hardware Passport; vainfo not guessed.\n'
    fi

    section 'LIBVA DRIVER-PATH COMPARISON (READ ONLY)'
    printf 'LIBVA_DRIVERS_PATH=%s\n' "${LIBVA_DRIVERS_PATH:-UNSET}"
    [[ -r /etc/ld.so.conf.d/mesa-freeworld-lib64.conf ]] && run sed -n '1,80p' /etc/ld.so.conf.d/mesa-freeworld-lib64.conf
    if available vainfo && [[ -n $render_node && -e $render_node ]]; then
        for driver_path in /usr/lib64/dri /usr/lib64/dri-freeworld; do
            [[ -r $driver_path/radeonsi_drv_video.so ]] || continue
            run env LIBVA_DRIVERS_PATH="$driver_path" vainfo --display drm --device "$render_node"
        done
    fi

    section 'FFMPEG'
    if available ffmpeg; then
        run ffmpeg -version
        run ffmpeg -hide_banner -hwaccels
        run ffmpeg -hide_banner -decoders
    else printf 'ffmpeg: NOT_FOUND\n'; fi

    section 'MPV'
    if available mpv; then
        run mpv --no-config --version
        run mpv --no-config --hwdec=help
    else printf 'mpv: NOT_FOUND\n'; fi

    section 'OPENHTPC HARDWARE PASSPORT — CODEC ALLOWLIST'
    if [[ -r $profile ]] && available python3; then
        python3 - "$profile" <<'PY' 2>&1
import json, pathlib, sys
data = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
keys = ("gpu_topology", "video_backend", "media_stack", "runtime_profiles", "runtime", "mpv_configuration_generated")
print(json.dumps({key: data.get(key) for key in keys if key in data}, ensure_ascii=False, indent=2, sort_keys=True))
PY
    else printf 'Hardware Passport: NOT_READABLE\n'; fi

    section 'OPENHTPC CAPABILITY CONSISTENCY'
    if [[ -r $profile && -r $audit_tool ]] && available python3; then
        run python3 "$audit_tool" "$profile"
    else
        printf 'Capability consistency audit: NOT_AVAILABLE\n'
    fi

    section 'OPENHTPC PURE RUNTIME'
    if [[ -r $pure ]]; then run sed -n '1,240p' "$pure"
    else printf 'PURE runtime not found at %s\n' "$pure"; fi

    section 'COLLECTOR SAFETY'
    printf 'configuration_mutations=NONE\nsudo_used=NO\nmedia_playback=NO\ngraphics_probe=NO\n'
} >"$output"

printf 'Forensic collection complete.\nOUTPUT: %s\n' "$output"
if available sha256sum; then
    sha256sum "$output"
fi

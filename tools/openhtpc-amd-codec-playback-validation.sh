#!/usr/bin/env bash
# Explicit physical playback helper. The operator supplies the source; no filename inference.
set -u
set -o pipefail

die() { printf 'ERROR: %s\n' "$*" >&2; exit 2; }
[[ $# -ge 3 && $2 == -- ]] || die "usage: $0 LABEL -- MPV_SOURCE_OR_OPTIONS..."
label=$1; shift 2
case "$label" in MPEG2_DVD|H264_1080P|HEVC_MAIN8|HEVC_MAIN10|VP9) ;; *) die "invalid test label" ;; esac

runtime="${OPENHTPC_PURE_CONF:-${HOME}/.config/openhtpc/runtime/mpv/pure.conf}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
reporter="$script_dir/openhtpc-codec-playback-report.py"
[[ -r $runtime && -r $reporter ]] || die "OPENHTPC PURE runtime or reporter unavailable"
command -v mpv >/dev/null 2>&1 || die "mpv unavailable"

stamp="$(date -u +%Y%m%d-%H%M%S)"
base="$PWD/openhtpc-amd-codec-${label,,}-$stamp"
log="$base.mpv.log"; probe="$base.ffprobe.json"; report="$base.report.json"
printf '{"streams":[]}\n' >"$probe"
last=${!#}
if [[ -f $last ]] && command -v ffprobe >/dev/null 2>&1; then
    ffprobe -v error -select_streams v:0 \
        -show_entries stream=codec_type,codec_name,profile,pix_fmt,width,height,r_frame_rate \
        -of json -- "$last" >"$probe" 2>/dev/null || printf '{"streams":[]}\n' >"$probe"
fi

requested="$(sed -n 's/^hwdec=//p' "$runtime" | head -n1)"
render_node="$(sed -n 's/^vaapi-device=//p' "$runtime" | head -n1)"
printf 'Test %s — press q after the observation period.\n' "$label"
mpv --no-config --include="$runtime" --audio=no --fullscreen=yes --terminal=yes \
    --msg-level=all=v --log-file="$log" \
    '--term-status-msg=OPENHTPC_METRICS vo_drop=${vo-drop-frame-count} decoder_drop=${decoder-frame-drop-count}' \
    "$@"
mpv_rc=$?
printf 'Fluid playback observed? [o/N] '
IFS= read -r answer
fluid=no; [[ $answer =~ ^[oOyY]$ ]] && fluid=yes
python3 "$reporter" --label "$label" --log "$log" --probe "$probe" --mpv-exit "$mpv_rc" \
    --requested "$requested" --render-node "$render_node" --visually-fluid "$fluid" --output "$report"
printf 'RAW_LOG: %s\nREPORT: %s\n' "$log" "$report"
exit "$mpv_rc"

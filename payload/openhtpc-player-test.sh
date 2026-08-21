#!/usr/bin/env bash

set -Eeuo pipefail

readonly PROFILE_FILE="${HOME}/.config/openhtpc/profile.json"
readonly RUNTIME_DIR="${HOME}/.config/openhtpc/runtime"
readonly ANALYZER="${OPENHTPC_ANALYZER:-${HOME}/.local/lib/openhtpc/openhtpc-playback-analyze.py}"

diagnostic=false
selected_profile=pure
media_file=""
while (($#)); do
    case $1 in
        --diagnostic)
            diagnostic=true
            shift
            ;;
        --profile)
            [[ $# -ge 2 ]] || { printf '[OPENHTPC] ERREUR : --profile exige pure ou reference.\n' >&2; exit 2; }
            selected_profile=${2,,}
            shift 2
            ;;
        --profile=*)
            selected_profile=${1#*=}
            selected_profile=${selected_profile,,}
            shift
            ;;
        -* )
            printf '[OPENHTPC] ERREUR : option inconnue : %s\n' "$1" >&2
            exit 2
            ;;
        *)
            [[ -z $media_file ]] || { printf '[OPENHTPC] ERREUR : un seul fichier vidéo est accepté.\n' >&2; exit 2; }
            media_file=$1
            shift
            ;;
    esac
done

if [[ $selected_profile != pure && $selected_profile != reference ]]; then
    printf '[OPENHTPC] ERREUR : profil invalide « %s » (pure ou reference attendu).\n' "$selected_profile" >&2
    exit 2
fi
if [[ -z $media_file ]]; then
    printf 'Usage : openhtpc-player-test [--profile pure|reference] [--diagnostic] /chemin/video\n' >&2
    exit 2
fi

[[ -f $media_file ]] || {
    printf '[OPENHTPC] ERREUR : fichier vidéo introuvable : %s\n' "$media_file" >&2
    exit 2
}
[[ -r $PROFILE_FILE ]] || {
    printf '[OPENHTPC] ERREUR : lancez d’abord openhtpc-builder.\n' >&2
    exit 3
}
command -v mpv >/dev/null 2>&1 || {
    printf '[OPENHTPC] ERREUR : MPV est introuvable.\n' >&2
    exit 3
}
if $diagnostic && [[ ! -r $ANALYZER ]]; then
    printf '[OPENHTPC] ERREUR : analyseur de lecture introuvable : %s\n' "$ANALYZER" >&2
    exit 3
fi

mapfile -t runtime_data < <(python3 - "$PROFILE_FILE" "${selected_profile^^}" <<'PY'
import json, sys
p = json.load(open(sys.argv[1], encoding="utf-8"))
r = p.get("runtime", {})
b = r.get("backend", {})
profile = p.get("runtime_profiles", {}).get("profiles", {}).get(sys.argv[2], {})
print(r.get("status", "pending"))
print(profile.get("config_path") or "")
print(b.get("decode_api") or "pending")
print(b.get("render_api") or "pending")
print(r.get("display_path", "pending"))
print(profile.get("generation_status", "pending"))
print(r.get("reason", "Runtime ou profil non préparé"))
PY
)

runtime_status=${runtime_data[0]:-pending}
config_file=${runtime_data[1]:-}
decode_api=${runtime_data[2]:-pending}
render_api=${runtime_data[3]:-pending}
display_path=${runtime_data[4]:-pending}
generation_status=${runtime_data[5]:-pending}
reason=${runtime_data[6]:-Runtime non préparé}

if [[ $runtime_status != ready || $generation_status != generated || -z $config_file || ! -r $config_file ]]; then
    printf '[OPENHTPC] Runtime : pending\n' >&2
    printf '[OPENHTPC] Raison  : %s\n' "$reason" >&2
    exit 4
fi

printf '[OPENHTPC] Configuration isolée : %s\n' "$config_file"
printf '[OPENHTPC] Profil de lecture     : %s\n' "${selected_profile^^}"
printf '[OPENHTPC] Backend demandé      : %s + %s\n' "$decode_api" "$render_api"
printf '[OPENHTPC] Chemin vidéo demandé : %s\n' "$display_path"
printf '[OPENHTPC] Validation réelle    : en attente de la sortie MPV\n'

source_resolution=""
source_category="inconnue"
if command -v ffprobe >/dev/null 2>&1; then
    source_resolution="$(ffprobe -v error -select_streams v:0 \
        -show_entries stream=width,height -of csv=s=x:p=0 -- "$media_file" 2>/dev/null | head -n 1 || true)"
fi
if [[ $source_resolution =~ ^([0-9]+)x([0-9]+)$ ]]; then
    source_width=${BASH_REMATCH[1]}
    source_height=${BASH_REMATCH[2]}
    if ((source_width >= 3840 || source_height >= 2160)); then
        source_category="UHD/4K"
    elif ((source_width >= 1920 || source_height >= 1080)); then
        source_category="1080p"
    elif ((source_width >= 1280 || source_height >= 720)); then
        source_category="720p"
    else
        source_category="SD"
    fi
    printf '[OPENHTPC] Source détectée       : %s (%s)\n' "$source_resolution" "$source_category"
else
    printf '[OPENHTPC] Source détectée       : résolution inconnue\n'
fi

mpv_args=(
    --no-config
    --load-scripts=no
    --input-conf=/dev/null
    "--include=$config_file"
)

if ! $diagnostic; then
    exec mpv "${mpv_args[@]}" -- "$media_file"
fi

mkdir -p "$RUNTIME_DIR/logs"
log_file="$RUNTIME_DIR/logs/playback-$(date +%Y%m%d-%H%M%S-%N).log"
printf '[OPENHTPC] Journal diagnostic   : %s\n' "$log_file"

set +e
mpv "${mpv_args[@]}" \
    "--log-file=$log_file" \
    '--term-status-msg=OPENHTPC_FRAME_TELEMETRY time=${=playback-time} dropped=${=drop-frame-count}' \
    '--msg-level=vo/gpu=debug,vo/gpu-next=debug,vd=debug,ffmpeg=warn' \
    -- "$media_file"
mpv_rc=$?
set -e

summary_base=${log_file%.log}
printf '\n'
if ! python3 "$ANALYZER" "$PROFILE_FILE" "$log_file" "$mpv_rc" "$summary_base" "${selected_profile^^}"; then
    printf '[OPENHTPC] ERREUR : analyse automatique du journal impossible.\n' >&2
    ((mpv_rc != 0)) && exit "$mpv_rc"
    exit 5
fi
exit "$mpv_rc"

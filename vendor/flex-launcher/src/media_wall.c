#include "media_wall.h"

#include <stdlib.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <strings.h>

typedef struct {
    const char *title;
    size_t index;
} SortItem;

static int compare_items(const void *left, const void *right)
{
    const SortItem *a = left;
    const SortItem *b = right;
    int result = strcasecmp(a->title != NULL ? a->title : "",
                            b->title != NULL ? b->title : "");
    if (result != 0)
        return result;
    return (a->index > b->index) - (a->index < b->index);
}

bool media_wall_init(MediaWallModel *model, const char *const *titles,
                     size_t count, size_t viewport)
{
    if (model == NULL || titles == NULL || count == 0 || viewport == 0)
        return false;

    memset(model, 0, sizeof(*model));
    model->az_order = malloc(count * sizeof(*model->az_order));
    SortItem *items = malloc(count * sizeof(*items));
    if (model->az_order == NULL || items == NULL) {
        free(model->az_order);
        free(items);
        memset(model, 0, sizeof(*model));
        return false;
    }

    for (size_t i = 0; i < count; i++) {
        items[i].title = titles[i];
        items[i].index = i;
    }
    qsort(items, count, sizeof(*items), compare_items);
    for (size_t i = 0; i < count; i++)
        model->az_order[i] = items[i].index;
    free(items);

    model->count = count;
    model->recent_count = count < MEDIA_WALL_RECENT_LIMIT
        ? count : MEDIA_WALL_RECENT_LIMIT;
    model->viewport = viewport;
    model->row = MEDIA_WALL_RECENT;
    return true;
}

void media_wall_destroy(MediaWallModel *model)
{
    if (model == NULL)
        return;
    free(model->az_order);
    memset(model, 0, sizeof(*model));
}

size_t media_wall_row_count(const MediaWallModel *model, MediaWallRow row)
{
    if (model == NULL)
        return 0;
    return row == MEDIA_WALL_RECENT ? model->recent_count : model->count;
}

size_t media_wall_manifest_index(const MediaWallModel *model,
                                 MediaWallRow row, size_t position)
{
    size_t count = media_wall_row_count(model, row);
    if (model == NULL || position >= count)
        return SIZE_MAX;
    return row == MEDIA_WALL_RECENT ? position : model->az_order[position];
}

size_t media_wall_current_manifest_index(const MediaWallModel *model)
{
    if (model == NULL)
        return SIZE_MAX;
    return media_wall_manifest_index(model, model->row,
                                     model->selected[model->row]);
}

bool media_wall_tab_selectable(MediaWallTab tab)
{
    return tab == MEDIA_WALL_TAB_FILMS || tab == MEDIA_WALL_TAB_DISQUE ||
           tab == MEDIA_WALL_TAB_DOSSIERS;
}

const char *media_wall_tab_target(MediaWallTab tab)
{
    if (tab == MEDIA_WALL_TAB_DISQUE)
        return "DISQUE";
    if (tab == MEDIA_WALL_TAB_DOSSIERS)
        return "MEDIA_ROOT";
    return NULL;
}

bool media_wall_move_horizontal(MediaWallModel *model, int direction)
{
    if (model == NULL || direction == 0)
        return false;
    if (model->tab_focused) {
        MediaWallTab old = model->tab;
        int next = (int) old + (direction > 0 ? 1 : -1);
        while (next >= MEDIA_WALL_TAB_FILMS && next <= MEDIA_WALL_TAB_DOSSIERS &&
               !media_wall_tab_selectable((MediaWallTab) next))
            next += (direction > 0 ? 1 : -1);
        if (next < MEDIA_WALL_TAB_FILMS || next > MEDIA_WALL_TAB_DOSSIERS)
            return false;
        model->tab = (MediaWallTab) next;
        return model->tab != old;
    }
    size_t row = (size_t) model->row;
    size_t count = media_wall_row_count(model, model->row);
    size_t previous = model->selected[row];

    if (direction < 0 && model->selected[row] > 0)
        model->selected[row]--;
    else if (direction > 0 && model->selected[row] + 1 < count)
        model->selected[row]++;

    if (model->selected[row] < model->scroll[row])
        model->scroll[row] = model->selected[row];
    else if (model->selected[row] >= model->scroll[row] + model->viewport)
        model->scroll[row] = model->selected[row] - model->viewport + 1;
    return previous != model->selected[row];
}

bool media_wall_move_vertical(MediaWallModel *model, int direction)
{
    if (model == NULL || direction == 0)
        return false;
    if (model->tab_focused) {
        if (direction < 0)
            return false;
        model->tab_focused = false;
        model->row = MEDIA_WALL_RECENT;
        return true;
    }
    if (direction < 0 && model->row == MEDIA_WALL_RECENT) {
        model->tab = MEDIA_WALL_TAB_FILMS;
        model->tab_focused = true;
        return true;
    }
    MediaWallRow previous = model->row;
    model->row = direction < 0 ? MEDIA_WALL_RECENT : MEDIA_WALL_ALL;
    return previous != model->row;
}

bool media_wall_reset_on_back(bool target_is_media_wall, bool configured_reset)
{
    return target_is_media_wall ? false : configured_reset;
}

unsigned int media_wall_focus_progress(unsigned int elapsed_ms)
{
    if (elapsed_ms >= 180U)
        return 1000U;
    unsigned int remaining = ((180U - elapsed_ms) * 1000U) / 180U;
    uint64_t cube = (uint64_t) remaining * remaining * remaining;
    return 1000U - (unsigned int) (cube / 1000000U);
}

bool media_wall_title_and_year(const char *title, char *name, size_t capacity,
                               unsigned int *year)
{
    if (title == NULL || name == NULL || year == NULL || capacity == 0)
        return false;
    size_t len = strlen(title);
    if (len < 8 || title[len - 1] != ')' ||
        title[len - 6] != '(' || title[len - 7] != ' ')
        return false;
    unsigned int parsed = 0;
    for (size_t i = len - 5; i < len - 1; i++) {
        if (title[i] < '0' || title[i] > '9')
            return false;
        parsed = parsed * 10 + (unsigned int)(title[i] - '0');
    }
    if (parsed < 1888 || parsed > 2100)
        return false;
    size_t namelen = len - 7;
    if (namelen == 0 || namelen >= capacity)
        return false;
    memcpy(name, title, namelen);
    name[namelen] = '\0';
    *year = parsed;
    return true;
}

MediaWallSourceFormat media_wall_parse_source_format(const char *fact6)
{
    if (fact6 == NULL)
        return MEDIA_WALL_FORMAT_UNKNOWN;
    const char *prefix = "COLORIMÉTRIE ";
    const size_t prefix_len = strlen(prefix);
    if (strncmp(fact6, prefix, prefix_len) != 0)
        return MEDIA_WALL_FORMAT_UNKNOWN;
    const char *format = fact6 + prefix_len;
    if (strcmp(format, "SDR") == 0)
        return MEDIA_WALL_FORMAT_SDR;
    if (strcmp(format, "HDR10") == 0)
        return MEDIA_WALL_FORMAT_HDR10;
    if (strcmp(format, "HDR10+") == 0)
        return MEDIA_WALL_FORMAT_HDR10_PLUS;
    if (strcmp(format, "HLG") == 0)
        return MEDIA_WALL_FORMAT_HLG;
    if (strcmp(format, "Dolby Vision") == 0 ||
        strcmp(format, "Dolby Vision · Profil 7") == 0 ||
        strcmp(format, "Dolby Vision · Profil 8") == 0)
        return MEDIA_WALL_FORMAT_DOLBY_VISION;
    return MEDIA_WALL_FORMAT_UNKNOWN;
}

const char *media_wall_source_format_label(MediaWallSourceFormat format)
{
    switch (format) {
    case MEDIA_WALL_FORMAT_SDR: return "SDR";
    case MEDIA_WALL_FORMAT_HDR10: return "HDR10";
    case MEDIA_WALL_FORMAT_HDR10_PLUS: return "HDR10+";
    case MEDIA_WALL_FORMAT_HLG: return "HLG";
    case MEDIA_WALL_FORMAT_DOLBY_VISION: return "Dolby Vision";
    default: return NULL;
    }
}

/* Only literal technical fields from the CORE-generated Metadata string.
 * No HDR/Dolby Vision inference, codec guesses, network IO or side effects. */
static bool media_wall_copy_token(char *out, size_t capacity,
                                  const char *token, size_t size)
{
    if (out == NULL || token == NULL || size == 0 || size >= capacity)
        return false;
    memcpy(out, token, size);
    out[size] = '\0';
    return true;
}

bool media_wall_parse_core_metadata(const char *metadata,
                                    MediaWallTechnical *out)
{
    if (out == NULL)
        return false;
    memset(out, 0, sizeof(*out));
    if (metadata == NULL || metadata[0] == '\0')
        return false;
    const char *segment = metadata;
    bool copied_any = false;
    while (*segment != '\0') {
        const char *separator = strstr(segment, " · ");
        size_t length = separator != NULL ? (size_t)(separator - segment)
                                          : strlen(segment);
        if (length > 0 && length < 64) {
            char token[64] = {0};
            memcpy(token, segment, length);
            unsigned int w = 0, h = 0;
            char trailing = 0;
            if (out->duration[0] == '\0' && length < sizeof(out->duration) &&
                strchr(token, 'h') != NULL && token[0] >= '0' && token[0] <= '9') {
                copied_any |= media_wall_copy_token(out->duration,
                    sizeof(out->duration), token, length);
            } else if (out->container[0] == '\0' &&
                       (!strcmp(token, "MKV") || !strcmp(token, "MP4") ||
                        !strcmp(token, "AVI") || !strcmp(token, "M2TS"))) {
                copied_any |= media_wall_copy_token(out->container,
                    sizeof(out->container), token, length);
            } else if (out->video_codec[0] == '\0' &&
                       (!strcmp(token, "HEVC") || !strcmp(token, "H.264") ||
                        !strcmp(token, "AV1") || !strcmp(token, "MPEG-2") ||
                        !strcmp(token, "VC-1"))) {
                copied_any |= media_wall_copy_token(out->video_codec,
                    sizeof(out->video_codec), token, length);
            } else if (out->resolution[0] == '\0' &&
                       sscanf(token, "%u×%u%c", &w, &h, &trailing) == 2 &&
                       w >= 320 && w <= 8192 && h >= 200 && h <= 4320) {
                copied_any |= media_wall_copy_token(out->resolution,
                    sizeof(out->resolution), token, length);
            } else if (out->audio[0] == '\0' &&
                       (strstr(token, "TrueHD") || strstr(token, "DTS") ||
                        strstr(token, "AC-3") || strstr(token, "E-AC-3") ||
                        strstr(token, "AAC") || strstr(token, "FLAC") ||
                        strstr(token, "PCM") || strstr(token, "Opus"))) {
                copied_any |= media_wall_copy_token(out->audio,
                    sizeof(out->audio), token, length);
            }
        }
        if (separator == NULL)
            break;
        segment = separator + strlen(" · ");
    }
    return copied_any;
}

/* Existing appliance mappings bind all D-pad / left-stick axes to :left/:right.
 * In MediaWall only, reinterpret the physical vertical controls; the mapping
 * and all pre-existing menus stay unchanged. */
/* The poster card always has a 2:3 geometry; crop to cover it without
 * stretching the source artwork, including posters with nonstandard ratios. */
/* Geometry of the original Claude 'Médiathèque V2' visual reference.
 * At 1920x1080: nine 180x270 posters, 28px gaps, two rows with 76px
 * of breathing room instead of the previous 173px. This is purely
 * visual; the model never depends on catalogue sample counts. */
bool media_wall_controller_input_allowed(bool focus_event_state,
                                         bool actual_keyboard_focus)
{
    return focus_event_state && actual_keyboard_focus;
}

bool media_wall_controller_rearm_after_neutral(bool *needs_neutral,
                                               bool any_mapped_input_pressed)
{
    if (needs_neutral == NULL)
        return false;
    if (!*needs_neutral)
        return true;
    if (!any_mapped_input_pressed)
        *needs_neutral = false;
    /* The neutral frame itself never dispatches a command. */
    return false;
}

bool media_wall_geometry(int screen_width, int screen_height, MediaWallGeometry *out)
{
    if (out == NULL || screen_width <= 0 || screen_height <= 0)
        return false;
    int h = screen_height;
    int ph = (270 * h + 540) / 1080;
    int pw = (ph * 2) / 3;
    int gap = (28 * h + 540) / 1080;
    int margin = screen_width / 50; /* 2% safe overscan on both sides */
    if (ph < 1 || pw < 1 || gap < 1)
        return false;
    int available = screen_width - 2 * margin;
    size_t columns = available > pw
        ? (size_t) ((available + gap) / (pw + gap)) : 1;
    if (columns > 9) columns = 9;
    if (columns < 1) columns = 1;
    *out = (MediaWallGeometry) {
        .poster_w = pw, .poster_h = ph, .gap = gap,
        .recent_label_y = (205 * h) / 1080,
        .recent_poster_y = (302 * h) / 1080,
        .all_label_y = (587 * h) / 1080,
        .all_poster_y = (674 * h) / 1080,
        .footer_y = (970 * h) / 1080,
        .footer_h = h - (970 * h) / 1080,
        .status_y = (107 * h) / 1080,
        .status_h = (86 * h) / 1080,
        .viewport = columns
    };
    return true;
}

bool media_wall_cover_crop(int source_w, int source_h, int card_w, int card_h,
                           MediaWallCrop *result)
{
    if (result == NULL || source_w <= 0 || source_h <= 0 ||
        card_w <= 0 || card_h <= 0)
        return false;
    int w = source_w, h = source_h;
    int64_t width_scaled = (int64_t) source_w * card_h;
    int64_t height_scaled = (int64_t) source_h * card_w;
    if (width_scaled > height_scaled) {
        w = (int) (((int64_t) source_h * card_w) / card_h);
    } else if (width_scaled < height_scaled) {
        h = (int) (((int64_t) source_w * card_h) / card_w);
    }
    if (w < 1) w = 1;
    if (h < 1) h = 1;
    *result = (MediaWallCrop){(source_w - w) / 2, (source_h - h) / 2, w, h};
    return true;
}

bool media_wall_is_directional_control(const char *label)
{
    if (label == NULL) return false;
    const char *controls[] = {
        "ButtonDPadLeft", "ButtonDPadRight", "ButtonDPadUp", "ButtonDPadDown",
        "LStickX-", "LStickX+", "LStickY-", "LStickY+"
    };
    for (size_t i = 0; i < sizeof(controls) / sizeof(controls[0]); i++) {
        if (strcmp(label, controls[i]) == 0)
            return true;
    }
    return false;
}

unsigned int media_wall_repeat_delay_frames(unsigned int frame_ms)
{
    if (frame_ms == 0) return 2;
    unsigned int frames = 420U / frame_ms +
                          (420U % frame_ms != 0 ? 1U : 0U);
    return frames < 2 ? 2 : frames;
}

unsigned int media_wall_repeat_interval_frames(unsigned int frame_ms)
{
    if (frame_ms == 0) return 1;
    unsigned int frames = 120U / frame_ms +
                          (120U % frame_ms != 0 ? 1U : 0U);
    return frames < 1 ? 1 : frames;
}

const char *media_wall_gamepad_override(const char *label)
{
    if (label == NULL) return NULL;
    if (strcmp(label, "ButtonDPadUp") == 0 || strcmp(label, "LStickY-") == 0)
        return ":up";
    if (strcmp(label, "ButtonDPadDown") == 0 || strcmp(label, "LStickY+") == 0)
        return ":down";
    return NULL;
}

#ifndef FLEX_MEDIA_WALL_H
#define FLEX_MEDIA_WALL_H

#include <stdbool.h>
#include <stddef.h>

#define MEDIA_WALL_ROWS 2
#define MEDIA_WALL_RECENT_LIMIT 12

typedef enum {
    MEDIA_WALL_RECENT = 0,
    MEDIA_WALL_ALL = 1
} MediaWallRow;

typedef enum {
    MEDIA_WALL_TAB_FILMS = 0,
    MEDIA_WALL_TAB_SERIES = 1, /* disabled until CORE provides series */
    MEDIA_WALL_TAB_DISQUE = 2,
    MEDIA_WALL_TAB_DOSSIERS = 3
} MediaWallTab;

typedef struct {
    size_t count;
    size_t recent_count;
    size_t viewport;
    size_t selected[MEDIA_WALL_ROWS];
    size_t scroll[MEDIA_WALL_ROWS];
    size_t *az_order;
    MediaWallRow row;
    bool tab_focused;
    MediaWallTab tab;
} MediaWallModel;

bool media_wall_init(MediaWallModel *model, const char *const *titles,
                     size_t count, size_t viewport);
void media_wall_destroy(MediaWallModel *model);
bool media_wall_move_horizontal(MediaWallModel *model, int direction);
bool media_wall_move_vertical(MediaWallModel *model, int direction);
const char *media_wall_tab_target(MediaWallTab tab);
bool media_wall_tab_selectable(MediaWallTab tab);
size_t media_wall_row_count(const MediaWallModel *model, MediaWallRow row);
size_t media_wall_manifest_index(const MediaWallModel *model,
                                 MediaWallRow row, size_t position);
size_t media_wall_current_manifest_index(const MediaWallModel *model);
bool media_wall_reset_on_back(bool target_is_media_wall, bool configured_reset);
/* 180 ms ease-out cubic in thousandths, for SDL-native focus animation. */
unsigned int media_wall_focus_progress(unsigned int elapsed_ms);
/* Read a trailing '(YYYY)' suffix only; never infer metadata from filenames. */
bool media_wall_title_and_year(const char *title, char *name, size_t name_capacity,
                               unsigned int *year);

/* Format advertised by the source metadata, not the actual playback output. */
typedef enum {
    MEDIA_WALL_FORMAT_UNKNOWN = 0,
    MEDIA_WALL_FORMAT_SDR,
    MEDIA_WALL_FORMAT_HDR10,
    MEDIA_WALL_FORMAT_HDR10_PLUS,
    MEDIA_WALL_FORMAT_HLG,
    MEDIA_WALL_FORMAT_DOLBY_VISION
} MediaWallSourceFormat;
MediaWallSourceFormat media_wall_parse_source_format(const char *core_fact6);
const char *media_wall_source_format_label(MediaWallSourceFormat format);

/* Strictly display-only: formatted tokens copied from the existing
 * CORE MovieDetail.Metadata string, never inferred from the poster. */
typedef struct {
    char duration[24];
    char container[16];
    char video_codec[24];
    char resolution[28];
    char audio[48];
    MediaWallSourceFormat source_format;
} MediaWallTechnical;
bool media_wall_parse_core_metadata(const char *metadata,
                                    MediaWallTechnical *out);
/* Return a wall-only command for the existing vertical gamepad inputs. */
const char *media_wall_gamepad_override(const char *label);
/* Directional repeats are deliberately slower in the poster wall only.
 * Immediate first presses and every non-wall menu keep CORE behavior. */
bool media_wall_is_directional_control(const char *label);
unsigned int media_wall_repeat_delay_frames(unsigned int frame_ms);
unsigned int media_wall_repeat_interval_frames(unsigned int frame_ms);

typedef struct {
    int poster_w, poster_h, gap;
    int recent_label_y, recent_poster_y;
    int all_label_y, all_poster_y;
    int footer_y, footer_h, status_y, status_h;
    size_t viewport;
} MediaWallGeometry;
bool media_wall_geometry(int screen_width, int screen_height, MediaWallGeometry *out);

/* Fail closed when an SDL instance is not the active Wayland window.
 * Independent of which menu is visible or whether playback is tracked. */
bool media_wall_controller_input_allowed(bool focus_event_state,
                                         bool actual_keyboard_focus);
/* After focus returns, require all mapped buttons/axes to be neutral for
 * at least one polling frame before allowing any command. */
bool media_wall_controller_rearm_after_neutral(bool *needs_neutral,
                                               bool any_mapped_input_pressed);

typedef struct { int x, y, w, h; } MediaWallCrop;
bool media_wall_cover_crop(int source_w, int source_h, int card_w, int card_h,
                           MediaWallCrop *result);

#endif

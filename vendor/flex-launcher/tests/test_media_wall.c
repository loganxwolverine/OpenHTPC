#include "media_wall.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static void test_order_and_recent_limit(void)
{
    const char *titles[] = {
        "Zulu", "alpha", "Echo", "Bravo", "delta", "Charlie",
        "Hotel", "Golf", "Foxtrot", "India", "Juliet", "Kilo", "Lima"
    };
    MediaWallModel model;
    assert(media_wall_init(&model, titles, 13, 5));
    assert(model.recent_count == 12);
    assert(media_wall_manifest_index(&model, MEDIA_WALL_RECENT, 0) == 0);
    assert(media_wall_manifest_index(&model, MEDIA_WALL_RECENT, 11) == 11);
    assert(media_wall_manifest_index(&model, MEDIA_WALL_ALL, 0) == 1);
    assert(media_wall_manifest_index(&model, MEDIA_WALL_ALL, 1) == 3);
    assert(media_wall_manifest_index(&model, MEDIA_WALL_ALL, 12) == 0);
    media_wall_destroy(&model);
}

static void test_bounds_scroll_and_row_memory(void)
{
    const char *titles[] = {"A", "B", "C", "D", "E", "F", "G", "H"};
    MediaWallModel model;
    assert(media_wall_init(&model, titles, 8, 3));
    assert(!media_wall_move_horizontal(&model, -1));
    for (int i = 0; i < 7; i++) assert(media_wall_move_horizontal(&model, 1));
    assert(model.selected[MEDIA_WALL_RECENT] == 7);
    assert(model.scroll[MEDIA_WALL_RECENT] == 5);
    assert(!media_wall_move_horizontal(&model, 1));

    assert(media_wall_move_vertical(&model, 1));
    assert(model.row == MEDIA_WALL_ALL);
    assert(media_wall_move_horizontal(&model, 1));
    assert(model.selected[MEDIA_WALL_ALL] == 1);
    assert(media_wall_move_vertical(&model, -1));
    assert(model.selected[MEDIA_WALL_RECENT] == 7);
    assert(model.scroll[MEDIA_WALL_RECENT] == 5);
    assert(media_wall_move_vertical(&model, 1));
    assert(model.selected[MEDIA_WALL_ALL] == 1);
    media_wall_destroy(&model);
}

static void test_header_controller_navigation(void)
{
    const char *titles[] = {"A", "B", "C", "D"};
    MediaWallModel model;
    assert(media_wall_init(&model, titles, 4, 3));
    assert(!model.tab_focused);
    assert(media_wall_move_horizontal(&model, 1));
    assert(model.selected[MEDIA_WALL_RECENT] == 1);
    assert(media_wall_move_vertical(&model, -1));
    assert(model.tab_focused && model.tab == MEDIA_WALL_TAB_FILMS);
    assert(media_wall_move_horizontal(&model, 1));
    assert(model.tab == MEDIA_WALL_TAB_DISQUE);
    assert(strcmp(media_wall_tab_target(model.tab), "DISQUE") == 0);
    assert(media_wall_move_horizontal(&model, 1));
    assert(model.tab == MEDIA_WALL_TAB_DOSSIERS);
    assert(strcmp(media_wall_tab_target(model.tab), "MEDIA_ROOT") == 0);
    assert(!media_wall_move_horizontal(&model, 1));
    assert(media_wall_move_horizontal(&model, -1));
    assert(model.tab == MEDIA_WALL_TAB_DISQUE);
    assert(media_wall_move_horizontal(&model, -1));
    assert(model.tab == MEDIA_WALL_TAB_FILMS);
    assert(!media_wall_move_horizontal(&model, -1));
    assert(!media_wall_tab_selectable(MEDIA_WALL_TAB_SERIES));
    assert(media_wall_tab_target(MEDIA_WALL_TAB_SERIES) == NULL);
    assert(media_wall_move_vertical(&model, 1));
    assert(!model.tab_focused && model.row == MEDIA_WALL_RECENT);
    assert(model.selected[MEDIA_WALL_RECENT] == 1);
    assert(media_wall_move_vertical(&model, -1)); /* up to tabs */
    assert(model.tab_focused);
    media_wall_destroy(&model);
}

static void test_selection_is_index_only(void)
{
    const char *titles[] = {"C", "A", "B"};
    MediaWallModel model;
    assert(media_wall_init(&model, titles, 3, 2));
    assert(media_wall_move_vertical(&model, 1));
    assert(media_wall_current_manifest_index(&model) == 1);
    assert(media_wall_move_horizontal(&model, 1));
    assert(media_wall_current_manifest_index(&model) == 2);
    /* The model exposes an index; it owns no command execution path. */
    media_wall_destroy(&model);
}

static void test_claude_reference_geometry(void)
{
    MediaWallGeometry g;
    assert(media_wall_geometry(1920, 1080, &g));
    assert(g.poster_w == 180 && g.poster_h == 270);
    assert(g.gap == 28 && g.viewport == 9);
    assert(g.recent_poster_y == 302 && g.all_poster_y == 674);
    assert(g.all_poster_y - g.recent_poster_y == 372);
    assert(g.all_label_y > g.recent_poster_y + g.poster_h);
    /* Footer and enlarged focus leave room for the label. */
    assert(g.all_poster_y - (g.poster_h * 14 / 100) -
           (g.poster_h * 16 / 270) >= g.all_label_y + 27);
    assert(g.footer_y >= g.all_poster_y + g.poster_h + 20);
    assert(media_wall_geometry(3840, 2160, &g));
    assert(g.poster_w == 360 && g.poster_h == 540 && g.viewport == 9);
    assert(!media_wall_geometry(0, 1080, &g));
}

static void test_focus_animation_180ms(void)
{
    assert(media_wall_focus_progress(0) == 0);
    assert(media_wall_focus_progress(180) == 1000);
    assert(media_wall_focus_progress(1000) == 1000);
    assert(media_wall_focus_progress(90) >= 860);
    unsigned int prior = 0;
    for (unsigned int ms = 1; ms <= 180; ms++) {
        unsigned int current = media_wall_focus_progress(ms);
        assert(current >= prior && current <= 1000);
        prior = current;
    }
}

static void test_footer_uses_only_grounded_title_year(void)
{
    char title[128];
    unsigned int year = 0;
    assert(media_wall_title_and_year("(500) jours ensemble (2009)",
                                      title, sizeof(title), &year));
    assert(strcmp(title, "(500) jours ensemble") == 0 && year == 2009);
    assert(media_wall_title_and_year("Alien : Romulus (2024)",
                                      title, sizeof(title), &year));
    assert(strcmp(title, "Alien : Romulus") == 0 && year == 2024);
    assert(!media_wall_title_and_year("Années 2000 : la suite",
                                       title, sizeof(title), &year));
    assert(!media_wall_title_and_year("Film (2101)", title, sizeof(title), &year));
    assert(!media_wall_title_and_year("Film (2024)", title, 3, &year));
}

static void test_wall_directional_repeat_timing(void)
{
    assert(media_wall_is_directional_control("ButtonDPadRight"));
    assert(media_wall_is_directional_control("ButtonDPadUp"));
    assert(media_wall_is_directional_control("LStickY-"));
    assert(media_wall_is_directional_control("LStickX+"));
    assert(!media_wall_is_directional_control("ButtonA"));
    assert(!media_wall_is_directional_control("ButtonB"));
    assert(!media_wall_is_directional_control(NULL));
    assert(media_wall_repeat_delay_frames(16) == 27);
    assert(media_wall_repeat_interval_frames(16) == 8);
    assert(media_wall_repeat_delay_frames(33) == 13);
    assert(media_wall_repeat_interval_frames(33) == 4);
    assert(media_wall_repeat_delay_frames(0) >= 2);
    assert(media_wall_repeat_interval_frames(0) >= 1);
    assert(media_wall_repeat_delay_frames(1000) >= 2);
    assert(media_wall_repeat_interval_frames(1000) >= 1);
}

static void test_controller_focus_neutral_rearming(void)
{
    bool needs_neutral = true;
    assert(!media_wall_controller_rearm_after_neutral(NULL, false));
    assert(!media_wall_controller_rearm_after_neutral(&needs_neutral, true));
    assert(needs_neutral);
    assert(!media_wall_controller_rearm_after_neutral(&needs_neutral, true));
    assert(needs_neutral);
    assert(!media_wall_controller_rearm_after_neutral(&needs_neutral, false));
    assert(!needs_neutral);
    assert(media_wall_controller_rearm_after_neutral(&needs_neutral, false));
    assert(media_wall_controller_rearm_after_neutral(&needs_neutral, true));
    /* A new focus handoff requires another full neutral cycle. */
    needs_neutral = true;
    assert(!media_wall_controller_rearm_after_neutral(&needs_neutral, true));
    assert(!media_wall_controller_rearm_after_neutral(&needs_neutral, false));
    assert(media_wall_controller_rearm_after_neutral(&needs_neutral, true));
}

static void test_controller_focus_gate(void)
{
    /* Do not consume input on a defocused window, even if a stale
     * window-event flag or a stale SDL focus handle says otherwise. */
    assert(!media_wall_controller_input_allowed(false, false));
    assert(!media_wall_controller_input_allowed(false, true));
    assert(!media_wall_controller_input_allowed(true, false));
    assert(media_wall_controller_input_allowed(true, true));
}

static void test_core_source_colorimetry(void)
{
    assert(media_wall_parse_source_format("COLORIMÉTRIE SDR") ==
           MEDIA_WALL_FORMAT_SDR);
    assert(media_wall_parse_source_format("COLORIMÉTRIE HDR10") ==
           MEDIA_WALL_FORMAT_HDR10);
    assert(media_wall_parse_source_format("COLORIMÉTRIE HDR10+") ==
           MEDIA_WALL_FORMAT_HDR10_PLUS);
    assert(media_wall_parse_source_format("COLORIMÉTRIE HLG") ==
           MEDIA_WALL_FORMAT_HLG);
    assert(media_wall_parse_source_format(
        "COLORIMÉTRIE Dolby Vision · Profil 7") ==
           MEDIA_WALL_FORMAT_DOLBY_VISION);
    assert(media_wall_parse_source_format(
        "COLORIMÉTRIE Dolby Vision · Profil 8") ==
           MEDIA_WALL_FORMAT_DOLBY_VISION);
    assert(media_wall_parse_source_format(
        "COLORIMÉTRIE Indéterminée") == MEDIA_WALL_FORMAT_UNKNOWN);
    assert(media_wall_parse_source_format(
        "COLORIMÉTRIE Dolby Vision · Profil 6") ==
           MEDIA_WALL_FORMAT_UNKNOWN);
    assert(media_wall_parse_source_format("Dolby Vision") ==
           MEDIA_WALL_FORMAT_UNKNOWN);
    assert(media_wall_parse_source_format("COLORIMÉTRIE SDR_HDR10") ==
           MEDIA_WALL_FORMAT_UNKNOWN);
    assert(media_wall_parse_source_format(NULL) ==
           MEDIA_WALL_FORMAT_UNKNOWN);
    assert(media_wall_source_format_label(MEDIA_WALL_FORMAT_UNKNOWN) == NULL);
    assert(strcmp(media_wall_source_format_label(MEDIA_WALL_FORMAT_DOLBY_VISION),
                  "Dolby Vision") == 0);
    assert(strcmp(media_wall_source_format_label(MEDIA_WALL_FORMAT_HDR10_PLUS),
                  "HDR10+") == 0);
}

static void test_core_metadata_badges(void)
{
    MediaWallTechnical result;
    const char *core_sample =
        "2019 · 2 h 49 · MKV · HEVC · 3840×2160 · 23.976 fps · "
        "TrueHD 7.1 · Audio EN/FR · ST EN/FR";
    assert(media_wall_parse_core_metadata(core_sample, &result));
    assert(strcmp(result.duration, "2 h 49") == 0);
    assert(strcmp(result.container, "MKV") == 0);
    assert(strcmp(result.video_codec, "HEVC") == 0);
    assert(strcmp(result.resolution, "3840×2160") == 0);
    assert(strcmp(result.audio, "TrueHD 7.1") == 0);
    assert(media_wall_parse_core_metadata(
        "2020 · MP4 · H.264 · 1920×1080 · AC-3 5.1", &result));
    assert(strcmp(result.video_codec, "H.264") == 0);
    assert(strcmp(result.resolution, "1920×1080") == 0);
    assert(strcmp(result.audio, "AC-3 5.1") == 0);
    assert(!media_wall_parse_core_metadata(NULL, &result));
    assert(!media_wall_parse_core_metadata("", &result));
    assert(!media_wall_parse_core_metadata("GENRES Comédie", &result));
    assert(!media_wall_parse_core_metadata("HEVC", NULL));
    assert(media_wall_parse_core_metadata("HEVC", &result));
    assert(result.resolution[0] == '\0');
    assert(result.audio[0] == '\0');
}

static void test_poster_cover_crop(void)
{
    MediaWallCrop crop;
    assert(media_wall_cover_crop(500, 750, 200, 300, &crop));
    assert(crop.x == 0 && crop.y == 0 && crop.w == 500 && crop.h == 750);
    assert(media_wall_cover_crop(500, 707, 200, 300, &crop));
    assert(crop.w >= 470 && crop.w <= 472 && crop.x > 0 && crop.h == 707);
    assert(media_wall_cover_crop(500, 800, 200, 300, &crop));
    assert(crop.w == 500 && crop.h == 750 && crop.y == 25);
    assert(!media_wall_cover_crop(0, 750, 200, 300, &crop));
}

static void test_media_wall_gamepad_mapping(void)
{
    assert(media_wall_gamepad_override(NULL) == NULL);
    assert(media_wall_gamepad_override("ButtonDPadLeft") == NULL);
    assert(media_wall_gamepad_override("LStickX+") == NULL);
    assert(media_wall_gamepad_override("ButtonDPadUp") != NULL);
    assert(media_wall_gamepad_override("ButtonDPadDown") != NULL);
    assert(media_wall_gamepad_override("LStickY-") != NULL);
    assert(media_wall_gamepad_override("LStickY+") != NULL);
    assert(media_wall_gamepad_override("ButtonDPadUp")[1] == 'u');
    assert(media_wall_gamepad_override("LStickY+")[1] == 'd');
}

static void test_back_policy_preserves_wall_state(void)
{
    assert(!media_wall_reset_on_back(true, true));
    assert(!media_wall_reset_on_back(true, false));
    assert(media_wall_reset_on_back(false, true));
    assert(!media_wall_reset_on_back(false, false));
}

int main(void)
{
    test_order_and_recent_limit();
    test_bounds_scroll_and_row_memory();
    test_header_controller_navigation();
    test_selection_is_index_only();
    test_back_policy_preserves_wall_state();
    test_media_wall_gamepad_mapping();
    test_poster_cover_crop();
    test_claude_reference_geometry();
    test_focus_animation_180ms();
    test_footer_uses_only_grounded_title_year();
    test_core_metadata_badges();
    test_core_source_colorimetry();
    test_controller_focus_gate();
    test_controller_focus_neutral_rearming();
    test_wall_directional_repeat_timing();
    puts("media-wall-model: all assertions passed");
    return 0;
}

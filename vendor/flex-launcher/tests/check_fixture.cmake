file(READ "${FIXTURE}" fixture)

if (NOT fixture MATCHES "\\[MEDIA_WALL_TEST\\][^[]*Layout=MediaWall")
  message(FATAL_ERROR "fixture has no explicit MediaWall section")
endif ()

string(REGEX MATCHALL ":submenu MEDIA_D_[0-9]+" detail_entries "${fixture}")
list(LENGTH detail_entries detail_count)
if (NOT detail_count EQUAL 13)
  message(FATAL_ERROR "expected 13 harmless detail submenu entries, got ${detail_count}")
endif ()

string(TOLOWER "${fixture}" fixture_lower)
if (fixture_lower MATCHES "(^|[^a-z])(mpv|:tracked|:fork)([^a-z]|$)")
  message(FATAL_ERROR "fixture contains a direct/external action")
endif ()

message(STATUS "fixture contract: explicit layout, 13 detail submenus, no direct action")

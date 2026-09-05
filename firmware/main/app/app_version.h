#pragma once

/* Bump KOLONKA_BUILD (and firmware/BUILDNUM) on every flashed image.
 * Bump KOLONKA_VERSION_* / firmware/VERSION when cutting a release.
 * Do not use firmware/BUILD — on Windows it collides with the build/ dir. */

#define KOLONKA_VERSION_MAJOR 0
#define KOLONKA_VERSION_MINOR 1
#define KOLONKA_VERSION_PATCH 1
#define KOLONKA_BUILD 4

#define KOLONKA_VERSION_STR "0.1.1"

#define KOLONKA_STRINGIFY_(x) #x
#define KOLONKA_STRINGIFY(x) KOLONKA_STRINGIFY_(x)
#define KOLONKA_VERSION_FULL "0.1.1+" KOLONKA_STRINGIFY(KOLONKA_BUILD)

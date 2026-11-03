#ifndef GUARD_SAVE_LAYOUT_H
#define GUARD_SAVE_LAYOUT_H

// Maritimes: the save layout version.
//
// Every save is stamped with SAVE_LAYOUT_STAMP (SaveBlock2.saveLayoutVersion, at a fixed offset
// among vanilla fields). A save stamped with anything else was written with another layout and
// would load as garbage (shifted flags and vars, a wrong party), so the game refuses it: the main
// menu says so and offers only NEW GAME (src/save.c LoadGameSave, src/main_menu.c).
//
// The numbers below describe the layout of this version; src/save.c asserts each one at build
// time. If the build stops with "SaveLayoutChanged_...", the save layout changed (a flag or
// trainer range was raised, a SaveBlock field added, an expansion config changed a block's size):
//   python dev/save_layout.py --update      (re-measures, rewrites these numbers, bumps the version)
// then rebuild and run dev/tests/ingame_save.py. Old saves stop loading, with the message.
#define SAVE_LAYOUT_VERSION 1
#define SAVE_LAYOUT_STAMP   (0x4D00 + SAVE_LAYOUT_VERSION)  // 'M' high byte: never 0 or 0xFFFF (erased flash)

// ---- measured by dev/save_layout.py; don't edit by hand ----
#define SAVE_LAYOUT_SAVEBLOCK1_SIZE   15660
#define SAVE_LAYOUT_SAVEBLOCK2_SIZE   3884
#define SAVE_LAYOUT_SAVEBLOCK3_SIZE   4
#define SAVE_LAYOUT_STORAGE_SIZE      34144
#define SAVE_LAYOUT_FLAGS_OFFSET      4720
#define SAVE_LAYOUT_VARS_OFFSET       5116
#define SAVE_LAYOUT_FLAGS_BYTES       396
#define SAVE_LAYOUT_VARS_COUNT        256
// ---- end of measured numbers ----

#endif // GUARD_SAVE_LAYOUT_H

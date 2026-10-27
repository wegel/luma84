# Modified 2026-10-27: Compile the QMK body-light driver adapter.
SRC += rgb_record/rgb_record.c

ifeq ($(strip $(RGBLIGHT_ENABLE)), yes)
	SRC += rgb_record/rgb_rgblight.c
	SRC += rgb_record/rgb_effect.c
	SRC += rgb_record/rgblight_driver_compat.c
endif

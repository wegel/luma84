# Personal lights

Branch `personal/wegel` keeps two backlight modes: solid color and solid color
with a ripple. The ripple expands from each pressed key into the surrounding
keys, then fades back to the background. It uses white rings on darker colors
and dark rings on lighter colors so it remains visible with the white preset.
QMK remembers up to eight recent presses, so several ripples can overlap.

The four LEDs on the body keep the same steady background color. The vendor's
Caps Lock, connection, pairing, and battery indicators can still show status.
The initial color is warm white, in solid mode.

## Controls

The Windows and Mac Fn layers use the same light controls:

- **Fn + Backspace:** turn all backlights on or off.
- **Fn + Backslash** or **Fn + Insert:** switch between solid and ripple.
- **Fn + L / Comma:** increase / decrease red.
- **Fn + Semicolon / Period:** increase / decrease green.
- **Fn + Quote / Slash:** increase / decrease blue.
- **Fn + Up / Down:** increase / decrease overall brightness.
- **Fn + Left / Right:** slower / faster ripples.
- **Fn + Enter:** select the next preset.

Each color channel runs from 0 to 255. Each press changes it by 17; hold
**Left Shift** as well for steps of 1. Holding a channel key starts repeating
after 350 ms. Overall brightness scales all three channels together and retains
the vendor's limit of 120. A ripple never exceeds that selected brightness.

## Presets

Hold Fn and press a digit:

- **1:** red `(255, 0, 0)`.
- **2:** orange `(255, 85, 0)`.
- **3:** yellow `(255, 255, 0)`.
- **4:** green `(0, 255, 0)`.
- **5:** cyan `(0, 255, 255)`.
- **6:** blue `(0, 0, 255)`.
- **7:** violet `(128, 0, 255)`.
- **8:** pink `(255, 0, 128)`.
- **9:** warm white `(255, 180, 100)`.
- **0:** white `(255, 255, 255)`.

The digits select presets. Bluetooth profiles remain on **Fn + Q / W / E**.
The existing **Fn + R** shortcut selects 2.4 GHz. **Fn + I** is Scroll Lock
and **Fn + O** is Pause.

## Saved color and mode

The keyboard saves the RGB channels and mode 500 ms after the last change.
Wait a second before unplugging if you want to keep a new color. A channel stops
at 0 or 255 rather than wrapping around. Color and mode controls preserve the
master light switch, including when it is off.

The personal code reuses eight of the vendor's sixteen per-effect color bytes
in external SPI flash. It leaves the keymap and other settings at their existing
addresses. A version marker identifies the personal bytes; factory resets choose
warm white and solid mode. Entering the vendor bootloader can reset settings,
including these preferences.

For VIA, load [this branch's definition](../keyboard/Epomaker%20Luma84.json).
It lists the two effects and matches the compiled custom keycodes. Use the
keyboard shortcuts for exact RGB channels; the old HSV color picker is removed.

## Checks

`tools/test_personal_rgb.py` executes the compiled ARM code in an emulator. It
checks the Fn maps, presets, independent channel limits, fine steps, held keys,
saved preferences, two-mode cycle, body lights, outward ripple, visible ripple
on white, brightness limits, and disabled-light behavior. It substitutes time,
SPI settings reads/writes, and the LED output, so it does not access a keyboard.
The existing wake checks also run in CI.

On October 28, 2026, the owner flashed this personal build and reported that it
works well on their Luma84. They did not provide a list of individual feature
tests, connection modes, or test duration.

# Luma84 firmware

Build EPOMAKER's published Luma84 source with a pinned QMK revision and a
documented ARM compiler. This repository keeps the board code, shared wireless
code, build changes, and firmware fixes.

EPOMAKER already publishes the [original board source](https://github.com/Epomaker/luma84).
This project adds a working build script, exact source revisions, and documented
changes needed to compile the vendor code. Nobody has tested this repository's
compiled firmware on a keyboard yet.

The wake hooks now honor the saved master light switch. See
[the source changes and test results](docs/build-changes.md) for details.

## Build on Linux x86_64

Install Python 3.11 or newer, Git, GNU Make, and [uv](https://docs.astral.sh/uv/). Run:

```sh
python3 tools/build.py
```

The script downloads and verifies ARM GCC 13.2.1, fetches QMK 0.28.0 and four
pinned submodules, creates a private Python 3.11 environment, applies the QMK
patch, and compiles `epomaker/hc844:via`. It writes ELF, HEX, BIN, and a JSON
report with source and output hashes under `dist/`. It never opens or flashes
a USB device. `work/` holds the generated checkout and tools.

To use an existing ARM GCC 13.2.1 install:

```sh
python3 tools/build.py --toolchain /path/to/arm-gcc
```

The compiler check establishes that the code compiles. It does not establish
that wired mode, Bluetooth, 2.4 GHz wireless, sleep, or lights behave correctly
on a physical keyboard. The local binary differs from EPOMAKER's published
factory image. Do not describe it as an unchanged factory build.

After building, run the wake checks with:

```sh
uv run --no-project --with unicorn==2.1.2 --with setuptools==75.8.2 python tools/test_wake.py
```

The checks execute both wake hooks from the compiled ELF in a Cortex-M emulator.
They check the master switch, body-light flag, brightness, initial LED power,
and initial key-light state. They replace radio, clock, and host callbacks with
test substitutes and do not access a keyboard.

## Read the code

- `keyboard/hc844.c` handles keys, lights, battery indicators, and wake events.
- `keyboard/wls/` handles the mode switch and sleep timer.
- `keyboard/rgb_record/` handles stored light patterns and the four body lights.
- `wireless/` handles messages between the main chip and the separate radio chip.
- `sources.lock.json` records the vendor, QMK, submodule, and compiler revisions.
- [Build changes](docs/build-changes.md) explains every change from the vendor files.

The vendor names this board `hc844`; the product name is Luma84. The source
targets a WB32FQ95 main chip. It includes the main chip's wireless-control code,
not the separate radio chip's own firmware.

## Contribute

For build reports, include the repository commit, host operating system,
compiler version, and relevant compiler output. For hardware reports, include
the keyboard's hardware revision if known, USB release field, connection mode,
firmware commit, and steps that let someone else repeat the test.

Record whether a bootloader visit may have reset settings. EPOMAKER's published
handler calls `eeconfig_disable()` before jumping to the bootloader. The main
chip's firmware dump does not include preferences stored in external SPI flash.

Keep device dumps and private logs outside this repository. `.gitignore` excludes
build outputs, binary dumps, local tools, and evidence directories. Link small,
reproducible source fixes to EPOMAKER's repository or the
[existing community QMK fork](https://github.com/carlosedp/qmk_firmware) when they
fit there.

The board and shared source retain their original copyright and license notices.
Project additions use GPL-2.0-or-later; see [LICENSE](LICENSE).

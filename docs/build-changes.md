# Changes from EPOMAKER's source

EPOMAKER published the board at commit
`3753140abcc9ba7c8cca04721f0e1400b82ff9fe`. The vendor README gives the target
`epomaker/hc844:default`, but it does not identify the QMK base or compiler used
for its factory HEX file. This project uses the VIA keymap and the revisions in
`sources.lock.json`.

The compiler needed these changes:

- `keyboard/config.h` adds the QMK names for the vendor's existing serial
  connection: SD3, transmit pin C10, receive pin C11, and alternate function 7.
  The vendor already declares the same serial peripheral and pins under older
  names. This change supplies the names used by QMK and the sleep code.
- `wireless/transport.c` calls
  `usb_device_state_set_protocol(USB_PROTOCOL_REPORT)` instead of writing the
  removed `keyboard_protocol` global.
- `keyboard/rgb_record/rgblight_driver_compat.c` supplies QMK 0.28's custom driver
  interface. It writes the vendor's body-light buffer. The main RGB matrix code
  still copies that buffer into the LED chain, so the adapter does not send a
  second hardware frame.
- `keyboard/rgb_record/rgb_record.mk` compiles that adapter.
- `patches/qmk-rgblight-overrides.patch` lets the vendor's `rgblight_set`, breathing,
  and rainbow-mood functions override QMK's defaults. It marks the three core
  functions weak, which tells the linker to use the vendor's definitions when
  both exist.

QMK 0.28 was chosen because it supplies the APIs used by the board and keeps
the VIA send call at line 461. The vendor's `wireless/md_raw.h` intercepts that
call using a line-number macro. Moving to another QMK revision requires checking
that macro, even if the compiler accepts the code.

These changes make a local build possible. We have not proved that they
reproduce the original vendor build or preserve every hardware behavior.
The original keymaps, light flags, and sleep rules remain in the source.

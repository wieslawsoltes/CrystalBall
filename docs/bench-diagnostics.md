# Offline first-article bench diagnostics

The `factory-diagnostics` ESP32-S3 profile runs the real display, LED and audio drivers without loading device credentials, initializing the application network, or contacting any gateway. It is **bench-only engineering firmware, not customer firmware or a manufacturing acceptance pass**. Existing automatic release gates remain blocked pending independently reviewed physical evidence.

## Power and programming boundary

Disconnect carrier power and **remove the DevKit from both carrier sockets before connecting either DevKit USB connector**. Do not attempt in-circuit USB programming or dual-power the controller. Program the removed development board, disconnect its USB cable, reinstall with the marked orientation and only then power the carrier from the reviewed 5 V source. Use the already defined current-limited first-power procedure. Do not attach a UART fixture to an unknown or powered interface. This mode deliberately needs no host serial connection while installed.

The image is for ESP32-S3-DevKitC-1-N8R8 and the Rev B module wiring. It does not burn eFuses, encrypt NVS, sign production firmware, override secure boot, or establish hardware safety. Do not use an unsigned bench image on a controller already enrolled in an irreversible production security policy. Never use a power adapter or PD jumper configuration that could deliver more than the specified input voltage.

## Build without a gateway certificate

Use ESP-IDF 5.5.2 and a clean, isolated build/config directory. From `firmware/`:

```bash
. "$IDF_PATH/export.sh"
idf.py -B build-diagnostics \
  -D SDKCONFIG="$PWD/build-diagnostics/sdkconfig" \
  -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.diagnostics" \
  -D IDF_TARGET=esp32s3 build
```

No `main/gateway_ca.pem` is required for this profile. `CONFIG_ORB_FACTORY_DIAGNOSTICS=y` selects a separate `factory_main.c`, excluding `app_main.c`, `network.c`, `config.c` and the CA embedding from the application. Framework dependency discovery remains unconditional because ESP-IDF expands component requirements before Kconfig values are available. Link-time checks inspect the actual ELF for absence of the application network/configuration functions and `esp_wifi_start`; this is not a claim that the SDK dependency graph contains no Wi-Fi components.

Review the generated `flasher_args.json` and all image addresses before using the standard IDF flash command, with the board physically removed as above. Do not invoke `erase-flash`: bench programming should not intentionally erase a separately provisioned NVS partition. The diagnostic application never reads that NVS content, but leaving it present does not provide confidentiality. Reinstall the intended application and requalify its provisioning before returning a board to use.

The CI bench artifact contains only the bootloader, partition table and diagnostic application, with exact addresses, a source commit and SHA-256 hashes. It contains **no NVS image, API key, gateway token, Wi-Fi password or CA**. Verify the artifact provenance and hashes before use. The hashes detect mismatched files; they do not replace a firmware-signing policy or physical inspection.

## Local controls and ten pages

Release both buttons after boot. **PAGE** advances one page per debounced press. **TALK** activates the selected LED, tone or microphone test. A held button at boot cannot trigger sound. Releasing and pressing again is required to repeat an action; none of the tests auto-repeat.

| Page | Operation | Required human observation |
|---|---|---|
| Help | Instructions; microphone and amplifier off | Correct boot/profile, legible text |
| Optical grid | Existing asymmetric orientation/calibration chart | Teller orientation, readable viewing zone, client-side leakage |
| Black | Exact RGB565 zero field, decorative pixels off | Leakage, lit/stuck pixels, ambient reflections |
| White | Exact RGB565 `0xffff`, no overlay text | Uniformity, dark/stuck pixels, optical contamination |
| Color bars | Eight vertical 40-pixel RGB565 bars | RGB/BGR assignment, column order, uniform color |
| Checker | Eight-pixel black/white cells | Pixel addressing, edge sharpness, interference patterns |
| Gray ramp | 32 horizontal intensity steps | Clipping, banding and contrast |
| Pixel walk | TALK advances one of 16 pixels in red, green then blue | Correct physical index, GRB wiring and missing/swapped pixels |
| Test tone | Hold TALK; release cancels | Speaker path, buzz/rattle, qualified acoustic measurements |
| Microphone | Hold TALK to capture; release displays statistics | Record indicator, usable signal and clipping with controlled stimulus |

Flat fields deliberately have no labels that would invalidate a uniformity/black-level test. The physical LCD's configured optical mirror transform still applies. PAGE extinguishes the pixel walk before leaving it. Driver success only means the driver accepted/completed the operation; the firmware has no optical or acoustic feedback sensor that could confirm a visible or audible pass.

The pixel walk uses one active channel at 12/255, further bounded by the global 32/255-per-channel driver cap. It is not a full-brightness power/thermal test. The 1 kHz tone is synthesized from a 24-sample table at nominal 24 kHz, with a peak digital amplitude of 2048/32768 and 10 ms start/end ramps. At most 24,000 tone frames are queued; the driver loop also checks a one-second monotonic deadline. Cancellation is checked at bounded write boundaries (100 ms write timeout), not by an independent hardware safety interrupt. Keep the speaker away from ears. Actual frequency, sound pressure, latency and amplifier startup behavior require instruments; none are certified by the digital sample values.

Microphone capture uses the same selected channel, configured sample shift, settling interval and high-pass processing as the application. The result shows sample count, integer RMS including residual DC, absolute peak, signed mean, rail-clipped sample count, zero crossings and free internal heap. These are **post-processing digital counts**, not raw converter values, dB SPL or calibrated microphone sensitivity. A zero clipping count cannot prove that the analog microphone or earlier digital stages did not saturate. The maximum retained sample count is 128,000 (eight seconds at 16 kHz), plus the driver's initial settling interval. Silence and malformed/short capture never become automatic passes. Captured WAV and scratch statistics are wiped and freed after display; no audio is saved or transmitted by this mode.

## Evidence, qualification and remaining scope

Record the exact source/artifact hash, unit serial, component lots, test setup, environment, instrument IDs, calibration status, uncertainty and observation in the existing first-article records. Use a controlled acoustic stimulus rather than customer speech. Do not store sensitive microphone recordings in repository artifacts. The factory first-article evaluator and externally authenticated release-evidence tooling remain the acceptance mechanisms; this diagnostic image only makes measurements and observations possible.

Host C tests exercise exact color pixels, bounds/canaries, PCM sign extension, RMS/peak/clipping arithmetic, and tone frequency/envelope using AddressSanitizer/UndefinedBehaviorSanitizer. CI additionally compiles the real ESP32-S3 diagnostic target without a CA and checks the linked symbol/flash-image contract. These checks do not establish actual display SPI timing, microphone I2S alignment, power integrity, optics, EMC, acoustic output, or first-article acceptance.

References reviewed 2026-09-16:
- ESP-IDF 5.5.2 build system: https://docs.espressif.com/projects/esp-idf/en/v5.5.2/esp32s3/api-guides/build-system.html
- ESP-IDF 5.5.2 I2S blocking APIs/timeouts: https://docs.espressif.com/projects/esp-idf/en/v5.5.2/esp32s3/api-reference/peripherals/i2s.html
- DevKitC-1 v1.1 mutually exclusive power options: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html

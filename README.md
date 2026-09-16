# CrystalBall

**Aether Orb — hardware, firmware, manufacturing engineering and a WebGPU digital studio.**

A tabletop AI-assisted entertainment prop with a hollow optical globe, an operator-facing reflected display, push-to-talk audio and a decorative illuminated base. The browser recreates the concept's sphere, purple illumination, black/gold celestial base and private teller display; the Engineering view loads the actual CAD tessellation.

**Release: engineering candidate. Not approved for production manufacture or sale.** Physical fit, optical privacy/readability, supplier selection, thermal/electrical qualification, production security and market compliance remain release gates. The browser's volumetric nebula is artistic, not a claim that LEDs create a cloud inside an empty globe. Exact visual identity has not been accepted.

## Browser prototype online

**[Open CrystalBall on GitHub Pages](https://wieslawsoltes.github.io/CrystalBall/)** — offline demo by default, including the WebGPU experience and CAD inspector. The Python gateway is hosted separately. [Pages deployment and pairing](docs/github-pages.md) explains the repository-path checks, publication manifest and CORS configuration.

## Start the browser without an API key

```sh
git clone https://github.com/wieslawsoltes/CrystalBall.git
cd CrystalBall
python -m http.server 8088 --directory web
```

Open `http://localhost:8088`. No build or CDN dependencies are needed. Demo readings are explicitly fictional samples. WebGPU is preferred; Canvas 2D is a fallback. The application includes teller/client/comparison modes, orbit/zoom, a separate glow-only client window, a CAD part inspector with explosion/isolation, text paging, cancellation and timed erasure. The client display mode is a presentation feature, not an authentication boundary.

## Use your OpenAI key for text and voice

The project API key stays on your trusted gateway host. The browser receives a separate device token; it does not ask for or persist an OpenAI project key.

```sh
python factory/configure_gateway.py --unit orb-0001 --url https://orb-gateway.home.arpa --speech
cd gateway
docker compose up --build -d
```

The tool prompts for the project key without echo and creates `gateway/.env` plus `factory/private/orb-0001.json` with restrictive POSIX permissions. It refuses to overwrite existing credentials. Windows deployments need corresponding NTFS ACLs.

Configure LAN DNS to point `orb-gateway.home.arpa` at the gateway machine. The supplied Caddy configuration uses a local CA: export and explicitly trust its **public root certificate** on your clients. Do not disable certificate verification or distribute CA private keys. Open the HTTPS site, select **Connect gateway**, enter its origin and the device token from the private JSON, then ask a question or hold the microphone button.

Text generation, transcription and synthesized speech use paid OpenAI APIs. Set model names in `.env` for models available to your account. No live paid provider test has been performed in this repository's CI. Speech requires `--speech`; the voice is disclosed as AI-generated. Experimental native WebRTC voice additionally requires `--realtime`. Leave it disabled for production until live provider/device and fault-injection qualification is completed. Known calls now have durable SQLite lifecycle recovery; ambiguous creates block new voice admission until an operator reconciles them. See [recovery and cancellation design](docs/runtime-recovery.md).

The gateway runs as UID 10001 on a read-only root filesystem, uses a persistent SQLite request-admission database, enforces bounded requests and permits a single worker. Request quotas are not exact monetary caps. The browser unlocks Web Audio in the user gesture, stops microphone tracks on cancellation and uses no local/session storage for credentials or transcripts. Actual Safari/iPhone audio and microphone behavior still require representative-device testing.

## Engineering and manufacturing files

| Area | Entry point |
|---|---|
| Manufacturing handbook | [Editable guide](manufacturing/handbook.md) / [PDF](manufacturing/generated/CrystalBall-RevB-Handbook.pdf) / [HTML](manufacturing/generated/handbook.html) |
| BOM, harness, inspection and fixture tables | [Generated manufacturing package](manufacturing/generated/) |
| Native KiCad CAM | [cam-native](manufacturing/cam-native/) — read the hold notice; do not mix export sets |
| ECAD project | [KiCad project](hardware/aether-carrier.kicad_pro), [PCB](hardware/aether-carrier.kicad_pcb), [schematic](hardware/aether-carrier.kicad_sch) |
| Mechanical source | [CadQuery generator](mechanical/model.py), [Rev B assembly STEP](mechanical/Aether_Orb_RevB_Assembly.step), individual [STEP](mechanical/step/) and [STL](mechanical/stl/) |
| Firmware | [ESP-IDF project](firmware/) |
| Gateway and browser | [gateway](gateway/) / [web](web/) |
| Commissioning | [Factory tools](factory/) |
| Release evidence gate | [Requirements](manufacturing/release-plan.json) / [checker](factory/release_gate.py) / [signed evidence](factory/evidence.py) |
| First-article data evaluator | [Draft plan](manufacturing/qualification-plan.json) / [measurement tool](factory/measurements.py) |
| Test provenance | [Verification notes](verification/README.md) and [validated screenshots](preview/validated/) |

The original **63 Rev A files** are preserved byte-for-byte at commit `f430900c5269cbada520c0550a1a0a9df75eb3ed`, checked by `provenance/reva/SHA256.json`. Subsequent revisions are separate commits. `parameters.json` is generated documentation; edit the mechanical generator's `P` dictionary, not that JSON, to change geometry.

## Build firmware and provision a development unit

Use ESP-IDF **v5.5.2** with the specified ESP32-S3-DevKitC-1-N8R8. Copy only your gateway's trusted public CA certificate to `firmware/main/gateway_ca.pem` and then:

```sh
cd firmware
idf.py set-target esp32s3
idf.py build
```

Before connecting DevKit USB: remove product power, allow and verify discharge, then **remove the DevKit from both carrier sockets**. Removing the RUN shunt alone does not isolate signal paths. Do not dual-power an installed DevKit.

```sh
# From repository root, in an activated ESP-IDF environment:
python factory/provision.py --device factory/private/orb-0001.json --generate
# Explicit NVS-only flash, with the DevKit already removed from both sockets:
python factory/provision.py --device factory/private/orb-0001.json --flash --port /dev/ttyUSB0 --devkit-detached
```

Use one provisioning invocation for a unit: the tool deliberately refuses to reuse its private output folder. The passphrase is prompted without echo. NVS offsets come from the checked-in partition table. **This is plaintext development provisioning, not production secure storage.** No eFuses are automatically changed. Production signing/encryption, key custody, recovery and update policy require an approved security workflow. CI certificates and build artifacts are test-only, not customer firmware.

## Verify and regenerate

```sh
python -m pip install './gateway[test]' reportlab
python -m pytest gateway/tests factory/tests -q
npm --prefix web test
python tools/manufacturing.py
python factory/release_gate.py --output manufacturing/generated/release-status.json
```

The final command currently exits **1 / BLOCKED** because physical qualification and owner approvals are absent. That is intentional. Without a trust policy it validates structure only. With an independently pinned reviewer policy, it verifies Ed25519 signatures, scoped reviewer quorums, expiry/revocation and both source and manufacturing-output fingerprints. No trusted reviewer ships with the project. Neither mode certifies the product or authorizes production. See [signed evidence and measured qualification](docs/qualification-evidence.md).

GitHub Actions also compiles all three firmware profiles, runs KiCad 9.0.9 ERC/DRC/schematic parity, exports native CAM, tests a read-only Docker deployment and exercises the browser on a software WebGPU adapter with mocked OpenAI responses. See [Actions](https://github.com/wieslawsoltes/CrystalBall/actions) for the exact commit under test. Archived evidence is dated, not automatically promoted to cover later design changes.

## Remaining production gates

The handbook and generated tables distinguish selected ordering codes from unresolved suppliers, proposed assembly lengths/torques/acceptance limits from measured limits, and envelope models from real components. Optical viewing-volume tests, a fitted first article, power/inrush/fault/thermal tests, radio/EMC/ESD and market assessment, secure provisioning/recovery, real OpenAI/mobile-device validation, assembly capability and transport qualification are still required. No conformity mark or production authorization is implied by this repository.

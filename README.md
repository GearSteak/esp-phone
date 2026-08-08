# DIY 4G Phone — ESP32-S3-SIM7670G-4G

Firmware aligned to the **official Waveshare pinout** (ESP32-S3-A/SIM7670X-4G).

## Corrected pin map (from board diagram)

| Function | GPIO | Notes |
|----------|------|--------|
| Modem ESP TX / RX | **17 / 18** | Pinout UART_TXD / UART_RXD |
| Modem RI / DTR | 40 / 45 | Shared: I2S DOUT / TFT RST |
| Onboard TF CMD/CLK/DAT/CD | **4 / 5 / 6 / 46** | Built-in microSD |
| Camera Y2–Y9 | 7–14 | FPC |
| Camera SIOD/SIOC | 15 / 16 | FPC |
| Camera XCLK/HREF/VSYNC/PCLK | 34 / 35 / 36 / 37 | FPC |
| TFT SCK / MOSI / CS / DC / RST | **39 / 19 / 21 / 33 / 45** | 19 = USB_DP net |
| I2S BCLK / LRCK / DOUT / DIN | **41 / 42 / 40 / 1** | Header pins only |
| Keyboard rows | **7–12** | Shared with camera — paused in Camera app |
| Keyboard cols | **13–16, 20, 46** | Shared with camera / CD |

**Not used (not on side headers):** 2, 3, 26–32, 47, 48.

### Camera vs keyboard
While Camera is open, the matrix is paused. Wire temporary Snap/Back to:
- **GPIO 1** = Confirm / Snap  
- **GPIO 42** = Back  

(Those are I2S lines; audio is stopped during camera.)

## Wiring quick list

| Peripheral | Connections |
|------------|-------------|
| TFT ILI9486 | SCK39, MOSI19, CS21, DC33, RST45, VCC 3V3, GND |
| MAX98357 | BCLK41, LRC42, DIN40, VIN 5V, GND |
| INMP441 | SCK41, WS42, SD1, VDD 3V3, L/R→GND |
| Keyboard | Rows 7–12, Cols 13–16 + 20 + 46 |
| microSD | Insert in **onboard TF slot** (FAT32) |
| OV2640 | FPC + enable **CAM** DIP |
| 4G + GNSS antennas | Required |
| External LoRa (SX1276 / Ra-02 / RFM95) | Shared TFT SPI + free pads — see below |

### LoRa emergency radio (external module)

The Waveshare board has **no LoRa onboard**. Wire an SX1276-class module for SOS / short text when cellular is dead.

| LoRa pin | ESP32-S3 GPIO | Notes |
|----------|---------------|--------|
| SCK | **39** | Shared with TFT |
| MOSI | **19** | Shared with TFT |
| MISO | **47** | Module pad (not on side header) |
| NSS/CS | **48** | Module pad |
| RST | **2** | Module pad |
| DIO0 | **3** | Module pad |
| VCC / GND | 3V3 / GND | Use adequate 3V3 supply for TX |

Set `LORA_FREQ_MHZ` in `Config.h` (default **906.875 MHz**, same as Heltec LoRa phones). Soft-disable with `-DLORA_ENABLE=0`.

**Heltec mesh compatible:** Uses the same binary packet format as your `meshtastic-t9/scratch_firmware` (`LoRaComm.cpp`): SF12 / BW250 / CR4/8 / sync `0x12`. No reflash needed on existing Heltec devices. Device ID = 6-digit phone number from MAC (or override in Settings → Accounts). SOS broadcasts to all nodes; set a target ID for direct messages.

**App:** Comm → **LoRa SOS** — type + Confirm to send, or **SOS NOW** (GPS if available). Settings → Accounts → **Save LoRa ID** / **Save LoRa target** (`loraDevId`, `loraTargetId` in `/settings.json`; target `0` = broadcast).

## SD folders / data files

```
/music/*.mp3
/books/*.txt
/audiobooks/*.mp3
/photos/
/settings.json   /contacts.json  /call_log.json
/sms_store.json  /notifs.json    /alarms.json
/calendar.json   /notes.json     /todos.json
```

## Apps

| Menu | Contents |
|------|----------|
| Phone | Dial / VoIP |
| Contacts · Call Log · Messages · Notifs | Daily comms |
| Clock · Alarms · Calendar | Time + reminders |
| Phone / Comm | Phone, Contacts, Call Log, Messages, Notifs, Email, **LoRa SOS** |
| Media | Camera, **Gallery**, **Voice notes**, GPS, Notes, Todos, Music, Ebooks, Audiobooks |
| Media | Camera, GPS, Notes, Todos, Music, Ebooks, Audiobooks |
| Games · Settings | PIN, profile, airplane, hotspot, Bluetooth name, voicemail dial |

**Skipped on purpose:** flashlight, face unlock, FM, auto-brightness (extra hardware).

### Settings notes
- **PIN:** type digits on Settings, Confirm to save; Clear PIN disables lock.
- **Profile:** Silent / Normal / Loud / Outdoor (tones respect Silent).
- **Airplane:** `AT+CFUN=0/1`.
- **Hotspot:** ESP32 SoftAP (`ESP-Phone` / `phone1234` by default) — local Wi‑Fi AP, not modem USB tethering.
- **Bluetooth:** ESP32-S3 is BLE-only (no Classic SPP). Settings stores a preference for a future BLE headset stack.
- **Battery:** modem `AT+CBC` (+ charging indicator in status bar). Optional ADC in `Config.h` if you add a divider.
- **Weather:** Open‑Meteo over modem HTTPS; uses GPS fix when valid.
- **Share location:** SMS a Google Maps link from GPS or Tools.
- **Google Calendar:** secret iCal URL on SD `/google_ics.url` — see `assets/online_setup.md`.
- **Email:** IMAP over WiFi Station (Gmail app password) — not Classic BT / not SoftAP.
- **Browser:** text-only pages via modem HTTPS (no JS/CSS).

## Settings app

Main → **Settings** opens a hub:

| Page | Controls |
|------|----------|
| Security | Set/clear PIN, lock timeout, lock now |
| Network | Airplane, SoftAP hotspot, WiFi STA, BT preference |
| Accounts | Google ICS, Email, voicemail, LoRa ID / target |
| Sounds | Profile (Silent/Normal/Loud/Outdoor), master sounds, tone tests |
| About | Modem/SIP/battery/storage info |

Online credential files (TF card): see `assets/online_setup.md`.

## Build (standalone TFT phone)

```bash
pio run -e esp32-s3-sim7670g -t upload
```

## Build (Pi Digivice — 2" 240×320)

```bash
# Heltec Wireless Tracker — LoRa only
pio run -e heltec-wireless-tracker-gateway -t upload
```

Pi UI: Waveshare **2" ST7789** SPI (**240×320**) + **7 hard buttons**.  
See [`pi_handset/README.md`](pi_handset/README.md), [`docs/WAVESHARE_2INCH_LCD.md`](docs/WAVESHARE_2INCH_LCD.md), [`docs/DIGI_BUTTONS.md`](docs/DIGI_BUTTONS.md).

Set SIP credentials in `/etc/esp-handset/sip.env` (Pi handset) or `include/Config.h` (standalone TFT phone).


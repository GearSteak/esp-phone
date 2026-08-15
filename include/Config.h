#pragma once

/*
 * DIY 4G Phone — pin map aligned to Waveshare ESP32-S3-A/SIM7670X-4G pinout
 *
 * RESERVED BY BOARD (do not wire peripherals here)
 *   Camera FPC: 7–16, 34–37
 *   Modem UART: 17 (TXD), 18 (RXD)
 *   Modem RI / DTR: 40 / 45  — reused carefully for I2S / TFT RST
 *   Modem USB_DN/DP: 19 / 20 — reused for TFT SPI (disable modem-USB DIP use)
 *   Onboard TF: 4 (CMD), 5 (CLK), 6 (DAT0), 46 (CD)
 *
 * KEYBOARD
 *   Standalone TFT phone: 6×6 on camera data pins (paused while OV2640 runs).
 *   GATEWAY_MODE (Pi handset): 5×10 real QWERTY — camera unused, so Y2–Y9 +
 *   VSYNC/HREF/PCLK/XCLK become matrix lines. Numbers on top row.
 *
 * Header-only: GPIOs 2,3,26–32,47,48 are NOT on the side headers — unused.
 */

#include <Arduino.h>

#ifndef GATEWAY_MODE
#define GATEWAY_MODE          0
#endif
#ifndef HELTEC_WIRELESS_TRACKER
#define HELTEC_WIRELESS_TRACKER 0
#endif

// ---------------------------------------------------------------------------
// Modem (SIM7670G) — matches pinout callout 5
// ---------------------------------------------------------------------------
#define MODEM_UART_NUM        1
#define MODEM_UART_RX         18   // ESP RX  <- module UART_RXD net / 4G data to ESP
#define MODEM_UART_TX         17   // ESP TX  -> module UART_TXD
#define MODEM_UART_BAUD       115200
#define MODEM_RI_PIN          40   // ring indicator (also I2S DOUT — input when idle)
#define MODEM_DTR_PIN         45   // also TFT RST
#define MODEM_PWRKEY_PIN      -1
#define MODEM_RESET_PIN       -1
#define MODEM_AT_TIMEOUT_MS   5000
#define MODEM_BOOT_DELAY_MS   3000

#define APN_NAME              "internet.freedommobile.ca"
#define APN_USER              ""
#define APN_PASS              ""

// ---------------------------------------------------------------------------
// SIP / VoIP
// ---------------------------------------------------------------------------
#define SIP_SERVER            "sip.zadarma.com"
#define SIP_PORT              5060
#define SIP_USERNAME          "440892"
#define SIP_PASSWORD          "Ping927Ld"
#define SIP_DISPLAY_NAME      "SIP"
#define SIP_LOCAL_PORT        5060
#define SIP_RTP_PORT          10000
#define SIP_REGISTER_EXPIRES  300
#define SIP_USER_AGENT        "ESP32-S3-Phone/1.0"

// ---------------------------------------------------------------------------
// Display — ILI9486 SPI 320×480 (header + USB GPIO pair)
// ---------------------------------------------------------------------------
#define TFT_WIDTH_PX          320
#define TFT_HEIGHT_PX         480
#define DISP_SCK              39   // right header
#define DISP_MOSI             19   // USB_DP net — OK as GPIO if not using 4G USB
#define DISP_MISO             -1   // unused (freed for keyboard)
#define DISP_CS               21
#define DISP_DC               33
#define DISP_RST              45   // shares modem DTR net
#define DISP_BL               -1
#define DISP_ROTATION         0

// ---------------------------------------------------------------------------
// LoRa emergency radio
// Default (Waveshare gateway / phone): external SX1276 on free pads.
// Heltec Wireless Tracker: onboard SX1262 (-DHELTEC_WIRELESS_TRACKER=1).
// ---------------------------------------------------------------------------
#ifndef LORA_ENABLE
#define LORA_ENABLE           1
#endif
#ifndef LORA_RADIO_SX1262
#define LORA_RADIO_SX1262     0
#endif
#define LORA_FREQ_MHZ         906.875   // match Heltec LoRa phones (scratch_firmware default)
#define LORA_BW_KHZ           250.0
#define LORA_SF               12
#define LORA_CR               8         // RadioLib 8 = coding rate 4/8
#define LORA_PREAMBLE         8
#define LORA_SYNC_WORD        0x12
#define LORA_TX_POWER_DBM     20
#define LORA_MAX_PAYLOAD      240
#define LORA_BROADCAST_ID     0xFFFFFFFFUL

#if HELTEC_WIRELESS_TRACKER
// Onboard SX1262 (Wireless Tracker V1.1 / V2.x)
#undef LORA_RADIO_SX1262
#define LORA_RADIO_SX1262     1
#define LORA_SCK              9
#define LORA_MOSI             10
#define LORA_MISO             11
#define LORA_CS               8
#define LORA_RST              12
#define LORA_BUSY             13
#define LORA_DIO1             14
#define LORA_DIO0             LORA_DIO1  // IRQ line name used in shared code
// Display — ST7735 160×80 notify panel (reconnect ribbon)
#define TFT_CS_PIN            38
#define TFT_RST_PIN           39
#define TFT_DC_PIN            40
#define TFT_SCLK_PIN          41
#define TFT_MOSI_PIN          42
#define TFT_BL_PIN            21
#define TFT_VEXT_PIN          3    // HIGH = panel + GNSS power
#define TFT_WIDTH_NOTIFY      160
#define TFT_HEIGHT_NOTIFY     80
#else
#define LORA_SCK              DISP_SCK
#define LORA_MOSI             DISP_MOSI
#define LORA_MISO             47
#define LORA_CS               48
#define LORA_RST              2
#define LORA_DIO0             3
#define LORA_BUSY             -1
#endif

// ---------------------------------------------------------------------------
// UI theme
// ---------------------------------------------------------------------------
#define UI_BG_COLOR           0x000000
#define UI_STATUS_BAR_COLOR   0x111111
#define UI_STATUS_BAR_HEIGHT  32
#define UI_CONTENT_BG_COLOR   0x000000
#define UI_CONTENT_BG_OPA     255
#define UI_STATUS_BG_OPA      230
#define UI_USE_WALLPAPER       0
// Prefer TF card art (/ui/...) over flash-baked arrays
#define UI_SD_ASSETS           1
// 1 = also allow flash-baked C-array icons (fallback only; prefer SD)
#define UI_USE_APP_ICONS       0
#define UI_USE_STATUS_ICONS    0

// ---------------------------------------------------------------------------
// Keyboard matrix
// ---------------------------------------------------------------------------
#if HELTEC_WIRELESS_TRACKER
// Digivice: M5Stack CardKB on Grove/I2C (preferred). Matrix unused when CARDKB_ENABLE=1.
// Pinout: docs/HELTEC_TRACKER_PINOUT.md
#ifndef CARDKB_ENABLE
#define CARDKB_ENABLE         1
#endif
#define CARDKB_ADDR           0x5F
#define CARDKB_SDA            6    // Grove yellow
#define CARDKB_SCL            17   // Grove white
// Grove red → 5V, Grove black → GND

// SW-520D tilt / step (one leg → GPIO, other → GND). Free with CardKB.
#ifndef STEP_TILT_ENABLE
#define STEP_TILT_ENABLE      1
#endif
#define STEP_TILT_PIN         7
#define STEP_TILT_DEBOUNCE_MS 25
#define STEP_TILT_MIN_MS      280   // refractory between counted steps

#define KB_ROWS               5
#define KB_COLS               10
#define KB_DEBOUNCE_MS        20
#define KB_SCAN_PERIOD_MS     10
// Matrix only if CARDKB_ENABLE=0 (shares 6/17 with CardKB — do not enable both)
static const uint8_t KB_ROW_PINS[KB_ROWS] = {4, 5, 6, 7, 17};
static const uint8_t KB_COL_PINS[KB_COLS] = {18, 26, 35, 36, 37, 43, 44, 45, 47, 48};
#define VOL_UP_PIN            1
#define VOL_DOWN_PIN          2
#define VOL_MUTE_PIN          46

#elif GATEWAY_MODE
#ifndef CARDKB_ENABLE
#define CARDKB_ENABLE         0
#endif
#ifndef STEP_TILT_ENABLE
#define STEP_TILT_ENABLE      0
#endif
// Waveshare-board gateway (legacy) — camera FPC pins reused
#define KB_ROWS               5
#define KB_COLS               10
#define KB_DEBOUNCE_MS        20
#define KB_SCAN_PERIOD_MS     10
static const uint8_t KB_ROW_PINS[KB_ROWS] = {7, 8, 9, 10, 11};
static const uint8_t KB_COL_PINS[KB_COLS] = {12, 13, 14, 15, 16, 20, 34, 35, 36, 37};

#ifndef CARDKB_ENABLE
#define CARDKB_ENABLE         0
#endif

#else
// Compact 6×6 for standalone Waveshare phone (shares OV2640 data lines)
#ifndef CARDKB_ENABLE
#define CARDKB_ENABLE         0
#endif
#ifndef STEP_TILT_ENABLE
#define STEP_TILT_ENABLE      0
#endif
#define KB_ROWS               6
#define KB_COLS               6
#define KB_DEBOUNCE_MS        20
#define KB_SCAN_PERIOD_MS     10
static const uint8_t KB_ROW_PINS[KB_ROWS] = {7, 8, 9, 10, 11, 12};
static const uint8_t KB_COL_PINS[KB_COLS] = {13, 14, 15, 16, 20, 46};
#endif

// While camera is open (standalone), matrix is paused; idle I2S pins as soft keys
#define KB_CAM_SNAP_PIN       1
#define KB_CAM_BACK_PIN       42

enum KeyCode : uint16_t {
  KEY_NONE   = 0,
  KEY_UP     = 0x1001,
  KEY_DOWN   = 0x1002,
  KEY_LEFT   = 0x1003,
  KEY_RIGHT  = 0x1004,
  KEY_CALL   = 0x1005,
  KEY_END    = 0x1006,
  KEY_SHIFT  = 0x1007,
};

#if GATEWAY_MODE
static const uint16_t KB_LAYOUT[KB_ROWS][KB_COLS] = {
  {'1', '2', '3', '4', '5', '6', '7', '8', '9', '0'},
  {'Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P'},
  {'A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', ';'},
  {'Z', 'X', 'C', 'V', 'B', 'N', 'M', ',', '.', '/'},
  {KEY_SHIFT, ' ', '\b', '\n', KEY_LEFT, KEY_RIGHT, KEY_UP, KEY_DOWN, KEY_CALL,
   KEY_END},
};
#else
static const uint16_t KB_LAYOUT[KB_ROWS][KB_COLS] = {
  {'Q', 'W', 'E', 'R', 'T', 'Y'},
  {'U', 'I', 'O', 'P', 'A', 'S'},
  {'D', 'F', 'G', 'H', 'J', 'K'},
  {'L', 'Z', 'X', 'C', 'V', 'B'},
  {'N', 'M', ' ', '\b', '\n', KEY_SHIFT},
  {KEY_LEFT, KEY_RIGHT, KEY_UP, KEY_DOWN, KEY_CALL, KEY_END},
};

// Legacy: shift+letter → digit/symbol (no number row on 6×6)
static const char KB_SHIFT_MAP[26] = {
  '1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '*', '#', '+', '-', '(',
  ')', '!', '@', '$', '%', '^', '&', '*', '?', '/', '.',
};
#endif

// Shifted digits / punctuation (gateway QWERTY number + symbol row)
static const char KB_DIGIT_SHIFT[10] = {
  '!', '@', '#', '$', '%', '^', '&', '*', '(', ')',
};

// ---------------------------------------------------------------------------
// Audio — I2S on right-header GPIOs (avoid camera / TF)
// ---------------------------------------------------------------------------
#define I2S_PORT_NUM          0
#define I2S_BCLK              41
#define I2S_LRCK              42
#define I2S_DOUT              40   // modem RI net — amp DIN
#define I2S_DIN               1    // mic SD
#define I2S_SAMPLE_RATE       8000
#define I2S_MEDIA_RATE        44100
#define I2S_BITS_PER_SAMPLE   16
#define AUDIO_FRAME_SAMPLES   160
#define AUDIO_LATENCY_MS      60

// ---------------------------------------------------------------------------
// Camera — pinout callout 3 (OV2640 FPC)
// ---------------------------------------------------------------------------
#define CAM_PWDN              -1
#define CAM_RESET             -1
#define CAM_XCLK              34
#define CAM_SIOD              15
#define CAM_SIOC              16
#define CAM_Y9                14
#define CAM_Y8                13
#define CAM_Y7                12
#define CAM_Y6                11
#define CAM_Y5                10
#define CAM_Y4                9
#define CAM_Y3                8
#define CAM_Y2                7
#define CAM_VSYNC             36
#define CAM_HREF              35
#define CAM_PCLK              37
#define CAM_XCLK_FREQ_HZ      20000000
#define CAM_JPEG_QUALITY      12
#define CAM_PHOTOS_DIR        "/photos"
#define VOICE_NOTES_DIR       "/voicenotes"
#define RINGTONE_DIR          "/music"

// ---------------------------------------------------------------------------
// Media paths on SD
// ---------------------------------------------------------------------------
#define MUSIC_DIR             "/music"
#define EBOOK_DIR             "/books"
#define AUDIOBOOK_DIR         "/audiobooks"
#define VIDEO_DIR             "/videos"
#define MEDIA_MAX_FILES       32
#define MEDIA_PATH_LEN        80
#define EBOOK_PAGE_CHARS      400
#define POINTER_STEP_PX       12

// ---------------------------------------------------------------------------
// Storage — onboard TF (SDMMC) per pinout callout 4
// ---------------------------------------------------------------------------
#define USE_SD_SPI            0
#define SD_SPI_SCK            DISP_SCK
#define SD_SPI_MISO           20
#define SD_SPI_MOSI           DISP_MOSI
#define SD_SPI_CS             40
#define SD_SPI_HZ             20000000

#define USE_ONBOARD_SD_MMC    1
#define SD_MMC_CLK            5
#define SD_MMC_CMD            4
#define SD_MMC_DAT0           6
#define SD_CD_PIN             46

// VBAT is a power pin on the header, not an ADC GPIO. Enable only if you add a divider.
#define BATTERY_ADC_PIN       -1
#define BATTERY_ADC_ENABLE    0
#define BATTERY_FULL_MV       4200
#define BATTERY_EMPTY_MV      3300

// ---------------------------------------------------------------------------
// FreeRTOS
// ---------------------------------------------------------------------------
#define CORE_MODEM            0
#define CORE_UI               1

#define PRIO_AUDIO            6
#define PRIO_SIP              5
#define PRIO_MODEM            4
#define PRIO_UI               3
#define PRIO_KEYBOARD         3
#define PRIO_GAMES            2
#define PRIO_MEDIA            5

#define STACK_AUDIO           4096
#define STACK_SIP             8192
#define STACK_MODEM           6144
#define STACK_UI              10240
#define STACK_KEYBOARD        3072
#define STACK_MEDIA           8192

enum CallState : uint8_t {
  CALL_IDLE = 0,
  CALL_DIALING,
  CALL_RINGING,
  CALL_IN_CALL,
  CALL_ENDED,
};

struct PhoneStatus {
  CallState callState;
  int csq;
  bool simReady;
  bool registered;
  bool pdpActive;
  bool sipRegistered;
  char ipAddr[32];
  char callerId[64];
  char dialBuffer[32];
  uint32_t callSeconds;
  int batteryPercent;
  int signalBars;
  int batteryMv;
  int chargeStatus;  // 0 idle, 1 charging, 2 charged
  bool airplaneMode;
  bool lowBatteryWarn;
};

// Legacy SoftAP names (unused in keyboard-only GATEWAY_MODE; cellular is SIM7600 on Pi)
#define GATEWAY_AP_SSID       "ESP-Handset"
#define GATEWAY_AP_PASS       "handset123"

// Volume side buttons — INPUT_PULLUP, active LOW
#if !HELTEC_WIRELESS_TRACKER
#define VOL_UP_PIN            26
#define VOL_DOWN_PIN          27
#define VOL_MUTE_PIN          28
#endif

// ---------------------------------------------------------------------------
// Online apps (Google Calendar ICS / email / browser defaults)
// Put long secrets on SD instead when possible:
//   /google_ics.url   — one-line secret Google Calendar iCal URL
//   /wifi_sta.txt     — line1=SSID line2=password
//   /email.txt        — line1=user line2=app-password (optional line3=host)
// ---------------------------------------------------------------------------
#ifndef GOOGLE_CAL_ICS_URL
#define GOOGLE_CAL_ICS_URL ""
#endif
#ifndef WIFI_STA_SSID
#define WIFI_STA_SSID ""
#endif
#ifndef WIFI_STA_PASS
#define WIFI_STA_PASS ""
#endif
#ifndef IMAP_HOST
#define IMAP_HOST "imap.gmail.com"
#endif
#ifndef IMAP_PORT
#define IMAP_PORT 993
#endif
#ifndef IMAP_USER
#define IMAP_USER ""
#endif
#ifndef IMAP_PASS
#define IMAP_PASS ""
#endif
#ifndef BROWSER_HOME_URL
#define BROWSER_HOME_URL "https://example.com"
#endif

# Speaker amp — MAX98357 / PAM8403 (Digivice Pi)

The USB dongle **green jack** is headphone/line level. Passive speakers are quiet. An **inline switch** on the external amp path keeps the speaker off when you only want headphones.

## Recommended for Digivice: PAM8403 + inline switch

Easiest on this build: tap the **green jack** into a **PAM8403** (analog stereo amp). Headphones stay on the jack; the amp drives a separate speaker when the switch is on.

```
USB DAC green jack ──┬── headphones (always)
                     └── [SPST switch] ── PAM8403 IN ── speaker 8Ω
```

| PAM8403 | Connect |
|---------|---------|
| **VCC** | 5V (Pi pin 2) through **inline switch** |
| **GND** | GND |
| **IN+ / IN−** | Green jack tip/ring (or mono: tip + sleeve) |
| **OUT+ / OUT−** | Speaker |

Switch **open** = amp off (headphones only). Switch **closed** = speaker live.

Test USB audio first: [`DIGIVICE_AUDIO.md`](DIGIVICE_AUDIO.md) · `sudo digivice-audio-fix.sh`

## MAX98357A (I2S — pin conflict on Digivice)

The **MAX98357** is a **digital I2S** amp (better/louder than PAM8403) but Pi I2S lives on fixed pins:

| I2S | BCM | Digivice use |
|-----|-----|----------------|
| BCLK | **18** | LCD backlight |
| LRCLK | **19** | Back button |
| DIN | **20** | (free on header pin 38) |
| DOUT | **21** | Select button |

So a stock MAX98357 on Pi I2S **fights the Waveshare LCD and buttons** on this passthrough layout.

### If you still want MAX98357

Pick one:

1. **Move LCD BL off GPIO 18** (hardware mod) then wire MAX98357 to standard I2S:

   | MAX98357 | Pi pin | BCM |
   |----------|--------|-----|
   | VIN | 2 | 5V (**inline switch**) |
   | GND | 6 | GND |
   | BCLK | 12 | 18 |
   | LRC | 35 | 19 |
   | DIN | 38 | 20 |
   | SD | 3.3V | always on, or second switch |
   | GAIN | GND | ~9 dB |

   Then enable I2S:

   ```bash
   # Adds enable_uart + I2S — only after you resolved GPIO 18/19 conflicts
   echo 'dtparam=i2s=on' | sudo tee -a /boot/firmware/config.txt
   echo 'dtoverlay=hifiberry-dac' | sudo tee -a /boot/firmware/config.txt
   sudo reboot
   ```

2. **Keep Digivice wiring** → use **PAM8403** on the green jack (above).

3. **Separate USB-I2S dongle** feeding MAX98357 — rare, but avoids Pi GPIO.

### Inline switch (both amp types)

- **PAM8403:** switch in **5V** to VCC (recommended).  
- **MAX98357:** switch **5V to VIN** or break **SD** (shutdown) so the amp is off; headphones on USB jack are unaffected.

Label the switch **SPEAKER**.

## ALSA

Digivice defaults to **USB** (`digivice-audio-usb`). PAM8403 shares that path automatically.

MAX98357 on I2S appears as a second card:

```bash
aplay -l
speaker-test -D plughw:max98357,0 -c 2 -t sine -f 880 -l 1
```

Use WirePlumber / `pactl` to pick USB (headphones) vs I2S (speaker) as default.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Headphones OK, speaker dead | Switch on? Amp powered? PAM8403 volume pot? |
| Both always loud | Add switch on amp **power**, not headphone cable |
| USB LED solid, no sound | `sudo digivice-audio-fix.sh` |
| MAX98357 clicks only | Wrong I2S pins or GPIO 18/19 still used by LCD/buttons |

See [`DIGIVICE_WIRING.md`](DIGIVICE_WIRING.md) for the full pin map.

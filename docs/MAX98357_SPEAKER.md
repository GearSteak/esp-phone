# Speaker amp — MAX98357 / PAM8403 (Digivice Pi)

The USB dongle **green jack** is headphone/line level. Passive speakers are quiet. An **inline switch** on the external amp path keeps the speaker off when you only want headphones.

## If you have a MAX98357 on hand

It will work — but **Pi hardware I2S is fixed** on BCM **18 / 19 / 20 / 21**, which Digivice already uses:

| I2S | BCM | Digivice today |
|-----|-----|----------------|
| BCLK | **18** | LCD backlight |
| LRCLK | **19** | Back button |
| DIN | **20** | free (header pin 38) |
| — | **21** | Select button |

### Option A — Remap pins (best use of your MAX98357)

1. Move LCD **BL** from pin **12** (BCM18) → free pin **16** (BCM23).  
2. Move **Back** from pin **35** (BCM19) → free pin **18** (BCM24).  
3. Wire the MAX98357:

| MAX98357 | Pi pin | BCM |
|----------|--------|-----|
| VIN | 2 | 5V through **inline SPEAKER switch** |
| GND | 6 | GND |
| BCLK | 12 | **18** |
| LRC | 35 | **19** |
| DIN | 38 | **20** |
| SD | 3.3V or switch | amp enable |
| GAIN | GND | ~9 dB |

4. Point Digivice’s Back button env / map at BCM24, and LCD BL at BCM23.  
5. Enable I2S and reboot:

```bash
echo 'dtparam=i2s=on' | sudo tee -a /boot/firmware/config.txt
echo 'dtoverlay=hifiberry-dac' | sudo tee -a /boot/firmware/config.txt
sudo reboot
aplay -l
speaker-test -D plughw:0,0 -c 2 -t sine -f 880 -l 1
```

### Option B — Keep current Digivice wiring

Leave the MAX98357 for after remapping. Use a **PAM8403** on the green jack (below) for now.

### Option C — Drive MAX98357 from Heltec

Wire the amp to free Heltec GPIOs and play alert tones there; Pi USB headphones stay independent. More firmware work.

## PAM8403 + inline switch (no pin remap)

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

Test USB audio first: [`DIGIVICE_AUDIO.md`](DIGIVICE_AUDIO.md) · `sudo digivice-audio-fix.sh`

## Inline switch (both amps)

Put an **SPST on amp 5V (VIN/VCC)** labeled **SPEAKER**. Open = headphones only; closed = speaker live. Do not put the switch only on the headphone cable if you want independent paths.

## ALSA

Digivice defaults to **USB** (`digivice-audio-usb`). PAM8403 shares that path.

MAX98357 on I2S is a second card — use WirePlumber / `pactl` to choose USB vs I2S as default.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Headphones OK, speaker dead | Switch on? Amp powered? |
| Both always loud | Switch on amp **power**, not headphone cable |
| USB LED solid, no sound | `sudo digivice-audio-fix.sh` |
| MAX98357 silent / clicks | Still sharing BCM18/19 with LCD/Back — finish remap |

See [`DIGIVICE_WIRING.md`](DIGIVICE_WIRING.md) for the full pin map.

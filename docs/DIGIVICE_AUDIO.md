# Digivice / Pi USB audio (green out · pink mic)

PC color code on most USB sound dongles:

| Jack | Color | Use |
|------|--------|-----|
| **Line / headphone out** | **Green** | Speakers / earbuds |
| **Mic in** | **Pink** | Microphone only — never speakers |

## LED clue (C-Media)

| LED | Meaning |
|-----|---------|
| **Blinks** while playing (Windows) | Stick is streaming — good |
| **Solid** on Linux while you “play” | Driver not actually streaming / needs USB reset |

Same stick **0d8c:0012** often needs an **unplug/replug after boot** on Linux, or:

```bash
sudo digivice-audio-usb
# watch LED:
speaker-test -D plughw:1,0 -c 2 -t sine -f 880 -l 2
```

If still solid: unplug USB → plug again → rerun the beep.

## Quiet speakers

Green is **headphone / line level**. Passive speakers (no amp) sound tiny even when Windows “works.”

- Swapping to a more sensitive / higher‑SPL speaker helps some  
- A **PAM8403** or **MAX98357** between DAC and speaker helps a lot  
- `digivice-audio-usb` adds a **Digivice Boost** softvol (`alsamixer -c 1`)

## Green jack PCB pads

On many of these jacks the **middle solder pad is ground**.

Mono speaker: **−** → middle, **+** → one outer pad.

## Force USB + beep (do this when Linux is silent but Windows works)

```bash
cd ~/esp-phone && git pull
sudo bash ~/esp-phone/pi_handset/session/digivice-audio-fix.sh
```

That script:

1. Disables HDMI sinks in WirePlumber  
2. Hard-resets the C-Media USB device (`authorized` 0→1)  
3. Stops PipeWire and plays an exclusive ALSA beep — **watch the red LED**  
4. Restarts PipeWire and sets USB as default  

| LED during beep | Meaning |
|-----------------|---------|
| **Blinks** + sound | Fixed |
| **Blinks** + silent | Jack/speakers/amp hardware |
| **Solid** | Still not streaming — unplug 5s, replug, `sudo digivice-audio-fix --beep-only` |

## Report

Tools → Transfer → **Prep audio report** → `http://<pi-ip>:8765/diag/audio.txt`

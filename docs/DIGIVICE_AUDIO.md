# Digivice / Pi USB audio (green out · pink mic)

PC color code on most USB sound dongles:

| Jack | Color | Use |
|------|--------|-----|
| **Line / headphone out** | **Green** | Speakers / earbuds |
| **Mic in** | **Pink** | Microphone only — never speakers |

Speakers on green is correct. Pink will never produce speaker sound.

## Green jack PCB pads (your board)

On many of these jacks the **middle solder pad is ground**.

Mono speaker:

- Speaker **−** → **middle** (GND)
- Speaker **+** → **one outer** pad (try both outers one at a time)

Stereo: left outer + right outer + shared middle GND.

## Why Linux “sees” USB but you hear nothing

1. **Playback still on HDMI** — Digivice/desktop default sink is often `vc4 HDMI`, not the USB card.
2. **Jack detect / Auto-Mute** — some dongles mute until a plug is inserted; soldering wires may not close the switch.
3. **Passive speaker on line-out** — green is headphone/line level; a bare 8 Ω speaker is often silent or tiny. Need a small amp (PAM8403 / MAX98357) between green and the speaker.
4. **Wrong pad** — signal on GND, or only mic (pink) wired for “sound”.

## Force USB + beep (on the Pi)

```bash
cd ~/esp-phone && git pull
sudo bash ~/esp-phone/pi_handset/session/digivice-audio-usb.sh
sudo bash ~/esp-phone/pi_handset/session/digivice-audio-doctor.sh

# Listen during this:
speaker-test -c 1 -t sine -f 880 -l 2
```

Also try plugging **earbuds into the green jack**. If earbuds work but the soldered speaker does not → wiring/amp. If earbuds are also silent → software default or mute/detect.

## Report for Cursor

Tools → Transfer → **Prep audio report**, then download  
`http://<pi-ip>:8765/diag/audio.txt`  
and paste it here.

# Stuck under Digivice (no working keyboard)

Digivice’s old `grabKeyboard()` could block USB keyboards. That is **removed** in current git.
If you are stuck *now* on an older install:

## A. Hard buttons only (no USB keyboard)

Try quickly:

- **Back** three times, or  
- **Home** three times  

(After you update — on old code Back×3 / Home×3 may not exist: use **Settings → Linux → Exit** if you can navigate with buttons.)

## B. SD card (works from any Windows/Mac PC)

1. Power off the Pi, pull the microSD.  
2. Put the card in a PC.  
3. Open the small **boot** volume (often named `bootfs` or `boot`).  
4. Create an **empty** file named exactly:

   `digivice-desktop`

   (no extension — not `digivice-desktop.txt`)

5. Eject card, put it back in the Pi, power on.  

Autostart sees that file → **desktop only**, Digivice does not start.

Later, to use Digivice again:

```bash
sudo rm -f /boot/firmware/digivice-desktop /boot/digivice-desktop
handset-session set-phone
handset-phone
```

## C. Phone / laptop over Wi‑Fi (if Pi is on the network)

```bash
ssh YOUR_USER@PI_IP
pkill -9 -f handset_app
echo desktop > ~/.esp-handset/session_mode
```

## D. After free: pull fixes + reinstall

```bash
cd ~/esp-phone && git pull
sudo bash pi_handset/install-handset.sh
# remove recovery flag if you used B:
sudo rm -f /boot/firmware/digivice-desktop /boot/digivice-desktop
```

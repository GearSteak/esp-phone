# Online credentials (put these on the phone TF card)

## Google Calendar → `/google_ics.url`
1. Google Calendar → Settings → your calendar  
2. **Integrate calendar** → **Secret address in iCal format**  
3. Copy the URL into a one-line file:

```
https://calendar.google.com/calendar/ical/.../private-.../basic.ics
```

Or set `GOOGLE_CAL_ICS_URL` in `include/Config.h`.

Then Calendar → **Sync Google**. Events show with a `[G]` prefix.

## Email → `/wifi_sta.txt` + `/email.txt`
Email uses **WiFi Station** (not 4G SoftAP).

`/wifi_sta.txt`:
```
YourHomeSSID
YourWifiPassword
```

`/email.txt` (Gmail: use an [App Password](https://myaccount.google.com/apppasswords)):
```
you@gmail.com
xxxx xxxx xxxx xxxx
imap.gmail.com
```

(Third line optional; defaults to `imap.gmail.com`.)

Then Email → **WiFi connect** → **Refresh inbox** → **Open**.

## Browser
Uses modem **4G HTTPS**. Type a URL and Confirm / Go.  
Text-only (HTML stripped). Left/Right change pages.

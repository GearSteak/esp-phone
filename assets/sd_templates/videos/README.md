# MJPEG clips for the Video app

Put concatenated JPEG frames here (extension `.mjpeg` or `.mjpg`).

Tips:
- Keep resolution ≤ 320×240 for smoother playback
- Silent video only (no MP4/H.264)
- ffmpeg example:

```bash
ffmpeg -i input.mp4 -vf scale=320:240 -q:v 8 -f mjpeg clip.mjpeg
```

# Camera screens

A screen with `camera:` shows that camera's current still, scaled to the matrix and refreshed every `refresh` seconds while it's on display (nothing is fetched while other screens show). The still comes from Home Assistant's camera proxy, which scales it down first; matrices showing the same camera share one fetch, and if a fetch fails the last good frame stays up.

```yaml
  screens:
    drive:
      camera: camera.drive          # any camera entity
      dwell: 15                     # optional: this screen's time in the rotation (overrides the matrix's dwell)
      fit: crop                     # crop (fill, cut the sides of a wide picture; default) or letterbox
      # autocontrast: true          # default: stretch the levels; makes dim and night-time infrared pictures readable
      # brightness: 1.0             # 1.0 = unchanged
      # contrast: 1.0
      # gamma: 1.0                  # above 1 darkens the mid-tones
```

Camera screens need **Pillow**: on Home Assistant OS, add `Pillow` to the AppDaemon app's `python_packages` option and restart it. The app reaches Home Assistant through the Supervisor (no token needed); elsewhere, set `ha_url` and `ha_token` (a long-lived access token) on the app.

At 64×64 you'll recognise the scene (a car on the drive, someone at the door), not faces.

Back to the [README](../../README.md#configuration).

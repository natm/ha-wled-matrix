# Network screen

Internet speed and the line in use, drawn pixel by pixel. List the main line first and the backup second.

```yaml
internet_big:
  network:
    style: big                    # big = large download figure; alert = failover interrupt (below)
    unit_label: MBIT/S            # shown once; speeds are in the entities' unit
    backup_active: binary_sensor.internet_on_starlink   # on while the backup line carries the traffic
    links:
      - name: FTTP
        icon: mdi:cable-data
        down: sensor.router_wan1_rx
        up: sensor.router_wan1_tx
        latency: sensor.router_wan1_latency
        max_down: 1800            # line speed, for the fill bar along the bottom
      - name: STARLINK
        icon: mdi:satellite-variant
        down: sensor.router_wan2_rx
        up: sensor.router_wan2_tx
        latency: sensor.router_wan2_latency
internet_alert:                   # shows only during a failover, for up to 60 s
  priority: true
  show_if: binary_sensor.internet_on_starlink
  max_time: 60
  network: {style: alert, backup_active: binary_sensor.internet_on_starlink, links: [...same as above...]}
```

`big`: the line's name and latency (green under 25 ms, amber under 60, red above) along the top, download in large
blue digits, upload in orange, and a bar showing how full the main line is. On the backup line the name turns amber
and "FTTP DOWN" flashes along the bottom. `alert`: a red flashing border, "FTTP DOWN", "ON STARLINK" and the backup's
speeds. Without `backup_active`, the backup counts as in use whenever the main line has no data.

Back to the [README](../../README.md#configuration).

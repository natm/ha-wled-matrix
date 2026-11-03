# WLED Matrix

An [AppDaemon](https://appdaemon.readthedocs.io/) app that shows Home Assistant values on **WLED LED matrices** (e.g. the 64×64 [Apollo M-1](https://apolloautomation.com/)) as simple screens: up to three rows of **icon + big number + unit**, with screens on rotation.

![energy screen: battery 41%, load 8.2 kW, grid 0 W](docs/energy.png)

- Draws everything itself in pure Python (pixel fonts and 14×14 icons; no Pillow needed).
- Sends frames to WLED over **DDP** (UDP 4048), so WLED shows them as live data. If the app stops, WLED goes back to its own effect or preset after its realtime timeout.
- Colours can follow the value (thresholds), and an icon can fill to the value (e.g. a battery).
- Several matrices, each with its own screens and dwell time; an optional on/off entity per matrix.

## Install

**HACS (custom repository):** HACS → ⋮ → Custom repositories → add this repository with category **AppDaemon**, then download "WLED Matrix". HACS needs AppDaemon apps enabled in its settings.

**Manual:** copy `apps/wled_matrix/` into your AppDaemon `apps` folder.

Then add a config to your `apps.yaml`.

## Configuration

```yaml
wled_matrix:
  module: wled_matrix
  class: WledMatrix
  refresh: 1                  # seconds between frames; keep below WLED's ~2.5 s realtime timeout
  matrices:
    - host: 192.168.1.50      # WLED device
      width: 64
      height: 64
      dwell: 10               # seconds per screen when there's more than one
      screens: [energy]
      enabled_entity: input_boolean.kitchen_matrix   # optional: only draw while this is on
  screens:
    energy:
      rows:
        - icon: battery
          entity: sensor.battery_state_of_charge
          format: percent
          fill: true
          icon_colour: [200, 200, 200]
          thresholds:
            - {above: 50, colour: [0, 190, 0]}
            - {above: 25, colour: [230, 150, 0]}
          colour: [230, 0, 0]
        - icon: plug
          entity: sensor.house_load_power
          format: power
          colour: [255, 150, 0]
        - icon: pylon
          entity: sensor.grid_power
          format: power
          thresholds:
            - {above: 50, colour: [230, 0, 0]}
          colour: [0, 110, 255]
```

Row options:

| Key | Meaning |
|---|---|
| `icon` | `battery`, `plug`, `pylon`, `sun`, `thermometer` |
| `entity` | Any entity with a numeric state. Unavailable or non-numeric shows `-` |
| `format` | `percent` (0–100, `%`), `power` (W, or kW from 1000 W), `number`, `decimal1` |
| `unit` | Override the unit text (characters available: `% W k C ° h`) |
| `colour` | `[r, g, b]` default colour |
| `thresholds` | List of `{above, colour}`, checked top to bottom; the first one the value reaches wins |
| `fill`, `fill_max` | Fill the icon's fill area in proportion to the value (default max 100) |
| `icon_colour` | Draw the icon outline in a fixed colour instead of the row colour |

## Notes

- WLED needs "Receive UDP realtime" on (the default).
- One 64×64 frame is 12 KB, sent as 9 UDP packets; a refresh of 1 s is light on the network.

## Licence

MIT

# Home Assistant dashboard

Three things the app gives a dashboard: a **sensor per matrix** saying which screen is showing, a way to **pick a
screen to show now** from a card, and the **live picture** itself, either embedded from the live view or in a card.

## The sensor

Each matrix has a sensor, created by the app when it starts: `sensor.wled_matrix_<name>` (the matrix's `name`, lower
case, non-letters as `_`; the host if it has no name), or the entity you give as `state_entity`:

```yaml
  matrices:
    - host: 192.168.1.50
      name: Kitchen
      screens: [energy, radar, weather]
      # state_entity: sensor.kitchen_matrix        # optional: instead of sensor.wled_matrix_kitchen
      # select_entity: input_select.kitchen_matrix  # optional: pick a screen from Home Assistant (below)
```

| State | Meaning |
|---|---|
| a screen name | What the matrix is showing |
| `idle` | On, but nothing to show (every screen in its rotation is hidden by `show_if`) |
| `off` | Its `enabled_entity` is off |

Attributes: `host`, `width`, `height`, `screens` (its rotation), `pinned` (the screen picked from a dashboard, or
null), `next` (the screen after this one in the rotation), `enabled`. The sensor is written only when something
changes, so it costs nothing at one frame a second. It is an entity the app sets directly, so it has no settings
page in Home Assistant; it comes back whenever the app starts.

## Picking a screen to show now

Give a matrix a `select_entity`: an **input_select helper** (Settings → Devices & services → Helpers → Dropdown; any
options, the app replaces them). When the app starts it sets the options to `Auto` plus every screen in your config,
in alphabetical order. Choose a screen and the matrix shows it from the next frame, instead of its rotation and ahead
of any priority screen, until you choose `Auto` again. Picks made from the live view or the card set the helper too,
so every surface agrees.

Any screen in the config can be picked, not only the ones in that matrix's rotation; it is drawn at the matrix's size.

## Cards

The letters match the mockups the design started from.

### A. Entities card with a dropdown

```yaml
type: entities
title: Matrices
entities:
  - entity: input_select.kitchen_matrix
    name: Kitchen
    secondary_info: last-changed
  - entity: input_select.hall_matrix
    name: Hall
```

Each row is a dropdown of `Auto` and the screens. To show the screen *being displayed* as well, add the sensor rows
(`sensor.wled_matrix_kitchen`) above or use card E.

### E. Entities card: tap the screen name to pick

```yaml
type: entities
title: Matrices
entities:
  - entity: sensor.wled_matrix_kitchen
    name: Kitchen
    secondary_info: last-changed
    tap_action:
      action: more-info
      entity: input_select.kitchen_matrix
  - entity: sensor.wled_matrix_hall
    name: Hall
    tap_action:
      action: more-info
      entity: input_select.hall_matrix
```

The state column reads `energy`, `radar`, `off`; tapping a row opens the helper's dialog, where you pick a screen or
`Auto`. The stock dialog shows the options as a dropdown. For the flat list of the mockup (F) inside a stock card, use
a **Tile card** with the select feature, which lists every option as a button under the tile:

```yaml
type: tile
entity: input_select.hall_matrix
name: Hall
features:
  - type: select-options
```

### C. Webpage card: the live view, every matrix

Needs `web: true` on the app. The live view's **All** view shows each matrix's picture (as sent, about once a second),
its name, what it is showing or what comes next, and a picker; `embed=1` hides the header:

```yaml
type: iframe
url: http://<appdaemon host>:5050/app/matrix?view=all&embed=1
aspect_ratio: 50%
```

For one matrix in Mirror view: `http://<appdaemon host>:5050/app/matrix?embed=1` (the page remembers the matrix
you picked).

### D and F. The custom card

A card of its own: the live picture, what is showing and what comes next with a dwell bar, a picker, and a preview
control that draws any screen *in the card* without touching the panel. It talks to the live view directly, so it
needs no entity, only `web: true`.

1. Settings → Dashboards → ⋮ → Resources → Add: URL `http://<appdaemon host>:5050/app/matrix_card`, type
   *JavaScript module*. (Reload the dashboard once.)
2. Add the card:

```yaml
type: custom:wled-matrix-card
url: http://<appdaemon host>:5050/app
matrix: Kitchen        # name, host or index
picker: chips          # chips: a button per screen (D) | dialog: tap the status line for a list (F) | none
preview: true          # the "Preview here" control
fps: 2                 # how often the picture is fetched
```

`picker: dialog` is mockup F: the status line ("Showing energy · radar in 6 s") is the tap target and opens a dialog
listing `Auto` and every screen, the current one marked.

## Reaching AppDaemon from the dashboard

Cards C and D load from AppDaemon's web server, not from Home Assistant, so the browser showing the dashboard must
reach `http://<appdaemon host>:5050`. Two things can get in the way:

- **https.** A dashboard served over https (Nabu Casa, your own certificate) will not load http content. Either serve
  the dashboard over plain http on the LAN, or go through the AppDaemon add-on's **ingress**, which puts the live view
  under Home Assistant's own origin: open the add-on, *Open Web UI*, and use that address (it starts with
  `/api/hassio_ingress/`) as the base in the card and the Webpage card. The live view builds its links relative to its
  own path, so it works there unchanged.
- **Another device on the LAN.** The URL is resolved by the browser, so use the AppDaemon host's address as that
  browser sees it, not `localhost`.

The routes send `Access-Control-Allow-Origin: *`, so the card can call them from the dashboard's origin. The live view
has no login (AppDaemon's web server is local); the pick route changes what a matrix shows, nothing else.

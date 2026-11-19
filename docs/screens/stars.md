# Stars screen

Weekly star points for children: each child's stars this week (gold when earned, dim when not) and a yearly total,
plus a pop-up when a star is added or taken away. Keep the counts in Home Assistant counters (e.g. a weekly counter
with maximum 7 and a yearly one), and set the `alert` text (`child,+` or `child,-`) and an on/off helper from the
script that changes them.

```yaml
stars:
  stars:
    style: week
    most: 7                       # stars per week
    kids:
      - {id: seth, name: Seth, colour: [0, 170, 255], week: counter.seth_stars_week, year: counter.seth_stars_year}
      - {id: dylan, name: Dylan, colour: [0, 220, 90], week: counter.dylan_stars_week, year: counter.dylan_stars_year}
stars_alert:
  priority: true
  show_if: input_boolean.stars_alert_showing
  max_time: 20
  restart_on: [input_text.stars_alert, counter.seth_stars_week, counter.dylan_stars_week]   # each press shows it again
  frame_rate: 3                   # twinkles (still at night)
  stars: {style: alert, alert: input_text.stars_alert, kids: [...same as above...]}
```

A `+` shows a shooting star, WELL DONE and the name (a trophy and "7 STARS!" when the week is full); a `-` shows a
calm grey STAR OFF.

Back to the [README](../../README.md#configuration).

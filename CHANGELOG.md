# Changelog

## 0.3.1

- Added a main-zone Home Assistant remote for eISCP receivers, including OSD navigation, playback keys, safe volume steps, and configured input selection. TX-NR6050 is the reference model; supported keys vary with the receiver.
- Added a reusable example dashboard card that can target different Home Assistant remote entities.

## 0.3.0

- Renamed the integration and Home Assistant domain to **Onkyo Receiver Plus** (`onkyo_receiver_plus`).
- Added bundled Home Assistant icon and logo.
- Pull requests and branch pushes build tested manual-install and HACS ZIPs. Version tags create an unpublished GitHub release draft.
- This is a fresh installation for users of the earlier `onkyo_extended` build. The older entry and its entities are not modified or migrated automatically.

## 0.2.2

- Added AccuEQ, manual EQ presets, the digital filter, stereo speaker assignment, Cinema Filter, ARC, and signal-dependent DTS:X dialog control.
- Added HDMI sub-output routing, Network Standby status, and DTS:X Dialog Control availability.
- Diagnostic exports omit custom input and listening-mode labels.

## 0.2.1

- Added receiver temperature, firmware version, and speaker configuration.

## 0.2.0

- Grouped all entities per receiver and added more audio, video, tuner and setup controls for the TX-NR6050.
- Setup displays receiver-reported input names with their physical HDMI ports.

## 0.1.x

- Added the temporary subwoofer level, stepwise volume on the standard media player, and input naming.

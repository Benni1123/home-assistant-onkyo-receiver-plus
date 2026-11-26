# Changelog

## 0.5.6

- Split the DAB browser into All stations (cached full list) and Presets (actual AVR memory slots).
- Recall DAB hardware presets directly through PRS, without stepping or muting. Refresh preset metadata when opening the folder and verify the selected preset explicitly.
- Fix NRI preset IDs: these are hexadecimal, so `0e` is slot 14 and `28` is slot 40. Previously entries containing letters were ignored and numeric-looking IDs above 9 were misnumbered.

## 0.5.5

- Fix TuneIn navigation timeouts when the receiver shortens a folder title (for example, "Dance & Electronic" becomes "Dance "). Verify the selected row and the expected child menu layer instead of requiring identical header text.
- DAB station selection uses the shorter direction through the cached service list instead of always stepping forward; it does not rerun enumeration.

## 0.5.4

- Fix false FM tuning errors caused by old frequency reports arriving before the requested frequency. Serialize tuning requests and wait for an exact confirmation instead of accepting the first TUN reply.

## 0.5.3

- Display the current DAB service name when no track title is available. For FM, use the name saved for the actual tuned frequency, falling back to the frequency itself.
- Request tuner station metadata on source updates, including reconnects; ignore stale tuner replies on other sources.

## 0.5.2

- Added native device-page FM name/frequency fields, save/delete buttons and a saved-station editor; no developer tools required.
- Fixed the registered FM action handlers and async radio callbacks that could terminate the shared receiver connection.
- DAB enumeration now runs explicitly in the background with a device-page button and status sensor. Stepping is muted, including station selection; incomplete scans keep the previous cache.
- Fixed radio media IDs and search responses, and use name-based FM IDs to avoid selecting a different station after deletion.
- Removed recursive NET metadata queries, isolate failing status callbacks, retry dropped connections, and explicitly close the old connection task on unload.
- Fetch receiver artwork through the media-player image proxy, stripping CGI headers embedded in the JPEG body; refresh artwork on metadata changes.

## 0.5.1

- Added a DAB+ media browser: on first open the integration steps through the receiver's scanned services once (with the receiver muted, source and mute state restored afterwards), caches the list persistently, and then offers instant browsing and searching. A "Rescan services (muted)" entry refreshes the list after a new DAB scan.
- Added an integration-owned FM station book with user-chosen names and manual frequencies (87.5–108.0 MHz in 50 kHz steps), browsable and searchable even while the receiver is off. New services `save_fm_station` and `delete_fm_station` manage entries; the receiver's tuner presets are not modified.

## 0.5.0

- Fixed the remote entity: `remote.send_command` failed with a missing-argument error because Home Assistant passes the service data as keyword arguments.
- Show title, artist, album and album artwork for NET sources (TuneIn, Spotify, ...). The receiver's anonymous `album_art.cgi` endpoint provides the artwork.
- Added a tuner preset select listing the stored FM/AM/DAB presets with their receiver-reported names. The receiver provides no station lists, only presets; presets empty at first show up after storing them on the AVR.

## 0.4.2

- The eISCP media player now rejects unsupported `play_media` content (such as stream URLs) with a clear error instead of silently ignoring it, and tuner presets require an FM/AM/DAB input.

## 0.4.1

- Fetch the current TuneIn title even when playback was already active or started from the receiver, rather than waiting for Home Assistant to start a station.

## 0.4.0

- Added a TuneIn media browser for the TX-NR6050: receiver-reported categories, favorites and nested folders, pagination, and station playback.
- Added search within the open TuneIn category, or in Local Radio and My Presets when searching from the TuneIn root.
- Display the receiver-reported TuneIn title during playback.

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

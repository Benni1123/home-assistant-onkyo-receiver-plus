![Onkyo Receiver Plus](custom_components/onkyo_receiver_plus/brand/logo.png)

# Onkyo Receiver Plus

[Deutsch](README.de.md) · [Releases](https://github.com/Benni1123/home-assistant-onkyo-receiver-plus/releases) · [Builds](https://github.com/Benni1123/home-assistant-onkyo-receiver-plus/actions) · [Issues](https://github.com/Benni1123/home-assistant-onkyo-receiver-plus/issues)

**Local control and diagnostics for Onkyo AV receivers in Home Assistant.** Onkyo Receiver Plus builds on Home Assistant’s built-in Onkyo integration and adds receiver-specific controls and sensors. It connects directly over eISCP on your local network. No cloud account or receiver Web Setup login is required.

## Compatibility

- **Home Assistant:** 2026.11.3 or newer.
- **Tested receiver:** Onkyo TX-NR6050. Other eISCP-compatible Onkyo, Integra, and Pioneer models may work for basic controls. Advanced features and remote keys vary by model, firmware, input, and listening mode. Older Pioneer models that use the Pioneer protocol are not supported.
- **Network:** Home Assistant must be able to reach the receiver over TCP port `60128`. Receiver artwork additionally needs HTTP access to the AVR. Enable **Network Standby** on the receiver if you want Home Assistant to turn it on from standby.

## Features

Zones, controls, and sensors are grouped under one receiver device in Home Assistant.

| Area | What you can do |
| --- | --- |
| Media players / zones | Power, mute, volume, input selection and listening modes. Available zones are discovered and grouped under the same device. Extra controls and browsing target the main zone; do not assume every feature is available in Zone 2. |
| Volume | Immediate or confirmed stepwise adjustment using the **standard HA slider**, maximum-volume ceiling, adjustable step delay and receiver volume resolution. No separate custom slider required. |
| Input names | Receiver names and reported HDMI assignments, such as **HDMI 2 / Console**. Options refresh these over the shared connection when opened. Optional automatic name import and HDMI prefixes; custom HA aliases remain possible. |
| Subwoofer | Temporary trim: **−15 to +12 dB in 0.5 dB steps**. This is not permanent speaker calibration and resets in standby. |
| Tone / dialog / timing | Bass and treble (**−10 to +10 dB**), dialog level (**0–5**), DTS:X Dialog Control (**0–6 dB**, when available), A/V sync (**0–500 ms in 5 ms steps**). |
| Listening / EQ | Listening-mode selection, AccuEQ, manual EQ presets, digital filter, Late Night, stereo speaker assignment, Music Optimizer and Cinema Filter, subject to receiver/source support. |
| HDMI / display / sleep | HDMI output selection, HDMI audio output, HDMI-CEC, ARC, display brightness and sleep timer (**0–90 minutes**, 0 disables it). |
| Channel muting | Individual channel-mute switches where the receiver reports support. These are not channel calibration controls. |
| Remote | Navigate the receiver’s on-screen menus, select inputs, adjust volume, or send playback keys to compatible NET/USB sources. |
| TuneIn | Browse receiver-reported categories and favorites, search within a category, and start internet radio stations on the TX-NR6050. |
| DAB+ | **All stations**: persistent service cache, search and muted selection by the shorter direction through the list. **Presets**: freshly read AVR presets, selected directly by number without stepping. |
| FM station book | Name and frequency editor, saved-station selector, save/delete buttons on the device page; persistent browsing/search and direct frequency tuning. Stored in HA, separately from AVR presets. |
| Hardware tuner controls | Recall stored FM/AM/DAB presets by number or name; live FM frequency control (**87.5–108 MHz, 50 kHz grid**). Tuner controls require a suitable active input. |
| Media metadata / artwork | NET title, artist, album and receiver artwork when supplied. DAB service name and saved FM station name/frequency are title fallbacks. |
| Diagnostics | Audio format, input/output channels, video signal/HDR, internal temperature, firmware, speaker layout, HDMI sub-output routing, front display, Network Standby, DTS:X Dialog Control availability and DAB list-read status. |
| Lifecycle | Shared receiver connection, reconnection after network errors, options changes/reloading without restarting HA, and cleanup of connection tasks and callbacks. Installing updated Python code still requires an HA restart. |

Advanced TX-NR6050 controls depend on power, signal format, input and listening mode. An entity can therefore be unavailable even on a supported receiver. Browsing support is currently enabled for the tested TX-NR6050, not promised for every eISCP device.

## Volume and receiver names

Open the integration's **Configure / Options** dialog to choose inputs and listening modes, set the maximum volume, select immediate or stepwise volume and adjust the delay between steps. Keep the receiver's volume resolution consistent with your installation; the HA slider represents a percentage of the configured ceiling, not the AVR's numeric front-panel volume.

The input selector refreshes names and HDMI assignments when options are opened. For example, renaming GAME to Console on the AVR should show **HDMI 2 / Console** after closing and reopening options, without reloading the integration. Automatic import supplies defaults for newly added inputs; deliberately configured HA aliases are preserved. The following name-editing step also allows custom input and listening-mode labels. These HA labels do not rename the AVR.

Options changes and ordinary integration reloads do not require an HA restart. **After installing/updating integration files, restart HA to load the changed Python code.**

## Titles and cover artwork

For NET sources, title, artist and album are shown when the receiver supplies them. Artwork comes from the AVR's `http://<AVR-IP>/album_art.cgi` endpoint through HA's media-image proxy; the integration handles the receiver's embedded CGI header text and refreshes the image on metadata changes.

When no track title is available, DAB shows the current service name. FM uses a saved name matching the actual frequency, then a reported preset name if available, otherwise the frequency itself. This does **not** add DAB song-title/DLS retrieval: that has not been verified. Not every source provides an image or complete metadata, and Cast playback has its own media entity.

## DAB+ and FM radio browsing

Open the main-zone media player and choose **Browse media → DAB+ Radio**:

- **All stations:** the complete list previously read into HA. Searching uses this local cache. Selecting a service steps silently in the shorter direction through the cached order; it does **not** run a new enumeration. A long distance can still take time.
- **Presets:** actual DAB memory slots stored on the receiver, for example **14: SPUTNIK**. Opening the folder refreshes them from the AVR. Selection directly recalls the slot, without stepping or mute changes. To add a preset, store the desired service on the receiver first; the folder does not create or overwrite AVR presets.

### Read the DAB service list

1. First run a normal DAB antenna scan on the receiver if it has not already found your services.
2. Turn on the receiver. On its **HA device page**, press **Read DAB service list (muted)**.
3. Watch **DAB list status** for progress, completion or the actual error.
4. Open **DAB+ Radio → All stations**. The list survives integration reloads and HA restarts.

This background read switches to DAB if needed and cycles through the existing services with confirmed muting. It restores the previous source and mute state afterwards; the volume level is not changed. It can interrupt another source's playback, and switching back is not a guarantee that an external stream resumes. An incomplete run does not overwrite the previous list. Repeat after changing the receiver's scanned service list.

**This is not an over-the-air scan button.** No direct DAB antenna-scan command has been verified over eISCP or Web Setup. The AVR also has no verified direct network command to retrieve the complete DAB service list, which is why enumeration is used. Direct preset selection is the faster alternative for favorites.

### Maintain the FM station book

For **FM Radio (own list)**, use the device-page **FM station name** and **FM station frequency** fields, then **Save FM station**. Select a saved station under **Edit FM station** to load its fields; save again to update its frequency, or press **Delete FM station**. Stations are stored persistently in HA; the AVR's hardware presets are not modified. The `save_fm_station` / `delete_fm_station` actions remain available for automations. Playing a station from the media browser selects FM and tunes the frequency.

- Frequencies: **87.5–108 MHz**, normalized to a **50 kHz grid**; up to **60 stations**, names up to **64 characters**.
- Saving an existing name updates its frequency (name matching is case-insensitive). A different name creates another entry.
- Saving/editing is local to HA and does not start playback. The **FM station frequency** editor is distinct from the receiver's **FM frequency** control, which tunes immediately.
- The saved FM list can be browsed/searched while the receiver is off. Turn it on before playback; tuning waits for confirmation of the requested frequency.

## Streaming URLs via Google Cast

The eISCP media player does **not** accept arbitrary MP3/stream URLs; unsupported content produces a clear error. A TX-NR6050 with **Chromecast built-in** can instead use HA's separate **Google Cast integration**. Send the URL to that Cast media player, not to the Receiver Plus entity. [Radio Browser](https://www.home-assistant.io/integrations/radio_browser/) is another way to find streams for the Cast player.

```yaml
action: media_player.play_media
target:
  entity_id: media_player.receiver_cast  # Replace with the Google Cast entity
data:
  media_content_id: https://example.com/live.mp3  # Replace with a real direct stream
  media_content_type: music
```

If discovery misses the Cast player, open **Settings → Devices & services → Google Cast → Options**, add the AVR's address to **Known hosts**, check that any allowed-device filter permits it, and reload Cast. Network reachability and Cast support must still be available. Playback is handled by Cast; receiver power/volume controls remain available in Receiver Plus. Switching to another input or opening native TuneIn can interrupt a Cast session.

## Installation

### HACS / Home Assistant Marketplace

Add `https://github.com/Benni1123/home-assistant-onkyo-receiver-plus` as a **custom repository** of type **Integration**, then install **Onkyo Receiver Plus** and restart HA. The HACS package is `onkyo_receiver_plus.zip` in a **published** GitHub release. A pushed tag or draft release alone is not an available HACS update; see [Latest release](https://github.com/Benni1123/home-assistant-onkyo-receiver-plus/releases/latest). Custom-repository installation does not imply inclusion in HACS's default catalog.

### Manual installation

1. Download **`onkyo_receiver_plus-ha.zip`** from [Releases](https://github.com/Benni1123/home-assistant-onkyo-receiver-plus/releases). To test a build before release, open a successful run under [Actions](https://github.com/Benni1123/home-assistant-onkyo-receiver-plus/actions), download the artifact, and find the `-ha.zip` inside it.
2. Extract it into your Home Assistant configuration directory so that `custom_components/onkyo_receiver_plus/manifest.json` is present. If installing from source, copy the `custom_components/onkyo_receiver_plus` directory instead.

### Set up the receiver

1. If another integration controls the **same receiver**, disable its entry before enabling this one. Competing eISCP connections can interfere. You can leave the old entry disabled for rollback.
2. Restart Home Assistant. Go to **Settings → Devices & services → Add integration → Onkyo Receiver Plus**.
3. Enter the receiver’s address or use eISCP discovery. Select the inputs and listening modes you want to expose. Supported receivers show their reported names and HDMI ports in the input selector.
4. Use **Configure** to set your volume limit, ramp delay, input labels, and HDMI prefixes. If you are moving from an existing Onkyo integration, start with the same volume resolution. This integration uses a separate HA domain, so check any dashboards or automations that reference the old entity IDs.

## Remote example

Use `remote.send_command` in an automation, script, or dashboard button. Replace the example entity ID with the remote shown on your receiver’s device page.

```yaml
action: remote.send_command
target:
  entity_id: remote.living_room_receiver
data:
  command: quick_menu
```

Other keys include `up`, `down`, `left`, `right`, `ok`, `back`, `setup`, `mute`, `volume_up`, `volume_down`, `power_on`, and `power_off`. Use `input:<name>` to select a configured input. Compatible NET/USB sources also support playback keys such as `play`, `pause`, and `next_track`.

Playback keys: `play`, `pause`, `play_pause`, `stop`, `next_track`, `previous_track`. Aliases: `enter` → `ok`, `exit` → `back`, `menu` → `setup`, `quick` → `quick_menu`. Commands may be sent as a list with `num_repeats` and `delay_secs`; `hold_secs` is not supported. The remote entity's `commands` attribute lists supported command names. Sending OSD keys does not provide a readable menu or highlighted-item state.

The [example dashboard card](examples/remote-card.yaml) uses standard Home Assistant buttons. Change the target at the `&receiver_remote` YAML anchor to reuse the card for another receiver.

## TuneIn internet radio

Turn on the receiver and open **Browse media → TuneIn Radio** on its main-zone media player. Select a category such as **My Presets**, **Local Radio**, or **By Location**, then pick a station. Large lists have additional pages.

Search filters the open category. From the TuneIn root it also searches **Local Radio** and **My Presets**; it is not a global TuneIn catalog search. Navigation uses the receiver’s own TuneIn menu: opening TuneIn switches to NET if necessary and may interrupt playback on another source. It does not change the volume or modify presets.

TuneIn's **My Presets** are internet-radio favorites, separate from the AVR's hardware FM/AM/DAB presets. Station selection verifies the original list item before playing it; a changed list can require reopening the folder. USB/DLNA browsing is not implemented just because remote playback keys are available for those inputs.

## Automation actions

Device-page controls are sufficient for normal radio editing. For automations, the station-book actions use `entity_id` **inside `data`**, not a `target` block:

```yaml
action: onkyo_receiver_plus.save_fm_station
data:
  entity_id: media_player.receiver  # Receiver Plus entity, not Cast
  name: Example FM
  frequency: 89.0
```

Use `onkyo_receiver_plus.delete_fm_station` with the same `entity_id` and `name` fields to remove an entry. Neither action changes AVR presets or tunes the receiver.

For stored AVR presets, `media_player.play_media` with `media_content_type: radio` and a preset number as `media_content_id` recalls a slot while a tuner input is active. Prefer the DAB Presets browser for DAB favorites. The legacy `media_player.onkyo_receiver_plus_select_hdmi_output` action remains for existing automations; the HDMI output select entity is the easier interactive control.

## Troubleshooting

- **Cannot connect:** Check the receiver’s IP, port `60128`, Network Standby, and whether another integration is connected to the same receiver.
- **A setting is unavailable:** Some settings require the main zone to be on or a matching input or signal. The temperature sensor updates once a minute while the main zone is on. HDMI-CEC, ARC, and the front-display sensor are disabled by default.
- **Volume looks wrong:** Check the volume resolution and the maximum volume setting. The HA slider is a percentage of the configured ceiling, not a direct readout of the receiver’s front-panel scale.
- **Input was renamed on the AVR:** Close and reopen options to fetch fresh labels. A deliberately configured HA alias takes precedence over automatic import.
- **DAB selection takes time:** All stations uses muted stepping; use AVR presets for direct selection. An empty list needs **Read DAB service list (muted)**, not an HA restart. The status sensor distinguishes actual read errors from an empty cache.
- **No song title / cover:** Metadata depends on the active source. DAB service-name fallback is not song-title support. Verify HA can reach the AVR's artwork endpoint; the Cast entity has its own metadata.
- **Options or reload fail:** Update to at least 0.5.7 and restart once to load the fix. It corrects the FM/DAB cleanup callback that caused `a coroutine was expected` errors. Subsequent ordinary reloads should not require an HA restart.
- **Reporting a problem:** Include the receiver model and firmware, HA and integration versions, and steps to reproduce. Remove addresses, device names, and other private information from any debug logs before sharing them.

### Boundaries

- Permanent speaker calibration, separate front L/R trim and AVR Web Setup editing are not implemented.
- Reading the DAB cache does not perform an antenna scan. Arbitrary DAB services are not directly addressable by a verified command; stored presets are.
- NET metadata and individual sound/HDMI controls are not guaranteed on every model or source. Some controls are intentionally disabled by default.

## Development and license

Run the test suite without a receiver:

```sh
uv run --python 3.14 --with-requirements requirements-test.txt python -m unittest discover -s tests -v
python scripts/build_release.py
```

The build script writes both installation ZIPs and SHA-256 checksums to `dist/`. GitHub Actions runs the tests and packages on pushes and pull requests. A version tag that matches `manifest.json` creates a release draft with both ZIPs.

See the [changelog](CHANGELOG.md), [Apache-2.0 license](LICENSE), and [source attribution](NOTICE). This is an independent project and is not affiliated with Onkyo or Home Assistant.

![Onkyo Receiver Plus](custom_components/onkyo_receiver_plus/brand/logo.png)

# Onkyo Receiver Plus

[Deutsch](README.de.md) · [Releases](https://github.com/Benni1123/home-assistant-onkyo-receiver-plus/releases) · [Builds](https://github.com/Benni1123/home-assistant-onkyo-receiver-plus/actions) · [Issues](https://github.com/Benni1123/home-assistant-onkyo-receiver-plus/issues)

**Local control and diagnostics for Onkyo AV receivers in Home Assistant.** Onkyo Receiver Plus builds on Home Assistant’s built-in Onkyo integration and adds receiver-specific controls and sensors. It connects directly over eISCP on your local network. No cloud account or receiver Web Setup login is required.

## Compatibility

- **Home Assistant:** 2026.11.3 or newer.
- **Tested receiver:** Onkyo TX-NR6050. Other eISCP-compatible Onkyo, Integra, and Pioneer models may work for basic controls. Advanced features and remote keys vary by model, firmware, input, and listening mode. Older Pioneer models that use the Pioneer protocol are not supported.
- **Network:** Home Assistant must be able to reach the receiver over TCP port `60128`. Enable **Network Standby** on the receiver if you want Home Assistant to turn it on from standby.

## Features

Zones, controls, and sensors are grouped under one receiver device in Home Assistant.

| Area | What you can do |
| --- | --- |
| Media player | Control power, mute, volume, inputs, and listening modes. Choose immediate or stepwise volume on the standard Home Assistant slider. Both modes respect the configured volume limit. Shows title, artist, album and artwork for NET sources such as TuneIn or Spotify. |
| Input names | Import receiver names and reported HDMI assignments, such as **HDMI 1 / Media Player**. Set your own labels in Home Assistant without renaming inputs on the receiver. |
| Sound | Adjust temporary subwoofer level, bass, treble, vocal level, A/V sync, and Late Night mode. Select AccuEQ, manual EQ presets, and the digital filter where available. |
| Remote | Navigate the receiver’s on-screen menus, select inputs, adjust volume, or send playback keys to compatible NET/USB sources. |
| TuneIn | Browse receiver-reported categories and favorites, search within a category, and start internet radio stations on the TX-NR6050. |
| Other controls | Switch HDMI outputs, set display brightness or a sleep timer, select radio presets with their receiver-reported names, or tune the FM frequency. |
| Diagnostics | Read audio/video signal details, internal temperature, firmware version, configured speakers, HDMI output routing, and Network Standby status. |

The temporary subwoofer trim is separate from speaker calibration and resets in standby. Permanent speaker calibration and separate front L/R trim are not supported. The remote can send menu keys but cannot determine which menu item is highlighted. The receiver exposes no FM/DAB station lists — only the presets stored on the AVR itself.

## DAB+ and FM radio browsing

**DAB+ Radio** contains two folders: **All stations** lists the cached service list (selection by muted stepping). **Presets** lists actual DAB presets stored on the AVR, for example **14: SPUTNIK**. Presets are recalled directly by number, without stepping or muting, and are read afresh when the folder is opened.

On the receiver's **Home Assistant device page**, press **Read DAB service list (muted)** while the receiver is on. The integration reads existing DAB services by stepping silently in the background; **DAB list status** shows progress or the actual error. This does not start an over-the-air DAB scan. The previous source and mute state are restored afterwards. Browse the cached list under **Browse media → DAB+ Radio**. Station selection also steps muted. An incomplete enumeration does not overwrite the previous list.

For **FM Radio (own list)**, use the device-page **FM station name** and **FM station frequency** fields, then **Save FM station**. Select a saved station under **Edit FM station** to load its fields; save again to update its frequency, or press **Delete FM station**. Stations are stored persistently in HA; the AVR's hardware presets are not modified. The `save_fm_station` / `delete_fm_station` actions remain available for automations. Playing a station from the media browser selects FM and tunes the frequency.

## Streaming URLs via Google Cast

The eISCP protocol cannot play arbitrary stream URLs, so this integration rejects them with a clear error. Most TX-NR6050 receivers also expose **Chromecast built-in**, which Home Assistant shows as its own media player. Send `media_player.play_media` with an MP3/AAC stream URL to that player instead — for example a station from the [Radio Browser](https://www.home-assistant.io/integrations/radio_browser/) integration.

If the cast player does not appear, discovery may be blocked in your network. Open **Settings → Devices & services → Google Cast → ⚙ Options**, add the receiver's IP (for example `10.0.0.249`) to **Known hosts**, and reload. Cast volume is separate from the receiver's main volume controlled by this integration.

## Installation

### HACS / Home Assistant Marketplace

Add `https://github.com/Benni1123/home-assistant-onkyo-receiver-plus` as a **custom repository** of type **Integration**, then install **Onkyo Receiver Plus**. The HACS package is `onkyo_receiver_plus.zip` in a **published** GitHub release. If no release is published yet, use the manual build below.

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

The [example dashboard card](examples/remote-card.yaml) uses standard Home Assistant buttons. Change the target at the `&receiver_remote` YAML anchor to reuse the card for another receiver.

## TuneIn internet radio

Turn on the receiver and open **Browse media → TuneIn Radio** on its main-zone media player. Select a category such as **My Presets**, **Local Radio**, or **By Location**, then pick a station. Large lists have additional pages.

Search filters the open category. From the TuneIn root it also searches **Local Radio** and **My Presets**; it is not a global TuneIn catalog search. Navigation uses the receiver’s own TuneIn menu: opening TuneIn switches to NET if necessary and may interrupt playback on another source. It does not change the volume or modify presets.

## Troubleshooting

- **Cannot connect:** Check the receiver’s IP, port `60128`, Network Standby, and whether another integration is connected to the same receiver.
- **A setting is unavailable:** Some settings require the main zone to be on or a matching input or signal. The temperature sensor updates once a minute while the main zone is on. HDMI-CEC, ARC, and the front-display sensor are disabled by default.
- **Volume looks wrong:** Check the volume resolution and the maximum volume setting. The HA slider is a percentage of the configured ceiling, not a direct readout of the receiver’s front-panel scale.
- **Reporting a problem:** Include the receiver model and firmware, HA and integration versions, and steps to reproduce. Remove addresses, device names, and other private information from any debug logs before sharing them.

## Development and license

Run the test suite without a receiver:

```sh
uv run --python 3.14 --with-requirements requirements-test.txt python -m unittest discover -s tests -v
python scripts/build_release.py
```

The build script writes both installation ZIPs and SHA-256 checksums to `dist/`. GitHub Actions runs the tests and packages on pushes and pull requests. A version tag that matches `manifest.json` creates a release draft with both ZIPs.

See the [changelog](CHANGELOG.md), [Apache-2.0 license](LICENSE), and [source attribution](NOTICE). This is an independent project and is not affiliated with Onkyo or Home Assistant.

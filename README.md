# Onkyo Receiver Plus für Home Assistant

![Onkyo Receiver Plus](custom_components/onkyo_receiver_plus/brand/logo.png)

Custom-Integration auf Basis von Home Assistant **Core 2026.11.3** für den **TX-NR6050**. Steuert den Receiver lokal per eISCP. Kein Web-Login erforderlich. Benötigt Home Assistant **2026.11.3 oder neuer**.

- **Subwoofer-Pegel (temporär):** eigener dB-Regler von −15 bis +12 dB, in 0,5-dB-Schritten. Der Zustand kommt vom Receiver; Standby setzt den temporären Pegel zurück.
- **Hauptlautstärke:** **Sofort** (Standard) oder **Schrittweise** mit einstellbarer Pause. Die Rampe wartet auf die Rückmeldung des Receivers und stoppt, wenn sie ausbleibt. Ein neues Ziel ersetzt das alte. Das konfigurierte Lautstärkelimit gilt in beiden Modi.
- **Eingänge:** Die gewünschten Eingänge in den Optionen auswählen. Beim Verbindungsaufbau übernimmt Home Assistant standardmäßig die Eingangsnamen und HDMI-Zuordnung des Receivers (z. B. **HDMI 1 / Google TV**). Unter **Eingangsnamen** kannst du eigene HA-Namen setzen; sie haben Vorrang vor den Receiver-Namen. Die übliche Aktion `media_player.select_source` akzeptiert auch den Namen ohne HDMI-Präfix.
- **Weitere TX-NR6050-Entitäten:** Bass/Höhen, Dialogpegel, A/V Sync, Nachtmodus, Music Optimizer, Dimmer, Einschlaftimer, HDMI-Ausgang, Radio-Speicherplatz und UKW-Frequenz. Dazu kommen Sensoren für Audio-/Video-Signal und Kanalzahl. Frontdisplay, HDMI-CEC und HDMI-Audioausgabe sind standardmäßig deaktiviert und können bei Bedarf aktiviert werden. Manche Regler sind nur im passenden Eingangs- oder Hörmodus verfügbar.
- **Ein Gerät:** Hauptzone, zusätzliche Zonen und alle Regler und Sensoren gehören demselben Gerät in Home Assistant.
- **Diagnose:** Interne Receiver-Temperatur (°C, bei eingeschalteter Hauptzone einmal pro Minute), Firmware-Version und erkannte Lautsprecherkonfiguration. Diese Sensoren ändern keine Receiver-Einstellungen.
- **Raumklang und HDMI:** AccuEQ, EQ-Presets, Digitalfilter, Stereo-Lautsprecherzuordnung und Cinema Filter. DTS:X Dialog Control ist nur verfügbar, wenn das Signal es unterstützt. Die HDMI-Zonenzuordnung und der Netzwerk-Standby sind reine Statusanzeigen; der ARC-Schalter ist standardmäßig deaktiviert.
- **Fernbedienung:** Eigene `remote`-Entität mit Menü-Navigation, Ein/Aus, Stummschaltung, Lautstärkeschritten, Eingangswahl und Wiedergabetasten für kompatible NET-/USB-Quellen.

## Manuell installieren

1. `onkyo_receiver_plus-ha.zip` in `/config` entpacken. Alternativ den Ordner `custom_components/onkyo_receiver_plus` nach `/config/custom_components/` kopieren.
2. Den bisherigen Eintrag (**Onkyo** oder **Onkyo Extended**) für diesen Receiver **deaktivieren**, nicht löschen. Zwei aktive Verbindungen können sich je nach Firmware stören.
3. Home Assistant neu starten.
4. Unter **Einstellungen → Geräte & Dienste → Integration hinzufügen** nach **Onkyo Receiver Plus** suchen, dann die IP manuell eingeben oder den Receiver suchen lassen. Dieselbe Lautstärkeauflösung wie beim bisherigen Onkyo-Eintrag wählen.
5. Über **Konfigurieren** Lautstärkelimit, **Sofort/Schrittweise**, Schritt-Pause und Eingänge festlegen. Bei dieser separaten Integration können sich die Entitäts-IDs ändern; Dashboards und Automationen gegebenenfalls auf die neuen Entitäten umstellen.

Für die Installation über **HACS/Marketplace** das öffentliche Repository als benutzerdefinierte Integration hinzufügen, sobald der erste Release veröffentlicht ist. `onkyo_receiver_plus.zip` ist das HACS-Paket; für die manuelle Installation bitte die Variante mit `-ha.zip` verwenden.

## Fernbedienung

Die Entität erscheint am TX-NR6050-Gerät. Über `remote.send_command` lassen sich `up`, `down`, `left`, `right`, `ok`, `back`, `setup`, `quick_menu`, `mute`, `volume_up`, `volume_down`, `power_on`, `power_off` und bei passender Quelle `play`, `pause`, `play_pause`, `stop`, `previous_track` oder `next_track` senden. `input:Google TV` wählt einen in Home Assistant konfigurierten Eingang. Die Lautstärketasten verwenden denselben Grenzwert wie der Medienplayer.

```yaml
action: remote.send_command
target:
  entity_id: remote.tx_nr6050_fernbedienung
data:
  command: quick_menu
```

Die Entitäts-ID ggf. ersetzen. `command` kann auch eine Liste sein; `delay_secs` und `num_repeats` steuern die Pause und Wiederholungen, jeweils mit insgesamt höchstens 32 Tastenbefehlen. Menü-Tasten bedienen das sichtbare Receiver-Menü, lesen dessen Position jedoch nicht zurück. Die Menü-Tastenbelegung wird bei unterstützten eISCP-Receivern aus deren Geräteinformationen übernommen.

Die [Beispielkarte](examples/remote-card.yaml) nutzt nur eingebaute HA-Karten. Vor dem Einfügen in eine manuelle Dashboard-Karte das Ziel beim YAML-Anker `&receiver_remote` ändern; die übrigen Buttons verwenden dieselbe Entität. So kann eine zweite Karte auf einen anderen AVR zeigen. Die Remote-Entität wird auch bei weiteren eISCP-Receivern angelegt; welche Tasten wirken, ist modellabhängig. AVRs mit anderen Protokollen benötigen eine eigene HA-Integration mit `remote.*`; deren Tastennamen bei Bedarf in `data.command` anpassen.

## Grenzen

Kein temporärer Front-Pegelregler: Der TX-NR6050 meldet dafür keinen separaten eISCP-Pegel. Kein automatisiertes Navigieren im TV-Menü. Die getrennten, dauerhaften L/R/Sub-Kalibrierwerte sind über Web Setup lesbar (`probe_calibration.py`), aber nicht Teil dieser Integrationsversion. Web Setup verwendet HTTP Basic Auth ohne Transportverschlüsselung; nur im eigenen vertrauenswürdigen Netz verwenden.

Die Originaldateien der Onkyo-Integration stammen aus [Home Assistant Core 2026.11.3](https://github.com/home-assistant/core/tree/2026.11.3/homeassistant/components/onkyo), lizenziert unter Apache 2.0 ([LICENSE](LICENSE)).

## Tests und Fehlermeldungen

Diese Erweiterungen wurden für den TX-NR6050 entwickelt. Andere Modelle und Firmware-Versionen sind nicht als unterstützt bestätigt. Die zusätzlichen Steuerbefehle können je nach Hörmodus oder Eingang nicht verfügbar sein. `uv run --python 3.14 --with-requirements requirements-test.txt python -m unittest discover -s tests -v` führt die lokalen Tests ohne Receiver aus.

Für Fehlermeldungen bitte Modell, Home-Assistant-Version, Integrationsversion und die Schritte zum Reproduzieren angeben. Vor dem Teilen eines Debug-Protokolls IP-Adressen, Gerätenamen und andere private Angaben entfernen.

## GitHub-Builds

- **Pull Requests und Pushes:** Der Workflow testet den Code und stellt unter **Actions → Artifacts** beide Installations-ZIPs bereit.
- **Versionstags**, z. B. `v0.3.0`: Der Tag muss zur Version in `manifest.json` passen. Der Workflow erstellt automatisch einen **Release-Entwurf** mit beiden ZIPs und SHA‑256-Prüfsummen. Erst das manuelle Veröffentlichen des Entwurfs macht ihn in GitHub Releases und HACS sichtbar.
- **Lokal:** `python scripts/build_release.py` erzeugt dieselben Dateien unter `dist/`. `scripts/build_brand.py` rendert bei Bedarf das Logo neu (Pillow erforderlich).

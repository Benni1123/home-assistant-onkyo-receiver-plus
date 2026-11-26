![Onkyo Receiver Plus](custom_components/onkyo_receiver_plus/brand/logo.png)

# Onkyo Receiver Plus

[English](README.md) · [Releases](https://github.com/Benni1123/home-assistant-onkyo-receiver-plus/releases) · [Builds](https://github.com/Benni1123/home-assistant-onkyo-receiver-plus/actions) · [Fehler melden](https://github.com/Benni1123/home-assistant-onkyo-receiver-plus/issues)

**Lokale Steuerung und Diagnose für Onkyo-AV-Receiver in Home Assistant.** Onkyo Receiver Plus baut auf der eingebauten Onkyo-Integration auf und ergänzt Regler und Sensoren. Die Verbindung läuft direkt über eISCP im lokalen Netz. Ein Cloud-Konto oder ein Login für Web Setup ist nicht nötig.

## Kompatibilität

- **Home Assistant:** 2026.11.3 oder neuer.
- **Getesteter Receiver:** Onkyo TX-NR6050. Bei anderen eISCP-fähigen Onkyo-, Integra- und Pioneer-Modellen können die Grundfunktionen ebenfalls funktionieren. Zusatzfunktionen und Fernbedienungstasten hängen von Modell, Firmware, Eingang und Hörmodus ab. Ältere Geräte mit dem Pioneer-Protokoll werden nicht unterstützt.
- **Netzwerk:** Der Receiver muss von Home Assistant aus über TCP-Port `60128` erreichbar sein. Zum Einschalten aus dem Standby muss am Receiver **Netzwerk-Standby** aktiviert sein.

## Funktionen

Zonen, Bedienelemente und Sensoren werden in Home Assistant unter einem Receiver-Gerät gruppiert.

| Bereich | Funktionen |
| --- | --- |
| Medienplayer | Ein/Aus, Stummschaltung, Lautstärke, Eingänge und Hörmodi. Der normale HA-Slider kann sofort oder schrittweise regeln. Das eingestellte Lautstärkelimit gilt in beiden Modi. |
| Eingangsnamen | Namen und gemeldete HDMI-Zuordnungen übernehmen, z. B. **HDMI 1 / Medienplayer**. Eigene Namen nur für HA vergeben, ohne die Bezeichnung am Receiver zu ändern. |
| Klang | Temporären Subwoofer-Pegel, Bass, Höhen, Dialogpegel, A/V-Sync und Nachtmodus einstellen. Je nach Modell und Hörmodus stehen AccuEQ, manuelle EQ-Presets und der Digitalfilter zur Verfügung. |
| Fernbedienung | Das Receiver-Menü bedienen, Eingänge wählen, Lautstärke ändern und Wiedergabetasten an kompatible NET-/USB-Quellen senden. |
| TuneIn | Am TX-NR6050 die vom Receiver gemeldeten Kategorien und Favoriten öffnen, im gewählten Ordner suchen und Internetradio starten. |
| Weitere Regler | HDMI-Ausgang, Display-Helligkeit, Einschlaftimer, Radio-Speicherplätze und UKW-Frequenz einstellen. |
| Diagnose | Audio-/Video-Signal, interne Temperatur, Firmware, Lautsprecherkonfiguration, HDMI-Zonenzuordnung und Netzwerk-Standby auslesen. |

Der temporäre Subwoofer-Pegel ist von der Einmessung getrennt und wird im Standby zurückgesetzt. Die dauerhafte Lautsprecherkalibrierung und getrennte Front-L/R-Pegel werden nicht unterstützt. Die Fernbedienung kann Menütasten senden, aber nicht erkennen, welcher Menüpunkt ausgewählt ist.

## Installation

### HACS / Home Assistant Marketplace

`https://github.com/Benni1123/home-assistant-onkyo-receiver-plus` als **benutzerdefiniertes Repository** vom Typ **Integration** hinzufügen und **Onkyo Receiver Plus** installieren. HACS verwendet `onkyo_receiver_plus.zip` aus einem **veröffentlichten** Release. Falls noch kein Release veröffentlicht ist, nutze den manuellen Build.

### Manuell

1. **`onkyo_receiver_plus-ha.zip`** aus den [Releases](https://github.com/Benni1123/home-assistant-onkyo-receiver-plus/releases) herunterladen. Für einen Test vor dem Release unter [Actions](https://github.com/Benni1123/home-assistant-onkyo-receiver-plus/actions) einen erfolgreichen Lauf öffnen, das Artefakt herunterladen und darin die Datei mit `-ha.zip` auswählen.
2. Die Datei ins Home-Assistant-Konfigurationsverzeichnis entpacken. Danach muss `custom_components/onkyo_receiver_plus/manifest.json` vorhanden sein. Alternativ aus dem Quellcode den Ordner `custom_components/onkyo_receiver_plus` kopieren.

### Receiver einrichten

1. Wenn eine andere Integration **denselben Receiver** steuert, deren Eintrag erst deaktivieren. Zwei gleichzeitige eISCP-Verbindungen können sich stören. Der deaktivierte Eintrag kann als Rückfalloption erhalten bleiben.
2. Home Assistant neu starten. Unter **Einstellungen → Geräte & Dienste → Integration hinzufügen** nach **Onkyo Receiver Plus** suchen.
3. Die Adresse manuell eingeben oder den Receiver suchen lassen. Dann die gewünschten Eingänge und Hörmodi auswählen. Unterstützte Geräte zeigen bei der Auswahl ihre gemeldeten Eingangsnamen und HDMI-Buchsen an.
4. Unter **Konfigurieren** Lautstärkelimit, Schritt-Pause, eigene Eingangsnamen und HDMI-Präfixe festlegen. Beim Wechsel von der bisherigen Onkyo-Integration zunächst dieselbe Lautstärkeauflösung wählen. Diese Integration hat eine eigene HA-Domain; bestehende Dashboards und Automationen gegebenenfalls auf die neuen Entitäts-IDs umstellen.

## Beispiel: Fernbedienung

`remote.send_command` funktioniert in Automationen, Skripten und Dashboard-Tasten. Die Beispiel-ID durch die Fernbedienungsentität auf der Geräteseite ersetzen.

```yaml
action: remote.send_command
target:
  entity_id: remote.wohnzimmer_receiver
data:
  command: quick_menu
```

Weitere Tasten sind unter anderem `up`, `down`, `left`, `right`, `ok`, `back`, `setup`, `mute`, `volume_up`, `volume_down`, `power_on` und `power_off`. `input:<Name>` wählt einen konfigurierten Eingang. Kompatible NET-/USB-Quellen unterstützen auch Wiedergabetasten wie `play`, `pause` und `next_track`.

Die [Beispielkarte](examples/remote-card.yaml) nutzt eingebaute HA-Tasten. Ändere das Ziel am YAML-Anker `&receiver_remote`, um die Karte für einen anderen Receiver zu verwenden.

## TuneIn-Internetradio

Den Receiver einschalten und beim Medienplayer der Hauptzone **Medien durchsuchen → TuneIn Radio** öffnen. Eine Kategorie wie **My Presets**, **Local Radio** oder **By Location** wählen und dann den gewünschten Sender anklicken. Für große Listen gibt es weitere Seiten.

Die Suche durchsucht den geöffneten Ordner. In der TuneIn-Übersicht sucht sie zusätzlich in **Local Radio** und **My Presets**, nicht im gesamten TuneIn-Katalog. Beim Öffnen von TuneIn schaltet die Integration bei Bedarf auf NET um; das kann andere Wiedergabe unterbrechen. Lautstärke und gespeicherte Sender bleiben unverändert.

## Hilfe bei Problemen

- **Keine Verbindung:** IP-Adresse, Port `60128` und Netzwerk-Standby prüfen. Sicherstellen, dass keine zweite Integration mit demselben Receiver verbunden ist.
- **Regler nicht verfügbar:** Einige Einstellungen benötigen eine eingeschaltete Hauptzone, einen bestimmten Eingang oder ein passendes Signal. Der Temperatursensor aktualisiert sich bei eingeschalteter Hauptzone einmal pro Minute. HDMI-CEC, ARC und der Frontdisplay-Sensor sind standardmäßig deaktiviert.
- **Lautstärkeanzeige stimmt nicht:** Lautstärkeauflösung und Lautstärkelimit prüfen. Der HA-Slider zeigt einen Prozentsatz des eingestellten Limits, nicht direkt die Skala auf dem Receiver-Display.
- **Fehler melden:** Receiver-Modell und Firmware, HA- und Integrationsversion sowie Schritte zum Nachstellen angeben. Vor dem Teilen von Debug-Protokollen Adressen, Gerätenamen und sonstige private Angaben entfernen.

## Entwicklung und Lizenz

Die Tests benötigen keinen Receiver:

```sh
uv run --python 3.14 --with-requirements requirements-test.txt python -m unittest discover -s tests -v
python scripts/build_release.py
```

Die beiden Installations-ZIPs und SHA‑256-Prüfsummen landen in `dist/`. GitHub Actions testet und baut bei Pushes und Pull Requests. Ein Versions-Tag passend zu `manifest.json` erzeugt einen Release-Entwurf mit beiden ZIPs.

Siehe [Changelog](CHANGELOG.md), [Apache-2.0-Lizenz](LICENSE) und [Quellenhinweise](NOTICE). Das Projekt ist unabhängig von Onkyo und Home Assistant.

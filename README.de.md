![Onkyo Receiver Plus](custom_components/onkyo_receiver_plus/brand/logo.png)

# Onkyo Receiver Plus

[English](README.md) · [Releases](https://github.com/Benni1123/home-assistant-onkyo-receiver-plus/releases) · [Builds](https://github.com/Benni1123/home-assistant-onkyo-receiver-plus/actions) · [Fehler melden](https://github.com/Benni1123/home-assistant-onkyo-receiver-plus/issues)

**Lokale Steuerung und Diagnose für Onkyo-AV-Receiver in Home Assistant.** Onkyo Receiver Plus baut auf der eingebauten Onkyo-Integration auf und ergänzt Regler und Sensoren. Die Verbindung läuft direkt über eISCP im lokalen Netz. Ein Cloud-Konto oder ein Login für Web Setup ist nicht nötig.

## Kompatibilität

- **Home Assistant:** 2026.11.3 oder neuer.
- **Getesteter Receiver:** Onkyo TX-NR6050. Bei anderen eISCP-fähigen Onkyo-, Integra- und Pioneer-Modellen können die Grundfunktionen ebenfalls funktionieren. Zusatzfunktionen und Fernbedienungstasten hängen von Modell, Firmware, Eingang und Hörmodus ab. Ältere Geräte mit dem Pioneer-Protokoll werden nicht unterstützt.
- **Netzwerk:** Der Receiver muss von Home Assistant aus über TCP-Port `60128` erreichbar sein. Cover benötigen zusätzlich HTTP-Zugriff auf den AVR. Zum Einschalten aus dem Standby muss am Receiver **Netzwerk-Standby** aktiviert sein.

## Funktionen

Zonen, Bedienelemente und Sensoren werden in Home Assistant unter einem Receiver-Gerät gruppiert.

| Bereich | Funktionen |
| --- | --- |
| Medienplayer / Zonen | Ein/Aus, Stummschaltung, Lautstärke, Eingänge und Hörmodi. Verfügbare Zonen werden erkannt und demselben Gerät zugeordnet. Zusatzregler und Medien-Browser bedienen die Hauptzone; nicht alle Funktionen sind für Zone 2 verfügbar. |
| Lautstärke | Sofort oder in bestätigten Schritten über den **normalen HA-Slider**, mit Lautstärkelimit, einstellbarer Schritt-Pause und Lautstärkeauflösung. Kein zusätzlicher eigener Slider nötig. |
| Eingangsnamen | Receiver-Namen und HDMI-Zuordnungen, z. B. **HDMI 2 / Konsole**. Beim Öffnen der Optionen frisch über die gemeinsame Verbindung abgefragt. Automatische Namensübernahme und HDMI-Präfixe sind optional; eigene HA-Namen bleiben möglich. |
| Subwoofer | Temporärer Pegel: **−15 bis +12 dB in 0,5-dB-Schritten**. Keine dauerhafte Kalibrierung; wird im Standby zurückgesetzt. |
| Klang / Dialog / Verzögerung | Bass und Höhen (**−10 bis +10 dB**), Dialogpegel (**0–5**), DTS:X Dialog Control (**0–6 dB**, bei Unterstützung), A/V-Sync (**0–500 ms in 5-ms-Schritten**). |
| Hörmodi / Equalizer | Hörmodusauswahl, AccuEQ, manuelle EQ-Presets, Digitalfilter, Nachtmodus, Stereo-Lautsprecherzuordnung, Music Optimizer und Cinema Filter – abhängig von Receiver und Quelle. |
| HDMI / Display / Timer | HDMI-Ausgang, HDMI-Audioausgabe, HDMI-CEC, ARC, Display-Helligkeit und Einschlaftimer (**0–90 Minuten**, 0 schaltet ihn aus). |
| Kanal-Stummschaltung | Einzelne Kanäle stummschalten, sofern der Receiver Unterstützung meldet. Das ersetzt keine Kanal-Kalibrierung. |
| Fernbedienung | Das Receiver-Menü bedienen, Eingänge wählen, Lautstärke ändern und Wiedergabetasten an kompatible NET-/USB-Quellen senden. |
| TuneIn | Am TX-NR6050 die vom Receiver gemeldeten Kategorien und Favoriten öffnen, im gewählten Ordner suchen und Internetradio starten. |
| DAB+ | **Alle Sender:** dauerhaft gespeicherte Liste, Suche und stumme Auswahl über die kürzere Richtung. **Presets:** frisch gelesene AVR-Speicherplätze, direkt per Nummer anwählbar – ohne Durchsteppen. |
| Eigene UKW-Senderliste | Name und Frequenz, Auswahl gespeicherter Einträge sowie Speichern-/Löschen-Tasten direkt auf der Geräteseite. Dauerhaftes Browsen/Suchen und direkte Frequenzabstimmung. In HA gespeichert, getrennt von AVR-Presets. |
| Tuner-Regler | Gespeicherte FM-/AM-/DAB-Presets per Nummer oder Name abrufen; UKW live abstimmen (**87,5–108 MHz, 50-kHz-Raster**). Benötigt einen passenden aktiven Tuner-Eingang. |
| Mediadaten / Cover | NET-Titel, Interpret, Album und Receiver-Cover, soweit gemeldet. Ohne Musiktitel erscheinen bei DAB der Sendername und bei FM der gespeicherte Name oder die Frequenz. |
| Diagnose | Audioformat, Ein-/Ausgangskanäle, Videosignal/HDR, interne Temperatur, Firmware, Lautsprecheraufbau, HDMI-Sub-Zuordnung, Frontdisplay, Netzwerk-Standby, DTS:X-Dialog-Verfügbarkeit und DAB-Einlesestatus. |
| Verbindung / Neuladen | Gemeinsame Receiver-Verbindung, Wiederverbindung nach Netzfehlern, Optionsänderungen und Neuladen ohne HA-Neustart sowie Aufräumen von Verbindungstasks und Callbacks. Geänderten Python-Code nach einem Update lädt weiterhin ein HA-Neustart. |

Die Zusatzfunktionen am TX-NR6050 hängen von Betriebszustand, Signalformat, Eingang und Hörmodus ab. Daher kann ein Regler auch bei unterstütztem Receiver zeitweise nicht verfügbar sein. Die Browser-Unterstützung ist derzeit für den getesteten TX-NR6050 freigeschaltet, nicht pauschal für alle eISCP-Geräte zugesichert.

## Lautstärke und Eingangsnamen

Unter **Konfigurieren / Optionen** wählst du Eingänge und Hörmodi, Lautstärkelimit, sofortige oder schrittweise Regelung sowie die Pause zwischen Schritten. Die Lautstärkeauflösung muss zum Receiver passen; der HA-Slider zeigt einen Prozentsatz des eingestellten Limits, nicht direkt die Zahl auf dem Frontdisplay.

Beim Öffnen der Optionen werden Eingangsnamen und HDMI-Zuordnungen neu abgefragt. Wurde beispielsweise GAME am AVR in Konsole umbenannt, sollte nach Schließen und erneutem Öffnen **HDMI 2 / Konsole** erscheinen – ohne Neuladen der Integration. Die automatische Übernahme liefert auch Standardnamen für neu hinzugefügte Eingänge; bewusst gesetzte eigene HA-Namen bleiben erhalten. Im folgenden Namensschritt können Eingänge und Hörmodi eigene Bezeichnungen erhalten. Diese HA-Namen benennen den AVR nicht um.

Optionsänderungen und gewöhnliches Neuladen benötigen keinen HA-Neustart. **Nach Installation/Aktualisierung der Integrationsdateien HA neu starten, damit der geänderte Python-Code geladen wird.**

## Titel und Cover

Bei NET-Quellen erscheinen Titel, Interpret und Album, soweit der Receiver sie meldet. Cover werden von `http://<AVR-IP>/album_art.cgi` über HAs Medienbild-Proxy abgerufen. Die Integration entfernt zusätzliche CGI-Header im Bildinhalt und aktualisiert das Bild bei geänderten Metadaten.

Ohne Musiktitel erscheint bei DAB der aktuelle Sendername. Bei FM wird ein zur tatsächlichen Frequenz passender gespeicherter Name verwendet, danach gegebenenfalls ein gemeldeter Preset-Name, sonst die Frequenz. Das ist **kein DAB-Musiktitel-/DLS-Abruf**; dieser ist bisher nicht verifiziert. Nicht jede Quelle liefert Cover oder vollständige Metadaten. Die Cast-Entität hat eigene Mediadaten.

## DAB+ und FM-Radio durchsuchen

Beim Medienplayer der Hauptzone **Medien durchsuchen → DAB+ Radio** öffnen:

- **Alle Sender:** die zuvor in HA eingelesene vollständige Liste. Die Suche nutzt diesen lokalen Speicher. Beim Auswählen geht es stumm in der kürzeren Richtung durch die gespeicherte Reihenfolge – das ist **kein erneutes Einlesen**. Eine größere Entfernung kann trotzdem dauern.
- **Presets:** echte DAB-Speicherplätze des Receivers, beispielsweise **14: SPUTNIK**. Beim Öffnen frisch vom AVR gelesen. Die Auswahl ruft den Platz direkt auf, ohne Durchsteppen oder Änderung der Stummschaltung. Neue Favoriten zunächst am Receiver speichern; der Ordner legt keine AVR-Presets an und überschreibt sie nicht.

### DAB-Senderliste einlesen

1. Falls der Receiver noch keine Sender gefunden hat, zuerst dort einen normalen DAB-Antennensuchlauf ausführen.
2. Receiver einschalten und auf seiner **HA-Geräteseite** **DAB-Senderliste einlesen (stumm)** drücken.
3. **DAB-Senderliste Status** zeigt Fortschritt, Abschluss oder den tatsächlichen Fehler.
4. **DAB+ Radio → Alle Sender** öffnen. Die Liste bleibt bei Neuladen und HA-Neustarts erhalten.

Beim Einlesen schaltet die Integration bei Bedarf auf DAB und durchläuft die vorhandenen Dienste mit bestätigter Stummschaltung. Quelle und Stummschaltzustand werden danach wiederhergestellt, der Lautstärkepegel bleibt unverändert. Andere Wiedergabe kann unterbrochen werden; ein Quellenwechsel zurück garantiert nicht, dass ein externer Stream fortgesetzt wird. Ein unvollständiger Lauf überschreibt die vorherige Liste nicht. Nach Änderungen an der gescannten Senderliste erneut einlesen.

**Der Button startet keinen neuen Antennensuchlauf.** Ein direkter DAB-Suchlaufbefehl über eISCP oder Web Setup ist bisher nicht verifiziert. Auch ein direkter Abruf der vollständigen DAB-Senderliste ist nicht verifiziert – deshalb das Einlesen durch Durchsteppen. Für Favoriten ist die direkte Preset-Anwahl schneller.

### Eigene UKW-Senderliste verwalten

Für **FM Radio (own list)** auf der Geräteseite **UKW-Sendername** und **UKW-Speicherfrequenz** ausfüllen, dann **UKW-Sender speichern** drücken. Über **UKW-Sender bearbeiten** einen gespeicherten Sender in die Felder laden; erneut speichern ändert seine Frequenz, **UKW-Sender löschen** entfernt ihn. Die Liste wird dauerhaft in HA gespeichert; die Hardware-Presets des Receivers bleiben unverändert. Die Aktionen `save_fm_station` / `delete_fm_station` bleiben für Automationen verfügbar. Beim Abspielen im Medien-Browser schaltet der Receiver auf FM und stimmt die Frequenz ab.

- Frequenzen: **87,5–108 MHz**, auf ein **50-kHz-Raster** gerundet; bis zu **60 Sender**, Namen bis **64 Zeichen**.
- Ein vorhandener Name aktualisiert seine Frequenz (Groß-/Kleinschreibung wird beim Abgleich ignoriert); ein anderer Name legt einen weiteren Eintrag an.
- Speichern und Bearbeiten erfolgen nur in HA und starten keine Wiedergabe. Der Editor **UKW-Speicherfrequenz** ist vom Regler **UKW-Frequenz** zu unterscheiden: Letzterer stimmt den Receiver sofort ab.
- Die gespeicherte FM-Liste kann auch bei ausgeschaltetem Receiver durchsucht werden. Zum Abspielen einschalten; die Abstimmung wartet auf Bestätigung der gewünschten Frequenz.

## Stream-URLs über Google Cast

Der eISCP-Medienplayer nimmt **keine beliebigen MP3-/Stream-URLs** entgegen; nicht unterstützte Inhalte ergeben eine klare Fehlermeldung. Ein TX-NR6050 mit **Chromecast built-in** kann dafür HAs separate **Google-Cast-Integration** verwenden. URLs an deren Medienplayer schicken, nicht an die Receiver-Plus-Entität. Über [Radio Browser](https://www.home-assistant.io/integrations/radio_browser/) lassen sich ebenfalls Streams für den Cast-Player finden.

```yaml
action: media_player.play_media
target:
  entity_id: media_player.receiver_cast  # Durch die Google-Cast-Entität ersetzen
data:
  media_content_id: https://example.com/live.mp3  # Echte direkte Stream-URL einsetzen
  media_content_type: music
```

Fehlt der Cast-Player bei der Erkennung: Unter **Einstellungen → Geräte & Dienste → Google Cast → Optionen** die AVR-Adresse bei **Known hosts** eintragen, gegebenenfalls den Filter erlaubter Geräte prüfen und Cast neu laden. Erreichbarkeit und Cast-Unterstützung müssen weiterhin gegeben sein. Cast übernimmt die Wiedergabe; Ein/Aus und Receiver-Lautstärke lassen sich weiter über Receiver Plus bedienen. Ein Quellenwechsel oder das Öffnen von nativem TuneIn kann Cast unterbrechen.

## Installation

### HACS / Home Assistant Marketplace

`https://github.com/Benni1123/home-assistant-onkyo-receiver-plus` als **benutzerdefiniertes Repository** vom Typ **Integration** hinzufügen, **Onkyo Receiver Plus** installieren und HA neu starten. HACS verwendet `onkyo_receiver_plus.zip` aus einem **veröffentlichten** Release. Ein gepushter Tag oder Release-Entwurf allein ist noch kein HACS-Update; siehe [Latest-Release](https://github.com/Benni1123/home-assistant-onkyo-receiver-plus/releases/latest). Das benutzerdefinierte Repository bedeutet keine Aufnahme in den HACS-Standardkatalog.

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

Wiedergabetasten: `play`, `pause`, `play_pause`, `stop`, `next_track`, `previous_track`. Aliase: `enter` → `ok`, `exit` → `back`, `menu` → `setup`, `quick` → `quick_menu`. Befehle können als Liste mit `num_repeats` und `delay_secs` gesendet werden; `hold_secs` wird nicht unterstützt. Das Attribut `commands` der Remote-Entität listet die unterstützten Befehlsnamen. Menütasten liefern keinen lesbaren Menüinhalt oder markierten Menüpunkt zurück.

Die [Beispielkarte](examples/remote-card.yaml) nutzt eingebaute HA-Tasten. Ändere das Ziel am YAML-Anker `&receiver_remote`, um die Karte für einen anderen Receiver zu verwenden.

## TuneIn-Internetradio

Den Receiver einschalten und beim Medienplayer der Hauptzone **Medien durchsuchen → TuneIn Radio** öffnen. Eine Kategorie wie **My Presets**, **Local Radio** oder **By Location** wählen und dann den gewünschten Sender anklicken. Für große Listen gibt es weitere Seiten.

Die Suche durchsucht den geöffneten Ordner. In der TuneIn-Übersicht sucht sie zusätzlich in **Local Radio** und **My Presets**, nicht im gesamten TuneIn-Katalog. Beim Öffnen von TuneIn schaltet die Integration bei Bedarf auf NET um; das kann andere Wiedergabe unterbrechen. Lautstärke und gespeicherte Sender bleiben unverändert.

TuneIns **My Presets** sind Internetradio-Favoriten und von den FM-/AM-/DAB-Speicherplätzen des AVR getrennt. Vor der Auswahl wird der ursprüngliche Listeneintrag geprüft; bei einer geänderten Liste den Ordner erneut öffnen. USB-/DLNA-Browsing ist nicht implementiert, auch wenn Fernbedienungs-Wiedergabetasten an solchen Quellen funktionieren können.

## Aktionen für Automationen

Für die normale Senderverwaltung reichen die Bedienelemente auf der Geräteseite. In Automationen steht bei den Senderlisten-Aktionen `entity_id` **in `data`**, nicht in einem `target`-Block:

```yaml
action: onkyo_receiver_plus.save_fm_station
data:
  entity_id: media_player.receiver  # Receiver-Plus-Entität, nicht Cast
  name: Beispiel FM
  frequency: 89.0
```

Zum Löschen `onkyo_receiver_plus.delete_fm_station` mit denselben Feldern `entity_id` und `name` verwenden. Beide Aktionen verändern keine AVR-Presets und stimmen den Receiver nicht ab.

Gespeicherte AVR-Presets können bei aktivem Tuner mit `media_player.play_media`, `media_content_type: radio` und der Speichernummer als `media_content_id` abgerufen werden. Für DAB-Favoriten ist der Preset-Ordner komfortabler. Die ältere Aktion `media_player.onkyo_receiver_plus_select_hdmi_output` bleibt für vorhandene Automationen erhalten; interaktiv ist die HDMI-Ausgangsauswahl einfacher.

## Hilfe bei Problemen

- **Keine Verbindung:** IP-Adresse, Port `60128` und Netzwerk-Standby prüfen. Sicherstellen, dass keine zweite Integration mit demselben Receiver verbunden ist.
- **Regler nicht verfügbar:** Einige Einstellungen benötigen eine eingeschaltete Hauptzone, einen bestimmten Eingang oder ein passendes Signal. Der Temperatursensor aktualisiert sich bei eingeschalteter Hauptzone einmal pro Minute. HDMI-CEC, ARC und der Frontdisplay-Sensor sind standardmäßig deaktiviert.
- **Lautstärkeanzeige stimmt nicht:** Lautstärkeauflösung und Lautstärkelimit prüfen. Der HA-Slider zeigt einen Prozentsatz des eingestellten Limits, nicht direkt die Skala auf dem Receiver-Display.
- **Eingang am AVR umbenannt:** Optionen schließen und erneut öffnen, um Namen frisch abzurufen. Bewusst konfigurierte eigene HA-Namen haben Vorrang vor automatischem Import.
- **DAB-Auswahl dauert:** Alle Sender nutzt stummes Durchsteppen; AVR-Presets lassen sich direkt anwählen. Eine leere Liste über **DAB-Senderliste einlesen (stumm)** füllen, nicht per HA-Neustart. Der Status-Sensor zeigt tatsächliche Einlesefehler.
- **Kein Musiktitel/Cover:** Hängt von der Quelle ab. Der DAB-Sendername ist kein Musiktitel-Abruf. Erreichbarkeit des Cover-Endpunkts aus HA prüfen; die Cast-Entität hat eigene Metadaten.
- **Optionen/Neuladen scheitern:** Mindestens 0.5.7 installieren und zum Laden des Fixes einmal neu starten. Die Version behebt den FM/DAB-Aufräum-Callback hinter `a coroutine was expected`. Nachfolgendes normales Neuladen sollte ohne HA-Neustart funktionieren.
- **Fehler melden:** Receiver-Modell und Firmware, HA- und Integrationsversion sowie Schritte zum Nachstellen angeben. Vor dem Teilen von Debug-Protokollen Adressen, Gerätenamen und sonstige private Angaben entfernen.

### Grenzen

- Dauerhafte Lautsprecherkalibrierung, separate Front-L/R-Pegel und Bearbeiten von AVR-Web-Setup-Einstellungen sind nicht implementiert.
- Das Einlesen der DAB-Liste ist kein Antennensuchlauf. Für beliebige DAB-Dienste ist keine direkte Auswahl verifiziert; gespeicherte Presets können direkt angewählt werden.
- NET-Metadaten und einzelne Klang-/HDMI-Regler sind nicht für jedes Modell und jede Quelle garantiert. Manche Bedienelemente sind absichtlich standardmäßig deaktiviert.

## Entwicklung und Lizenz

Die Tests benötigen keinen Receiver:

```sh
uv run --python 3.14 --with-requirements requirements-test.txt python -m unittest discover -s tests -v
python scripts/build_release.py
```

Die beiden Installations-ZIPs und SHA‑256-Prüfsummen landen in `dist/`. GitHub Actions testet und baut bei Pushes und Pull Requests. Ein Versions-Tag passend zu `manifest.json` erzeugt einen Release-Entwurf mit beiden ZIPs.

Siehe [Changelog](CHANGELOG.md), [Apache-2.0-Lizenz](LICENSE) und [Quellenhinweise](NOTICE). Das Projekt ist unabhängig von Onkyo und Home Assistant.

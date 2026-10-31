# Community Stats – Anleitung

Community Stats stellt gemeldete Installationszahlen und GitHub-Release-Downloads als Sensoren in Home Assistant bereit. Jede genaue Version bekommt eine eigene, feste Messreihe. Grafana und InfluxDB werden nicht benötigt.

## Installation über HACS / Marketplace

Voraussetzung: **Home Assistant 2026.10 oder neuer**.

Bis zur Aufnahme in den öffentlichen Katalog:

1. In HACS beziehungsweise im Marketplace **Benutzerdefinierte Repositories** öffnen.
2. `https://github.com/SoftwareSchmied/community-stats` als **Integration** hinzufügen.
3. Community Stats herunterladen und Home Assistant neu starten.
4. **Einstellungen → Geräte & Dienste → Integration hinzufügen → Community Stats** öffnen.

Alternativ das Release-Archiv `community_stats.zip` nach `config/custom_components/community_stats/` entpacken und Home Assistant neu starten.

## Projekte einrichten

Für jedes Projekt einen Eintrag hinzufügen. Die beobachteten Projekte müssen nicht bei dir installiert sein.

- **Custom-Integration:** Domain eingeben, zum Beispiel `bosch_buderus_heating`. Sie erhält Gesamtzahlen und genaue Versionszahlen, sofern Analytics diese meldet.
- **Core-Integration:** Beispielsweise `mqtt` auswählen beziehungsweise als Domain eingeben. Sie erhält die Gesamtzahl meldender Installationen. Eine Versionsverteilung pro Core-Integration existiert in dieser Quelle nicht.
- **Dashboard-Karte oder Theme:** GitHub-Repository angeben, etwa `Sturmi77/heatpump-hydraulic-card`. Es entstehen Downloadsensoren, sofern passende Release-Dateien existieren.

Bei lokal installierten Custom-Integrationen kann das Repository aus dem Integrationsmanifest vorgeschlagen werden. Eine vollständige Domain-zu-Repository-Liste liefert Analytics nicht. In Gegenrichtung liest Community Stats das Manifest im GitHub-Repository aus. Bei mehreren Integrationen erscheint eine Auswahl. Du kannst Domain und Repository auch beide ausdrücklich angeben.

Prüfe die vorgeschlagene Zuordnung im Bestätigungsschritt. Um ausschließlich Installationen zu beobachten, den Repository-Vorschlag ausschalten und das Repository-Feld leer lassen. Die automatische Statistik-Erkennung bevorzugt Custom-Daten; bei einer Domain, die zugleich im Core vorkommt, die gewünschte Quelle ausdrücklich auswählen. Mit einer ausdrücklich gewählten Quelle lassen sich auch noch nicht gemeldete Domains vormerken; ihre Sensoren bleiben zunächst nicht verfügbar.

## Welche Dateien zählen?

GitHub zählt Abrufe der **an Releases angehängten Dateien**. Quellcodearchive, beliebige Repository-Dateien oder Git-Clones haben keine entsprechenden öffentlichen Zähler. Ein HACS-Download zählt nur dann in dieser Statistik, wenn der jeweilige Downloadweg diese Release-Datei verwendet.

Pro Zeile einen genauen Dateinamen oder ein Muster angeben, etwa:

```text
heatpump-hydraulic-card.js
```

`*.zip` erfasst passende ZIP-Dateien. `*` würde sämtliche Dateien einschließlich alternativer Pakete und Prüfsummen erfassen. Überlappende Muster zählen dieselbe Datei nur einmal. Eine einzelne Datei wird automatisch vorgeschlagen, wenn ein aktuelles Release genau eine Datei anbietet.

Es gibt einen Downloadsensor pro ausgewähltem Release sowie eine Gesamtsumme über passende Dateien aller aktuell verfügbaren veröffentlichten Releases. Vorabversionen sind in der Gesamtsumme enthalten, Entwürfe nicht. Fehlende passende Dateien bedeuten **nicht verfügbar**, ein gemeldeter Zählerstand von null bedeutet **0**.

Andere Dateimuster oder ein anderes Repository erzeugen neue Download-Messreihen. So werden verschieden definierte Zähler nicht im selben Verlauf vermischt. Alte Sensoren können als nicht verfügbar im Geräteverzeichnis bleiben. Bei Rückkehr zur gleichen Auswahl werden ihre ursprünglichen Identitäten wiederverwendet.

## Versionen und Verläufe

Standardmäßig werden je Quelle die **zehn Versionen mit den höchsten Zahlen** neu erfasst; einstellbar sind 1 bis 100. Veröffentlichungsdatum und Versionsnummer bestimmen die Rangfolge nicht. Betaversionen und genaue Schreibweisen bleiben erhalten. GitHub-Tags und Integrationsversionen werden getrennt behandelt.

Ein einmal erfasster Versionssensor bleibt seiner Version zugeordnet und wird auch außerhalb der Top-Auswahl weiter aktualisiert. Die Zahl der Sensoren kann deshalb langfristig über zehn steigen. Ein Neustart, eine kleinere Top-Auswahl oder das Ausschließen neuer Betaversionen beendet diese bestehenden Verläufe nicht. Nicht mehr gewünschte Sensoren lassen sich in Home Assistant deaktivieren.

Fehlt eine Version später in der Quelle, ist ihr Sensor nicht verfügbar. Kehrt sie zurück, wird derselbe Sensor weitergeführt. Die Installationstotalzahl wird unabhängig davon genutzt, ob für jede Version gültige Daten vorliegen. Die Summe der beobachteten Versionssensoren muss nicht der Gesamtzahl entsprechen.

Alle Zähler verwenden die Zustandsklasse **measurement**. Sinkende Installationszahlen und verringerte Downloadzahlen werden als gültige Messwerte behandelt. Der Recorder kann langfristige stündliche Minimum-, Maximum- und Mittelwerte speichern; die Sensoren dürfen dafür nicht vom Recorder ausgeschlossen sein. Die Aufbewahrung der detaillierten Historie richtet sich nach deinen Recorder-Einstellungen.

Der Verlauf beginnt mit der eigenen Aufzeichnung. Eine historische Versionsentwicklung wird nicht nachgeladen. [Dashboard-Beispiele](../examples/dashboard.yaml) zeigen Gesamtzahlen und einzelne Versionen. Eine zusätzliche Vorlage für gestapelte Flächen verwendet optional die ApexCharts Card; sie ist keine Voraussetzung für die Integration.

## Aktualisierung und Zugriff

Standard: **alle zwölf Stunden**, je Projekt zwischen einer und 168 Stunden einstellbar. Die Schaltfläche **Aktualisieren** am Gerät erlaubt eine manuelle Abfrage. Erfolgreiche Daten werden für fünf Minuten geteilt; häufiges Klicken umgeht weder dieses Zeitfenster noch GitHubs Limits.

GitHub erlaubt normalerweise 60 Anfragen pro Stunde je öffentlicher IP ohne Token und 5.000 je Benutzerkonto mit Token. Andere Anwendungen können dasselbe Kontingent nutzen. Ein API-Aufruf liefert bis zu 100 Releases und damit viele Sensorwerte. Die Integration bündelt Abfragen, berücksichtigt das verbleibende Kontingent und setzt unterbrochene Seitenabrufe nach einer Limitsperre fort. Unvollständige Summen werden nicht veröffentlicht. Sehr große Repositories können mehrere Stunden benötigen; ein länger als 24 Stunden unterbrochener Scan startet neu.

Ein GitHub-Token ist optional und benötigt keine Schreibrechte. In den Projekteinstellungen lässt er sich ergänzen oder entfernen. Ein leeres Token-Eingabefeld behält den vorhandenen Token. Derselbe Token wird über gemeinsame Clients genutzt, muss aber in jedem gewünschten Projekteintrag hinterlegt sein.

Analytics und GitHub aktualisieren sich unabhängig voneinander. Statussensoren, der letzte erfolgreiche Abruf und gegebenenfalls die nächste GitHub-Freigabe machen Ausfälle sichtbar. Der standardmäßig deaktivierte Sensor für verbleibende GitHub-Anfragen zeigt das zuletzt beobachtete Kontingent.

Die Installationszahlen stammen aus der freiwilligen [Home-Assistant-Statistik](https://analytics.home-assistant.io/). Sie entsprechen weder allen Nutzern noch Downloadzahlen. Die Integration liest öffentliche Datenquellen; Sensorverläufe bleiben in deiner Home-Assistant-Umgebung.

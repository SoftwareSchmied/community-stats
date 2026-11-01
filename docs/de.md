# Community Stats – Anleitung

Community Stats stellt gemeldete Installationszahlen, GitHub-Release-Downloads sowie Sterne, Forks, Beobachter und Issues als Sensoren in Home Assistant bereit. Jede genaue Version bekommt eine eigene, feste Messreihe. Grafana und InfluxDB werden nicht benötigt.

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

Lass die Dateimuster leer, wenn du nur Repository-Statistiken erfassen möchtest. In diesem Fall werden keine Downloadsensoren angelegt. Das funktioniert auch für Repositories ohne Release-Dateien.

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

## Sterne, Forks, Beobachter und Issues

Für jedes konfigurierte GitHub-Repository entstehen außerdem Sensoren für **Sterne**, **Forks**, **Beobachter**, **Issues gesamt** und **offene Issues**. Alle liefern numerische Zustände und unterstützen Langzeitstatistiken. Auch diese Zahlen dürfen sinken.

Beobachter sind tatsächliche Repository-Abonnenten. GitHubs Feld `watchers_count` entspricht dagegen historisch der Sternezahl und wird dafür nicht verwendet. Issues gesamt umfasst offene und geschlossene Issues; Pull Requests werden bei beiden Issue-Sensoren ausgeschlossen. Dafür werden zwei Suchabfragen verwendet. Der GitHub-Suchindex kann Änderungen verzögert anzeigen; unvollständige Suchergebnisse gelten als nicht verfügbar.

Diese Messreihen bleiben bei Änderungen der Download-Dateimuster erhalten. Eigene Statussensoren zeigen Fehler der Repository- und Issue-Abfragen an.

## Aktualisierung und Zugriff

**Ohne GitHub-Token** teilen sich alle entsprechenden Projekte dieser Home-Assistant-Instanz eine Warteschlange. **Alle 61 Minuten** wird das nächste Projekt abgefragt. Bei zehn Projekten ist jedes etwa **alle zehn Stunden und zehn Minuten** an der Reihe. Das erste Projekt startet sofort, sofern keine zuvor gespeicherte Pause läuft. Weitere Projekte warten auf ihren Platz. Für GitHub ersetzt diese Rotation das eingestellte Stundenintervall.

**Mit GitHub-Token** gilt das eingestellte Intervall: standardmäßig **alle zwölf Stunden**, je Projekt zwischen einer und 168 Stunden einstellbar. Diese Projekte sind unabhängig von der Warteschlange. Ein ungültiger Token führt zu einem Authentifizierungsfehler; es erfolgt kein automatischer Wechsel zu anonymen Abfragen.

**Home Assistant Analytics** verwendet immer das eingestellte Intervall, unabhängig von der GitHub-Warteschlange. Die Schaltfläche **Aktualisieren** und die Aktion `homeassistant.update_entity` erlauben eine manuelle Aktualisierung. Sie beachten den Fünf-Minuten-Cache, die Warteschlange und GitHubs Limits.

Reihenfolge, nächste erlaubte Abfrage und zuletzt gelesene GitHub-Werte bleiben über Neustarts und Neuladen erhalten. Während der Wartezeit bleiben vorhandene Werte mit ihrem ursprünglichen letzten Abrufzeitpunkt sichtbar. Vor dem ersten Abruf sind die Sensoren nicht verfügbar; der Status zeigt **Wartet auf ersten GitHub-Abruf**. Ein gescheiterter Abruf macht die betroffene Quelle bis zum nächsten erfolgreichen Abruf nicht verfügbar. Nach einem Neustart werden versäumte Abrufe nicht auf einmal nachgeholt.

GitHub erlaubt normalerweise 60 Anfragen pro Stunde je öffentlicher IP ohne Token und 5.000 je Benutzerkonto mit Token. Andere Anwendungen können dasselbe Kontingent nutzen. Ein API-Aufruf liefert bis zu 100 Releases und damit viele Sensorwerte. Die Integration bündelt Abfragen, berücksichtigt das verbleibende Kontingent und setzt unterbrochene Seitenabrufe nach einer Limitsperre fort. Ohne Token wartet das Projekt zusätzlich auf seinen nächsten Platz in der Warteschlange. Unvollständige Summen werden nicht veröffentlicht. Sehr große Repositories können mehrere Stunden benötigen; ein länger als 24 Stunden unterbrochener Scan startet neu.

Ein GitHub-Token ist optional und benötigt keine Schreibrechte. In den Projekteinstellungen lässt er sich ergänzen oder entfernen. Ein leeres Token-Eingabefeld behält den vorhandenen Token. Derselbe Token wird über gemeinsame Clients genutzt, muss aber in jedem gewünschten Projekteintrag hinterlegt sein.

Mit einer Seite Releases benötigt ein Repository normalerweise **vier GitHub-Abfragen je Aktualisierung**: eine für Repository-Zahlen, zwei für echte Issue-Zahlen und eine für die Downloads. Ohne Downloads sind es drei. Einrichtung und weitere Release-Seiten kommen gegebenenfalls hinzu. Die Suchabfragen besitzen ein zusätzliches eigenes Kontingent. Bei einer Suchsperre können Sterne, Forks, Beobachter und Downloads weiter aktualisiert werden. Größere Sammlungen verteilen sich bei Bedarf auf mehrere Freigabezeiträume.

Analytics und GitHub aktualisieren sich unabhängig voneinander. Statussensoren, der letzte erfolgreiche Abruf und gegebenenfalls die nächste GitHub-Freigabe machen Ausfälle sichtbar. Der eigene Platz in der Warteschlange kann später als diese Freigabe liegen. Herunterladbare Diagnosedaten zeigen den Abfragemodus und den voraussichtlichen nächsten Platz. Der standardmäßig deaktivierte Sensor für verbleibende GitHub-Anfragen zeigt das zuletzt beobachtete Kontingent.

Die Projekterkennung bei der Einrichtung benötigt eigene Abfragen und beachtet dieselben API-Limits. Die Rotation steuert die Sensoraktualisierungen. Weitere Home-Assistant-Instanzen oder Anwendungen an derselben öffentlichen IP teilen diese Warteschlange nicht.

Die Installationszahlen stammen aus der freiwilligen [Home-Assistant-Statistik](https://analytics.home-assistant.io/). Sie entsprechen weder allen Nutzern noch Downloadzahlen. Die Integration liest öffentliche Datenquellen; Sensorverläufe bleiben in deiner Home-Assistant-Umgebung.

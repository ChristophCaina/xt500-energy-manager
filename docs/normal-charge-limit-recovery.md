# Normal-Ladelimit nach Kommunikationsfehlern

## Befund

Ausgangspunkt ist der vom Benutzer belegte Ablauf am 06.10.2026 (Europe/Berlin):
90 % um 18:29, Schreibfehler um 23:13:38, Geräte-Rückmeldung 100 %, unmittelbar
anschließend gespeichertes Normal-Ladelimit 100 %, Recovery ready um 23:14:53.
Eine lokale Ausführung des unveränderten HEAD-Controllers mit normal_limit=90,
device_limit=100 und ohne Ladeanforderung, Override oder ausstehenden Schreibwert
liefert normal_limit=100. Die Runtime speichert diese Entscheidung unabhängig
von der Fehlersperre. number.py zeigt diesen gespeicherten Wert an.

Damit ist der Mechanismus für die dauerhafte Übernahme belegt, jedoch nicht die
Herkunft der ersten Geräte-Rückmeldung. Der aktuelle Repository-Code enthält:

- Produktion: Ladegrenze aus select_charge_limit; im Normalbetrieb gespeicherter
  Wert, bei manueller, Zyklus- oder Tarifladung mindestens der jeweilige Ziel-SOC.
  100 % sind hier bei entsprechendem temporärem Ladeziel möglich.
- Recovery: unveränderter aktueller Wechselrichterwert als Schreibprobe;
  keine explizite Ladegrenze von 100 %.
- Abschalten: Netz- und Wechselrichterwert 0 W sowie gespeichertes Normal-Ladelimit.
- Explizite Benutzeränderung: async_set_system_charge_limit speichert den
  gewünschten Wert und schreibt ihn außerhalb einer temporären Ladung.
- Initialisierung: Gerätewert nur dann als Startwert, wenn kein Normal-Ladelimit
  gespeichert ist; vorhandene Einstellungen bleiben erhalten.

Die Integration liest HA-Entitäten, keine Rohantworten des XT500. Ohne damaligen
Service-Aufruf samt Zielwert, aktive Ladeanforderung, SunEnergyXT-Rohantwort und
Geräteprotokoll lässt sich nicht entscheiden, ob die ersten 100 % von einem
Schreibpfad, der SunEnergyXT-Aufbereitung oder einem Geräte-Reset stammen.
Der gleichzeitige Wechsel von drei Gerätewerten ist dafür allein kein Beweis.
Es wurden keine Live-Abfragen und keine Live-Änderungen vorgenommen.

## Korrektur

Die Runtime markiert die Ladegrenze bereits beim Eintritt in control_error oder
Kommunikationspause als wiederherzustellenden Override. Auch ohne Berechnung
während der Pause bleibt diese Sperre nach Recovery erhalten.
Die Synchronisierung akzeptiert während Fehlersperre, Kommunikationspause oder
Recovery keine Gerätewerte und bestätigt dort auch keine ausstehenden Writes.
Nach Recovery bleibt das gespeicherte Normal-Ladelimit das Produktionsziel,
bis der Gerätewert wieder damit übereinstimmt. Dann wird die Sperre gelöst.
Die Bestätigung eines ausstehenden Normal-Limit-Writes kann gleichzeitig die
Wiederherstellung bestätigen. Anschließende manuelle Geräteänderungen werden wie
bisher gespeichert. Temporäre Ladeziele bleiben wie bisher getrennt.

Keine Änderung von Speicherformat, Standardwerten, Migration oder Version.
Bereits vor der Korrektur gespeicherte 100 % werden nicht automatisch auf 90 %
zurückgesetzt: Der Code kann die frühere Benutzerabsicht nicht rekonstruieren.

## Grenzen

Manuelle Änderungen über die Geräteentität während einer Störung oder vor der
Wiederherstellung werden nicht als neue Benutzerabsicht akzeptiert. Der Manager
versucht nach Freigabe, den gespeicherten Normalwert wiederherzustellen.
Die explizite Manager-Einstellung bleibt der eindeutige Weg für eine neue Absicht.
Ein isolierter, gültiger Reset-Wert ohne erkannten Kommunikationsfehler ist
weiterhin nicht von einer normalen manuellen Geräteänderung unterscheidbar.
Die Bestätigung basiert wie bisher auf HA-Entitätswerten, nicht auf einem neuen
Protokoll zur Herkunft oder Frische einzelner Geräteantworten. Die Tests belegen
lokale Logik und ausgeführte Runtime-Blöcke, keine Geräte-/Firmwarewirkung.

## Regressionstests und Ergebnis

- Originalcode reproduziert Übernahme von 90 auf 100 %.
- Fehlersample und wiederholte 100-%-Samples nach ready erhalten 90 %.
- Wiederherstellung auf 90 %, danach manuelle Änderung auf 85 % wird gespeichert.
- Ausstehender Write wird während der Störung nicht bestätigt.
- Temporäre Ladeziele 80, 95 und 100 % erhalten das Normal-Ladelimit;
  das vorhandene Maximum aus Normal-Limit und Ladeziel bleibt erhalten.
- Ausgeführter Runtime-Synchronisierungsblock: control_error, Kommunikationspause
  und Recovery speichern keine Reset-Werte; normale Änderung speichert wieder.
- Ausgeführte Fehlereintrittsmethoden setzen die Sperre ohne Zwischenberechnung.

Validierung: 140 Python-Tests und 18 Dashboard-Tests erfolgreich.
Keine Installation, kein Release, keine Änderung einer Live-Ladegrenze.

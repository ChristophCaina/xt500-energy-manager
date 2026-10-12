# Änderungsprotokoll

## 1.11.2 – 2026-10-12

- Gespeichertes Normal-Ladelimit gegen Geräte-Rückmeldungen während Schreibfehlern,
  Kommunikationspausen und Wiederherstellung geschützt.
- Schutz bleibt nach Recovery erhalten, bis das Gerät den gespeicherten Normalwert
  bestätigt. Danach werden manuelle Änderungen über die Geräteentität wieder übernommen.
- Temporäre Ladeziele und vorhandene Einstellungen bleiben erhalten; bereits
  gespeicherte 100 % werden nicht automatisch zurückgesetzt.
- Regressionstests für Fehlerablauf, Wiederherstellung, manuelle Änderungen,
  ausstehende Writes und temporäre Ladeziele ergänzt.

## 1.11.1 – 2026-10-02

- Pendeln zwischen Normalbetrieb und Vollakku-PV-Bypass behoben: Beim Einstieg
  wird öffentliche Einspeisung nicht mehr von der Akkuunterstützung abgezogen.
  Batterieenergie am Netz durfte bisher eine erneute Freigabe vortäuschen.
- Einstieg erst nach 30 Sekunden durchgehend erfüllter Leistungsfreigabe mit
  maximal 10 W Akkuentladung und 10 W Netzbezug gegenüber dem Netzziel. Die
  bisherige 30-W-Ausstiegstoleranz bleibt im aktiven Bypass erhalten.
- Versorgungslücken und Ladeaufträge beenden den Bypass weiterhin sofort.
  Die normale Regelung läuft während der erneuten Einstiegsprüfung weiter.
- Timer funktioniert auch bei unveränderten Messwerten und wird bei fehlenden
  Eingaben, ausgeschalteter Regelung und Entladen der Integration beendet.
- Lokale Tests über mehrere Regelzyklen und aktualisierte Anleitungen. Keine
  Übertragung auf ein laufendes System und keine erneute Geräteprüfung.

## 1.11.0 – 2026-09-30

- Optionale externe saldierte Netzmessung mit Power-Entity-Selector und Vorzeicheninvertierung in Einrichtung und Optionen.
- Drei Leistungssensoren und zwei persistente kWh-Zähler für das Energie-Dashboard; ereignisbasierte linke Integration mit lokalem Minutencheckpoint und Datenlückenschutz.
- Bestehende Regelung, Quellzuordnungen und Unique IDs bleiben erhalten.
- Tests für Berechnung, Wiederherstellung, Unterbrechungen, Einheiten, UI-Schema und Energie-Metadaten ergänzt.

## 1.10.7 – 2026-09-30

- Vollakku-PV-Bypass nur freigeben, wenn die verfügbare DC-PV den Verbrauch
  decken kann. Bei fehlender PV-Leistung kehrt der gewählte Grundmodus zurück;
  im Normalbetrieb kann der Akku den Hausverbrauch wieder unterstützen.
- Tatsächliche XT500-Ausgabe, öffentlicher Netzbezug und Akkuunterstützung
  berücksichtigen Versorgungslücken und Umwandlungsverluste. Eine Rückmeldung
  mit 30 W Toleranz verhindert erneutes Aktivieren bei fortbestehendem Defizit.
- Den Live-Vergleich vor, während und nach dem 1.10.6-Test dokumentiert und
  die beobachtete Versorgungslücke durch Regressionstests reproduziert.
  Anleitungen und Dashboard-Hilfe beschreiben die Freigabebedingungen.
- Direkt über SunEnergyXT sowie mit Energiemanager 1.10.7 am Gerät geprüft:
  PV-Ausgabe ohne gemessene Akkuentladung, tatsächliche öffentliche Einspeisung
  und Rückwechsel zur normalen Akkuunterstützung bei fehlender PV beobachtet.
  Messungen und Grenzen des Kurztests sind in `docs/testing/` dokumentiert.

## 1.10.6 – 2026-09-30

- Fehler beim Aktivieren des Vollakku-PV-Bypasses behoben: Der neue Status
  war nicht als erlaubter Zustand des Home-Assistant-Sensors registriert.
  Dadurch konnte eine Anzeigeaktualisierung die Schreibschleife stoppen.
- Fehler einzelner Anzeigeaktualisierungen werden protokolliert und getrennt
  von Geräte-Schreibfehlern behandelt; andere Entitäten werden weiter aktualisiert.
- Die Wechselrichter-Obergrenze im Bypass wird innerhalb der konfigurierten
  Leistungsgrenzen geöffnet, statt durch eine möglicherweise schon abgeregelte
  PV-Messung begrenzt zu werden. Die Rückregelung bei gemessener Akkuentladung
  bleibt erhalten. Regler-/Sensor-Vertrag und Fehlerisolation sind durch
  zusätzliche Regressionstests abgesichert.

## 1.10.5 – 2026-09-29

- Optionaler, standardmäßig ausgeschalteter PV-Bypass nach Erreichen der
  System-Ladegrenze: `GS = 0 W`, `IS` bis zur erlaubten Wechselrichterleistung.
  Die eingestellte Hausnetzgrenze wird zusätzlich über die IS-Obergrenze
  berücksichtigt.
- Eine neue Ladeanforderung, fehlende DC-PV-Freigabe, Ausschalten der Option
  oder ein SOC unterhalb des 1-%-Haltebandes beendet den Bypass. Gemessene
  Akkuentladung senkt die IS-Obergrenze. Status, Diagnose und Anleitungen zeigen
  den neuen Zustand; bestehende Modi bleiben bei ausgeschalteter Option gleich.

## 1.10.4 – 2026-08-22

- Vorübergehend fehlende Sollwert-Rückmeldungen werden nach einem Schreibbefehl
  im Sekundentakt bis zu drei Geräte-Abfragezyklen lang erneut geprüft. Sobald
  die Rückmeldung wieder vorliegt, arbeitet die Regelung unmittelbar weiter.
- Die Schreibfreigabe wird bei ungültigen Daten weiterhin sofort entzogen.
  Kommunikationspausen erscheinen im Status und als Warnung jedoch erst nach
  30 Sekunden; die unveränderte harte Sicherheitsabschaltung greift nach
  90 Sekunden.
- Die Anzeige **Produktivregelung betriebsbereit** bleibt bei kurzen, zuvor aus
  einem stabilen Betrieb entstandenen Pausen ruhig. Die exakte interne
  Schreibfreigabe steht als standardmäßig deaktivierte Diagnoseentität bereit.

## 1.10.3 – 2026-08-21

- Die Einstellung heißt im Dashboard nun eindeutig **Bevorzugte
  Akku-Ladeleistung im PV-Überschussmodus**.
- Anleitung und Dokumentation erklären den gemessenen Netto-Ladezielwert, die
  vollständige Gegenregelung jeder Akkuentladung, das Halteband gegen Pendeln
  und die Abgrenzung zu einer festen Netzladung.
- Die Totzone wird korrekt als reine Netzeinspeisungs-Totzone bezeichnet.

## 1.10.2 – 2026-08-21

- Der PV-Überschussmodus regelt jetzt jede gemessene Akkuentladung vollständig
  gegen. Die einstellbare Totzone gilt nur noch für die Netzeinspeisung.
- Die bevorzugte Akku-Ladeleistung bleibt auch bei kurzzeitigem Netzbezug aktiv,
  damit der Sollwert nicht wieder in die Akkuentladung zurückpendelt.
- Die Einstellungsseiten verwenden kompakte Zeilen statt großer Zahlenkacheln.
  Laden und Feinabstimmung sind übersichtliche Unterseiten der Einstellungen.

## 1.10.1 – 2026-08-21

- Die bisher sehr lange Einstellungsseite wurde in die drei klar getrennten
  Reiter Einstellungen, Laden und Feinabstimmung aufgeteilt. Lange Bereiche
  sind zusätzlich in gleichmäßigere, logisch benannte Abschnitte zerlegt.
- Der PV-Überschussmodus kann nun eine gemessene Akku-Ladereserve halten
  (Standard: 50 W). Dadurch liegt der Arbeitspunkt bevorzugt leicht auf der
  Ladeseite statt direkt an der instabilen Grenze zur Batterieentladung. Bei
  bestehendem Netzbezug wird keine zusätzliche Ladereserve erzwungen.

## 1.10.0 – 2026-08-21

- Die automatische 100-%-Zyklusladung endet nicht mehr allein anhand des
  gerundeten SOC-Werts. Sie hält 100 % zunächst standardmäßig zehn Minuten und
  bestätigt das Ladeende erst, wenn die gemessene Batterieladeleistung fünf
  Minuten lang höchstens 30 W beträgt.
- Während dieser Bestätigung wird die Zyklus-Ladeleistung auf standardmäßig
  300 W begrenzt. Nach spätestens 60 Minuten endet der Vorgang mit einem im
  Status sichtbaren Zeitlimit, damit keine endlose Zwangsladung entsteht.
- Haltezeit, Ladeende-Schwelle, Bestätigungsdauer, Zeitlimit und
  Nachladeleistung sind einstellbar. Laufende Bestätigungen überstehen einen
  Neustart oder ein Neuladen der Integration.

- kompatibel mit SunEnergyXT 500 Series 1.1.3 und dessen einstellbarem
  Geräte-Abfrageintervall von 3 bis 60 Sekunden
- die neuen optionalen Gerätewerte `SI1` und `SA1` werden bei Einrichtung und
  Upgrade automatisch erkannt; die Entlade-Hysterese des Energiemanagers wird
  mit `SI1` synchronisiert und beide Werte sind im Dashboard beschreibbar
- Rücklese-, Wiederherstellungs- und Kommunikationsfristen berücksichtigen das
  tatsächlich in der Originalintegration eingestellte Abfrageintervall
- der PV-Überschussmodus verwendet die gemessene Akkuentladung und die
  öffentliche Netzeinspeisung als gemeinsame Rückkopplung; `GS` und `IS`
  werden mit dem größeren der beiden Fehler abgeregelt, ohne denselben
  Leistungsüberschuss doppelt zu zählen
- eine im Dashboard einstellbare Totzone verhindert Flattern um 0 W; Diagnose
  und Übersicht zeigen die aktuell wirksame PV-Überschuss-Abregelung
- Dokumentation weist auf die Geräte-Standardwerte von jeweils 5 % hin; nach
  einem Test sollen benutzerdefinierte SI1-/SA1-Werte wieder auf 5 % gesetzt
  werden, wenn sie nicht dauerhaft benötigt werden

## 1.9.3 – 2026-08-18

- der Entlade-Haltezustand wird nach Neustart oder Neuladen innerhalb des
  Hysteresebereichs sicher rekonstruiert; Status und Sollwerte melden dadurch
  nicht mehr fälschlich Normalbetrieb, während der XT500 noch gesperrt ist
- neuer Dashboard-Knopf für eine einmalige temporäre Entladefreigabe bis zur
  eingestellten unteren Entladegrenze
- die dafür vorübergehend abgesenkte originale XT500-System-Entladegrenze wird
  beim Erreichen der regulären Grenze, beim Abschalten sowie nach einem
  Neustart mit Rücklesekontrolle wiederhergestellt
- eigene Statusanzeigen unterscheiden Entladesperre und temporäre Freigabe
  eindeutig; die reguläre Entladegrenze bleibt im Energiemanager sichtbar
- Dashboard-Anleitung und Diagnosedaten erklären den Sicherheitsablauf

## 1.9.2 – 2026-08-18

- die aktuelle originale SunEnergyXT-System-Batterieleistung (`BP`) wird
  automatisch erkannt und für die tatsächliche Lade- und Entladeleistung im
  Dashboard verwendet
- bestehende Einrichtungen werden beim Update automatisch auf den eindeutigen,
  vorzeichenbehafteten Batteriesensor migriert; Gesamt-Ein- und Ausgang bleiben
  nur als Rückfalllösung für ältere SunEnergyXT-Versionen erhalten
- die tatsächliche Ladequelle wird aus einer gemessenen Akkuladung und den
  real verfügbaren PV-/Netzquellen bestimmt; normales Laden aus direkt
  angeschlossener PV wird dadurch korrekt angezeigt
- PV-Überschuss bleibt auf die wirklich verfügbare PV-Leistung begrenzt und
  erhöht Sollwerte nicht aufgrund einer vermeintlichen, aus Gesamtleistungen
  berechneten Akkuladung

## 1.9.1 – 2026-08-04

- beim Ausschalten werden Netzanschluss-Sollwert und Wechselrichter-Obergrenze
  neutralisiert, eine temporäre Ladegrenze zurückgestellt und alle Werte vor
  der Abschaltbestätigung zurückgelesen
- die Wechselrichter-Obergrenze verwendet bei Geräten ohne zulässige `0 W` den
  kleinsten von der SunEnergyXT-Entität angebotenen Wert
- das normale maximale SOC wird im Normalbetrieb zwischen Energiemanager und
  originaler SunEnergyXT-System-Ladegrenze bidirektional synchronisiert
- temporäre Ladeziele werden nicht als neues normales Ladelimit übernommen und
  nach Ende der Zielladung zuverlässig zurückgestellt

## 1.9.0 – 2026-08-02

- AC-gekoppelte PV wird in Normalbetrieb, manueller Zielladung,
  Zyklusladung und Tarifladung durchgängig berücksichtigt
- der öffentliche Stromzähler bleibt alleinige Sicherheits- und
  Regelungsgrundlage; ein externer AC-PV-Leistungssensor ist optional
- klare Auswahl der PV-Berücksichtigung: Hybrid, nur XT500-PV oder nur
  externe AC-PV; die zuvor gleichwirkenden Auswahlwerte Automatisch und Hybrid
  sind ohne Funktionsverlust zusammengeführt
- getrennte DC- und AC-Hysteresen verhindern gegenseitige Freigaben und
  Flattern bei geringer Leistung
- Netzladung bezeichnet den gewünschten öffentlichen Netzanteil; bei
  **PV + Netz** bleibt die Ladeleistung dagegen das gesamte Ladeziel
- eindeutige Statuswerte für aktiven Vorgang, ausgewählten und aktiven
  Lademodus, Moduszustand, ausgewählte und aktive Kopplung sowie Ladequelle
- adaptive Regelabweichung verwendet den zum aktiven Modus gehörenden
  öffentlichen Netz-Sollwert und behandelt beabsichtigte Ladung nicht als Fehler
- Dashboard und Diagnose zeigen DC-PV, optionale AC-PV und verfügbaren
  AC-Überschuss getrennt
- eindeutige Begriffe trennen externe AC-PV-Erzeugung, den am Netzanschluss
  tatsächlich verfügbaren AC-PV-Überschuss und die wirkliche Akkuladequelle
- bei der optionalen externen AC-PV-Quelle kann getrennt ausgewählt werden, ob
  Erzeugung als positiver oder negativer Wert gemeldet wird
- eine nicht mehr verwendete optionale AC-PV-Quelle kann in den Optionen wieder
  vollständig entfernt werden; der Optionsdialog ist mit Home Assistant 2026.7
  kompatibel
- im reinen XT500-PV-Betrieb blendet das Dashboard die nicht verwendeten
  AC-PV-Leistungsflüsse aus
- der nur intern benötigte Rückmeldungs-Handshake bleibt in den Diagnosedaten,
  wird aber nicht mehr als Binärsensor angelegt; dadurch entfallen tausende
  unnötige Recorder-Zustandswechsel pro Tag

## 1.8.1 – 2026-07-30

- die Entladegrenze des Energiemanagers verwendet jetzt direkt die originale
  SunEnergyXT-System-Entladegrenze (`SI`); Änderungen an beiden Stellen wirken
  damit auf denselben Gerätewert
- bestehende Konfigurationen erkennen `SI` beim Upgrade automatisch
- Systemlastanschluss-Entladegrenze (`SO`) bleibt als unabhängige,
  bereits direkt verbundene Geräte-Einstellung erhalten

## 1.8.0 – 2026-07-29

- optionale Tagesenergie-Sensoren der originalen SunEnergyXT-Integration
  1.1.2 werden automatisch am ausgewählten XT500 erkannt
- neue Übersicht **Energie heute** mit PV-Erzeugung, Netzladung,
  Netzeinspeisung und Off-Grid-Ausgabe in kWh
- die zusätzlichen Werte stammen direkt aus der Originalintegration; es werden
  dafür keine Hilfssensoren angelegt
- kompaktere, responsive Speicherübersicht mit drei Spalten auf breiten
  Bildschirmen und platzsparenden Standard-Kacheln
- Leistungsflüsse, Schnellsteuerung und Tagesenergien verwenden kurze,
  eindeutig lesbare Bezeichnungen
- der neue Block **Energie heute** kann im Strategy-Editor verschoben oder
  ausgeblendet werden
- laufende Regel-, Start-, PV- und Wiederherstellungsaufgaben werden beim
  Entladen der Integration abgebrochen und vollständig abgewartet; dadurch
  verzögert der Energiemanager das Herunterfahren nicht mehr

## 1.7.0 – 2026-07-27

- eigene, providerunabhängige Tarif-Ladeanforderung mit separatem Ladeziel und
  separater Netz-Ladeleistung
- zeitlich begrenzte Anforderung fällt ohne regelmäßige Erneuerung automatisch
  und sicher in den Grundbetrieb zurück
- klare Priorität: manuelle Zielladung, Zyklusladung, Tarifladung, Grundbetrieb
- eigener Tarifstatus und Ablaufzeitpunkt in Dashboard und Diagnosedaten
- mitgelieferter Automation-Blueprint für beliebige numerische Preissensoren
  mit getrennter Start-/Stoppschwelle, Hysterese und sicherem Verhalten bei
  ungültigen Preisen
- der Blueprint wird bei Neuinstallation automatisch angelegt und nach einem
  HACS-Update beim Home-Assistant-Start sicher synchronisiert
- eine verwaltete Prüfsumme schützt manuell veränderte Blueprint-Kopien vor
  unbeabsichtigtem Überschreiben
- ausführliche Anleitung mit Tibber-Beispiel, Einheitenhinweis und Abgrenzung
  zu vorausschauender Preisoptimierung

## 1.6.0 – 2026-07-27

- neue empfohlene Einrichtung über eine native SunEnergy-XT500-Geräteauswahl
- originale XT500-Sensoren, Sollwerte und Leistungsgrenzen werden anhand ihrer
  stabilen SunEnergyXT-Kennungen automatisch erkannt
- nur der externe Gesamt-Stromzähler und seine Vorzeichenrichtung müssen
  weiterhin manuell ausgewählt werden
- vollständige manuelle Entitätsauswahl bleibt als Expertenmodus erhalten
- automatische Erkennung kann später über **Konfigurieren** erneut ausgeführt
  werden
- Stromzählerauswahl zeigt nur Leistungssensoren und erklärt ausdrücklich,
  dass die Gesamtleistung am öffentlichen Netzanschlusspunkt benötigt wird
- ungültige Eingangsdaten nennen den betroffenen Eingang, die Entität, ihren
  Zustand und die genaue Ursache
- letzter Eingangsfehler sowie Fehler- und Erholungszeitpunkt bleiben nach
  einer kurzen Störung in Entitätsattributen und Diagnosedaten sichtbar
- Start- und Neuladephasen erzeugen keine Serie irreführender Warnmeldungen
- Installationsanleitung und Fehlerbehebung an den neuen Einrichtungsablauf
  angepasst

## 1.5.0 – 2026-07-26

- Inhalte der Seiten **Speicher** und **Einstellungen** sind in eigenständige,
  frei anordenbare Blöcke aufgeteilt
- grafischer Strategy-Editor kann jeden Block mit Pfeiltasten verschieben oder
  über einen Sichtbarkeitsschalter ausblenden
- getrennte Reihenfolgen für Speicherübersicht und Einstellungsseite
- Schaltfläche **Standard wiederherstellen** setzt Reihenfolge und Sichtbarkeit
  einer Seite sicher zurück
- bestehende Dashboard-Konfigurationen verwenden automatisch die bisherige
  Standardreihenfolge

## 1.3.0 – 2026-07-25

- grafischer Strategy-Editor zum Einbinden einzelner Ansichten aus anderen
  Home-Assistant-Dashboards
- eingebundene Ansichten erscheinen als echte Reiter in der oberen
  Dashboard-Leiste und werden beim Neuladen aus ihrer Quelle aktualisiert
- optionaler eigener Titel und eigenes Symbol sowie zusätzliche Sichtbarkeit
  „Nur für mich“
- bestehende Benutzerbeschränkungen der Quellansicht bleiben erhalten
- Schutz vor Doppelimport, Selbstimport und verschachtelten Ansichtsstrategien
- eine nicht erreichbare Quellansicht beeinträchtigt die beiden
  Energiemanager-Ansichten nicht

## 1.2.0 – 2026-07-24

- Normalbetrieb gleicht jetzt zusätzlich die Differenz zwischen angefordertem
  XT500-Sollwert und tatsächlich gemessener Netzanschlussleistung aus
- dauerhafter kleiner Netzbezug durch Wandlungsverluste, Verzögerung oder
  Leistungsabweichungen des XT500 wird begrenzt nachgeregelt
- Ziellademodi, PV-Überschussbetrieb, Lastanschluss-Aufteilung und bestehende
  Leistungsgrenzen bleiben unverändert
- schnell wechselnde Regelwerte werden nicht mehr zusätzlich als Attribute des
  Statussensors gespeichert; sie bleiben als eigene Live-Entitäten und im
  Diagnosebericht verfügbar
- originale Systemlastanschluss-Entladegrenze kann bei der Einrichtung
  zugeordnet und im Einstellungs-Dashboard direkt verändert werden
- Statusblock zeigt den nächsten berechneten Termin der Zyklusladung
- der Termin wird als festes Datum mit Uhrzeit statt als relativer Zeitraum
  angezeigt
- Batterie lädt/entlädt werden aus den originalen Gesamtleistungen als
  gegenseitig ausschließende Nettowerte angezeigt

## 1.1.0

- Zyklusladung kann unabhängig von der Fälligkeit sofort manuell gestartet
  werden
- einstellbare tägliche Prüfzeit für den Start einer fälligen automatischen
  Zyklusladung
- eindeutiger Zyklusstatus trennt automatische Überwachung, fälligen Zyklus,
  manuelle Ladung, automatische Ladung und angehaltene Ladung
- eigener Zustand „Zyklusladung aktiv“ zusätzlich zur reinen
  Zyklusüberwachung
- Rücksetzknopf setzt die Zyklustage auf 0 und beendet eine laufende
  Zyklusladung, ohne eine künstliche Vollladung einzutragen
- manuelle und automatische Zyklusladung verwenden denselben separat
  einstellbaren Zyklus-Lademodus und dasselbe Vollladeziel
- verpasste Prüfzeit wird nach einem Neustart sicher nachgeholt; wird der
  Zyklus erst nach der Prüfzeit fällig, startet er erst am Folgetag
- Dashboard und Anleitung um Zyklusstatus, Start, Prüfzeit und Rücksetzen
  ergänzt
- Zyklusstatus, Zyklustage und Prüfzeit werden im Dashboard jeweils nur an
  einer passenden Stelle angezeigt
- „Neu berechnen“ aus dem automatisch erzeugten Dashboard entfernt

## 1.0.7

- neue Installationen und Aktualisierungen starten die Zyklusladung Automatik
  nicht mehr sofort, wenn noch keine Volladung aufgezeichnet wurde
- beim ersten Aktivieren beginnt stattdessen das eingestellte Zyklusintervall
- eine tatsächlich erreichte automatische Ziel-SOC setzt den Zeitplan zurück
- Diagnoseausgabe zeigt Zeitanker, Fälligkeit und nächsten Zykluszeitpunkt
- Dashboard-Ressource auf Version 1.0.7 angehoben

## 1.0.6

- einzelne SunEnergyXT-Schreib-Timeouts führen nicht mehr sofort zur
  Sicherheitsverriegelung
- nach einem Timeout wird zunächst auf die Rückmeldung des möglicherweise
  bereits übernommenen Zielwerts gewartet
- falls nötig folgen höchstens zwei idempotente Wiederholungen mit wachsender
  Wartezeit
- erst drei fehlgeschlagene Schreibversuche lösen den bestehenden
  `control_error` samt iPhone-Benachrichtigung aus
- Diagnoseattribute zeigen Anzahl, letzten Timeout und erfolgreiche
  vorübergehende Wiederherstellung
- Fehlermeldungen enthalten jetzt betroffene Entität und Zielwert
- Dashboard-Ressource auf Version 1.0.6 angehoben

## 1.0.5

- kontrollierte automatische Wiederherstellung nach einem Schreibfehler
- einstellbare Stabilitätszeit und eigener Ein-/Aus-Schalter
- wirkungsloser Schreibtest auf den bereits aktuellen Wechselrichter-Sollwert
- Freigabe erst nach neuen Messrückmeldungen
- höchstens drei Wiederherstellungsversuche mit wachsender Wartezeit
- eigener Wiederherstellungsstatus in Integration, Diagnose und Dashboard
- leere Timeout-Fehlertexte zeigen jetzt mindestens den Exception-Typ
- Dashboard-Ressource auf Version 1.0.5 angehoben

## 1.0.4

- „Zyklusladung“ in der Bedienoberfläche einheitlich in
  „Zyklusladung Automatik“ umbenannt
- Schnellsteuerung um Schalter für manuelle Zielladung und
  Zyklusladung Automatik ergänzt
- Dashboard-Ressource auf Version 1.0.4 angehoben

## 1.0.3

- erster öffentlicher Betateststand
- HACS als empfohlenen Installations- und Aktualisierungsweg dokumentiert
- manuelle Installation als Alternative beibehalten
- öffentliche Test- und Fehlermeldehinweise ergänzt
- Dashboard-Ressource auf Version 1.0.3 angehoben

## 1.0.2

- Batteriesymbol für das aktive Ladeziel korrigiert
- Eingangsdaten werden als „Gültig“ oder „Ungültig“ angezeigt
- Dashboard-Ressource auf Version 1.0.2 angehoben

## 1.0.1

- Zustandsübersetzungen für die Prüfung der Eingangsdaten ergänzt
- explizites Symbol für das aktive Ladeziel ergänzt

## 1.0.0

- erster produktiver Stand
- adaptive Nulleinspeisungsregelung
- Normalbetrieb und PV-Überschuss-Grundmodus
- manuelle Zielladung mit vier Lademodi
- automatische Zyklusladung mit getrenntem Lademodus
- normales Ladelimit und temporäre Anhebung während einer Zielladung
- Niedrig-PV-Sperre mit einstellbarer Hysterese und Startverzögerung
- automatisch erzeugtes Dashboard mit Standardkarten

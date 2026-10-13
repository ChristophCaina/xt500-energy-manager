# Lokale Prüfung einer optionalen Entladereserve

Voruntersuchung vom 13.10.2026, zunächst ohne Produktänderung.
Die anschließend lokal umgesetzte Erweiterung ist unten dokumentiert.
Keine Live-Installation und keine Gerätebefehle.

## Ziel und Umfang

Optionale höhere Entladegrenze im Netzbetrieb, damit Energie für einen späteren
Stromausfall verbleibt. Die Ladegrenze bleibt ausschließlich die bestehende
Originalgrenze. Die neue Funktion verändert weder Geräte-SOC-Grenzen noch
Geräte-Hysteresen. Eine automatische Notstromversorgung wird nicht zugesagt.

## Ergebnisse

- Python 3.12: 140 bestehende Tests bestanden.
- Node: 18 bestehende Dashboard-Tests bestanden.
- `tools/check_soc_feasibility.py`: 17.010 Hysterese-Grenzprüfungen bestanden.
  Untere Grenzen 1–99 %, Hysterese 1–10 Prozentpunkte, nur Kombinationen mit
  Wiederfreigabe bis 100 %. Vorzustand gesperrt, freigegeben oder unbekannt.
  Geprüft: knapp unter/auf/über Sperrgrenze und Wiederfreigabegrenze.
- 432 Regler-Szenarien bestanden: AC/DC/automatische Kopplung, Normalbetrieb
  und PV-Überschuss, PV 0/300/2.000 W, Lastanschluss 0/500 W,
  Netzleistung -1.200/0/1.200 W, bisheriger Netzsollwert 0/800 W,
  Reserve 40/80 %. Bei Sperre kein positiver Netzsollwert und
  Wechselrichter-Sollwert höchstens verfügbare DC-PV.
- System-Python 3.9 ist zu alt; dessen Importfehler wurden durch Verwendung
  von vorhandenem Python 3.12 beseitigt, ohne Produktänderung.

Diese Prüfungen betreffen vorhandene reine Reglerfunktionen, keine bereits
implementierte neue Reservefunktion und keine simulierte Gerätephysik.

## Grenzen und notwendige Umsetzung

Der aktuelle Runtime-Code übernimmt weiterhin die Geräte-Entladegrenze und
Geräte-Hysterese. Die Number-Entität übernimmt den Gerätebereich und schreibt
Änderungen zurück. Eine höhere HA-Reserve braucht eigene gespeicherte Werte
und einen expliziten Schalter; reine Erweiterung des Schiebereglers genügt nicht.

Die HA-Reserve kann strenger als die Geräte-Entladegrenze sein. Sie kann eine
Gerätesperre nicht aufheben. Für Freigabe müssen beide Sperren aufgehoben sein:
Geräte-Hysterese und Reserve-Hysterese getrennt halten.

Der dokumentierte Inselbetrieb hat SO als eigene Entladegrenze. GS/IS sind
kein Beleg dafür, dass ein Last-/Inselausgang gesperrt wird. Bei bereits aktivem
Lastanschluss kann Energie trotz Netzreserve verbraucht werden. Keine automatische
Abschaltung des Lastanschlusses vorsehen. Reserve im Netzbetrieb und nutzbare
Reserve im Inselbetrieb müssen verständlich unterschieden werden.

Bei ungültigen Daten beendet der Runtime neue normale Regelbefehle. Bei Entladen
können letzte Gerätesollwerte bestehen bleiben. Auch `async_stop` neutralisiert
GS/IS nicht generell; der ausdrückliche Regelschalter-Aus-Pfad neutralisiert sie
mit Rücklesebestätigung. Somit keine Ausfallgarantie bei HA-/Netzwerkausfall.

Die bestehende Schrittbegrenzung kann das Absenken eines Sollwerts verzögern.
Für die neue Reserve muss eine Sperre Vorrang vor normaler Leistungsrampe haben.
Auch der minimale Geräte-IS-Wert (typisch 1 W) und zeitversetzte GS/IS-Schreibvorgänge
verhindern, aus einem mathematischen Null-Sollwert einen physisch exakten Stopp
abzuleiten. Gemessene Akkuentladung muss später zur Wirkungskontrolle dienen.

Manuelle, Tarif- und Zyklusladung dürfen die Reserve nicht umgehen. Bestehende
Einmal-Entladefreigabe darf eine ausdrücklich aktive Reserve nicht stillschweigend
aufheben. Reservezustand bei Neustart im Hystereseband konservativ sperren.

## Vorschlag für einfache Bedienung

- Schalter „Reserve für Stromausfall behalten“, standardmäßig aus.
- Ein sichtbarer Wert „Reserve“ in Prozent, Beispiel 40 %.
- Wiederfreigabe standardmäßig 5 Prozentpunkte höher, nur unter Erweitert ändern.
- Klartext: „Entladen stoppt bei 40 %. Wieder freigegeben ab 45 %.“
- Einstellbereich aus Originalgrenze und Wiederfreigabe ableiten, ungültige
  Kombinationen ablehnen; Geräte-Sperren sichtbar erklären.
- Status „Reserve erreicht“, „Reserve wird aufgebaut“, „Gerätesperre aktiv“
  oder „Regelung nicht verfügbar“. Höhere Reserve veranlasst keine Netzladung.
- Bei Ausstellen nur diese zusätzliche Sperre entfernen, vorhandene Regelung
  und unveränderte Gerätewerte weiterverwenden.

## Noch erforderliche Prüfung vor Freigabe

Neue Runtime/Number/Switch-Pfade einschließlich Speicherung, Neustart,
Datenverlust, gleichzeitiger Bedienung, Gerätewertänderung, Fehler bei Befehlen,
Leistungsrampe und aller Ladeanforderungen lokal testen. Danach separat autorisierter
Gerätetest mit tatsächlicher Akkuleistung und nachgewiesenem Inselverhalten.
Keine Zusage „verursacht keine Probleme“ aus lokalen Reglerprüfungen ableiten.

Quelle: https://github.com/SunEnergyXT/SunEnergyXT-500-Series/blob/main/API.de.md
Die API beschreibt GS/IS, getrennte SI/SO-Grenzen sowie erforderliches Rücklesen.


## Anschließende lokale Umsetzung

Reserve-Schalter und eigener Prozentwert sind umgesetzt; originale Gerätewerte
bleiben erhalten. Die originale Entlade-Hysterese wird übernommen. Die
Wiederfreigabe ist sichtbar und auf 100 % begrenzt. Gerätesperre und zusätzliche
Reserve bleiben getrennte Zustände; bei Neustart im Band bleibt die Reserve
vorsorglich gesperrt. Einmalfreigabe und Vollakku-Bypass umgehen sie nicht.
Absenkungen bei Reserve-Sperre umgehen die normale Leistungsrampe; die
Gerätequantisierung bleibt erhalten. Diagnosedaten enthalten Reserve und Freigabe.

Die erste Einrichtung kann Ressource und Dashboard automatisch über die
vorhandenen HA-Lovelace-Verwaltungsobjekte anlegen. Ein zweiter Speicher-Writer
wird nicht erzeugt. Der Zugriff auf die Dashboard-Collection erfolgt über den
gebundenen HA-Listenhandler und ist ein versionsabhängiger, geprüfter Adapter;
eine nicht unterstützte Version erzeugt eine sichtbare Benachrichtigung.
Vorhandene Dashboards und Änderungen bleiben erhalten. Die einmal gespeicherte
Einrichtung verhindert Wiederanlage nach bewusster Löschung. Bei Fehlern bleibt
ein angefangener Pfad für den nächsten Versuch gespeichert. YAML-Ressourcen
werden nicht automatisch verändert. Neue Installationen starten ohne Regelbefehle;
gespeicherte Einstellungen bestehender Installationen werden übernommen.

Die gesamte README wurde mit der Umsetzung abgeglichen: Funktionsübersicht,
Voraussetzungen, automatische und manuelle Einrichtung, Reserve, Unterseiten,
Aktualisierung und Fehlerbehebung. Die Navigationslinks berücksichtigen den
gewählten Dashboard-Pfad.

Abschließende Prüfung: 161 Python-Tests und 20 Dashboard-Tests bestanden,
Python-Kompilierung und JavaScript-Syntaxprüfung erfolgreich, JSON-Dateien und
lokale README-Dateilinks gültig, `git diff --check` ohne Befund. Zusätzlich
17.010 Hysterese-Grenzprüfungen und 432 bestehende Regler-Szenarien bestanden.

Die neuen Lifecycle-Tests verwenden HA-Schnittstellen-Doubles und echte
Produktionsfunktionen bzw. deren AST-extrahierte Methoden. Sie ersetzen keine
Erstinstallation auf einer echten HA-Version und keine physische Geräteprüfung.
Die automatische Erstinstallation auf einer echten HA-Version steht weiterhin aus.

## Live-Test auf Achims Home Assistant

Die Testversion 1.11.3.dev1 wurde am 13.10.2026 mit Sicherung installiert.
Alle 56 vorherigen Einstellungen blieben beim Update erhalten. Das bestehende
Dashboard blieb erhalten; die neue Reserve-Bedienung wurde im Browser geprüft.

Für einen Test mit einem gemeldeten Prozentpunkt wurde die Reserve auf 17 %
gesetzt. Die bereits aktive Sperre wurde bei 18 % durch kurzzeitiges Absenken
der originalen SI1-Hysterese von 3 % auf 1 % freigegeben. Anschließend wurde
SI1 sofort wieder auf 3 % zurückgestellt. Die normale Hausversorgung lief bis
17 % weiter. Um 08:19:50 MESZ meldete der Speicher 17 % und die Reserve-Sperre
wechselte auf aktiv. Um 08:19:52 wurde der Netzanschluss-Sollwert von 240 W
auf 0 W gesetzt. Dieser Verlauf belegt die Reaktion der realen Installation
auf die Reservegrenze; eine garantierte Restenergie oder Inselversorgung
wurde damit nicht geprüft.

Später vom Nutzer vorgenommene Einstellungen (Reserve 30 %, Reserve-Schalter
aus) wurden für die Veröffentlichung nicht verändert.

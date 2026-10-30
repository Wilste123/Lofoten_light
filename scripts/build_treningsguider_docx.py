#!/usr/bin/env python3
"""Generate research-backed training guide Word docs for athlete self-planning."""
from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.shared import Pt


def add_title(doc: Document, title: str, subtitle: str = "") -> None:
    p = doc.add_heading(title, level=0)
    p.alignment = WD_PARAGRAPH_ALIGNMENT.LEFT
    if subtitle:
        s = doc.add_paragraph(subtitle)
        s.runs[0].italic = True
        s.runs[0].font.size = Pt(11)
    doc.add_paragraph(f"Versjon {date.today().isoformat()} · For egen planlegging · Lofoten_light repo")


def add_h(doc: Document, text: str, level: int = 1) -> None:
    doc.add_heading(text, level=level)


def add_p(doc: Document, text: str) -> None:
    doc.add_paragraph(text)


def add_bullets(doc: Document, items: list[str]) -> None:
    for item in items:
        doc.add_paragraph(item, style="List Bullet")


def add_refs(doc: Document, refs: list[str]) -> None:
    add_h(doc, "Referanser og kilder", 2)
    for r in refs:
        doc.add_paragraph(r, style="List Number")


def doc1_ukeplanlegging() -> Document:
    doc = Document()
    add_title(
        doc,
        "Ukeplanlegging etter fase",
        "Praktisk rammeverk for triathlon / lang utholdenhet — ikke «AI-kalender», men struktur du eier selv",
    )

    add_p(
        doc,
        "Denne guiden hjelper deg å sette en uke som henger sammen faglig: "
        "hva som må inn, hva som er volum, og hva som er ekte stimulus. "
        "Timer i tabellene er veiledende — juster etter jobb, søvn og skadehistorikk.",
    )

    add_h(doc, "1. Før du fyller mandag–søndag")
    add_bullets(
        doc,
        [
            "Bestem fase (re-etablering, aerob base, build, spesifikk, taper) — se dokumentet Periodisering.",
            "Sett uke-mål i timer og antall harde stimulusdager (typisk 2–3 i base/build, 1–2 i recovery).",
            "Legg inn faste ankre: svøm (svak diskiplin = planlegg først), styrke 2×, én lang sykkel, én løp-Q.",
            "Fyll deretter rolig volum rundt ankrene (Seiler: mesteparten av økter under VT1).",
            "Skriv Plan B for hver harde økt (kortere, roligere, flyttet dag).",
        ],
    )

    add_h(doc, "2. Fase A — Re-etablering (ca. 8–11 t/uke)")
    add_p(doc, "Formål: kontakt, vaner, skadefri tilbakekomst. Ingen terskel-jakt på løp.")
    add_bullets(
        doc,
        [
            "Svøm 2–3× (teknikk + lett aerob).",
            "Løp 2–3× lett + strides; unngå 6×3/6×4 terskel.",
            "Sykkel 2–4× rulle/Z2; variasjon mot kjedsomhet.",
            "Styrke 2× full program (MSK for senere volum).",
            "1 harde stimulus/uke totalt (f.eks. lett sykkel SS eller svøm-fokus).",
        ],
    )

    add_h(doc, "3. Fase B — Aerob base (ca. 11–14 t → mot 12–15 t)")
    add_p(
        doc,
        "Formål: bygge aerob kapasitet og 2–3 kvalitative stimulusdager per uke på tvers av svøm, sykkel og løp. "
        "Dette er fasen de fleste «comeback»-utøvere bør bruke lenge nok — ikke hoppe over for å «se elite ut».",
    )
    add_bullets(
        doc,
        [
            "Sykkel-Q: sweet spot / threshold (2×20 min, 3×15 min) eller FTP-test når du er uthvilt.",
            "Løp-Q: aerob power (6×3, 6×4) eller tempo — maks ~2 harde løp/uke.",
            "Strukturert aerob løp (f.eks. 6×5 min @ Z2/sub terskel HR) er volum med struktur — ikke samme kategori som intervall @ RPE 7+.",
            "Svøm 3×: teknikk → aerob med god form → korte harde reps før CSS-test.",
            "Lang Z2 sykkel 2 h+ og lang rolig løp 1–1,5 h.",
        ],
    )

    add_h(doc, "4. Fase C — Build (ca. 14–16 t)")
    add_bullets(
        doc,
        [
            "Roter sykkel threshold/VO2 og løp intervall — unngå maks på begge samme uke første gang.",
            "Brick 1×/uke med progresjon (kort → lengre).",
            "Fueling 60–90 g karbohydrater/time på 4 h+ sykkel.",
            "Fortsatt 80 % rolig volum; ikke bytte rolig til «moderat hver dag».",
        ],
    )

    add_h(doc, "5. Fase D — Konkurranse-spesifikk (8–12 uker pre-start)")
    add_bullets(
        doc,
        [
            "Lang kontinuerlig svøm, terreng/løp spesifikt, store brick, race nutrition.",
            "Cut-back uke hver 3. uke (−25–35 % volum).",
            "Taper: volum ned, korte race-pace blokker, prioritér friskhet.",
        ],
    )

    add_h(doc, "6. Recovery-uke (hver 3.–4. uke i base/build)")
    add_p(
        doc,
        "Ikke null trening — redusert volum og færre harde dager. Olympiatoppen / norsk langrenn: "
        "ofte −25–35 % timer. En moderat løp- eller sykkel-Q kan beholdes for å «maintain».",
    )

    add_h(doc, "7. Eksempel uke base (~12 t) — mal du fyller selv")
    table = doc.add_table(rows=8, cols=4)
    hdr = table.rows[0].cells
    hdr[0].text = "Dag"
    hdr[1].text = "Økt"
    hdr[2].text = "Rolle"
    hdr[3].text = "Ca. tid"
    rows = [
        ("Man", "Løp strukturert aerob (6×5 Z2) eller rolig 60 min", "Volum", "1–1,25 t"),
        ("Tir", "Sykkel SS eller FTP hvis fresh", "Sykkel-Q", "1–1,5 t"),
        ("Ons", "Svøm teknikk + styrke", "Svøm / MSK", "1,5 t"),
        ("Tor", "Sykkel Z2 eller løp lett", "Volum", "1 t"),
        ("Fre", "Løp intervall (6×3 el.l.)", "Løp-Q", "1 t"),
        ("Lør", "Lang sykkel Z2", "Volum", "2–3 t"),
        ("Søn", "Svøm + kort rolig eller hvile", "Svøm / rest", "0,5–1 t"),
    ]
    for i, row in enumerate(rows, start=1):
        for j, val in enumerate(row):
            table.rows[i].cells[j].text = val

    add_h(doc, "8. Hvorfor planen sier 12 t en uke og 10 t neste")
    add_p(
        doc,
        "Det er periodisering (mesosyklus), ikke at «noen kutter deg ned». "
        "Klassisk 3 uker opp + 1 uke avlasting gir lavere skaderisiko (IOC: akutt/kronisk belastning 0,8–1,3) "
        "og bedre adaptasjon enn lineær økning hver uke. Du kan planlegge 12 t som mål i opptaksuker "
        "og 8–10 t i recovery — begge er bevisste valg.",
    )

    add_refs(
        doc,
        [
            "Seiler & Tønnessen (2009). Intervals, Thresholds, and Long Slow Distance. sportsci.org — 80/20 og 1–3 harde økter/uke.",
            "Soligard et al. (2016). IOC consensus on load and injury risk. BJSM — ACWR og gradvis progresjon.",
            "Olympiatoppen — Treningskvalitet (utholdenhet fagstoff). olympiatoppen.no — plan, fokus, tilpasning.",
            "Rønnestad et al. (2025). Best-practice training in Olympic endurance (Norwegian WC coaches). Sports Medicine Open — periodisering, nøkkeløkter, avlastningsuker.",
        ],
    )
    return doc


def doc2_okt_kvalitet() -> Document:
    doc = Document()
    add_title(doc, "Øktoppbygging og treningskvalitet", "Hva som gjør en økt «god» — OLT, ikke Strava-TSS")

    add_h(doc, "1. Definisjon: treningskvalitet")
    add_p(
        doc,
        "Olympiatoppen: verdensmestere trener ikke nødvendigvis flere timer enn lagkamerater — "
        "de får mer ut av hver økt (plan, fokus, riktig intensitet, tilpasning). "
        "Optimal effekt = riktig belastning + høy kvalitet i gjennomføring + balanse mot restitusjon.",
    )

    add_h(doc, "2. Anatomi i en komplett økt")
    add_bullets(
        doc,
        [
            "Oppvarming: gradvis puls, bevegelse prep; løp 10–15 min + strides; sykkel 15–20 min.",
            "Hoveddel: én tydelig utviklingsoppgave (terskel, teknikk, aerob volum, VO2, osv.).",
            "Nedtrapping: 10–15 min lett — ikke stoppe på rød puls rett fra siste intervall.",
            "Etter: fueling/hydration ved lang eller hard økt; notat (RPE, form, søvn i går).",
        ],
    )

    add_h(doc, "3. Før økten (OLT)")
    add_bullets(
        doc,
        [
            "Vit hva du skal oppnå (teknikkpunkt, watt, pace, HR-sone).",
            "Sjekk readiness: søvn, resting HR, HRV, bein — juster ikke bare «for grønn kalender».",
            "Plan B skriftlig: hva gjør du ved gul/rød kropp?",
        ],
    )

    add_h(doc, "4. Under økten")
    add_bullets(
        doc,
        [
            "100 % fokus på oppgaven i hoveddelen (chunk lange intervaller i under-mål).",
            "Intensitet styrt av soner/HR/laktat — ikke ego pace.",
            "Stopp hard del når teknikk bryter (svøm, løp) — dårlige repetisjoner lærer feil mønster.",
            "Rolig økt skal føles rolig (RPE 3–4); «stolt moderat» hver dag er junk load.",
        ],
    )

    add_h(doc, "5. Etter økten")
    add_bullets(
        doc,
        [
            "Logg: gjennomført vs plan, subjektiv kvalitet, én læring.",
            "Hard økt: hvordan resten av dagen og neste dag er beskyttet (lett, søvn, mat).",
        ],
    )

    add_h(doc, "6. Hva teller som «hard stimulus» per disiplin")
    add_p(doc, "Triathlon: du har 3 ben — 2–3 harde stimulusdager totalt i uka er normalt i base/build, ikke 3 harde løp + 3 harde sykler.")
    table = doc.add_table(rows=4, cols=3)
    table.rows[0].cells[0].text = "Disiplin"
    table.rows[0].cells[1].text = "Typisk hard stimulus"
    table.rows[0].cells[2].text = "Volum / struktur (ikke «hard»)"
    data = [
        ("Løp", "6×3/6×4 @ RPE 7+, tempo @ terskel, bakke hard", "6×5 min Z2, lang rolig løp, terreng lett"),
        ("Sykkel", "SS, FTP-test, VO2-blokker", "Lang Z2, coffee ride"),
        ("Svøm", "6×50/8×100 @ CSS etter test, korte reps med form", "Drill, 4×100 aerob med stabil teknikk"),
    ]
    for i, row in enumerate(data, start=1):
        for j, v in enumerate(row):
            table.rows[i].cells[j].text = v

    add_h(doc, "7. Vanlige kvalitetsfeil")
    add_bullets(
        doc,
        [
            "Maks TSS på rolig dag.",
            "Lange harde sett med kollaps teknikk (svøm).",
            "To store økter samme dag uten recovery mellom (f.eks. intervall løp + 2 t sykkel samme kveld).",
            "Ingen tydelig hoveddel — «bare 90 min moderat» hver gang.",
        ],
    )

    add_refs(
        doc,
        [
            "Olympiatoppen — Hvordan skape høy treningskvalitet (utholdenhet).",
            "Seiler (2011). Best practice for training intensity distribution. PubMed 20861519.",
            "Stöggl & Sperlich (2014). Polarized training in endurance. Frontiers in Physiology.",
            "Midgley et al. (2006). Threshold interval training and endurance performance — lang intervall ved terskel.",
        ],
    )
    return doc


def doc3_periodisering() -> Document:
    doc = Document()
    add_title(doc, "Periodisering", "Makro, meso, mikro — og norsk utholdenhetspraksis")

    add_h(doc, "1. Nivåer")
    add_bullets(
        doc,
        [
            "Makro (6–12 mnd): retning mot hovedkonkurranse; total timer og faser.",
            "Meso (3–6 uker): ofte 3 uker progresjon + 1 avlasting.",
            "Mikro (1 uke): daglig fordeling; 2–3 nøkkeløkter.",
        ],
    )

    add_h(doc, "2. Tradisjonell periodisering")
    add_p(
        doc,
        "General → spesifikk; volum ofte høyere tidlig, intensitet og spesifisitet øker nær konkurranse. "
        "Norske verdensklasse-trenere (2025) bruker tradisjonell plan, men pragmatisk hybrid (blokker, altitude, kamplister).",
    )

    add_h(doc, "3. Intensitetsfordeling over året")
    add_p(
        doc,
        "Langrenn elite: mye lav intensitet i general prep; mer polarisert nær konkurranse (Sandbakk/Tønnessen). "
        "Triathlon: pyramidal volum i deler av året (Blummenfelt case, J Applied Physiol 2024) — høyt årsvolum med kontrollert intensitet.",
    )

    add_h(doc, "4. Mesosyklus 3+1 (praktisk)")
    add_bullets(
        doc,
        [
            "Uke 1–3: gradvis ↑ timer eller TSS (typisk ≤10 %/uke individuelt).",
            "Uke 4: −25–35 % volum; behold litt stimulus.",
            "Gjenta med justert startpunkt.",
        ],
    )

    add_h(doc, "5. Belastningsstyring")
    add_p(
        doc,
        "IOC: rask økning i belastning øker skaderisiko. ACWR 0,8–1,3 assosiert med lavere risiko; >1,5 mer enn dobler i enkelte data. "
        "Subjektive tegn (søvn, fatigue) er viktige — bruk sammen med TSS/CTL, ikke i stedet for egen dømmekraft.",
    )

    add_h(doc, "6. Triathlon-spesifikt")
    add_bullets(
        doc,
        [
            "Svak disiplin (ofte svøm) planlegges først — ellers fyller sykkel/løp kalenderen.",
            "Brick øker spesifisitet; introduser gradvis.",
            "Spesifisitet mot race (Half Extreme: lang svøm, terreng, kulde/OWS senere).",
        ],
    )

    add_h(doc, "7. Taper")
    add_p(
        doc,
        "Reduser volum 2–3 uker pre-start; behold korte race-pace. Målet er friskhet, ikke fitness-tap — "
        "cycling literature (Sagan/Vila): freshness som konkurransestrategi.")

    add_refs(
        doc,
        [
            "Matveyev / tradisjonell periodisering — lærebokstandard (via Rønnestad 2025 coach study).",
            "Rønnestad et al. (2025). Sports Medicine Open — norske OL-utholdenhetstrenere.",
            "Sandbakk & Tønnessen — intensitetsfordeling langrenn (Frontiers reviews).",
            "Blummenfelt annual training volume (2024). Journal of Applied Physiology.",
            "Soligard et al. (2016). IOC load consensus Part 1.",
        ],
    )
    return doc


def doc4_testing() -> Document:
    doc = Document()
    add_title(doc, "Testing og soner", "Når teste, hva du får ut av det, og vanlige feil")

    add_h(doc, "1. Hvorfor teste")
    add_bullets(
        doc,
        [
            "Intensitet (FTP, terskel løp, CSS svøm) — ikke gjetting fra gammel form.",
            "Spore progresjon over måneder.",
            "Kalibrere soner i TP/Garmin.",
        ],
    )

    add_h(doc, "2. Sykkel — FTP / terskel")
    add_bullets(
        doc,
        [
            "Ramp-test eller 20 min test når du er uthvilt (ikke etter hard uke).",
            "Oppdater FTP i profil; bruk HR parallelt første uker.",
            "Ikke to «maks»-tester tett uten grunn — én valid test per meso er nok for de fleste.",
        ],
    )

    add_h(doc, "3. Løp — terskel pace / HR")
    add_bullets(
        doc,
        [
            "Felt-test: 30 min tempo eller 5 km hard (med forbehold om form).",
            "Intervallprescription: RPE 7+ og HR soner til du har bedre data.",
        ],
    )

    add_h(doc, "4. Svøm — CSS")
    add_p(
        doc,
        "Critical Swim Speed: typisk 400 m + 200 m tid (standard protokoll), eller 2×400/200 variant. "
        "Ikke meningsfullt før du tåler ~800 m kontinuerlig med stabil teknikk — ellers tester du kamp, ikke kapasitet.",
    )

    add_h(doc, "5. Fysiologiske tester (valgfritt)")
    add_p(
        doc,
        "Laktat, VO2max, DLW volum — for de som har lab. Ikke nødvendig for god ukeplanlegging; "
        "fingerprikk/laktat brukes av mange norske utholdenhetsutøvere for threshold-dager (media/tri).")

    add_h(doc, "6. Hva du ikke skal gjøre")
    add_bullets(
        doc,
        [
            "Teste på sykdom, dårlig søvn, eller midt i recovery-uke og tolke som «sanning».",
            "Bruke 2019 peak FTP som dagens sone.",
            "CSS-test før teknikk sitter — planlegg progresjon først.",
        ],
    )

    add_refs(
        doc,
        [
            "Coggan & Allen — FTP and training zones (sykkel praksis).",
            "Swim CSS protocols — triathlon coaching literature / Critical Swim Speed research.",
            "Buchheit & Laursen — VO2max and interval training reviews.",
            "Olympiatoppen treningsdagbok — testresultater i langsiktig statistikk.",
        ],
    )
    return doc


def doc5_restitusjon() -> Document:
    doc = Document()
    add_title(doc, "Restitusjon og load–recovery", "Søvn, stress, sykdom, avlasting")

    add_h(doc, "1. Grunnprinsipp")
    add_p(
        doc,
        "Adaptasjon skjer i restitusjon, ikke under økten. Olympiatoppen: optimal effekt krever balanse belastning–restitusjon; "
        "dagbok og dialog ukentlig.",
    )

    add_h(doc, "2. Søvn")
    add_bullets(
        doc,
        [
            "7–9 h for de fleste voksne utøvere; konsistent leggetid.",
            "Hard Q tidlig på dagen hvis kveldstrening ødelegger søvn.",
            "Jetlag, alkohol, skjerm — dokumenterte restitusjonsdempere.",
        ],
    )

    add_h(doc, "3. Subjektiv og objektiv monitoring")
    add_bullets(
        doc,
        [
            "Wellness: fatigue, søvnkvalitet, muskelømhet, stress.",
            "HRV: trend og overnight verdi — ett snapshot kan lyve; bruk sammen med kontekst.",
            "IOC: subjektive mål ofte mer sensitive enn ett objektivt tall alene.",
        ],
    )

    add_h(doc, "4. Recovery-uke / deload")
    add_p(
        doc,
        "−25–35 % volum hver 3.–4. uke i opptrapping. Behold lett kontakt og 1 moderat stimulus om ønskelig.")

    add_h(doc, "5. Sykdom og skade")
    add_bullets(
        doc,
        [
            "Feber — ikke hard trening; gradvis retur.",
            "Smerte som endrer teknikk — stopp hard belastning; få vurdert ved vedvarende.",
            "Nikotin/snus: dokumentert påvirkning søvn/HRV — egen plan ved seponering.",
        ],
    )

    add_h(doc, "6. Ernæring og restitusjon (kort)")
    add_bullets(
        doc,
        [
            "Protein jevnt; karbo rundt hard og lang økt.",
            "Lang økt: 60–90 g CHO/time i build (triathlon anbefalinger).",
            "Kaloriunderskudd + høy load = høyere skaderisiko og dårlig kvalitet.",
        ],
    )

    add_h(doc, "7. Overtrening — tegn")
    add_bullets(
        doc,
        [
            "Langvarig dårlig søvn, HRV ned, performance ned, irritabilitet.",
            "Seiler: mer enn ~2–3 HIT/terskel-økter per uke gir sjelden ekstra, øker risiko.",
            "Tilbake: volum lett, søvn, så gradvis Q.",
        ],
    )

    add_refs(
        doc,
        [
            "Soligard et al. (2016). IOC consensus load–injury. BJSM.",
            "Soligard et al. (2016). IOC consensus load–illness Part 2. PubMed 27535991.",
            "Olympiatoppen — treningsdagbok som verktøy.",
            "Fullagar et al. — sleep and athletic performance (review literature).",
            "Seiler (2011) — frequency of high-intensity sessions and overreaching.",
        ],
    )
    return doc


def main() -> None:
    out_dir = Path("/opt/cursor/artifacts/treningsguider-docx")
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = Path("/opt/cursor/artifacts/william-treningsguider.zip")

    docs = [
        ("01-Ukeplanlegging-etter-fase.docx", doc1_ukeplanlegging()),
        ("02-Oktoppbygging-og-treningskvalitet.docx", doc2_okt_kvalitet()),
        ("03-Periodisering.docx", doc3_periodisering()),
        ("04-Testing-og-soner.docx", doc4_testing()),
        ("05-Restitusjon.docx", doc5_restitusjon()),
    ]
    readme = out_dir / "LESMEG.txt"
    readme.write_text(
        "William — treningsguider for egen planlegging\n"
        "============================================\n\n"
        "Fem Word-dokumenter, forankret i forskning og Olympiatoppen/IOC/Seiler m.fl.\n"
        "Ikke generert ukeplan — rammeverk du eier.\n\n"
        "1. Ukeplanlegging etter fase\n"
        "2. Øktoppbygging og treningskvalitet\n"
        "3. Periodisering\n"
        "4. Testing og soner\n"
        "5. Restitusjon\n\n"
        f"Pakke laget: {date.today().isoformat()}\n",
        encoding="utf-8",
    )

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(readme, "LESMEG.txt")
        for name, document in docs:
            path = out_dir / name
            document.save(path)
            zf.write(path, name)

    print(f"Wrote {zip_path} ({zip_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()

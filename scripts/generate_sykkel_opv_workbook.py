#!/usr/bin/env python3
"""Generate Excel workbook: OPV 2018 bike archive + build 3+1 rotation."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

_REPO = Path(__file__).resolve().parents[1]
OUT = _REPO / "docs/athlete/sykkel-opv-2018-build-rotasjon.xlsx"

HEADER_FILL = PatternFill("solid", fgColor="1E3A5F")
HEADER_FONT = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=14)


def style_header(ws, row: int, ncol: int) -> None:
    for c in range(1, ncol + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(wrap_text=True, vertical="top")


def set_col_widths(ws, widths: list[int]) -> None:
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def sheet_intro(wb: Workbook) -> None:
    ws = wb.active
    ws.title = "Les meg"
    lines = [
        ("Sykkel — OPV 2018 og build-rotasjon (Half Extreme 2027)", ""),
        ("", ""),
        ("Formål", "Kun sykkeløkter. Svøm, løp og styrke er ikke planlagt her, men tri-ramme styrer plassering."),
        ("2018-kilde", "TrainingPeaks okt–des 2018 (NTG). Se også plans/notater/tp-2018-okt-des-sykkel-opv.md"),
        ("FTP skalering", "Bruk % av gjeldende FTP i TP (200 W nov 2026 → oppdater etter test)."),
        ("Build 3+1", "Uke 1–3 progresjon, uke 4 recovery (~−25–35 % sykkeltimer). Gjelder M7–M9 (mai–jul 2027)."),
        ("Max belastning", "Maks 2 harde dager/uke totalt (tri). Ark har Q1 + valgfri 2. Q — velg 1 eller 2 sykkel-Q per uke."),
        ("Mål des 2026", "275 W 31.12 — bruk redusert variant av samme økttyper (ark Base_des2026)."),
        ("", ""),
        ("Ark", "Innhold"),
        ("2018_Sykkel", "Alle sykkeløkter av betydning okt–des 2018"),
        ("Tri_ramme", "Hva resten av uken tar plass til"),
        ("Build_B6_M7", "Mai — build 1, meso uke 1–4"),
        ("Build_B7_M8", "Juni — build 2 (brick/OWS)"),
        ("Build_B8_M9", "Juli — volumtopp"),
        ("Base_des2026", "Nov–des 2026 mot 275 W (samme logikk, lavere dose enn NTG)"),
    ]
    for r, (a, b) in enumerate(lines, start=1):
        ws.cell(r, 1, a)
        ws.cell(r, 2, b)
        if r == 1:
            ws.cell(r, 1).font = TITLE_FONT
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 90


def sheet_2018(wb: Workbook) -> None:
    ws = wb.create_sheet("2018_Sykkel")
    headers = [
        "Dato",
        "Tittel (TP)",
        "Kategori",
        "Preskripsjon / struktur",
        "Varighet (h)",
        "TSS",
        "Betydning",
        "2026–27 (% FTP @ 200 W)",
    ]
    ws.append(headers)
    rows = [
        (
            "2018-10-02",
            "Kapasitet rulle",
            "Kapasitet / NM",
            "30 min opp · 4×12 × (30 s hard / 15 s lett) · 5 min mellom serier · 20 min ned",
            1.25,
            61,
            "Raske føtter, OPV innendørs",
            "30 s @ 120–125 % · 15 s @ 50 %",
        ),
        (
            "2018-10-05",
            "Vekkedrag",
            "Lang / terreng",
            "Lang tur (beskrivelse tom i TP)",
            2.06,
            99,
            "Varighet + terreng",
            "Z2–Z3 RPE, ikke intervall",
        ),
        (
            "2018-10-31",
            "Terreng",
            "Lang Z2",
            "Terrengsykkel ~2,5 h",
            2.49,
            120,
            "Grunnmur",
            "65–75 % FTP",
        ),
        (
            "2018-11-03",
            "Langtur",
            "Lang Z2",
            "Rolig langtur",
            1.88,
            90,
            "Mellom FTP og Q",
            "65–72 % FTP",
        ),
        (
            "2018-11-05",
            "FTP test",
            "Test",
            "30 min opp · 30 min FTP-test (gruppe)",
            1.54,
            44,
            "250 W milepæl",
            "Ramp / 20 min — oppdater profil",
        ),
        (
            "2018-11-08",
            "Kontrolløkt",
            "Moderat",
            "Kontroll ~2 h",
            2.07,
            76,
            "Belastning uten max",
            "Z2 med korte drag",
        ),
        (
            "2018-11-13",
            "Crisscross SS/terskel",
            "Hard Q",
            "6×10′: 45 s terskel / 15 s SS · 2 min pause · 5×8″ spurt · 10′ rolig",
            None,
            None,
            "OPV-signatur",
            "45 s ~100 % / 15 s ~88–92 % FTP",
        ),
        (
            "2018-11-19",
            "Intervaller terskel",
            "Hard Q",
            "20 min opp · 6×8 min + 7×8 min @ 95–102 % FTP · 20 min ned ~50 W",
            1.85,
            65,
            "Gjentatt 26.11, 3.12",
            "Comeback: 4×8 @ 90 % eller 5×10 @ 98 %",
        ),
        (
            "2018-11-21",
            "Kort langtur",
            "Z2",
            "Rolig, OPV: prioriter å stå intervalløkter",
            1.67,
            60,
            "Støtte",
            "65–72 % FTP",
        ),
        (
            "2018-12-01",
            "Sweetspot",
            "Hard Q",
            "Sweetspot, pauser 40 % (PerfPro) — TSS høy",
            1.92,
            123,
            "Des FTP-bygg",
            "2×20 @ 88–92 % · pause 40 % FTP",
        ),
        (
            "2018-12-03",
            "Intervaller terskel (felles)",
            "Hard Q",
            "Samme som 6×8 + 7×8 @ 95–102 %",
            1.45,
            75,
            "NTG fellesøkt",
            "4×8 @ 90 % når TSB ok",
        ),
        (
            "2018-12-08",
            "Sweetspot",
            "Hard Q",
            "Sweetspot 40 % pause",
            1.95,
            92,
            "Repeat SS",
            "2×20 @ 88–92 %",
        ),
        (
            "2018-12-10",
            "18×3′ terskel/VO2",
            "Hard Q",
            "16–20×3′: 8× @ 95 % (1′) + 10× @ 100 % (1,5′) — yngre 8+8",
            1.84,
            85,
            "OPV 18×3",
            "Full: 18×3 som opv-nokkelokter — build only",
        ),
        (
            "2018-12-13",
            "VO2 sykkel (alt)",
            "Hard Q",
            "4–5×6 min, topper 110–115 %",
            1.26,
            71,
            "Alternativ til løp",
            "5×3 @ 106–112 %",
        ),
        (
            "2018-12-15",
            "8–9×6 min terskel",
            "Hard Q",
            "20 min opp · 8–9×6 min, 2 min pause · 93–96 % / 96–98 % annenhver",
            1.67,
            66,
            "Terskel volum",
            "Comeback: 5×6 @ 95 %",
        ),
        (
            "2018-12-18",
            "FTP test",
            "Test",
            "FTP test",
            1.51,
            80,
            "325 W milepæl",
            "Ramp — mål 275 des 2026",
        ),
        (
            "2018-12-23",
            "18×3′",
            "Hard Q",
            "18×3′ (95 % / 100 % pauser som 10.12)",
            2.0,
            None,
            "Repeat VO2/terskel",
            "Kun hvis forrige uke grønn",
        ),
        (
            "2018-12-27",
            "Langtur",
            "Lang Z2",
            "Rolig langtur 3,5 h",
            3.5,
            None,
            "Før crisscross",
            "65–70 % FTP",
        ),
        (
            "2018-12-28",
            "Langtur + crisscross",
            "Hard Q",
            "6×10′ 45/15 @ 93/83 % · 2 min pause · spurter · 2 h total",
            2.0,
            120,
            "Kvalitet i langtur",
            "Samme som OPV crisscross i Z2-ramme",
        ),
        (
            "2018-12-30",
            "Langtur",
            "Lang Z2",
            "Rolig 3,5 h — «intervall i morgen»",
            3.5,
            None,
            "Taper inn VO2",
            "Z2",
        ),
        (
            "2018-12-31",
            "VO2 max 30-15",
            "Hard Q",
            "30-15 sykkel (OPV: eller 4×8 ski/løp)",
            2.0,
            None,
            "Årsavslutning",
            "30 s @ 115 % / 15 s lett × 12–15",
        ),
        (
            "2018-11-12",
            "Sykkel rest",
            "Recovery",
            "Restitusjonssykkel ~2 h",
            2.0,
            70,
            "Mellom Q",
            "Z1–Z2",
        ),
        (
            "2018-12-04",
            "Sykkel etter styrke",
            "Støtte",
            "1 h rolig etter styrke · ev. 5×8 s spurt",
            1.0,
            None,
            "Dobbel dag",
            "Z2 + neuromuskulært",
        ),
    ]
    for row in rows:
        ws.append(row)
    style_header(ws, 1, len(headers))
    set_col_widths(ws, [11, 28, 14, 52, 10, 8, 22, 28])
    for r in range(2, ws.max_row + 1):
        for c in range(1, len(headers) + 1):
            ws.cell(r, c).alignment = Alignment(wrap_text=True, vertical="top")


def sheet_tri(wb: Workbook) -> None:
    ws = wb.create_sheet("Tri_ramme")
    headers = ["Regel", "Praktisk for sykkelplassering", "Kilde repo"]
    ws.append(headers)
    rows = [
        (
            "Maks 2 harde dager/uke (totalt)",
            "Q1 = standard tri. **2. Q** kun hvis du dropper hard løp-Q den uken ELLER TB grønn + du tåler 2 sykkel-hard.",
            "knowledge/coach/ukemaler.md fase C",
        ),
        (
            "2 sykkel-Q samme uke",
            "Tillatt i arket som **alternativ** — da **ingen** hard løp-Q samme uke; svøm teknikk/Z2 ok.",
            "2018 NTG (ofte 2–3 sykkel-Q) vs tri",
        ),
        (
            "Svøm 3×/uke (prioritet)",
            "Legg hard sykkel på tir/ons/lør — unngå å klemme begge svøm-Q og sykkel-Q fre.",
            "goals.md nov–des blokk",
        ),
        (
            "Løp: maks 1 hard Q/uke",
            "Roter løp-Q og sykkel-Q på **ulike** uker i build (B5+).",
            "blokker B5–B6",
        ),
        (
            "Styrke 2×/uke",
            "«Sykkel etter styrke» 45–60 min Z2 ok (2018-modell), ikke ny hard Q.",
            "forebygging-styrke-mobilitet.md",
        ),
        (
            "Recovery uke 4",
            "Ingen crisscross/18×3/SS. Spin 45–60 min + ev. 1×90 min Z2.",
            "mengdeperioder 3+1",
        ),
        (
            "TSB / TB-Score",
            "Gul/rød → Plan B sykkel (Z2 only). Ikke jakt 275 W med rød PMC.",
            "AGENTS.md rapporter",
        ),
        (
            "FTP / soner",
            "Oppdater TP etter hver test før du kjører OPV-watt.",
            "profile.md",
        ),
        (
            "Des 2026 vs build 2027",
            "Nov–des: ~4–5 h sykkel/uke hard+myskt (tri), ikke 2018s 10+ h sykkel.",
            "tp-2018-analyse",
        ),
    ]
    for row in rows:
        ws.append(row)
    style_header(ws, 1, 3)
    set_col_widths(ws, [28, 55, 32])


def sheet_build_block(
    wb: Workbook,
    title: str,
    phase: str,
    weeks: list[tuple],
) -> None:
    ws = wb.create_sheet(title)
    ws.cell(1, 1, phase).font = TITLE_FONT
    ws.cell(
        2,
        1,
        "Velg per uke: kun Q1 (tri) ELLER Q1 + 2. Q. Ved 2 sykkel-Q: ingen hard løp-Q samme uke.",
    )
    headers = [
        "Meso-uke",
        "Hard sykkel-Q1 (hoved)",
        "Preskripsjon Q1",
        "Alternativ 2. Q (valgfri)",
        "Preskripsjon Q2",
        "Sykkel timer ca. (1 Q / 2 Q)",
        "Sykkel Z2 / støtte",
        "2018-ref Q1",
        "2018-ref Q2",
        "Hvorfor Q1",
        "Tri: 1 vs 2 sykkel-Q",
    ]
    ws.append([])
    ws.append(headers)
    start_row = 4
    for row in weeks:
        ws.append(row)
    style_header(ws, start_row, len(headers))
    set_col_widths(ws, [10, 20, 34, 20, 34, 16, 26, 14, 14, 28, 26])
    for r in range(start_row + 1, ws.max_row + 1):
        for c in range(1, len(headers) + 1):
            ws.cell(r, c).alignment = Alignment(wrap_text=True, vertical="top")


def add_build_sheets(wb: Workbook) -> None:
    sheet_build_block(
        wb,
        "Build_B6_M7",
        "B6 Build 1 · mai 2027 (M7) · ~14–15 t/uke total · FTP-mål >250 validert",
        [
            (
                "Uke 1",
                "Sweet spot 2×20",
                "15 min opp · 2×20 @ 88–92 % FTP · 5 min @ 40 % · 10 min ned",
                "Kapasitet 3×10×30/15",
                "10 min opp · 3 serier ×10 (30 s @ 120 % / 15 s @ 50 %) · 3 min pause · ned",
                "4,5–5,5 h / 5,5–6,5 h",
                "Man/fre: 90 min Z2 · Lør: 2 h Z2",
                "2018-12-01",
                "2018-10-02",
                "SS bygger FTP-tid",
                "1 Q: normal tri. 2 Q: drop hard løp; minst 48 t mellom Q1 og Q2",
            ),
            (
                "Uke 2",
                "Crisscross 6×10",
                "15 min opp · 6×10′ 45/15 @ 93/83 % · 2 min pause · 10 min ned",
                "SS 2×12 @ 90 %",
                "15 min opp · 2×12 min @ 90 % · 4 min @ 40 % · ned (lettere enn uke 1)",
                "5–6 h / 6–7 h",
                "Ons: 90 min Z2 · Søn: 2,5 h Z2",
                "2018-11-13",
                "2018-12-08",
                "Crisscross = OPV-signatur",
                "2 Q: ikke løp intervall; gul TB → kun Q1",
            ),
            (
                "Uke 3",
                "Terskel 4×8 @ 90 %",
                "15 min opp · 4×8 min @ 90 % · 4 min pause · 15 min ned",
                "5×10 @ 98 % ELLER 5×6 @ 95 %",
                "Alternativ A: 5×10 @ 98 %, 3 min pause · Alt B: 5×6 @ 95 %, 2 min pause",
                "5,5–6,5 h / 6,5–7,5 h",
                "Tir: 2 h Z2 · Lør: 3 h Z2 (fueling)",
                "2018-11-19",
                "2018-12-15",
                "Terskel før VO2-meso",
                "2 Q: splitt på 2 dager; ikke samme dag som lang løp",
            ),
            (
                "Uke 4 (+1)",
                "Recovery — ingen Q1",
                "45–60 min spin Z1",
                "— (ingen 2. Q)",
                "—",
                "2–2,5 h",
                "Valgfri 1×75–90 min Z2",
                "2018-11-12",
                "—",
                "Recovery",
                "Kun 1 «økt» — alltid 0 hard Q",
            ),
        ],
    )
    sheet_build_block(
        wb,
        "Build_B7_M8",
        "B7 Build 2 · juni 2027 (M8) · brick/OWS · ~15–16 t/uke",
        [
            (
                "Uke 1",
                "18×3′ (OPV)",
                "15 min opp · 8×3 @ 95 %/1′ · 10×3 @ 100 %/1,5′ (Plan B: 12×3)",
                "VO2 5×3 @ 108 %",
                "15 min opp · 5×3 min @ 106–112 % · 3 min pause · ned",
                "5–6 h / 6–7 h",
                "90 min Z2 · Brick 2 h bike + 20 min run Z2 (annen dag)",
                "2018-12-10",
                "2018-12-13",
                "VO2/terskel topp",
                "2 Q: ingen brick hard samme dag; ingen løp-Q",
            ),
            (
                "Uke 2",
                "5×6 min terskel",
                "20 min opp · 5×6 @ 93–98 % · 2 min pause · ned",
                "Crisscross 4×10",
                "4×10′ 45/15 @ 93/83 % · 2 min pause (kort versjon)",
                "5,5–6,5 h / 6,5–7 h",
                "Lør: 3–4 h Z2 sykkel",
                "2018-12-15",
                "2018-11-13",
                "Terskel volum",
                "2 Q: OWS dag = Z2 only",
            ),
            (
                "Uke 3",
                "Crisscross i langtur",
                "2 h Z2 · 6×10′ 45/15 · 2 min pause · rolig hjem",
                "SS 2×15 @ 90 %",
                "Egen dag: 2×15 @ 90 % · 5 min @ 40 % (ikke dagen etter langtur-Q1)",
                "6–7 h / 7–8 h",
                "Ons: 90 min Z2 · Brick 2,5 h + 30 min run",
                "2018-12-28",
                "2018-12-08",
                "Steady + surges",
                "1 Q anbefalt uke med brick; 2 Q kun uten hard løp",
            ),
            (
                "Uke 4 (+1)",
                "Recovery spin",
                "45 min Z1",
                "—",
                "—",
                "2–2,5 h",
                "1×90 min Z2",
                "2018-12-25",
                "—",
                "Absorber brick",
                "0–1 økt hard = 0",
            ),
        ],
    )
    sheet_build_block(
        wb,
        "Build_B8_M9",
        "B8 Build 3 · juli 2027 (M9) · volumtopp · ~15,5–16 t/uke",
        [
            (
                "Uke 1",
                "Lang sykkel 4 h",
                "4 h @ 65–72 % FTP · fueling 60 g CHO/h",
                "Kapasitet 4×8″ spurt",
                "Etter langtur annen dag: 4×8 s @ max · 2 min pause (OPV nedkjøring-stil)",
                "5–5,5 h / 5,5–6 h",
                "Ons: 75 min Z2",
                "2018-12-27",
                "2018-11-13 spurter",
                "Varighet 100 km",
                "2 Q: spurt ≠ ny hard dag 1 — lett NM",
            ),
            (
                "Uke 2",
                "Sweet spot 3×15",
                "15 min opp · 3×15 @ 90 % · 5 min @ 40 % · ned",
                "4×8 @ 90 %",
                "15 min opp · 4×8 @ 90 % · 4 min pause · ned",
                "5,5 h / 6,5–7 h",
                "2 h Z2 · 90 min Z2",
                "2018-12-08",
                "2018-11-19",
                "Hold threshold",
                "2 Q: splitt tir + fre; ingen løp-Q",
            ),
            (
                "Uke 3",
                "Race-sim 4,5–5 h",
                "68–72 % + 3×20 min @ 78 % siste 2 h",
                "Crisscross 5×10",
                "Innlegg 5×10′ 45/15 midt i uka (egen dag, ikke etter race-sim)",
                "6–6,5 h / 7–8 h",
                "Spin dag 2",
                "2018 langtur",
                "2018-12-28",
                "Peak timer",
                "1 Q anbefalt uke 3; 2 Q kun TB grønn",
            ),
            (
                "Uke 4 (+1)",
                "Cut-back Z2",
                "2 h rolig",
                "—",
                "—",
                "2,5 h",
                "Spin 45",
                "2018 juleavlast",
                "—",
                "Cut volum",
                "0 hard Q",
            ),
        ],
    )
    sheet_build_block(
        wb,
        "Base_des2026",
        "Base nov–des 2026 · mot 275 W · tri ~10–12 t/uke (ikke NTG-dose)",
        [
            (
                "Uke 1",
                "SS 2×15",
                "88–90 % FTP · pauser 40 %",
                "Sykkel etter styrke 45–60 min Z2",
                "Rolig; ev. 5×8 s spurt (2018 eldre) — ikke hard Q",
                "3,5–4,5 h / 4–5 h",
                "2×75–90 min Z2",
                "2018-12-01",
                "2018-12-04",
                "Mot 275; ikke max etter FTP-test uke",
                "2. = støtte, teller ikke som Q med mindre spurter hard",
            ),
            (
                "Uke 2",
                "Crisscross 5×10",
                "45/15 @ 93/83 %",
                "4×8 @ 88–90 %",
                "Kortere terskel · 4 min pause",
                "4–5 h / 5–6 h",
                "90 + 120 min Z2",
                "2018-11-13",
                "2018-12-03",
                "Variety",
                "2 Q: drop FIRDA/løp-Q samme uke",
            ),
            (
                "Uke 3",
                "4×8 @ 90 %",
                "15 min opp · 4×8 · 4 min pause · ned",
                "Kapasitet 3×10×30/15 ELLER 18×3 (Plan B 12×3)",
                "Velg én: kapasitet (lettere) eller 18×3 (kun TB grønn)",
                "4–5,5 h / 5,5–6,5 h",
                "2 h Z2 · FTP retest uke",
                "2018-11-19",
                "2018-10-02 / 12-10",
                "275-test uke",
                "2 Q: ikke retest + 18×3 samme uke",
            ),
            (
                "Uke 4 (+1)",
                "Recovery",
                "Spin · 90 Z2",
                "—",
                "—",
                "2–2,5 h",
                "28–31 des kort ok",
                "2018-12-14",
                "—",
                "TSB opp",
                "0 hard Q",
            ),
        ],
    )


def main() -> None:
    wb = Workbook()
    sheet_intro(wb)
    sheet_2018(wb)
    sheet_tri(wb)
    add_build_sheets(wb)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()

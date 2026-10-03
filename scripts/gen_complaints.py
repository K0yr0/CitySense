"""Generate synthetic Warsaw 19115-style complaints -> data/complaints_synth.json.

40 issue spots on real Warsaw streets (approximate coordinates), 1–40 reports each
(~370 total), ~20 % with vague locations ("koło sklepu", "przy przystanku"), timestamps
clustered per spot over the last ~10 days. Six spots sit on the Marszałkowska tram
corridor (Plac Bankowy -> Plac Unii Lubelskiej) where the demo sensor rides run.

Record: {"text", "created_at", "true_issue_id", "true_category", "lon", "lat", "street"};
`true_*` are ground truth for evaluation only (never shown to the pipeline).

    python scripts/gen_complaints.py              # deterministic template mode (seeded)
    python scripts/gen_complaints.py --llm        # Claude writes the texts (needs ANTHROPIC_API_KEY)
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_OUT = REPO_ROOT / "data" / "complaints_synth.json"
VAGUE_RATE = 0.20
WINDOW_DAYS = 10

# (street, lon, lat, category, n_reports, specific place phrases, landmark phrases)
SPOTS: list[tuple[str, float, float, str, int, list[str], list[str]]] = [
    # --- Marszałkowska tram corridor (demo sensor rides) ---
    ("Marszałkowska", 21.0064, 52.2391, "tram_track", 12,
     ["na Marszałkowskiej przy Królewskiej", "na skrzyżowaniu Marszałkowskiej z Królewską", "ul. Marszałkowska róg Królewskiej"],
     ["przy przystanku Królewska", "koło Ogrodu Saskiego od strony Marszałkowskiej"]),
    ("Marszałkowska", 21.0087, 52.2352, "tram_track", 40,
     ["na Marszałkowskiej przy Świętokrzyskiej", "na skrzyżowaniu Marszałkowskiej i Świętokrzyskiej", "ul. Marszałkowska róg Świętokrzyskiej"],
     ["przy wyjściu z metra Świętokrzyska", "koło Domów Towarowych Centrum"]),
    ("Marszałkowska", 21.0115, 52.2309, "road_damage", 22,
     ["na Marszałkowskiej przy Rondzie Dmowskiego", "na Rondzie Dmowskiego", "na Marszałkowskiej przy Alejach Jerozolimskich"],
     ["przy Rotundzie", "koło przystanku Centrum"]),
    ("Marszałkowska", 21.0137, 52.2265, "tram_track", 8,
     ["na Marszałkowskiej przy Wilczej", "na skrzyżowaniu Marszałkowskiej z Wilczą", "ul. Marszałkowska róg Hożej"],
     ["przy przystanku Hoża", "koło Empiku na Marszałkowskiej"]),
    ("Plac Konstytucji", 21.0158, 52.2219, "streetlight", 15,
     ["na Placu Konstytucji", "na Marszałkowskiej przy Placu Konstytucji", "pl. Konstytucji od strony Marszałkowskiej"],
     ["pod arkadami MDM", "przy parkingu na Placu Konstytucji"]),
    ("Plac Unii Lubelskiej", 21.0228, 52.2118, "tram_track", 6,
     ["na Placu Unii Lubelskiej", "na Marszałkowskiej przy Placu Unii", "na skrzyżowaniu Marszałkowskiej z Puławską"],
     ["przy przystanku Plac Unii Lubelskiej", "koło Placu Unii City Shopping"]),
    # --- rest of the city ---
    ("Puławska", 21.0228, 52.2045, "road_damage", 19,
     ["na Puławskiej przy Madalińskiego", "na skrzyżowaniu Puławskiej i Madalińskiego", "ul. Puławska róg Madalińskiego"],
     ["przy przystanku Morskie Oko", "koło Biedronki na Puławskiej"]),
    ("Puławska", 21.0225, 52.1810, "tram_track", 9,
     ["na Puławskiej przy Domaniewskiej", "na Puławskiej koło metra Wilanowska", "ul. Puławska róg Domaniewskiej"],
     ["przy przystanku Metro Wilanowska", "koło stacji benzynowej na Puławskiej"]),
    ("Puławska", 21.0233, 52.1900, "streetlight", 5,
     ["na Puławskiej przy Królikarni", "na Puławskiej koło Malczewskiego", "ul. Puławska przy Malczewskiego"],
     ["przy Królikarni", "koło przystanku Królikarnia"]),
    ("Grójecka", 20.9845, 52.2195, "tram_track", 17,
     ["na Grójeckiej przy Placu Narutowicza", "na Placu Narutowicza", "na Grójeckiej koło Akademika"],
     ["przy przystanku Plac Narutowicza", "koło kościoła na Placu Narutowicza"]),
    ("Grójecka", 20.9790, 52.2147, "road_damage", 10,
     ["na Grójeckiej przy Banacha", "na skrzyżowaniu Grójeckiej z Banacha", "ul. Grójecka róg Banacha"],
     ["przy przystanku Banacha", "koło Lidla na Grójeckiej"]),
    ("Grójecka", 20.9722, 52.2082, "flooding", 4,
     ["na Grójeckiej przy Opaczewskiej", "na skrzyżowaniu Grójeckiej i Opaczewskiej"],
     ["przy przystanku Opaczewska", "koło bazarku na Grójeckiej"]),
    ("Aleje Jerozolimskie", 21.0040, 52.2288, "road_damage", 27,
     ["w Alejach Jerozolimskich przy Emilii Plater", "na skrzyżowaniu Alej Jerozolimskich i Emilii Plater", "Al. Jerozolimskie róg Emilii Plater"],
     ["przy Dworcu Centralnym", "koło Złotych Tarasów"]),
    ("Aleje Jerozolimskie", 21.0218, 52.2318, "tram_track", 11,
     ["na Rondzie de Gaulle'a", "w Alejach Jerozolimskich przy Nowym Świecie", "Al. Jerozolimskie róg Nowego Światu"],
     ["przy palmie na Rondzie de Gaulle'a", "koło przystanku Muzeum Narodowe"]),
    ("Aleje Jerozolimskie", 20.9660, 52.2195, "flooding", 7,
     ["w Alejach Jerozolimskich przy Dworcu Zachodnim", "w tunelu pod Alejami Jerozolimskimi przy Zachodnim", "Al. Jerozolimskie przy Tunelowej"],
     ["przy Dworcu Zachodnim", "koło przystanku Dworzec Zachodni"]),
    ("Aleje Jerozolimskie", 20.9897, 52.2240, "tram_track", 13,
     ["na Placu Zawiszy", "w Alejach Jerozolimskich przy Placu Zawiszy", "na skrzyżowaniu Alej Jerozolimskich z Grójecką"],
     ["przy przystanku Plac Zawiszy", "koło hotelu przy Placu Zawiszy"]),
    ("Rondo Daszyńskiego", 20.9832, 52.2302, "road_damage", 14,
     ["na Rondzie Daszyńskiego", "na skrzyżowaniu Prostej i Towarowej", "przy Rondzie Daszyńskiego od strony Prostej"],
     ["przy wyjściu z metra Rondo Daszyńskiego", "koło biurowców przy Rondzie Daszyńskiego"]),
    ("Świętokrzyska", 21.0005, 52.2343, "road_damage", 6,
     ["na Świętokrzyskiej przy Emilii Plater", "ul. Świętokrzyska róg Emilii Plater", "na skrzyżowaniu Świętokrzyskiej i Emilii Plater"],
     ["koło Pałacu Kultury od strony Świętokrzyskiej", "przy przystanku Emilii Plater"]),
    ("Świętokrzyska", 21.0128, 52.2370, "waste", 3,
     ["na Świętokrzyskiej przy Mazowieckiej", "ul. Świętokrzyska róg Mazowieckiej"],
     ["przy wejściu do metra na Świętokrzyskiej", "koło kawiarni na Mazowieckiej"]),
    ("Aleja Solidarności", 20.9935, 52.2428, "tram_track", 8,
     ["na Alei Solidarności przy Jana Pawła II", "na skrzyżowaniu Solidarności i Jana Pawła", "al. Solidarności róg Jana Pawła II"],
     ["przy przystanku Hala Mirowska", "koło Hali Mirowskiej"]),
    ("Aleja Solidarności", 20.9815, 52.2410, "streetlight", 4,
     ["na Alei Solidarności przy Okopowej", "na skrzyżowaniu Solidarności z Okopową"],
     ["przy przystanku Okopowa", "koło stacji benzynowej przy Okopowej"]),
    ("Aleja Solidarności", 21.0355, 52.2546, "waste", 9,
     ["na Alei Solidarności przy Dworcu Wileńskim", "na Targowej koło Dworca Wileńskiego"],
     ["przy Dworcu Wileńskim", "koło Galerii Wileńskiej"]),
    ("Targowa", 21.0398, 52.2508, "road_damage", 12,
     ["na Targowej przy Ząbkowskiej", "na skrzyżowaniu Targowej i Ząbkowskiej", "ul. Targowa róg Ząbkowskiej"],
     ["przy Bazarze Różyckiego", "koło metra Dworzec Wileński"]),
    ("Targowa", 21.0428, 52.2482, "flooding", 5,
     ["na Targowej przy Kijowskiej", "na skrzyżowaniu Targowej z Kijowską"],
     ["przy Dworcu Wschodnim", "koło przystanku Dworzec Wschodni"]),
    ("Grochowska", 21.0890, 52.2448, "tram_track", 10,
     ["na Grochowskiej przy Wiatracznej", "na Rondzie Wiatraczna", "na skrzyżowaniu Grochowskiej i Wiatracznej"],
     ["przy przystanku Wiatraczna", "koło Biedronki przy Wiatracznej"]),
    ("Grochowska", 21.0770, 52.2453, "road_damage", 7,
     ["na Grochowskiej przy Zamienieckiej", "ul. Grochowska róg Zamienieckiej"],
     ["przy przystanku Zamieniecka", "koło kościoła na Grochowskiej"]),
    ("Grochowska", 21.0650, 52.2460, "streetlight", 3,
     ["na Grochowskiej przy Kinowej", "ul. Grochowska róg Kinowej"],
     ["przy przystanku Kinowa"]),
    ("Nowy Świat", 21.0200, 52.2340, "waste", 16,
     ["na Nowym Świecie przy Chmielnej", "na rogu Nowego Światu i Chmielnej", "ul. Nowy Świat róg Chmielnej"],
     ["koło Bliklego na Nowym Świecie", "przy wejściu w Chmielną"]),
    ("Krakowskie Przedmieście", 21.0160, 52.2403, "streetlight", 1,
     ["na Krakowskim Przedmieściu przy Uniwersytecie"], ["przy bramie Uniwersytetu"]),
    ("Andersa", 20.9978, 52.2510, "tram_track", 5,
     ["na Andersa przy Muranowskiej", "na skrzyżowaniu Andersa i Muranowskiej"], ["przy przystanku Muranowska"]),
    ("Okopowa", 20.9850, 52.2512, "flooding", 6,
     ["na Okopowej przy Stawkach", "na skrzyżowaniu Okopowej i Stawek"],
     ["przy przystanku Stawki", "koło cmentarza na Okopowej"]),
    ("Wolska", 20.9668, 52.2330, "road_damage", 8,
     ["na Wolskiej przy Płockiej", "ul. Wolska róg Płockiej"], ["przy przystanku Płocka", "koło Biedronki na Wolskiej"]),
    ("Górczewska", 20.9460, 52.2385, "flooding", 1,
     ["na Górczewskiej przy Prymasa Tysiąclecia"], ["koło Wola Parku"]),
    ("Rakowiecka", 21.0065, 52.2063, "streetlight", 6,
     ["na Rakowieckiej przy Alei Niepodległości", "ul. Rakowiecka róg Niepodległości"], ["koło SGH", "przy przystanku Rakowiecka"]),
    ("Jagiellońska", 21.0230, 52.2600, "tram_track", 4,
     ["na Jagiellońskiej przy Ratuszowej", "ul. Jagiellońska róg Ratuszowej"],
     ["przy przystanku Ratuszowa-ZOO", "koło ZOO od strony Jagiellońskiej"]),
    ("Radzymińska", 21.0490, 52.2560, "flooding", 3,
     ["na Radzymińskiej przy Ząbkowskiej", "ul. Radzymińska róg Ząbkowskiej"], ["koło Lidla na Radzymińskiej"]),
    ("Modlińska", 21.0020, 52.2930, "road_damage", 5,
     ["na Modlińskiej przy Żeraniu", "ul. Modlińska koło FSO"], ["przy przystanku Żerań FSO"]),
    ("Ostrobramska", 21.1110, 52.2350, "road_damage", 4,
     ["na Ostrobramskiej przy Fieldorfa", "ul. Ostrobramska róg Fieldorfa"], ["koło CH Promenada"]),
    ("Aleja KEN", 21.0430, 52.1500, "waste", 1, ["na KEN przy metrze Imielin"], ["przy metrze Imielin"]),
    ("Słowackiego", 20.9845, 52.2690, "streetlight", 1, ["na Słowackiego przy Placu Wilsona"], ["przy Placu Wilsona"]),
]

VAGUE = ["koło sklepu", "przy przystanku", "na mojej ulicy", "pod blokiem", "przy szkole", "tam gdzie zawsze",
         "na rogu", "obok apteki", "przy Biedronce", "koło Żabki", "na osiedlu", "przy przejściu dla pieszych",
         "niedaleko kościoła", "przy pętli", "u nas na ulicy", ""]

PROBLEMS: dict[str, list[str]] = {
    "road_damage": [
        "Ogromna dziura w jezdni {loc}.", "{Loc} jest wielka dziura, auta wpadają w nią kołami.",
        "dziura na dziurze {loc}, jezdnia cała rozwalona", "Wyrwa w asfalcie {loc}, z każdym dniem większa.",
        "Zapadnięta nawierzchnia {loc}.", "{Loc} asfalt się kruszy i robi się głęboka wyrwa.",
        "Koleiny i dziury {loc}, nie da się normalnie jechać.", "Uszkodzony chodnik {loc}, płyty powyrywane.",
        "{Loc} znowu dziura, tym razem jeszcze głębsza.", "Głęboka dziura {loc}, w deszczu jej w ogóle nie widać.",
        "rozwalony asfalt {loc}, opona do wymiany", "Wyrwany krawężnik i dziura przy przejściu {loc}.",
        "Na jezdni {loc} zrobił się ubytek na pół pasa.", "dziura w drodze {loc} jak krater",
    ],
    "tram_track": [
        "Tory tramwajowe {loc} są w fatalnym stanie, tramwaj strasznie stuka.",
        "{Loc} szyny wystają ponad asfalt.", "Głośne walenie tramwajów {loc}, coś jest nie tak z torowiskiem.",
        "Pęknięta szyna {loc}?? Tramwaj podskakuje.", "Rozjazd tramwajowy {loc} hałasuje całą noc.",
        "Torowisko {loc} się zapada, między szynami dziury.", "Zwrotnica {loc} chyba uszkodzona, tramwaje zwalniają do zera.",
        "Płyty torowiska {loc} ruszają się pod kołami tramwaju.", "{Loc} tramwaj mocno szarpnął na torach.",
        "tramwaje {loc} trzęsą jak pralka, tory do remontu", "Uszkodzone tory {loc}, słychać metaliczne uderzenia.",
        "Szczelina przy szynie tramwajowej {loc}, koło roweru wpada.",
    ],
    "streetlight": [
        "Latarnia {loc} nie świeci od tygodnia.", "{Loc} ciemno jak w lesie, żadna latarnia nie działa.",
        "Nie działa oświetlenie uliczne {loc}.", "latarnie {loc} mrugają cały wieczór",
        "Zgasły wszystkie lampy {loc}, strach chodzić po zmroku.", "Brak oświetlenia na przejściu dla pieszych {loc}.",
        "{Loc} lampa uliczna wisi krzywo i nie świeci.", "Od kilku dni {loc} kompletnie ciemno, latarnie nie działają.",
        "latarnia nie świeci {loc}", "Nie świeci się żadna latarnia {loc}.",
    ],
    "flooding": [
        "Po każdym deszczu {loc} zalana jezdnia, woda po kostki.", "Zatkana studzienka kanalizacyjna {loc}, woda nie schodzi.",
        "{Loc} stoi ogromna kałuża, auta chlapią na ludzi.", "Zalany przejazd {loc}.",
        "Cofa się kanalizacja {loc}, śmierdzi ściekami.", "Woda wybija ze studzienki {loc}.",
        "Pękła rura? Woda leje się na ulicę {loc}.", "Zalane przejście {loc}, nie da się przejść suchą stopą.",
        "Studzienka {loc} zapchana, cała ulica zalana.", "{Loc} po ulewie wielkie rozlewisko, kratki nie odbierają wody.",
    ],
    "waste": [
        "Przepełnione kosze na śmieci {loc}.", "Ktoś wyrzucił gruz i stare meble {loc}.",
        "{Loc} leżą worki ze śmieciami od kilku dni.", "Dzikie wysypisko śmieci {loc}.",
        "Śmieci wysypują się z kontenerów {loc}.", "Butelki i odpady wszędzie {loc}, nikt nie sprząta.",
        "Porzucone opony i inne odpady {loc}.", "Kosz {loc} pełny, śmieci fruwają po chodniku.",
        "{Loc} góra śmieci przy koszu.", "Nikt nie wywozi odpadów {loc}, śmietnik się przelewa.",
    ],
}
PROBLEMS_EN = {
    "road_damage": "Huge pothole {loc}, please fix it.", "tram_track": "The tram tracks {loc} are broken, trams are very loud.",
    "streetlight": "Streetlight {loc} is out, it is very dark at night.",
    "flooding": "Flooded street {loc} after rain, the drains are blocked.", "waste": "Rubbish everywhere {loc}, bins overflowing.",
}
SHORT = {"road_damage": "dziura", "tram_track": "tory", "streetlight": "latarnia nie świeci",
         "flooding": "zalane", "waste": "śmieci"}
DETAILS: dict[str, list[str]] = {
    "road_damage": ["Prawie urwałem koło.", "Rowerzysta się dziś przewrócił.", "Auta gwałtownie hamują i omijają.",
                    "Zaraz będzie wypadek.", "Dzieci tędy chodzą do szkoły.", "W nocy jej w ogóle nie widać.",
                    "Uszkodziłem felgę.", "Autobusy zjeżdżają na drugi pas.", "Niebezpiecznie dla motocyklistów."],
    "tram_track": ["W tramwaju wszystko się trzęsie.", "Ludzie w tramwaju lecą na siebie.", "Rowerzysta wpadł kołem w szynę.",
                   "Hałas słychać na całym osiedlu.", "Tramwaje jeżdżą tu bardzo wolno.", "Jakby zaraz miał się wykoleić.",
                   "Niebezpieczne dla rowerzystów."],
    "streetlight": ["Strach wracać wieczorem.", "Piesi na przejściu są niewidoczni.", "Dzieci wracają tędy z treningów po ciemku.",
                    "Ktoś się już przewrócił po ciemku.", "Kierowcy nie widzą ludzi na pasach."],
    "flooding": ["Piesi muszą chodzić jezdnią.", "Woda wlewa się do klatki schodowej.", "Auta stają w wodzie.",
                 "Smród nie do wytrzymania.", "Zimą będzie lodowisko."],
    "waste": ["Szczury biegają.", "Smród nie do wytrzymania.", "Wiatr roznosi śmieci po ulicy.",
              "Wygląda to jak wysypisko.", "Dzieci się tam bawią."],
}
TIMES = ["Trwa to od tygodnia.", "Od wczoraj.", "Już trzeci dzień.", "Zgłaszam już drugi raz.", "Problem jest od miesiąca.",
         "Nikt nic z tym nie robi od tygodni.", "Zauważyłem dziś rano.", "Wczoraj wieczorem było jeszcze gorzej."]
OPENERS = ["", "", "", "Dzień dobry,", "Witam,", "Dzień dobry.", "Zgłaszam:", "Halo,", "Szanowni Państwo,", "Hej,",
           "Kolejne zgłoszenie:", "Ludzie,", "Pilne!"]
CLOSERS = ["", "", "Proszę o interwencję.", "Proszę o pilną naprawę.", "Zróbcie coś z tym!", "Pozdrawiam.", "Dziękuję.",
           "Ile można czekać?!", "Masakra.", "Dramat.", "Serio, ile jeszcze?", "Bardzo proszę o szybką reakcję.",
           "Kto za to odpowiada?"]
SLANG = ["masakra", "dramat jakiś", "no ludzie", "kurde", "serio", "porażka", "szok", "no bez jaj"]
_ASCII = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")


# --------------------------------------------------------------------------- template generator
def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def _typo(word: str, rng: random.Random) -> str:
    i = rng.randrange(1, len(word) - 1)
    op = rng.choice(("swap", "drop", "double"))
    if op == "swap":
        return word[:i] + word[i + 1] + word[i] + word[i + 2:]
    if op == "drop":
        return word[:i] + word[i + 1:]
    return word[:i] + word[i] + word[i:]


def _style(text: str, rng: random.Random) -> str:
    """Typos, missing diacritics, lowercase, shouting, slang."""
    if rng.random() < 0.30:
        words = text.split(" ")
        for _ in range(rng.randint(1, 2)):
            idx = [i for i, w in enumerate(words) if len(w) >= 5 and w.isalpha()]
            if idx:
                j = rng.choice(idx)
                words[j] = _typo(words[j], rng)
        text = " ".join(words)
    if rng.random() < 0.15:
        slang = rng.choice(SLANG)
        text = f"{_cap(slang)}, {text[:1].lower()}{text[1:]}" if rng.random() < 0.5 else f"{text} {_cap(slang)}."
    if rng.random() < 0.25:
        text = text.translate(_ASCII)
    r = rng.random()
    if r < 0.05:
        text = text.upper().rstrip(".") + "!!!"
    elif r < 0.30:
        text = text.lower()
    if rng.random() < 0.10:
        text = re.sub(r"\.$", "!!", text)
    return text


def template_text(spot: tuple, rng: random.Random, vague: bool) -> str:
    """One complaint about `spot` in a random style."""
    street, _, _, cat, _, places, marks = spot
    if vague:
        loc = rng.choice(VAGUE)
    elif marks and rng.random() < 0.3:
        loc = rng.choice(marks)
    else:
        loc = rng.choice(places)
    roll = rng.random()
    if roll < 0.05:  # expat in English
        loc_en = rng.choice(["near the shop", "at the bus stop", "on my street", ""]) if vague else f"on {street}"
        body = PROBLEMS_EN[cat].format(loc=loc_en)
    elif roll < 0.15:  # terse / repeat reporter
        short = SHORT[cat]
        body = rng.choice([f"{short} {loc}", f"znowu to samo {loc} – {short}", f"{_cap(loc)} {short}!!", f"{short}. {loc}"])
    else:
        opener = rng.choice(OPENERS)
        tpl = rng.choice(PROBLEMS[cat])
        body = _cap(tpl.replace("{Loc}", _cap(loc)).replace("{loc}", loc).strip())
        if opener.endswith(","):
            body = body[:1].lower() + body[1:]
        if not body.endswith((".", "!", "?")):
            body += "."
        parts = [opener, body]
        if rng.random() < 0.5:
            parts.append(rng.choice(DETAILS[cat]))
        if rng.random() < 0.35:
            parts.append(rng.choice(TIMES))
        parts.append(rng.choice(CLOSERS))
        body = " ".join(p for p in parts if p)
    body = re.sub(r"\s+([,.!?:])", r"\1", re.sub(r"\s{2,}", " ", body)).strip(" –")
    return _style(_cap(body), rng)


# --------------------------------------------------------------------------- LLM generator
LLM_PROMPT = """You write realistic synthetic citizen complaints for testing a Warsaw 19115 hotline triage system.
Write the requested number of complaints in Polish, each by a different person, about the SAME problem at the SAME \
place. Vary length (3 words to 4 sentences), tone (polite, angry, ironic, tired), slang, typos, missing Polish \
diacritics, lowercase typing, and sentence order. Roughly {vague_pct}% of them must have a vague location only \
("koło sklepu", "przy przystanku", "pod blokiem", or no place at all) without the street name. Never include \
personal data (names, phone numbers, plate numbers). Return ONLY the JSON object."""


def llm_texts(spot: tuple, n: int) -> list[str] | None:
    """Ask Claude for `n` complaint texts about `spot`; None on failure."""
    from pydantic import BaseModel

    from backend.triage.structure import call_claude

    class _Batch(BaseModel):
        texts: list[str]

    street, _, _, cat, _, places, marks = spot
    request = (f"Number of complaints: {n}\nProblem category: {cat} ({SHORT[cat]})\nStreet: {street}\n"
               f"Exact place: {places[0]}\nNearby landmarks: {', '.join(marks) or '-'}")
    try:
        out = call_claude(LLM_PROMPT.format(vague_pct=int(VAGUE_RATE * 100)), request, schema=_Batch,
                          max_tokens=16000)
        texts = [t.strip() for t in out.texts if t.strip()]
        return texts or None
    except Exception as exc:
        print(f"  LLM failed for {street} ({exc}); using templates", file=sys.stderr)
        return None


# --------------------------------------------------------------------------- assembly
def _jitter(lon: float, lat: float, rng: random.Random, sigma_m: float = 8.0, max_m: float = 25.0) -> tuple[float, float]:
    """Citizen pin noise around the true spot (GPS / tapping inaccuracy)."""
    dx, dy = (max(-max_m, min(max_m, rng.gauss(0, sigma_m))) for _ in range(2))
    return (round(lon + dx / (111_320 * math.cos(math.radians(lat))), 6), round(lat + dy / 111_320, 6))


def _timestamps(n: int, now: datetime, rng: random.Random) -> list[datetime]:
    """n timestamps clustered in a 0.3–4 day burst somewhere in the last WINDOW_DAYS days."""
    burst = timedelta(days=rng.uniform(0.3, 4.0))
    start = now - timedelta(days=rng.uniform(0.2, WINDOW_DAYS - 0.2))
    start = min(start, now - burst - timedelta(minutes=10))
    offsets = sorted(rng.betavariate(1.2, 2.5) for _ in range(n))  # front-loaded: most reports early in the burst
    return [(start + burst * o).replace(microsecond=0) for o in offsets]


def generate(seed: int = 19115, now: datetime | None = None, use_llm: bool = False,
             stats: dict | None = None) -> list[dict]:
    """All synthetic complaints, sorted by created_at. `stats` (optional) receives counts."""
    now = (now or datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)).astimezone(timezone.utc)
    records: list[dict] = []
    n_vague = 0
    for issue_id, spot in enumerate(SPOTS, start=1):
        street, lon, lat, cat, n, _, _ = spot
        rng = random.Random(seed * 1000 + issue_id)
        vague_flags = [rng.random() < VAGUE_RATE for _ in range(n)]
        texts = llm_texts(spot, n) if use_llm else None
        if texts:
            texts = (texts + [template_text(spot, rng, v) for v in vague_flags])[:n]
        else:
            texts = [template_text(spot, rng, v) for v in vague_flags]
            n_vague += sum(vague_flags)
        for text, ts in zip(texts, _timestamps(n, now, rng)):
            plon, plat = _jitter(lon, lat, rng)
            records.append({"text": text, "created_at": ts.isoformat(), "true_issue_id": issue_id,
                            "true_category": cat, "lon": plon, "lat": plat, "street": street})
    records.sort(key=lambda r: r["created_at"])
    if stats is not None:
        stats.update(total=len(records), spots=len(SPOTS), vague=n_vague)
    return records


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--llm", action="store_true", help="let Claude write the texts (falls back to templates)")
    ap.add_argument("--seed", type=int, default=19115)
    ap.add_argument("--now", help="reference time, ISO-8601 (default: current UTC hour)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    use_llm = args.llm
    if use_llm:
        from backend.triage.structure import llm_available

        if not llm_available():
            print("--llm requested but no ANTHROPIC_API_KEY; using templates", file=sys.stderr)
            use_llm = False
    now = datetime.fromisoformat(args.now) if args.now else None
    if now is not None and now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    stats: dict = {}
    records = generate(args.seed, now, use_llm, stats)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    by_cat: dict[str, int] = {}
    for r in records:
        by_cat[r["true_category"]] = by_cat.get(r["true_category"], 0) + 1
    print(f"wrote {len(records)} complaints about {stats['spots']} spots -> {args.out}")
    print(f"  per category: {by_cat}; vague locations (template mode): {stats['vague']}")


if __name__ == "__main__":
    main()

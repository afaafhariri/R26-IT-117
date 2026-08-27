"""
generate_synthetic.py — Generates synthetic Sri Lankan coastal cadastral plan text.

Creates 300 realistic synthetic OCR texts with known correct entity labels.
Focuses on coastal districts. No manual review needed — labels are 100% correct.

Run from Architecture/:
    python generate_synthetic.py
"""

import json
import math
import random
from pathlib import Path

random.seed(42)

OUTPUT_DIR = Path(__file__).resolve().parent / "data" / "ocr_results"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Coastal districts and their villages ─────────────────────────────────────

_DISTRICTS = {
    "Ampara": [
        "Kalmunai", "Sammanthurai", "Addalaichenai", "Nintavur", "Akkaraipattu",
        "Pottuvil", "Oluvil", "Sainthamaruthu", "Karaitivu", "Thirukkovil",
        "Alayadivembu", "Ninthavur", "Maruthamunai", "Irakkamam", "Kalmunaikudy",
    ],
    "Batticaloa": [
        "Batticaloa", "Kattankudy", "Eravur", "Valaichenai", "Oddamavadi",
        "Kallar", "Koddaikallar", "Passikudah", "Kallady", "Arayampathy",
        "Chenkalady", "Vakarai", "Mankerni", "Paddiruppu",
    ],
    "Trincomalee": [
        "Trincomalee", "Kinniya", "Mutur", "Kantale", "Nilaveli",
        "Uppuveli", "Kuchchaveli", "Gomarankadawala", "Thambalagamuwa",
    ],
    "Jaffna": [
        "Jaffna", "Nallur", "Chavakachcheri", "Point Pedro", "Karainagar",
        "Velanai", "Kayts", "Delft", "Manipay", "Kopay", "Uduvil",
    ],
    "Galle": [
        "Galle", "Hikkaduwa", "Unawatuna", "Ahangama", "Balapitiya",
        "Ambalangoda", "Bentota", "Karandeniya", "Baddegama",
    ],
    "Matara": [
        "Matara", "Weligama", "Mirissa", "Dikwella", "Dondra",
        "Hakmana", "Akuressa", "Kamburupitiya", "Deniyaya",
    ],
    "Hambantota": [
        "Hambantota", "Tangalle", "Tissamaharama", "Weeraketiya",
        "Beliatta", "Ambalantota", "Sooriyawewa", "Lunugamvehera",
    ],
    "Puttalam": [
        "Puttalam", "Chilaw", "Mundel", "Marawila", "Dankotuwa",
        "Wennappuwa", "Nattandiya", "Anamaduwa",
    ],
    "Colombo": [
        "Colombo", "Dehiwala", "Moratuwa", "Mount Lavinia",
        "Wellawatte", "Ratmalana", "Panadura",
    ],
    "Gampaha": [
        "Negombo", "Wattala", "Ja-Ela", "Seeduwa", "Katunayake",
        "Hendala", "Peliyagoda", "Ragama",
    ],
    "Kalutara": [
        "Kalutara", "Panadura", "Beruwala", "Aluthgama",
        "Bentota", "Wadduwa", "Matugama", "Horana",
    ],
}

_PROVINCES = {
    "Ampara": "EASTERN PROVINCE",
    "Batticaloa": "EASTERN PROVINCE",
    "Trincomalee": "EASTERN PROVINCE",
    "Jaffna": "NORTHERN PROVINCE",
    "Galle": "SOUTHERN PROVINCE",
    "Matara": "SOUTHERN PROVINCE",
    "Hambantota": "SOUTHERN PROVINCE",
    "Puttalam": "NORTH WESTERN PROVINCE",
    "Colombo": "WESTERN PROVINCE",
    "Gampaha": "WESTERN PROVINCE",
    "Kalutara": "WESTERN PROVINCE",
}

# ── Surveyor names by region ──────────────────────────────────────────────────

_SURVEYORS_MUSLIM = [
    ("M.M.Ibrahim", "FSI"), ("S.M.Ibrahim", "CSSI Sri Lanka"),
    ("A.L.Mohamed Husyen", "FSI"), ("Mohamed Thasleem", "FSI"),
    ("A.R.Nazar", "FSI"), ("M.H.Farook", "CSSI Sri Lanka"),
    ("Abdul Hameed", "FSI"), ("Mohamed Saleem", "FSI"),
    ("Noor Mohamed", "FSI"), ("M.I.Mohideen", "FSI"),
    ("A.M.Farook", "CSSI Sri Lanka"), ("S.A.Nazar", "FSI"),
    ("M.S.Mubarak", "FSI"), ("I.L.Hameed", "FSI"),
    ("A.B.Samsudeen", "CSSI Sri Lanka"),
]

_SURVEYORS_TAMIL = [
    ("K.Krishnamoorthy", "FSI"), ("S.Sivapalan", "FSI"),
    ("T.Rajaratnam", "CSSI Sri Lanka"), ("V.Karunakaran", "FSI"),
    ("A.Mahendran", "FSI"), ("M.Kandiah", "FSI"),
    ("R.Thambipillai", "FSI"), ("S.Yogaratnam", "FSI"),
    ("K.Balasubramaniam", "CSSI Sri Lanka"), ("T.Nadarajah", "FSI"),
]

_SURVEYORS_SINHALA = [
    ("H.D.Perera", "FSI"), ("R.M.Silva", "CSSI Sri Lanka"),
    ("D.C.Fernando", "FSI"), ("W.A.Jayasinghe", "FSI"),
    ("P.K.Wickramasinghe", "FSI"), ("S.B.Dissanayake", "FSI"),
    ("M.R.Gunasekara", "CSSI Sri Lanka"), ("B.G.Ranasinghe", "FSI"),
]

_SURVEYORS_BY_DISTRICT = {
    "Ampara":      _SURVEYORS_MUSLIM,
    "Batticaloa":  _SURVEYORS_TAMIL + _SURVEYORS_MUSLIM,
    "Trincomalee": _SURVEYORS_TAMIL + _SURVEYORS_MUSLIM,
    "Jaffna":      _SURVEYORS_TAMIL,
    "Galle":       _SURVEYORS_SINHALA,
    "Matara":      _SURVEYORS_SINHALA,
    "Hambantota":  _SURVEYORS_SINHALA,
    "Puttalam":    _SURVEYORS_SINHALA + _SURVEYORS_MUSLIM,
    "Colombo":     _SURVEYORS_SINHALA + _SURVEYORS_TAMIL,
    "Gampaha":     _SURVEYORS_SINHALA,
    "Kalutara":    _SURVEYORS_SINHALA,
}

_ADDRESSES_BY_DISTRICT = {
    "Ampara":      ["11/A, Main Street, Kaanady Lane, Sainthamaruthu",
                    "24, Akkaraipattu Road, Kalmunai", "370, Union Road, Akkaraipattu"],
    "Batticaloa":  ["42, Bar Road, Batticaloa", "15, Trinco Road, Eravur"],
    "Trincomalee": ["12, Inner Harbour Road, Trincomalee", "5, Dockyard Road, Trincomalee"],
    "Jaffna":      ["23, Stanley Road, Jaffna", "7, Hospital Road, Chavakachcheri"],
    "Galle":       ["18, Closenberg Road, Galle", "5, Wakwella Road, Galle"],
    "Matara":      ["12, Anagarika Dharmapala Mawatha, Matara", "3, Beach Road, Weligama"],
    "Hambantota":  ["6, New Town Road, Hambantota", "14, Tangalle Road, Hambantota"],
    "Puttalam":    ["8, Kurunegala Road, Puttalam", "22, Main Street, Chilaw"],
    "Colombo":     ["45, Galle Road, Colombo 03", "12, Duplication Road, Colombo 04"],
    "Gampaha":     ["15, Colombo Road, Negombo", "8, Kurana Road, Ja-Ela"],
    "Kalutara":    ["5, Galle Road, Kalutara", "12, Marine Drive, Beruwala"],
}

_ROAD_TYPES = [
    "Main Road", "Provincial Road", "Road (RDA)", "Private Lane",
    "Grama Road", "School Road", "Mosque Road", "Church Road",
    "Temple Road", "Beach Road", "Harbour Road", "New Road",
]

_LAND_NAMES = [
    "Thennamthottam", "Roadadykandam", "Aanaikulaththukadu", "Thennanthoddapoomi",
    "Puthukudiyiruppu", "Kadatkaraippalli", "Sinnakkadai", "Periyapandivirichchan",
    "Maruthamunai", "Oluvil South", "Karaitivu North", "Nintavur East",
    "Ninthavur Garden", "Akkaraipattu South", "Kalmunai North",
]

_PLAN_PREFIXES = ["", "T/", "N/", "K/", "AP/", "BT/", "TR/"]

_SCALES = [500, 1000, 2000, 2500]

# SLD99 coordinate ranges per district (N, E) — approximate real ranges
_COORD_RANGES = {
    "Ampara":      ((480000, 560000), (600000, 650000)),
    "Batticaloa":  ((520000, 600000), (630000, 670000)),
    "Trincomalee": ((600000, 680000), (580000, 640000)),
    "Jaffna":      ((720000, 800000), (520000, 580000)),
    "Galle":       ((280000, 340000), (380000, 430000)),
    "Matara":      ((260000, 310000), (430000, 480000)),
    "Hambantota":  ((280000, 360000), (470000, 550000)),
    "Puttalam":    ((580000, 660000), (380000, 430000)),
    "Colombo":     ((410000, 440000), (390000, 420000)),
    "Gampaha":     ((420000, 460000), (380000, 410000)),
    "Kalutara":    ((360000, 410000), (380000, 420000)),
}


# ── Area generation ───────────────────────────────────────────────────────────

def _random_area():
    """Returns (sqm, ha, A, R, P) for a random realistic plot size."""
    sqm = round(random.uniform(30, 1500), 1)
    ha  = round(sqm / 10000, 5)
    perches_total = sqm / 25.2929
    A = int(perches_total // 160)
    R = int((perches_total % 160) // 40)
    P = round(perches_total % 40, 2)
    return sqm, ha, A, R, P


def _area_format_1(sqm, ha, A, R, P):
    return (
        f"The entire Land is containing in extent :{ha:.5f} Hectare "
        f"({A}A-{R}R-{P:.2f}P)={sqm} Square metre"
    )

def _area_format_2(sqm, ha, A, R, P):
    return f"Containing Total Extent {ha:.4f} Hectare or {A}A:{R}R:{P:.2f}P"

def _area_format_3(sqm, ha, A, R, P):
    return f"containing in extent :{sqm} Square metre"

def _area_format_4(sqm, ha, A, R, P):
    return f"Containing in Extent of Lot 1  {ha:.4f}  {A}.  {R}.  {P:.2f}"

def _area_format_5(sqm, ha, A, R, P):
    return f"Total Extent {sqm} sq.m ({ha:.4f} Ha)"

_AREA_FORMATS = [_area_format_1, _area_format_2, _area_format_3, _area_format_4, _area_format_5]


# ── Plan text generation ──────────────────────────────────────────────────────

def _make_plan_text(district, village, surveyor_name, credential, address,
                    plan_no, scale, road, land_name, area_text, licence_no,
                    lot="A", coord_n=None, coord_e=None):
    province   = _PROVINCES[district]
    coord_line = ""
    coord_note = ""
    if coord_n and coord_e:
        # 50/50 between GPS note and grid coordinates in text
        if random.random() < 0.5:
            coord_note = "* Hand GPS Coordinates were used for Location\n"
            coord_line = f"{coord_n} N\n{coord_e} E\n"
        else:
            coord_line = (
                f"The National Survey Grid Coordinates were used for the surveying.\n"
                f"N : {coord_n}\nE : {coord_e}\n"
            )
    return f"""{surveyor_name}, {credential}
Registered Licensed Surveyor Leveller and Court Commissioner
{address}
Licence No.{licence_no}
Land Survey Council Registration No.{random.randint(1000000, 9999999)}
{coord_note}
PLAN No.{plan_no}

Scale 1:{scale}
{coord_line}
PLAN
of an allotment of Land called "{land_name}"
situated in {village} within the local limits of {village} Pradeshiya Sabha
in {village} Divisional Secretariat Area in

{district.upper()} DISTRICT
{province}

Lot {lot} bounded as follows:
North by : Garden, Claimed by Road and {road}
East by  : {road} and Garden Claimed by adjoining owner
South by : Garden and Private Lane
West by  : Garden Claimed by present owner

{area_text}

The survey was requested by the claimant and the boundaries pointed out by the claimant.
Surveyed on : {random.randint(2015,2025)}.{random.randint(1,12):02d}.{random.randint(1,28):02d}
Plan issued on : {random.randint(2015,2025)}.{random.randint(1,12):02d}.{random.randint(1,28):02d}

{surveyor_name}
Registered Licensed Surveyor. (Regtn. No {random.randint(10000000, 99999999)})
"""


# ── Main generator ────────────────────────────────────────────────────────────

def main():
    existing = {p.stem for p in OUTPUT_DIR.glob("synth_*.json")}
    generated = 0
    idx = 0

    districts = list(_DISTRICTS.keys())

    while generated < 300:
        idx += 1
        filename = f"synth_{idx:04d}.pdf"
        stem     = f"synth_{idx:04d}"

        if stem in existing:
            generated += 1
            continue

        district  = random.choice(districts)
        village   = random.choice(_DISTRICTS[district])
        surveyor_name, credential = random.choice(_SURVEYORS_BY_DISTRICT[district])
        address   = random.choice(_ADDRESSES_BY_DISTRICT[district])
        prefix    = random.choice(_PLAN_PREFIXES)
        plan_num  = f"{prefix}{random.randint(100, 4999)}"
        scale     = random.choice(_SCALES)
        road      = random.choice(_ROAD_TYPES)
        land_name = random.choice(_LAND_NAMES)
        licence   = str(random.randint(100000, 999999))
        lot       = random.choice(["A", "B", "1", "2", "3"])

        sqm, ha, A, R, P = _random_area()
        area_fmt  = random.choice(_AREA_FORMATS)
        area_text = area_fmt(sqm, ha, A, R, P)

        # 50% of plans have coordinates, 50% do not
        coord_n, coord_e = None, None
        if random.random() < 0.5:
            n_range, e_range = _COORD_RANGES[district]
            coord_n = random.randint(*n_range)
            coord_e = random.randint(*e_range)

        text = _make_plan_text(
            district, village, surveyor_name, credential, address,
            plan_num, scale, road, land_name, area_text, licence, lot,
            coord_n=coord_n, coord_e=coord_e,
        )

        # Build NER corrected — 100% accurate since we control generation
        ner = {
            "plan_number":    plan_num,
            "district":       district,
            "area_sqm":       sqm,
            "scale":          scale,
            "surveyor":       surveyor_name,
            "road_access":    road,
            "lot_number":     lot,
            "is_coastal":     True,
            "province":       _PROVINCES[district],
            "coordinate_n":   float(coord_n) if coord_n else None,
            "coordinate_e":   float(coord_e) if coord_e else None,
            "licence_number": licence,
        }

        record = {
            "filename":       filename,
            "raw_text":       text,
            "token_count":    len(text.split()),
            "ner_auto":       ner,
            "ner_corrected":  ner,   # same — synthetic data is already correct
        }

        out_path = OUTPUT_DIR / f"{stem}.json"
        out_path.write_text(
            json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        generated += 1

        if generated % 50 == 0:
            print(f"Generated {generated}/300 ...")

    print(f"\nDone! 300 synthetic examples saved to {OUTPUT_DIR}")
    print("Next step: run  python convert_to_spacy.py  then  python train_ner.py")


if __name__ == "__main__":
    main()

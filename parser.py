#!/usr/bin/env python3
"""Parse a Finnish air-surveillance voice report transcript into a structured report.

Field order is fixed (see memory/project_voice_report_format.md):
  wake word -> maalin numero -> sijainti (MGRS) -> suunta -> nopeus -> korkeus
  -> lukumaara -> muodostelma -> [muut tiedot]

Closed-vocabulary fields (suunta word, nopeus, korkeus, lukumaara) are matched
by anchor keywords; open fields (numero, MGRS, degrees, muodostelma, extra)
are extracted from the text between anchors.
"""
import re
import sys
import json
import difflib
import urllib.request

INGEST_URL = "http://127.0.0.1:8642/ingest"

DIGIT_WORDS = {
    "nolla": "0", "yksi": "1", "kaksi": "2", "kolme": "3", "neljä": "4",
    "viisi": "5", "kuusi": "6", "seitsemän": "7", "kahdeksan": "8", "yhdeksän": "9",
}

NATO_ALPHABET = {
    "alpha": "A", "bravo": "B", "charlie": "C", "delta": "D", "echo": "E",
    "foxtrot": "F", "golf": "G", "hotel": "H", "india": "I", "juliet": "J",
    "kilo": "K", "lima": "L", "mike": "M", "november": "N", "oscar": "O",
    "papa": "P", "quebec": "Q", "romeo": "R", "sierra": "S", "tango": "T",
    "uniform": "U", "victor": "V", "whiskey": "W", "xray": "X", "yankee": "Y",
    "zulu": "Z",
}

COMPASS_WORDS = {
    "pohjoiseen": "N", "koilliseen": "NE", "itään": "E", "kaakkoon": "SE",
    "etelään": "S", "lounaaseen": "SW", "länteen": "W", "luoteeseen": "NW",
}

SPEED_WORDS = {"hidas": "Hidas", "nopea": "Nopea", "erittäin nopea": "Erittäin nopea"}

ALTITUDE_WORDS = {"pinnassa": "Pinnassa", "matalalla": "Matalalla", "korkealla": "Korkealla"}

COUNT_WORDS = {"yksittäinen": "1", "pari": "2", "useita": "Useita"}

WAKE_WORDS = ("uusi maali", "maali")


def normalize(text):
    text = text.lower()
    text = text.replace("-", " ")
    text = re.sub(r"[.,!?]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize_digits(tokens, start, max_count=None):
    """Consume consecutive digit-words (or literal digits) starting at `start`,
    up to `max_count` digits if given (e.g. target number is always exactly 4,
    direction degrees always exactly 3 - capping avoids swallowing digits that
    belong to the next field when the spoken cadence runs together)."""
    digits = []
    i = start
    while i < len(tokens) and (max_count is None or len(digits) < max_count):
        tok = tokens[i]
        if tok in DIGIT_WORDS:
            digits.append(DIGIT_WORDS[tok])
            i += 1
        elif tok.isdigit():
            digits.append(tok)
            i += 1
        else:
            break
    return "".join(digits), i


def fuzzy_lookup(word, vocab, cutoff=0.72):
    """Exact match first, else closest vocab key by string similarity (handles
    near-miss STT transcription like 'maik' for 'mike', 'kepek' for 'quebec')."""
    if word in vocab:
        return word
    matches = difflib.get_close_matches(word, vocab.keys(), n=1, cutoff=cutoff)
    return matches[0] if matches else None


def find_anchor(tokens, start, vocab, fuzzy_cutoff=0.75, max_lookahead=8):
    """Find the next token (or bigram, for 'erittäin nopea') matching vocab from
    start, exact or fuzzy. Lookahead is bounded to avoid spurious fuzzy matches
    far away in the transcript."""
    end = min(len(tokens), start + max_lookahead)
    i = start
    while i < end:
        if i + 1 < len(tokens):
            bigram = tokens[i] + " " + tokens[i + 1]
            if bigram in vocab:
                return bigram, i, i + 2
        if tokens[i] in vocab:
            return tokens[i], i, i + 1
        fuzzy = fuzzy_lookup(tokens[i], vocab, cutoff=fuzzy_cutoff)
        if fuzzy:
            return fuzzy, i, i + 1
        i += 1
    return None, None, None


def find_wake_positions(tokens):
    """Token indices where a report starts: 'uusi maali' or bare 'maali'."""
    positions = []
    i = 0
    while i < len(tokens):
        if i + 1 < len(tokens) and tokens[i] == "uusi" and tokens[i + 1] == "maali":
            positions.append(i)
            i += 2
        elif tokens[i] == "maali":
            positions.append(i)
            i += 1
        else:
            i += 1
    return positions


def split_into_reports(transcript):
    """Split a transcript on every wake-word occurrence so multiple reports
    caught in one window are parsed separately instead of mashed together."""
    text = normalize(transcript)
    tokens = text.split(" ")
    positions = find_wake_positions(tokens)
    if not positions:
        return [parse_report(transcript)]
    segments = []
    for idx, start in enumerate(positions):
        end = positions[idx + 1] if idx + 1 < len(positions) else len(tokens)
        segments.append(" ".join(tokens[start:end]))
    return [parse_report(segment) for segment in segments]


def is_usable(report):
    """Minimum-quality gate before a report should be sent to the app. Only
    mgrsRaw is strictly required - without a location there's nothing to plot
    on the map. Other fields (id, direction, etc.) can be missing and still
    show up as a sparse row/point; per user preference, showing a plausibly
    wrong/incomplete track is better than silently dropping it."""
    return bool(report["mgrsRaw"])


def parse_report(transcript):
    text = normalize(transcript)
    tokens = text.split(" ")

    report = {
        "id": "",
        "mgrsRaw": "",
        "direction": None,
        "altitude": "",
        "speed": "",
        "count": "",
        "extra": "",
        "_raw": transcript,
        "_warnings": [],
    }

    # 1. Wake word
    pos = 0
    found_wake = False
    for w in WAKE_WORDS:
        wlen = len(w.split(" "))
        if " ".join(tokens[0:wlen]) == w:
            pos = wlen
            found_wake = True
            break
    if not found_wake:
        report["_warnings"].append("wake word not found at start; parsing from position 0")

    # 2. Maalin numero - always exactly 4 digits
    target_id, pos = tokenize_digits(tokens, pos, max_count=4)
    if not target_id:
        report["_warnings"].append("no target number found after wake word")
    report["id"] = target_id

    # 3. Sijainti (MGRS): 2 phonetic letters + 2 digits (KKDD)
    letters = []
    while pos < len(tokens) and len(letters) < 2:
        tok = tokens[pos]
        match = fuzzy_lookup(tok, NATO_ALPHABET, cutoff=0.65)
        if match:
            letters.append(NATO_ALPHABET[match])
            pos += 1
        elif len(tok) == 1 and tok.isalpha():
            letters.append(tok.upper())
            pos += 1
        else:
            break
    mgrs_digits, pos = tokenize_digits(tokens, pos, max_count=2)
    if len(letters) == 2 and len(mgrs_digits) >= 2:
        report["mgrsRaw"] = letters[0] + letters[1] + mgrs_digits[0] + mgrs_digits[1]
    else:
        report["_warnings"].append(f"MGRS parse incomplete: letters={letters} digits={mgrs_digits}")

    # 4. Suunta: compass word + 3 digit degrees
    compass, cpos, after_compass = find_anchor(tokens, pos, COMPASS_WORDS)
    if compass:
        pos = after_compass
        degrees, pos = tokenize_digits(tokens, pos, max_count=3)
        if degrees:
            report["direction"] = int(degrees)
        else:
            report["_warnings"].append(f"compass word '{compass}' found but no degrees followed")
    else:
        report["_warnings"].append("no compass direction word found")

    # 5. Nopeus
    speed, spos, pos2 = find_anchor(tokens, pos, SPEED_WORDS)
    if speed:
        report["speed"] = SPEED_WORDS[speed]
        pos = pos2
    else:
        report["_warnings"].append("no speed category word found")

    # 6. Korkeus
    altitude, apos, pos2 = find_anchor(tokens, pos, ALTITUDE_WORDS)
    if altitude:
        report["altitude"] = ALTITUDE_WORDS[altitude]
        pos = pos2
    else:
        report["_warnings"].append("no altitude category word found")

    # 7. Lukumäärä (+ optional exact count number directly after)
    count, copos, pos2 = find_anchor(tokens, pos, COUNT_WORDS)
    if count:
        pos = pos2
        exact, pos_after_count = tokenize_digits(tokens, pos)
        if exact:
            report["count"] = exact
            pos = pos_after_count
        else:
            report["count"] = COUNT_WORDS[count]
    else:
        report["_warnings"].append("no count category word found")

    # 8-9. Muodostelma + muut tiedot: remaining free text
    remainder = " ".join(tokens[pos:]).strip()
    report["extra"] = remainder

    return report


def send_to_app(report):
    body = json.dumps(report, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        INGEST_URL, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


if __name__ == "__main__":
    send = "--send" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--send"]
    transcript = " ".join(args) if args else sys.stdin.read()

    results = split_into_reports(transcript)
    print(json.dumps(results, ensure_ascii=False, indent=2))

    if send:
        for result in results:
            if not is_usable(result):
                print(f"Ohitettu (puutteellinen): id={result['id']} mgrs={result['mgrsRaw']}",
                      file=sys.stderr)
                continue
            try:
                ack = send_to_app(result)
                print(f"Lähetetty sovellukseen: {ack}", file=sys.stderr)
            except Exception as e:
                print(f"Lähetys epäonnistui: {e}", file=sys.stderr)

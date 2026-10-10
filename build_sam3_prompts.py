"""Distil noisy planogram SKU names into a closed vocabulary of SAM 3 text prompts."""

import json
import logging
import os
import re
import unicodedata
import urllib.request
from collections import defaultdict
from pathlib import Path

log = logging.getLogger("build_sam3_prompts")

# Retail noise that SAM 3 does not understand: grade, units, pack words, origin acronyms.
STOPLIST = {
    "KG", "G", "GR", "EMB", "SC", "SACO", "CNT", "CAT", "CAL", "IGP", "IMP", "BIO", "INT",
    "DO", "DA", "DE", "P", "S", "A", "AA", "AAA", "I", "D", "PRONTO", "COMER", "INTEIRO",
    "INTEIRA", "INTEIR", "ALGARVE", "NACIONAL", "SEMENTES", "POUCAS", "SWEET", "SUPER",
}
UNIT_WORDS = {"kg", "g", "gr", "emb", "sc", "saco", "cnt", "cat", "cal", "igp", "imp", "bio", "int", "r"}

# Ordered PT -> EN rules: (tokens that must all be present, prompt). Specific rules come first;
# the first match wins. Merge look-alike varieties; split only when obvious and named differently.
RULES = [
    ({"TOMATE", "CHERRY"}, "cherry tomatoes"),
    ({"TOMATE", "MINI"}, "cherry tomatoes"),
    ({"TOMATE"}, "tomatoes"),
    ({"CEBOLA", "ROXA"}, "red onions"),
    ({"CEBOLINHA"}, "shallots"),
    ({"CEBOLA"}, "onions"),
    ({"BATATA", "DOCE"}, "sweet potatoes"),
    ({"BATATA"}, "potatoes"),
    ({"PIMENTO", "VERMELHO"}, "red peppers"),
    ({"PIMENTO", "VERDE"}, "green peppers"),
    ({"UVA", "BRANCA"}, "green grapes"),
    ({"UVA"}, "red grapes"),
    ({"COUVE", "BROCOLO"}, "broccoli"),
    ({"COUVE", "FLOR"}, "cauliflower"),
    ({"COUVE", "ROXA"}, "red cabbages"),
    ({"COUVE", "BRANCA"}, "cabbages"),
    ({"COUVE"}, "collard greens"),
    ({"BANANA"}, "bananas"),
    ({"MACA"}, "apples"),
    ({"LARANJA"}, "oranges"),
    ({"CITRINOS"}, "oranges"),
    ({"CITR"}, "oranges"),
    ({"CLEMENTINA"}, "oranges"),
    ({"LIMAO"}, "lemons"),
    ({"LIMA"}, "limes"),
    ({"ALFACE"}, "lettuce"),
    ({"MELANCIA"}, "watermelons"),
    ({"MELAO"}, "melons"),
    ({"MELOA"}, "melons"),
    ({"PERA"}, "pears"),
    ({"KIWI"}, "kiwis"),
    ({"MORANGO"}, "strawberries"),
    ({"MANGA"}, "mangoes"),
    ({"ABACAXI"}, "pineapples"),
    ({"ALHO"}, "garlic"),
    ({"ABACATE"}, "avocados"),
    ({"ABOBORA"}, "pumpkins"),
    ({"ALPERCE"}, "apricots"),
    ({"BERINGELA"}, "eggplants"),
    ({"CEREJA"}, "cherries"),
    ({"CHUCHU"}, "chayotes"),
    ({"CURGETE"}, "zucchini"),
    ({"FEIJAO"}, "green beans"),
    ({"GENGIBRE"}, "ginger"),
    ({"GOIABA"}, "guavas"),
    ({"GRANADILHA"}, "passion fruits"),
    ({"MARACUJA"}, "passion fruits"),
    ({"MAMAO"}, "papayas"),
    ({"PAPAIA"}, "papayas"),
    ({"NECTARINA"}, "nectarines"),
    ({"PESSEGO"}, "peaches"),
    ({"PEPINO"}, "cucumbers"),
    ({"PITAYA"}, "dragon fruits"),
]
SEED_VOCABULARY = sorted({prompt for _, prompt in RULES})

PROMPT_RE = re.compile(r"^[a-z]+( [a-z]+){0,3}$")

LLM_INSTRUCTION = (
    "You name produce for an object-segmentation model whose text prompt must be a short, "
    "simple English noun phrase. For each product below, return ONLY a short English noun phrase "
    "(1-3 words, lowercase, plural) naming the visible produce. No units, grade, brand, variety, "
    "or origin. Merge varieties that look alike on a shelf (Gala/Fuji/Granny -> 'apples'). Keep "
    "separate only when visually obvious and differently named (cherry tomatoes vs tomatoes; red "
    "onions vs onions). When unsure, MERGE - coarser is safer. Prefer reusing a phrase from the "
    "existing vocabulary exactly as written; only add a new phrase if none fits. Name only the "
    "produce and never mention packaging (loose or packaged).\n"
    "Existing vocabulary: {vocab}\n"
    'Reply with a JSON object mapping each product_id to its phrase, e.g. {{"11908": "bananas"}}. '
    "Include every product_id exactly once.\n"
    "Products (product_id: raw names):\n{products}"
)


def _strip_accents(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _tokens(raw_name):
    """Upper-case, accent-free tokens, without digit-bearing or stoplist tokens."""
    text = _strip_accents(raw_name).upper()
    out = []
    for tok in re.split(r"[^A-Z0-9]+", text):
        if not tok or any(c.isdigit() for c in tok) or tok in STOPLIST:
            continue
        out.append(tok)
    return out


def rule_based_prompt(raw_names):
    """Deterministic fallback. Returns (prompt, known) where known is False for an unmapped head noun."""
    token_sets = [set(_tokens(n)) for n in raw_names]
    for required, prompt in RULES:
        if any(required <= ts for ts in token_sets):
            return prompt, True
    for raw in sorted(raw_names):
        toks = _tokens(raw)
        if toks:
            return toks[0].lower(), False
    return "", False


PACK_TOKENS = {"EMB", "SACO", "SC", "REDE", "CUVETE", "CX"}
# Fixed weight in grams ("500 G", "250GR"); the number must not be part of a calibre like 70/95 or 24+.
GRAMS_RE = re.compile(r"(?<![A-Z\d/.,+])(\d+(?:[.,]\d+)?)\s*(?:GR|G)\b")
# Fixed pack weight in kg ("1 KG", "1.5 KG", "3KG"); a calibre such as 70/95 KG does not count.
PACK_KG_RE = re.compile(r"(?<![A-Z\d/.,+])(\d+(?:[.,]\d+)?)\s*KG\b")
BARE_KG_RE = re.compile(r"\bKG\b")
PACKAGED_PREFIX = "packaged"


def classify_packaging(raw_name):
    """Deterministic packaging decision from one SKU name.

    Returns (packaged, reason, ambiguous). Any pack token or fixed weight makes it packaged, even
    when a bare KG also appears. No pack signal and a bare KG is loose. Neither is ambiguous: loose + flag.
    """
    text = _strip_accents(raw_name).upper()
    triggers = [f"token {t}" for t in sorted(PACK_TOKENS & set(re.split(r"[^A-Z0-9]+", text)))]
    triggers += [f"fixed weight {m.group(0).strip()!r}" for m in GRAMS_RE.finditer(text)]
    triggers += [f"pack weight {m.group(0).strip()!r}" for m in PACK_KG_RE.finditer(text)]
    if triggers:
        return True, ", ".join(triggers), False
    if BARE_KG_RE.search(text):
        return False, "bare KG, no pack token or fixed weight", False
    return False, "no pack signal and no bare KG (defaulted to loose)", True


def packaging_for_product(raw_names):
    """Combine the decisions for every raw name of one product_id: (packaged, reason, needs_review_reason)."""
    decisions = [classify_packaging(n) for n in sorted(raw_names)]
    verdicts = {d[0] for d in decisions}
    if len(verdicts) > 1:
        return False, "raw names disagree (defaulted to loose)", "raw names disagree on packaging"
    packaged, reason, ambiguous = decisions[0]
    return packaged, reason, (reason if ambiguous else None)


def validate_prompt(prompt):
    """Return an error string, or None when the prompt is a clean 1-4 word lowercase noun phrase."""
    if not isinstance(prompt, str) or not PROMPT_RE.match(prompt):
        return "not 1-4 lowercase alphabetic words"
    if any(w in UNIT_WORDS for w in prompt.split()):
        return "contains unit/grade token"
    return None


def _canonicalise(phrase, vocabulary):
    """Lowercase/clean an LLM phrase and snap singular/plural variants onto the vocabulary."""
    phrase = re.sub(r"[^a-z ]", "", str(phrase).strip().lower())
    phrase = re.sub(r"\s+", " ", phrase).strip()
    phrase = re.sub(rf"^(?:{PACKAGED_PREFIX}|loose)\s+", "", phrase)  # packaging is decided by rule, not the LLM
    if phrase in vocabulary:
        return phrase
    for variant in (phrase + "s", phrase + "es", phrase[:-1], phrase[:-2], re.sub(r"ies$", "y", phrase)):
        if variant and variant in vocabulary:
            return variant
    return phrase


def llm(prompt):
    """Call an OpenAI-compatible chat endpoint; key and endpoint come from the environment."""
    key = os.environ.get("LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("no LLM key: set LLM_API_KEY, DEEPSEEK_API_KEY or OPENAI_API_KEY")
    if os.environ.get("LLM_API_KEY") or not os.environ.get("DEEPSEEK_API_KEY"):
        default_url, default_model = "https://api.openai.com/v1", "gpt-4o-mini"
    else:
        default_url, default_model = "https://api.deepseek.com", "deepseek-v4-pro"
    base_url = os.environ.get("LLM_BASE_URL", default_url).rstrip("/")
    body = {
        "model": os.environ.get("LLM_MODEL", default_model),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.load(resp)["choices"][0]["message"]["content"]


def _collect_products(planogram):
    names = defaultdict(set)
    for category_data in planogram.values():
        for camera_data in category_data["cameras"].values():
            for area in camera_data["products"]:
                names[str(area["product_id"])].add(area["product_name"])
    return names


def _suggest_with_llm(names, pids, vocabulary):
    """Ask the LLM for a concept per needs-review product. Returns {product_id: phrase}; never raises."""
    products_text = "\n".join(f"{pid}: {' | '.join(sorted(names[pid]))}" for pid in sorted(pids))
    try:
        data = json.loads(llm(LLM_INSTRUCTION.format(vocab=json.dumps(sorted(vocabulary)), products=products_text)))
        if not isinstance(data, dict):
            raise ValueError("LLM reply is not a JSON object")
    except Exception as exc:
        log.warning("LLM suggestion call failed (%s)", exc)
        print(f"WARNING: LLM suggestion call failed ({exc}); no suggestions")
        return {}
    suggestions = {}
    for pid, phrase in data.items():
        pid = str(pid)
        if pid not in pids:  # never invent a product_id
            continue
        phrase = _canonicalise(phrase, vocabulary)
        if not validate_prompt(phrase):
            suggestions[pid] = phrase
    return suggestions


def build_sam3_prompts(planogram_path, output_path="classes.json", use_llm=False):
    """Map every distinct product_id to one SAM 3 prompt; write {prompt: [product_ids]} to output_path.

    The classes come only from the deterministic cleaner (PT->EN rules + packaging rule), so the
    output is reproducible. use_llm=True only prints suggested dictionary entries for needs_review
    products; it never changes classes.json.
    """
    with open(planogram_path) as f:
        names = _collect_products(json.load(f))

    rule = {pid: rule_based_prompt(raw) for pid, raw in names.items()}
    review = defaultdict(list)  # product_id -> reasons
    concept_review = set()  # product_ids the dictionary could not map cleanly (LLM may suggest for these)
    for pid, (_, known) in rule.items():
        if not known:
            review[pid].append("rule-based: head noun not in PT->EN dictionary")
            concept_review.add(pid)

    packaging = {}
    for pid, raw in names.items():
        packaged, reason, flag = packaging_for_product(raw)
        packaging[pid] = (packaged, reason)
        if flag:
            review[pid].append(f"packaging: {flag}")

    final = {}
    for pid, (concept, _) in rule.items():
        final[pid] = f"{PACKAGED_PREFIX} {concept}" if packaging[pid][0] else concept
        error = validate_prompt(concept) or validate_prompt(final[pid])
        if error:
            review[pid].append(f"final prompt {final[pid]!r} failed validation ({error})")
            concept_review.add(pid)

    classes = defaultdict(list)
    for pid, prompt in final.items():
        classes[prompt].append(pid)
    classes = {k: sorted(v, key=lambda x: (len(x), x)) for k, v in sorted(classes.items())}
    assert sorted(p for v in classes.values() for p in v) == sorted(names), "product_id lost or duplicated"
    Path(output_path).write_text(json.dumps(classes, indent=2, ensure_ascii=False) + "\n")

    suggestions = _suggest_with_llm(names, concept_review, set(SEED_VOCABULARY)) if use_llm and concept_review else {}
    _print_report(names, classes, review, packaging, suggestions if use_llm else None)
    return classes


def _print_report(names, classes, review, packaging, suggestions):
    print("\n=== SAM 3 prompt review ===")
    print(f"distinct product_ids: {len(names)}")
    print(f"SAM 3 classes:        {len(classes)}")
    print(f"  loose / packaged:   {sum(not k.startswith(PACKAGED_PREFIX) for k in classes)}"
          f" / {sum(k.startswith(PACKAGED_PREFIX) for k in classes)}\n")
    print("Mapping (packaging decision and trigger per product):")
    for prompt, pids in classes.items():
        print(f"  {prompt!r} ({len(pids)})")
        for pid in pids:
            kind = "packaged" if packaging[pid][0] else "loose"
            print(f"      {pid}: {' | '.join(sorted(names[pid]))}  -> {kind}: {packaging[pid][1]}")
    print(f"\nNeeds review ({len(review)}):")
    for pid in sorted(review):
        line = f"  {pid} {' | '.join(sorted(names[pid]))}: {'; '.join(review[pid])}"
        if suggestions and pid in suggestions:
            line += f"  [LLM suggests dictionary entry: {suggestions[pid]!r}]"
        print(line)

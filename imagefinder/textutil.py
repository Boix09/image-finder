from __future__ import annotations

import html
import re
import unicodedata

PROVIDER_WEIGHTS = {
    "Yandex Images": 1.0,
    "DuckDuckGo": 1.0,
    "Openverse": 0.9,
    "Wikimedia Commons": 0.85,
}

FILLER_WORDS = {
    # articles et petits mots
    "le", "la", "les", "l", "un", "une", "des", "de", "du", "d",
    "au", "aux", "et", "ou", "a", "the", "an", "of", "in", "on", "for", "with",
    "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix",
    "onze", "douze", "treize", "quatorze", "quinze", "seize", "vingt",
    "trente", "cinquante", "cent", "quelques", "plusieurs", "some", "many",
    "1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
    "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "top",
    # demandes
    "je", "j", "tu", "vous", "nous", "il", "elle", "on", "me", "moi", "te", "toi",
    "veux", "voudrais", "aimerais", "souhaite", "peux", "pouvez",
    "telecharge", "telecharges", "telechargez", "telecharger", "telechargement",
    "cherche", "cherches", "cherchez", "chercher", "recherche", "recherches",
    "recherchez", "rechercher", "trouve", "trouves", "trouvez", "trouver",
    "recupere", "recuperes", "recuperez", "recuperer",
    "donne", "donnes", "donnez", "donner", "montre", "montrez", "montrer",
    "affiche", "affichez", "afficher", "genere", "generes", "generez", "generer",
    "cree", "crees", "creez", "creer", "fais", "faites", "faire",
    "download", "downloads", "find", "search", "get", "show", "give",
    # politesse
    "stp", "svp", "please", "plait", "plais", "s",
    # nature de l'image
    "image", "images", "photo", "photos", "picture", "pictures", "pic", "pics",
    # qualificatifs
    "plus", "belle", "belles", "beau", "beaux", "joli", "jolie", "jolies",
    "populaire", "populaires", "meilleur", "meilleure", "meilleurs", "meilleures",
    "adapte", "adaptee", "adaptes", "adaptees",
    "pertinent", "pertinente", "pertinents", "pertinentes",
    "gratuit", "gratuite", "gratuits", "gratuites",
}

STOPWORDS = {
    "de", "du", "des", "la", "le", "les", "un", "une", "et", "and", "the",
    "of", "a", "an", "to", "in", "on", "for", "with", "sur", "dans", "pour",
    "avec", "par", "au", "aux", "image", "images", "photo", "photos",
    "picture", "pictures", "wallpaper", "wallpapers", "best", "top", "new",
    "latest", "high", "quality", "hd",
}

SYNONYMS = {
    "voiture": {"car", "auto", "automobile", "vehicle"},
    "car": {"voiture", "auto", "automobile"},
    "chat": {"cat", "kitten"},
    "chien": {"dog", "puppy"},
    "maison": {"house", "home"},
    "paysage": {"landscape", "scenery"},
    "montagne": {"mountain"},
    "mer": {"sea", "ocean"},
    "plage": {"beach"},
    "fleur": {"flower"},
    "nourriture": {"food"},
    "ville": {"city"},
    "femme": {"woman"},
    "homme": {"man"},
    "enfant": {"child"},
    "oiseau": {"bird"},
    "cheval": {"horse"},
    "moto": {"motorcycle"},
    "avion": {"airplane", "plane"},
    "bateau": {"boat"},
    "espace": {"space"},
}

FOLDER_PATTERN = re.compile(
    r"\s*(?:dans|vers)\s+(?:le\s+|la\s+|un\s+|une\s+)?"
    r"(?:dossier|r[ée]pertoire)\s+[\"']?(.+?)[\"']?\s*$",
    re.IGNORECASE,
)


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    return text.lower()


def split_folder(text: str) -> tuple[str, str | None]:
    match = FOLDER_PATTERN.search(text or "")
    if not match:
        return (text or "").strip(), None
    folder = match.group(1).strip(" .,;\"'")
    if not folder:
        return (text or "").strip(), None
    return (text or "")[: match.start()].strip(" ,;"), folder


def clean_query(text: str) -> str:
    text = re.sub(
        r"[,\s]+(?:s['’]?il te plait|stp|svp|please)\s*$", "", text or "",
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\s+(?:sur|on)\s+(?:internet|le net|le web|google)\s*$", "", text,
        flags=re.IGNORECASE,
    )
    words = re.findall(r"[^\W_]+", text, flags=re.UNICODE)
    index = 0
    while index < len(words) and fold(words[index]) in FILLER_WORDS:
        index += 1
    query = " ".join(words[index:]).strip()
    if not query:
        raise ValueError("precisez un sujet, par exemple : voiture de sport")
    return query


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _stem(word: str) -> str:
    word = fold(word)
    if len(word) > 3 and word.endswith(("s", "x")):
        word = word[:-1]
    return word


def meaningful_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for word in re.findall(r"[^\W_]+", text or "", flags=re.UNICODE):
        token = _stem(word)
        if len(token) < 3 or token in STOPWORDS:
            continue
        tokens.add(token)
    expanded = set(tokens)
    for token in tokens:
        expanded.update(SYNONYMS.get(token, set()))
    return expanded


def metadata_score(title: str, rank: int, provider: str, query: str) -> float:
    query_tokens = meaningful_tokens(query)
    title_tokens = meaningful_tokens(title)
    if query_tokens:
        overlap = len(query_tokens & title_tokens) / len(query_tokens)
    else:
        overlap = 0.5
    phrase = 1.0 if fold(query) and fold(query) in fold(title) else 0.0
    rank_score = max(0.0, 1.0 - (max(rank, 1) - 1) / 50.0)
    provider_score = PROVIDER_WEIGHTS.get(provider, 0.5)
    return 0.50 * rank_score + 0.25 * overlap + 0.10 * phrase + 0.15 * provider_score


def matches_orientation(width: int, height: int, orientation: str) -> bool:
    if orientation == "any" or not width or not height:
        return True
    ratio = width / height
    if orientation == "landscape":
        return ratio >= 1.1
    if orientation == "portrait":
        return ratio <= 0.9
    if orientation == "square":
        return 0.9 <= ratio <= 1.1
    return True


def resolution_score(width: int, height: int, min_side: int) -> float:
    if not width or not height:
        return 0.55
    short, long = sorted((width, height))
    target = max(900, min_side)
    size = min(1.0, short / target)
    if min_side and short < min_side:
        size *= 0.35
    ratio = long / short if short else 1.0
    aspect = 1.0 if ratio <= 2.0 else max(0.25, 2.0 / ratio)
    return 0.80 * size + 0.20 * aspect

# -*- coding: utf-8 -*-
"""Tables de correspondance : identifiants Apple -> noms commerciaux, couleurs, etc."""

PRODUCT_NAMES = {
    "iPhone8,1": "iPhone 6s", "iPhone8,2": "iPhone 6s Plus", "iPhone8,4": "iPhone SE (1re gén.)",
    "iPhone9,1": "iPhone 7", "iPhone9,3": "iPhone 7", "iPhone9,2": "iPhone 7 Plus", "iPhone9,4": "iPhone 7 Plus",
    "iPhone10,1": "iPhone 8", "iPhone10,4": "iPhone 8", "iPhone10,2": "iPhone 8 Plus", "iPhone10,5": "iPhone 8 Plus",
    "iPhone10,3": "iPhone X", "iPhone10,6": "iPhone X",
    "iPhone11,2": "iPhone XS", "iPhone11,4": "iPhone XS Max", "iPhone11,6": "iPhone XS Max", "iPhone11,8": "iPhone XR",
    "iPhone12,1": "iPhone 11", "iPhone12,3": "iPhone 11 Pro", "iPhone12,5": "iPhone 11 Pro Max",
    "iPhone12,8": "iPhone SE (2e gén.)",
    "iPhone13,1": "iPhone 12 mini", "iPhone13,2": "iPhone 12", "iPhone13,3": "iPhone 12 Pro", "iPhone13,4": "iPhone 12 Pro Max",
    "iPhone14,4": "iPhone 13 mini", "iPhone14,5": "iPhone 13", "iPhone14,2": "iPhone 13 Pro", "iPhone14,3": "iPhone 13 Pro Max",
    "iPhone14,6": "iPhone SE (3e gén.)",
    "iPhone14,7": "iPhone 14", "iPhone14,8": "iPhone 14 Plus", "iPhone15,2": "iPhone 14 Pro", "iPhone15,3": "iPhone 14 Pro Max",
    "iPhone15,4": "iPhone 15", "iPhone15,5": "iPhone 15 Plus", "iPhone16,1": "iPhone 15 Pro", "iPhone16,2": "iPhone 15 Pro Max",
    "iPhone17,3": "iPhone 16", "iPhone17,4": "iPhone 16 Plus", "iPhone17,1": "iPhone 16 Pro", "iPhone17,2": "iPhone 16 Pro Max",
    "iPhone17,5": "iPhone 16e",
}

# Couleurs (DeviceEnclosureColor) : les codes varient selon les modèles,
# on ne garde que la valeur brute + une indication si elle est connue.
COLOR_HINTS = {
    "1": "Noir / Gris sidéral", "2": "Blanc / Argent", "3": "Or", "4": "Or rose",
    "5": "Gris", "6": "Rouge (PRODUCT)RED", "7": "Jaune", "8": "Corail", "9": "Bleu",
}

# 1re lettre du numéro de modèle (ex. MLPF3ZD/A)
MODEL_ORIGIN = {
    "M": ("Neuf (vente au détail)", "ok"),
    "F": ("Reconditionné par Apple", "warn"),
    "N": ("Appareil de remplacement (échange SAV Apple)", "warn"),
    "P": ("Personnalisé (gravure)", "ok"),
    "3": ("Appareil de démonstration", "warn"),
}

# Suffixe de région (RegionInfo, ex. "ZD/A")
REGIONS = {
    "ZD/A": "Europe (France, Belgique, Allemagne…)", "NF/A": "France / Belgique / Luxembourg",
    "FN/A": "France", "B/A": "Royaume-Uni / Irlande", "LL/A": "États-Unis", "QL/A": "Espagne / Italie / Portugal",
    "TY/A": "Italie", "DN/A": "Allemagne / Autriche", "J/A": "Japon", "CH/A": "Chine", "ZA/A": "Singapour",
    "ZP/A": "Hong Kong", "KH/A": "Corée", "X/A": "Australie", "C/A": "Canada", "AE/A": "Émirats",
    "PO/A": "Pologne", "RU/A": "Russie", "HN/A": "Inde", "CL/A": "Canada", "ZQ/A": "Afrique du Sud",
}


def product_name(product_type):
    if not product_type:
        return "iPhone inconnu"
    return PRODUCT_NAMES.get(product_type, product_type)


def model_origin(model_number):
    if not model_number:
        return ("Inconnue", "muted")
    return MODEL_ORIGIN.get(model_number[0].upper(), ("Code « %s » non répertorié" % model_number[0], "muted"))


def region_name(region_info):
    if not region_info:
        return "Inconnue"
    return REGIONS.get(region_info, region_info)


def human_storage(nbytes):
    """Capacité commerciale arrondie (64, 128, 256 Go…)."""
    try:
        gb = float(nbytes) / 1e9
    except (TypeError, ValueError):
        return None
    for size in (16, 32, 64, 128, 256, 512, 1024, 2048):
        if gb <= size * 1.02:
            return "%d Go" % size if size < 1024 else "%d To" % (size // 1024)
    return "%.0f Go" % gb

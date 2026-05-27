import json

import database


TEXTILE_UNIT = "kg CO2eq/kg textile"

# Development estimates used to keep the scan-to-report flow working.
# Replace carbon_factor values with team-approved source data before final reporting.
MATERIAL_SEEDS = [
    {
        "name_ko": "\uba74",
        "name_en": "cotton",
        "aliases": ["\uba74", "\ucf54\ud2bc", "cotton", "COTTON"],
        "carbon_factor": 8.3,
    },
    {
        "name_ko": "\ud3f4\ub9ac\uc5d0\uc2a4\ud130",
        "name_en": "polyester",
        "aliases": ["\ud3f4\ub9ac\uc5d0\uc2a4\ud130", "polyester", "POLYESTER", "poly"],
        "carbon_factor": 9.5,
    },
    {
        "name_ko": "\ub808\uc774\uc628",
        "name_en": "rayon",
        "aliases": ["\ub808\uc774\uc628", "rayon", "RAYON"],
        "carbon_factor": 6.4,
    },
    {
        "name_ko": "\ub098\uc77c\ub860",
        "name_en": "nylon",
        "aliases": ["\ub098\uc77c\ub860", "nylon", "NYLON", "polyamide"],
        "carbon_factor": 11.0,
    },
    {
        "name_ko": "\uc6b8",
        "name_en": "wool",
        "aliases": ["\uc6b8", "\ubaa8", "wool", "WOOL"],
        "carbon_factor": 13.9,
    },
    {
        "name_ko": "\uc544\ud06c\ub9b4",
        "name_en": "acrylic",
        "aliases": ["\uc544\ud06c\ub9b4", "acrylic", "ACRYLIC", "polyacryl"],
        "carbon_factor": 10.0,
    },
    {
        "name_ko": "\uc2a4\ud310\ub371\uc2a4",
        "name_en": "spandex",
        "aliases": ["\uc2a4\ud310\ub371\uc2a4", "\uc5d8\ub77c\uc2a4\ud14c\uc778", "spandex", "elastane", "lycra"],
        "carbon_factor": 12.0,
    },
    {
        "name_ko": "\ub9b0\ub128",
        "name_en": "linen",
        "aliases": ["\ub9b0\ub128", "\ub9ac\ub128", "\ub9c8", "linen", "LINEN"],
        "carbon_factor": 4.5,
    },
    {
        "name_ko": "\ube44\uc2a4\ucf54\uc2a4",
        "name_en": "viscose",
        "aliases": ["\ube44\uc2a4\ucf54\uc2a4", "viscose", "VISCOSE", "viskose"],
        "carbon_factor": 6.4,
    },
    {
        "name_ko": "\uc2e4\ud06c",
        "name_en": "silk",
        "aliases": ["\uc2e4\ud06c", "\uacac", "silk", "SILK"],
        "carbon_factor": 15.0,
    },
    {
        "name_ko": "\ubaa8\ub2ec",
        "name_en": "modal",
        "aliases": ["\ubaa8\ub2ec", "modal", "MODAL"],
        "carbon_factor": 6.0,
    },
    {
        "name_ko": "\uce90\uc2dc\ubbf8\uc5b4",
        "name_en": "cashmere",
        "aliases": ["\uce90\uc2dc\ubbf8\uc5b4", "cashmere", "CASHMERE", "kashmir"],
        "carbon_factor": 30.0,
    },
    {
        "name_ko": "\ud3f4\ub9ac\uc6b0\ub808\ud0c4",
        "name_en": "polyurethane",
        "aliases": ["\ud3f4\ub9ac\uc6b0\ub808\ud0c4", "polyurethane", "PU", "pu"],
        "carbon_factor": 12.0,
    },
    {
        "name_ko": "\uac00\uc8fd",
        "name_en": "leather",
        "aliases": ["\uac00\uc8fd", "leather", "LEATHER"],
        "carbon_factor": 20.0,
    },
    {
        "name_ko": "\ub77c\ubbf8",
        "name_en": "ramie",
        "aliases": ["\ub77c\ubbf8", "ramie", "RAMIE"],
        "carbon_factor": 4.5,
    },
    {
        "name_ko": "\ub9ac\uc624\uc140",
        "name_en": "lyocell",
        "aliases": ["\ub9ac\uc624\uc140", "\ud150\uc140", "lyocell", "tencel"],
        "carbon_factor": 5.5,
    },
    {
        "name_ko": "\ub2e4\uc6b4",
        "name_en": "down",
        "aliases": ["\ub2e4\uc6b4", "\uc6b0\ubaa8", "\uc624\ub9ac\uc19c\ud138", "\uac70\uc704\uc19c\ud138", "down"],
        "carbon_factor": 18.0,
    },
    {
        "name_ko": "\uae43\ud138",
        "name_en": "feather",
        "aliases": ["\uae43\ud138", "\uc624\ub9ac\uae43\ud138", "\uac70\uc704\uae43\ud138", "feather"],
        "carbon_factor": 12.0,
    },
    {
        "name_ko": "\uc57c\ud06c",
        "name_en": "yak",
        "aliases": ["\uc57c\ud06c", "yak", "YAK"],
        "carbon_factor": 18.0,
    },
    {
        "name_ko": "\ubaa8\ud5e4\uc5b4",
        "name_en": "mohair",
        "aliases": ["\ubaa8\ud5e4\uc5b4", "mohair", "MOHAIR"],
        "carbon_factor": 18.0,
    },
    {
        "name_ko": "\ub300\ub098\ubb34",
        "name_en": "bamboo",
        "aliases": ["\ub300\ub098\ubb34", "bamboo", "BAMBOO"],
        "carbon_factor": 5.0,
    },
    {
        "name_ko": "\ud050\ud504\ub85c",
        "name_en": "cupro",
        "aliases": ["\ud050\ud504\ub85c", "cupro", "CUPRO"],
        "carbon_factor": 6.0,
    },
]


def seed_materials():
    database.ensure_schema()
    db = database.SessionLocal()

    try:
        for item in MATERIAL_SEEDS:
            material = (
                db.query(database.Material)
                .filter(database.Material.name_en == item["name_en"])
                .first()
            )

            if material is None:
                material = database.Material(name_en=item["name_en"], name_ko=item["name_ko"])
                db.add(material)

            material.name_ko = item["name_ko"]
            material.aliases = json.dumps(item["aliases"], ensure_ascii=False)
            material.carbon_factor = item["carbon_factor"]
            material.unit = TEXTILE_UNIT

        db.commit()
        print("Material seed data is ready.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_materials()

import json

import database


MATERIAL_SEEDS = [
    {
        "name_ko": "면",
        "name_en": "cotton",
        "aliases": ["면", "코튼", "cotton", "COTTON"],
        "carbon_factor": 8.3,
        "unit": "kg CO2eq/kg textile",
    },
    {
        "name_ko": "폴리에스터",
        "name_en": "polyester",
        "aliases": ["폴리에스터", "polyester", "POLYESTER", "poly"],
        "carbon_factor": 9.5,
        "unit": "kg CO2eq/kg textile",
    },
    {
        "name_ko": "나일론",
        "name_en": "nylon",
        "aliases": ["나일론", "nylon", "NYLON"],
        "carbon_factor": 11.0,
        "unit": "kg CO2eq/kg textile",
    },
    {
        "name_ko": "울",
        "name_en": "wool",
        "aliases": ["울", "모", "wool", "WOOL"],
        "carbon_factor": 13.9,
        "unit": "kg CO2eq/kg textile",
    },
    {
        "name_ko": "리넨",
        "name_en": "linen",
        "aliases": ["리넨", "린넨", "linen", "LINEN"],
        "carbon_factor": 4.5,
        "unit": "kg CO2eq/kg textile",
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
            material.unit = item["unit"]

        db.commit()
        print("Material seed data is ready.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_materials()

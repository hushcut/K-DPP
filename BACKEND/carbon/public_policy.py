"""Reviewed public selection -> executable manifest; never fall back to TE/V1."""
import json
from pathlib import Path


SELECTION_PATH = Path(__file__).resolve().parents[1] / "policies/idemat_2026_free_public_selection.json"


def load_selection():
    return json.loads(SELECTION_PATH.read_text(encoding="utf-8"))


def public_display_notes():
    """Korean per-material assumption sentences shown with IDEMAT results, in selection order."""
    return {item["material"]: item["display_note_ko"]
            for item in load_selection()["factors"] if item.get("display_note_ko")}


def approved_public_manifest():
    from .policy_admin import PolicyManifest
    selection = load_selection()
    profile = {"key": selection["profile_key"], "version": selection["version"],
        "formula_version": "fiber_mass_v2", "method": selection["method"],
        "scope": selection["scope"], "usage_scope": "public_estimate"}
    factors = []
    for item in selection["factors"]:
        factors.append({"material": item["material"],
            "factor_key": "idemat-2026-" + item["material"], "version": selection["version"],
            "value_decimal": item["value_decimal"], "unit": selection["unit"],
            "method": selection["method"], "scope": selection["scope"],
            "product_form": item["product_form"], "production_system": "source process proxy",
            "geography": item.get("geography", "source process; not a Korean average"),
            "publication_year": 2026, "data_years": [],
            "source_name": "IDEMAT 2026 RevB2; data from www.ecocostsvalue.com",
            "source_url": selection["source"]["url"],
            "source_locator": "; ".join(item["source_cells"]),
            "evidence_type": item["evidence_type"], "usage_scope": "public_estimate",
            "limitations": ["Free educational capstone only; paid software needs separate licensing.",
                "Not certification or comparative environmental claims.", *item["excluded"],
                *item.get("unsupported_variants", [])],
            "carbon_accounting": {"method_locator": selection["source"]["method_locator"],
                "source_sha256": selection["source"]["sha256"],
                "license_page": selection["source"]["license_page"]},
            "components": item.get("derivation"),
            "selection_assumption": " ".join(item["assumptions"]),
            "review_note": "Delegated technical selection; independent approval not claimed.",
            "evidence_reviewed_at": item["reviewed_on"] + "T00:00:00Z",
            "technical_selector": item["technical_selector"]})
    return PolicyManifest.model_validate({"profile": profile, "factors": factors})


if __name__ == "__main__":
    # Emit, do not register or activate a database policy.
    print(approved_public_manifest().model_dump_json(indent=2))

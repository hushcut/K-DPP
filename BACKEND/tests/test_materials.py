def test_get_materials_returns_seeded_materials(client):
    response = client.get("/materials")

    body = response.json()
    names = {material["name_en"] for material in body}

    assert response.status_code == 200
    assert "cotton" in names
    assert "polyester" in names
    assert all("carbon_factor" in material for material in body)
    assert all("unit" in material for material in body)


def test_get_clothing_types_returns_weight_catalog(client):
    response = client.get("/clothing-types")
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "success"
    assert body["source"] == "backend"
    assert body["unit"] == "g"
    assert body["items"][0] == {
        "id": "short_sleeve_tshirt",
        "label": "반팔 티셔츠",
        "category": "상의",
        "min_weight_grams": 100,
        "max_weight_grams": 250,
        "estimated_weight_grams": 180,
    }
    assert any(item["id"] == "outer" for item in body["items"])

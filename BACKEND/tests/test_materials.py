def test_get_materials_returns_seeded_materials(client):
    response = client.get("/materials")

    body = response.json()
    names = {material["name_en"] for material in body}

    assert response.status_code == 200
    assert "cotton" in names
    assert "polyester" in names
    assert all("carbon_factor" in material for material in body)
    assert all("unit" in material for material in body)

from unittest.mock import patch


def test_gstin_lookup_endpoint_validates_length(org):
    c = org()
    r = c.get("/api/gstin/lookup/INVALID")
    assert r.status_code == 400
    assert "15 characters" in r.text


def test_gstin_lookup_mocked_success(org):
    c = org()
    mock_result = {
        "gstin": "29AAACI4798L1ZU",
        "name": "INFOSYS LIMITED",
        "legal_name": "INFOSYS LIMITED",
        "trade_name": "INFOSYS LIMITED",
        "party_type": "B2B",
        "bill_addr": "3RD CROSS, INFOSYS LIMITED, 44 AND 97A, ELECTRONIC CITY, BANGALORE",
        "bill_city": "BANGALORE",
        "bill_state": "29",
        "bill_pin": "560100",
        "pan": "AAACI4798L",
        "status": "Active",
        "taxpayer_type": "Regular",
        "constitution": "Public Limited Company",
        "registration_date": "01/07/2017",
        "einvoice_status": "Yes",
    }
    with patch("app.routers.masters.lookup_gstin", return_value=mock_result):
        r = c.get("/api/gstin/lookup/29AAACI4798L1ZU")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "INFOSYS LIMITED"
        assert data["bill_city"] == "BANGALORE"
        assert data["pan"] == "AAACI4798L"
        assert data["bill_state"] == "29"

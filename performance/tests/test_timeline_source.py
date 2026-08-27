from timeline_source.local_provider import _project_row_to_dict


def test_project_row_to_dict_includes_coordinates_when_present():
    row = (1, "Test Project", "Galle", "Southern Province", 2, "Residential", 6.0535, 80.221)
    result = _project_row_to_dict(row)
    assert result["latitude"] == 6.0535
    assert result["longitude"] == 80.221


def test_project_row_to_dict_handles_null_coordinates():
    row = (2, "Older Project", "Jaffna", "Northern Province", 1, "Residential", None, None)
    result = _project_row_to_dict(row)
    assert result["latitude"] is None
    assert result["longitude"] is None
    # Existing district/province fields must still work unchanged, so
    # older projects without coordinates keep resolving weather by name.
    assert result["district"] == "Jaffna"
    assert result["province"] == "Northern Province"

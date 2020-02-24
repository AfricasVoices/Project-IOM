import json

from core_data_modules.data_models import CodeScheme


def _open_scheme(filename):
    with open(f"code_schemes/{filename}", "r") as f:
        firebase_map = json.load(f)
        return CodeScheme.from_firebase_map(firebase_map)


class CodeSchemes(object):
    SOMALIA_OPERATOR = _open_scheme("somalia_operator.json")

    S06E01_REASONS = _open_scheme("s06e01_reasons.json")
    S06E02_REASONS = _open_scheme("s06e02_reasons.json")

    MOGADISHU_SUB_DISTRICT = _open_scheme("mogadishu_sub_district.json")
    SOMALIA_DISTRICT = _open_scheme("somalia_district.json")
    SOMALIA_REGION = _open_scheme("somalia_region.json")
    SOMALIA_STATE = _open_scheme("somalia_state.json")
    SOMALIA_ZONE = _open_scheme("somalia_zone.json")
    GENDER = _open_scheme("gender.json")
    AGE = _open_scheme("age.json")
    AGE_CATEGORY = _open_scheme("age_category.json")
    RECENTLY_DISPLACED = _open_scheme("recently_displaced.json")
    IN_IDP_CAMP = _open_scheme("in_idp_camp.json")

    HAVE_VOICE = _open_scheme("have_voice.json")
    SUGGESTIONS = _open_scheme("suggestions.json")

    WS_CORRECT_DATASET = _open_scheme("ws_correct_dataset.json")

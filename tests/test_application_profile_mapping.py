from app.application_autofill import _field_key, _identity, _question_answer


PROFILE={
    "name":"Hemanth Kavula",
    "contact":{
        "phone":"+1 (856) 510-7610",
        "email":"hemanth@example.com",
        "linkedin":"linkedin.com/in/example",
        "address":{"line1":"32 Beau Rivage Dr","city":"Glassboro","state":"NJ","postal_code":"08028","country":"United States"},
    },
    "application_preferences":{
        "legal_working_age":True,
        "background_check_willing":True,
        "relocation":{"willing_to_relocate":True},
        "voluntary_disclosures":{"disability_status":"No disability","veteran_status":"Not a veteran","gender":"Male","ethnicity":"Asian (South Asian)"},
    },
}
ITEM={"known_answers":{"authorized_to_work_us":"Yes","requires_sponsorship_now":"No","requires_future_sponsorship":"Yes"}}


def test_identity_maps_name_phone_and_address():
    identity=_identity(PROFILE)
    assert identity["first_name"]=="Hemanth"
    assert identity["last_name"]=="Kavula"
    assert identity["phone"]=="8565107610"
    assert identity["city"]=="Glassboro"
    assert identity["state"]=="NJ"
    assert identity["postal_code"]=="08028"


def test_address_field_keys():
    assert _field_key("Street Address")=="address_line1"
    assert _field_key("City")=="city"
    assert _field_key("State")=="state"
    assert _field_key("ZIP Code")=="postal_code"
    assert _field_key("Country")=="country"


def test_work_authorization_answers_remain_consistent():
    assert _question_answer("Are you authorized to work in the United States?",ITEM,PROFILE)=="Yes"
    assert _question_answer("Will you now require sponsorship?",ITEM,PROFILE)=="No"
    assert _question_answer("Will you require sponsorship in the future?",ITEM,PROFILE)=="Yes"


def test_static_application_preferences_are_profile_backed():
    assert _question_answer("Are you at least 18 years old?",ITEM,PROFILE)=="Yes"
    assert _question_answer("Are you willing to undergo a background check?",ITEM,PROFILE)=="Yes"
    assert _question_answer("Are you willing to relocate?",ITEM,PROFILE)=="Yes"
    assert _question_answer("Veteran Status",ITEM,PROFILE)=="Not a veteran"
    assert _question_answer("Disability Status",ITEM,PROFILE)=="No disability"

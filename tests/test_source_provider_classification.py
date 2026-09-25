from app import discovery

PUBLIC_BOARD_PROVIDERS={
"recruitee","teamtailor","bamboohr","breezyhr","rippling","pinpoint","careerplug","freshteam","jobscore","personio","comeet",
"clearcompany","applicantpro","fountain","hirebridge","zoho_recruit","manatal","join","applitrack","hireology","paycor","peopleadmin",
"isolved","hibob","gohire","hiringthing","homerun","pageup","dover","gem","polymer","hirehive","deel","applicantstack","ceipal",
"trakstar_hire","neogov","recruiting_com","taleo","brassring","paycom","bullhorn","jobdiva","greenhouse_eu","trinet","kula","rival",
"werecruit","firststage","recruiterbox","talentbrew","radancy","paradox","schooljobs","higheredjobs","applynow","talentreef","icims_alt",
"jobappnetwork","myworkchoice"
}

def test_no_recognized_ats_is_left_in_fallback():
    assert discovery.FALLBACK_ATS_PROVIDERS == ()

def test_promoted_public_boards_are_direct():
    assert PUBLIC_BOARD_PROVIDERS.issubset(set(discovery.DIRECT_PROVIDERS))

def test_direct_provider_names_are_unique():
    assert len(discovery.DIRECT_PROVIDERS) == len(set(discovery.DIRECT_PROVIDERS))

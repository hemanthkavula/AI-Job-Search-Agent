from app import discovery

GENERIC_PUBLIC_PROVIDERS={
"recruitee","teamtailor","bamboohr","breezyhr","rippling","pinpoint","careerplug","freshteam","jobscore","personio","comeet",
"clearcompany","applicantpro","fountain","hirebridge","zoho_recruit","manatal","join","applitrack","hireology","paycor","peopleadmin",
"isolved","hibob","gohire","hiringthing","homerun","pageup","dover","polymer","hirehive","deel","applicantstack","ceipal",
"trakstar_hire","neogov","recruiting_com","taleo","brassring","paycom","bullhorn","jobdiva","greenhouse_eu","trinet","kula","rival",
"werecruit","firststage","recruiterbox","talentbrew","radancy","paradox","schooljobs","higheredjobs","icims_alt","myworkchoice"
}

def test_generic_public_collectors_are_not_reported_as_native():
    assert GENERIC_PUBLIC_PROVIDERS.issubset(set(discovery.GENERIC_PUBLIC_ATS_PROVIDERS))
    assert GENERIC_PUBLIC_PROVIDERS.isdisjoint(set(discovery.NATIVE_ATS_PROVIDERS))

def test_native_provider_names_are_unique():
    assert len(discovery.NATIVE_ATS_PROVIDERS) == len(set(discovery.NATIVE_ATS_PROVIDERS))

def test_all_provider_classes_are_disjoint_and_executable():
    assert set(discovery.NATIVE_ATS_PROVIDERS).isdisjoint(set(discovery.GENERIC_PUBLIC_ATS_PROVIDERS))
    assert set(discovery.ALL_ATS_PROVIDERS)==set(discovery.NATIVE_ATS_PROVIDERS)|set(discovery.GENERIC_PUBLIC_ATS_PROVIDERS)

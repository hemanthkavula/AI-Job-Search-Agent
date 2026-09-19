from app.application_autofill import _identity, _verify_deterministic_fields
from tests.test_application_profile_mapping import PROFILE


class FakeElement:
    def __init__(self,label,value,accept_fill=True):
        self.label=label
        self.value=value
        self.accept_fill=accept_fill

    def is_visible(self): return True
    def get_attribute(self,name):
        return {"type":"text","aria-label":self.label}.get(name)
    def input_value(self): return self.value
    def evaluate(self,script):
        if "aria-label" in script or "parts" in script:
            return self.label
        return "input"
    def fill(self,value):
        if self.accept_fill:self.value=str(value)
    def click(self): pass
    def press(self,key):
        if key=="Backspace" and self.accept_fill:self.value=""
    def press_sequentially(self,value,delay=0):
        if self.accept_fill:self.value+=str(value)


class FakeLocator:
    def __init__(self,elements): self.elements=elements
    def count(self): return len(self.elements)
    def nth(self,i): return self.elements[i]


class FakeScope:
    url="https://example.com/apply"
    def __init__(self,elements): self.elements=elements
    def locator(self,selector): return FakeLocator(self.elements)


def _verify(elements):
    result={}
    failures=_verify_deterministic_fields(FakeScope(elements),_identity(PROFILE),result)
    return failures,result


def test_correct_identity_values_pass_unchanged():
    fields=[FakeElement("First Name","Hemanth"),FakeElement("Last Name","Kavula")]
    failures,result=_verify(fields)
    assert failures==[]
    assert all(x["matched"] for x in result["field_verification"])
    assert not any(x.get("corrected") for x in result["field_verification"])


def test_wrong_last_name_is_corrected_and_revalidated():
    field=FakeElement("Last Name","Hemanth")
    failures,result=_verify([field])
    assert failures==[]
    assert field.value=="Kavula"
    check=result["field_verification"][0]
    assert check["corrected"] is True
    assert check["actual_after_correction"]=="Kavula"
    assert check["matched"] is True


def test_truncated_phone_is_corrected_and_revalidated():
    field=FakeElement("Phone Number","5107610")
    failures,result=_verify([field])
    assert failures==[]
    assert field.value=="8565107610"
    check=result["field_verification"][0]
    assert check["corrected"] is True
    assert check["matched"] is True


def test_field_that_rejects_correction_remains_unresolved():
    field=FakeElement("Last Name","Hemanth",accept_fill=False)
    failures,result=_verify([field])
    assert failures==["Last Name"]
    check=result["field_verification"][0]
    assert check["corrected"] is True
    assert check["matched"] is False

import pytest
from pydantic import ValidationError
from app.core.config import Settings
from app.schemas.recruiter_chat import RecruiterInterpretation


def test_valid_https_form_config_is_accepted_and_redacted():
    url="https://docs.google.com/forms/d/e/synthetic-test-form/viewform?usp=sf_link"
    configuration=Settings(_env_file=None, application_form_url=url)
    assert configuration.application_form_url.get_secret_value()==url
    assert url not in repr(configuration)


def test_missing_application_form_is_allowed(monkeypatch):
    monkeypatch.delenv("APPLICATION_FORM_URL",raising=False)
    assert Settings(_env_file=None).application_form_url is None


@pytest.mark.parametrize("value", ["not-a-url","http://docs.google.com/forms/demo","https://user:PRIVATE_PASSWORD@docs.google.com/forms/demo","https://user@docs.google.com/forms/demo","javascript:alert(1)","https://","https://localhost/form","https://127.0.0.1/form","https://example.invalid:99999/form","https://example.invalid/form\x00","https://example.invalid/%0a","https://example.invalid/a b","https://example.invalid/#fragment","https://example.invalid/"+"x"*2049])
def test_invalid_application_configuration_is_rejected_safely(value):
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None,application_form_url=value)
    assert "input_value" not in str(error.value)
    assert value not in str(error.value.errors(include_input=False, include_url=False))
    assert "PRIVATE_PASSWORD" not in str(error.value)


def test_environment_configuration_is_supported(monkeypatch):
    monkeypatch.setenv("APPLICATION_FORM_URL","https://forms.gle/synthetic-test")
    configuration=Settings(_env_file=None)
    assert configuration.application_form_url.get_secret_value()=="https://forms.gle/synthetic-test"


def test_llm_extraction_cannot_supply_application_url():
    from test_recruiter_chat import extracted_data
    data=extracted_data()
    data["requirements"]["application_url"]="https://example.invalid/untrusted-form"
    with pytest.raises(ValidationError):
        RecruiterInterpretation.model_validate(data)

"""Never consume an operator's real provider credentials during automated tests."""
import pytest
from plan_classification import config


@pytest.fixture(autouse=True)
def provider_configuration(tmp_path,monkeypatch):
    # Individual provider tests may install synthetic settings after this fixture.
    # The real project file is neither read nor edited, and subprocess env is local.
    monkeypatch.setattr(config,'ENV_FILE',tmp_path/'unconfigured-provider.env')
    for name in config.SETTING_NAMES:
        monkeypatch.delenv(name,raising=False)

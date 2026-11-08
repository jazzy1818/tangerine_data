"""Dashboard must disclose dated scope and incomplete funding prominently."""
import pytest
from test_crisis_ui import app, custom, metric


def test_delayed_income_shock_has_dated_warning_without_official_green_runway(app):
    custom(app,{'effects':[dict(type='income_multiplier',value=0.,start_month=3,duration_months=4)]})
    assert metric(app,'Dated first shortfall')=='Month 6 (end)'
    assert any('Month 1 reference' in m.value for m in app.markdown)
    assert not any('Official Shock Runway' in m.value for m in app.markdown)
    assert not any('runway-badge-safe' in m.value and 'Months</div>' in m.value for m in app.tabs[1].markdown)


def test_unknown_event_has_partial_headlines_and_unknown_G25(app):
    custom(app,{'effects':[dict(type='unspecified_event')]})
    assert not app.exception
    assert any('**G25:** unknown' in m.value for m in app.markdown)
    assert metric(app,'Quantified Cash Need (partial estimate)')
    assert not any(m.label=='Extra Starting Cash Needed' for m in app.metric)
    assert any('Full funding need: Not established' in c.value for c in app.caption)
    assert any('Goal held for review' in m.value for m in app.info)


@pytest.mark.parametrize('label',['Layoff (EI 55%)','Furnace Repair','Layoff + 15% Bills'])
def test_organizer_presets_keep_official_scope(app,label):
    next(b for b in app.button if label in b.label).click().run()
    assert not app.exception
    assert any('Official Shock Runway' in m.value for m in app.markdown)
    assert not any('Month 1 reference — dated scenario' in m.value for m in app.markdown)

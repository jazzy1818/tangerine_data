from test_crisis_ui import app, custom


def add_schedule(app, fee=0.):
    app.text_input(key='transfer_id').set_value('judge-goal')
    app.text_input(key='transfer_source').set_value('Explicit synthetic judge schedule')
    app.number_input(key='transfer_amount').set_value(300.)
    app.number_input(key='transfer_end').set_value(6)
    app.checkbox(key='transfer_included').check()
    app.checkbox(key='transfer_approved').check()
    if fee is not None:app.number_input(key='transfer_fee').set_value(fee)
    next(b for b in app.button if b.label=='Add evidenced schedule').click().run()
    assert not app.exception


def test_dashboard_applies_schedule_and_resets_account_evidence(app):
    custom(app,{'effects':[{'type':'income_multiplier','value':0.,'duration_months':6}]})
    add_schedule(app)
    assert len(app.session_state['transfer_records'])==6
    assert any('net cash retained: CAD 1,800.00' in m.value for m in app.markdown)
    # Reruns do not duplicate scheduled payments.
    app.run()
    assert len(app.session_state['transfer_records'])==6
    app.number_input(key='account_selector').set_value(20111).run()
    assert not app.exception
    assert 'transfer_records' not in app.session_state
    assert any('No existing-transfer pause' in m.value for m in app.markdown)


def test_unknown_fee_and_duplicate_schedule_get_no_invented_cash(app):
    add_schedule(app,fee=None)
    assert any('No existing-transfer pause' in m.value for m in app.markdown)
    next(b for b in app.button if b.label=='Add evidenced schedule').click().run()
    assert not app.exception
    assert len(app.session_state['transfer_records'])==6
    assert any('Duplicate schedule' in m.value for m in app.error)


def test_excessive_release_blocks_advice_without_crashing(app):
    add_schedule(app)
    app.number_input(key='transfer_amount').set_value(1000000.)
    app.text_input(key='transfer_id').set_value('too-large')
    next(b for b in app.button if b.label=='Add evidenced schedule').click().run()
    assert not app.exception
    assert any('cannot be applied' in m.value for m in app.error)

from test_crisis_ui import app, backup_cash_chart, custom


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
    add_schedule(app, fee=25.)
    assert len(app.session_state['transfer_records'])==6
    assert any('net cash retained: CAD 1,650.00' in m.value for m in app.markdown)
    paths = {trace['name']: trace for trace in backup_cash_chart(app)['data']}
    applied = paths['With supported actions']
    shocked = paths['Shock only']
    assert round(applied['y'][-1] - shocked['y'][-1], 2) == 1650.
    first_payment = applied['x'].index('Month 1 start')
    assert 'Action fee: $25.00' in applied['customdata'][first_payment]
    assert 'Action fee' not in shocked['customdata'][first_payment]
    assert any('full-period funding need is $1,650.00 lower' in c.value for c in app.tabs[2].caption)
    # Reruns do not duplicate scheduled payments.
    app.run()
    assert len(app.session_state['transfer_records'])==6
    app.number_input(key='account_selector').set_value(20111).run()
    assert not app.exception
    assert 'transfer_records' not in app.session_state
    assert any('No existing-transfer pause' in m.value for m in app.markdown)
    assert all('Action fee' not in note for trace in backup_cash_chart(app)['data'] for note in trace['customdata'])


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
    assert backup_cash_chart(app) is None

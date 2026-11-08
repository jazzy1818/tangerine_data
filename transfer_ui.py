"""Explicit analyst evidence; no transfer inferred from historical payments."""
import streamlit as st
from crisis_response import ExistingGoalTransfer


def render_transfers(horizon):
    with st.expander('Existing goal transfers — supplied evidence (optional)'):
        st.caption('Enter only supplied schedules. Inclusion means the payment is already counted in projected spending. Approval and fees must be explicitly supplied. These entries are scenario evidence, not verified live bank records.')
        with st.form('transfer_form'):
            event = st.text_input('Schedule identifier', key='transfer_id')
            source = st.text_input('Evidence source', key='transfer_source')
            amount = st.number_input('Payment amount (CAD)', min_value=.01, value=None, key='transfer_amount')
            start = st.number_input('First payment month', min_value=1, max_value=120, value=1, key='transfer_start')
            end = st.number_input('Last payment month (inclusive)', min_value=1, max_value=120, value=1, key='transfer_end')
            included = st.checkbox('Explicitly included in baseline spending', key='transfer_included')
            approved = st.checkbox('Pause explicitly approved in supplied evidence', key='transfer_approved')
            fee = st.number_input('Known pause fee per payment (CAD; blank means unknown)', min_value=0., value=None, key='transfer_fee')
            submitted = st.form_submit_button('Add evidenced schedule')
        saved = st.session_state.get('transfer_records', [])
        if submitted:
            try:
                if amount is None or end < start:
                    raise ValueError('Supply an amount and a valid payment-month range.')
                entries = [ExistingGoalTransfer(event_id=f'{event.strip()}:{m}', month=m, amount=amount,
                    source=source, included_in_baseline=included, pause_approved=approved, pause_fee=fee).model_dump()
                    for m in range(start, end+1)]
                if not event.strip():
                    raise ValueError('A schedule identifier is required.')
                ids = [t['event_id'] for t in saved + entries]
                if len(ids) != len(set(ids)):
                    raise ValueError('Duplicate schedule/payment: remove the old schedule before replacing it.')
                saved = saved + entries
                st.session_state['transfer_records'] = saved
            except ValueError as exc:
                st.error(f'Schedule not added: {exc}')
        if st.button('Clear supplied transfer schedules', key='transfer_clear'):
            saved = []
            st.session_state['transfer_records'] = []
        if saved:
            st.dataframe(saved, hide_index=True)
            if any(t['month'] > horizon for t in saved):
                st.info('Payments beyond the selected horizon remain recorded but release no cash inside it.')
        return saved

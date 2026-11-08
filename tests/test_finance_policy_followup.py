"""Evidence identity and analyst-facing requirements from the v1.1 handoff."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from backup_comparison import build_comparison
from crisis_response import make_crisis_plan
from plan_classification.schemas import ShockScenario
from scenario_execution import execute_scenario, scenario_hash
from test_crisis_execution import account, compound, normal_goal
from test_finance_decision_policy import assess, deferral, loan_account, transfers


@pytest.mark.parametrize('included', [False, True])
def test_generated_id_cannot_make_a_withheld_deferral_look_posted(included):
    shock = {'effects': [
        {'type': 'one_off_cost', 'value': 50., 'start_month': 0},
        deferral(effect_id='effect-1', obligation_payment=300.,
                 obligation_source='Hypothetical payment terms', payment_in_baseline=included),
    ]}
    plan = assess(loan_account(), shock)
    action = next(item for item in plan['candidate_action_decisions']
                  if item['action_id'] == 'deferral:effect-1')
    path = plan['no_action']
    assert path['schedule'][0]['applied_effect_ids'] == ['effect-1-generated']
    assert action['status'] == ('CONDITIONAL_ONLY' if included else 'BLOCKED_OR_UNKNOWN')
    assert action['evidence'] == (['BANK_CONFIRMED'] if included else ['UNKNOWN_OR_CONFLICTING'])
    assert path['schedule'][1]['spending'] == (2100. if included else 2400.)
    assert path['schedule'][4]['deferred_repayment'] == (650. if included else 0.)
    assert [item['effect_id'] for item in plan['financial_diagnosis']['effect_evidence']] == [
        'effect-1-generated', 'effect-1']


def test_resolved_ids_remain_unique_without_rewriting_scenario_inputs():
    shock = ShockScenario(effects=[
        {'type': 'one_off_cost', 'value': 50., 'start_month': 0},
        {'type': 'one_off_cost', 'value': 10., 'start_month': 0, 'effect_id': 'effect-1'},
        {'type': 'one_off_cost', 'value': 20., 'start_month': 0, 'effect_id': 'effect-1-generated'},
    ])
    original = shock.model_dump()
    fingerprint = scenario_hash(shock)
    path = execute_scenario(account(), shock)
    ids = path['schedule'][0]['applied_effect_ids']
    assert ids == ['effect-1-generated-generated', 'effect-1', 'effect-1-generated']
    assert len(ids) == len(set(ids))
    assert path['schedule'][0]['one_off_cost'] == 80.
    assert shock.model_dump() == original
    assert scenario_hash(shock) == fingerprint


def test_evidence_prompt_stays_bound_to_the_unpriced_event():
    crisis = make_crisis_plan(account(), {'effects': [
        {'type': 'unspecified_event'},
        {'type': 'one_off_cost', 'value': 20., 'start_month': 0, 'effect_id': 'effect-1'},
    ]}, normal_goal=normal_goal())
    notes = build_comparison(crisis)['evidence_notes']
    assert any(note.startswith('Event 1 · Enter the cash impact') for note in notes)
    assert not any(note.startswith('Event 2 · Enter the cash impact') for note in notes)
    assert crisis['finance_plan']['remaining_gap_cad'] is None


def test_pending_deferral_keeps_its_resolved_execution_identity():
    plan = assess(loan_account(), {'effects': [
        deferral(effect_id=None, repayment_month=None, repayment_amount=None, repayment_unresolved=True),
        {'type': 'one_off_cost', 'value': 20., 'start_month': 0, 'effect_id': 'effect-1'},
    ]})
    assert plan['no_action']['pending_effects'][0]['effect_id'] == 'effect-1-generated'
    assert plan['candidate_action_decisions'][0]['action_id'] == 'deferral:effect-1-generated'
    assert plan['candidate_action_decisions'][0]['status'] == 'BLOCKED_OR_UNKNOWN'


def test_review_deadline_precedes_a_hold_even_without_a_shortage():
    plan = assess(account(), {'effects': [
        {'type': 'liquidity_hold', 'value': 100., 'start_month': 2, 'duration_months': 2},
    ]})
    assert plan['comparison']['after']['first_shortfall'] is None
    assert plan['next_review_checkpoint']['checkpoint'] == {'month': 2, 'phase': 'start'}
    assert 'cash hold' in plan['next_review_checkpoint']['reason']
    assert plan['supported_action']['schedule'][2]['held_cash'] == 100.
    assert plan['supported_action']['schedule'][4]['held_cash'] == 0.


@pytest.mark.parametrize('kind', ['pause', 'deferral'])
def test_supplied_approvals_have_an_explicit_bank_review_flag(kind):
    plan = (assess(account(), compound(), existing_transfers=transfers()) if kind == 'pause'
            else assess(loan_account(), {'effects': [deferral()]}))
    assert any(flag.startswith('SUPPLIED_ACTION_TERMS:') for flag in plan['bank_review_flags'])
    assert plan['finance_approval'] == 'PENDING'
    assert all(item['not_executed'] is True for item in plan['candidate_action_decisions'])


def render_finance(plan):
    if not shutil.which('node'):
        pytest.skip('Node is required to verify the website review renderer')
    script = """
      import {readFileSync} from 'node:fs';
      import {financePlanView} from './web_app/static/reviews.js';
      process.stdout.write(financePlanView(JSON.parse(readFileSync(0, 'utf8'))));
    """
    return subprocess.check_output(['node', '--input-type=module', '-e', script],
        input=json.dumps(plan), text=True, cwd=Path(__file__).resolve().parents[1], timeout=10)


def test_website_action_cards_show_tradeoffs_and_review_deadlines():
    plan = assess(account(), compound(), existing_transfers=transfers())
    html = render_finance(plan)
    assert '<strong>Trade-offs</strong>' in html
    assert 'The original savings goal is delayed.' in html
    assert '<strong>Review by</strong> Month 1 start' in html
    assert '<strong>First remaining shortage after supported actions</strong> Month 3 end' in html
    assert '$1,560.00' in html
    # Retain escaping for all analyst text and compatibility with older cards.
    plan['prioritized_actions'][0]['tradeoffs'] = ['<img src=x onerror=alert(1)>']
    html = render_finance(plan)
    assert '<img' not in html and '&lt;img' in html
    for action in plan['prioritized_actions']:
        action.pop('tradeoffs', None)
    assert '<strong>Trade-offs</strong>' not in render_finance(plan)


def test_website_deferral_card_keeps_the_cost_tradeoff_visible():
    html = render_finance(assess(loan_account(), {'effects': [deferral()]}))
    assert 'The deferral increases total funding need over the modeled horizon.' in html
    assert '$650.00' in html and 'Month 4 start' in html
    assert '<strong>Review by</strong> Month 1 start' in html


def test_streamlit_action_cards_show_tradeoffs_and_review_deadlines():
    from streamlit.testing.v1 import AppTest
    crisis = make_crisis_plan(account(), compound(), normal_goal=normal_goal(), existing_transfers=transfers())
    script = ('import json\nfrom backup_comparison import render_backup_comparison\n'
              f'render_backup_comparison(json.loads({json.dumps(crisis)!r}))')
    app = AppTest.from_string(script).run(timeout=20)
    assert not app.exception
    assert any('Trade-off: The original savings goal is delayed.' in item.value for item in app.markdown)
    assert any('Review by Month 1 (start)' in item.value for item in app.caption)

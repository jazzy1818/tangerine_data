import {money, number} from './common.js';

export const purposes={cash_flow:'Manage cash flow',unexpected_cost:'Cover an unexpected expense',debt:'Review payment pressure',recovery:'Rebuild cash reserves',savings:'Review a savings goal',other:'Other customer need'};
export const reviewStatuses={in_progress:'In progress',awaiting_information:'Awaiting information',ready_to_discuss:'Ready for discussion',follow_up:'Follow-up scheduled',closed:'Closed'};
export const goalStatuses={NOT_SCHEDULED:'No regular contribution established',REVIEW_REQUIRED:'More information needed',BASELINE_REVIEW_REQUIRED:'Existing goal needs review',MAINTAINED:'Contribution can be maintained',REDUCED:'Reduce the proposed contribution',PAUSED:'Pause the proposed contribution',EXISTING_TRANSFERS_PAUSED:'Review supported payment pauses'};
export const recoveryStatuses={RECOVERY_UNVERIFIED:'Updated figures needed',ACTIVE_CRISIS:'Cash flow still needs attention',RESERVE_RESTORED:'Reserve target reached on supplied figures',REBUILDING:'Rebuilding reserves'};
export const focusNames={M1:'Maintain income',M2:'Rebalance spending',M3:'Cover an urgent cash need',M4:'Protect essential payments',M5:'Coordinate several financial pressures',M6:'Rebuild cash reserves',M7:'Address payment timing and access',M8:'Plan for additional funds'};
export const reasonLabels={income_reduction:'Income is reducing',income_increase:'Income is increasing',cost_increase:'Regular costs are increasing',cost_reduction:'Regular costs are reducing',one_off_expense:'A one-time expense is due',windfall:'Additional funds are expected',debt_payment_change:'Loan payments are changing',timing_or_access:'Payment timing or access needs review',compound_effects:'Several circumstances are changing',immediate_liquidity_pressure:'Available cash is under immediate pressure',recurring_shortfall:'Regular spending exceeds inflow',surplus_available:'Regular inflow exceeds spending',reserve_below_target:'Cash reserves are below the planning target',historical_timing_stress:'Past overdrafts recovered before month end',essential_obligations_at_risk:'Existing obligations need attention',recovery:'The customer is rebuilding',missing_details:'Some information remains unconfirmed',no_new_effect:'Reviewing existing circumstances',restricted_modules:'Some responses are unavailable',investment_change:'Investment value has changed'};
export const effectNames={income_multiplier:'Income level',income_delta:'Regular income',expense_delta:'Regular spending',expense_percent:'Regular spending',household_bills_percent:'Household bills',household_bills_delta:'Household bills',debt_payment_delta:'Loan payment',one_off_cost:'One-time expense',one_off_receipt:'Additional funds',liquidity_hold:'Cash temporarily unavailable',payment_delay_days:'Payment delay',investment_return:'Investment value',unspecified_event:'Change awaiting confirmation'};
export const sources={judge_specified:'Provided information',user_confirmed:'Confirmed information',assumed:'Estimate to confirm',unknown:'Not yet confirmed'};

export function plainNote(text) {
  let value=String(text||'').replace(/^[A-Z][A-Z0-9_]+:\s*/,'');
  if(value.includes('A normal/no-change scenario cannot contain financial shocks')) return 'Choose “Assessing a change” when financial changes are listed.';
  const substitutions={HISTORICAL_PROXY:'historical cash estimate',SUPPLIED_SCENARIO:'supplied cash figure',LIQUID_RESERVE_EARMARK:'cash kept in reserve',PROPOSED_TRANSFER:'proposed savings transfer',G25:'goal affordability', 'runtime validation':'financial checks', 'quantified components':'known amounts', 'quantified-component':'known-amount', 'quantified cash':'cash based on known amounts', 'classification proposal':'suggested response', 'classifier':'assessment', 'effect_id':'payment reference', 'competition historical buffer proxy':'historical cash estimate', 'Historical full-history medians':'Historical typical inflows and spending'};
  for(const [old,replacement] of Object.entries({...effectNames,...substitutions})) value=value.replaceAll(old,replacement);
  return value.replace(/\bM[1-8]\b/g,code=>focusNames[code]);
}

export function effectSummary(f) {
  const name=effectNames[f.type]||'Financial change';
  let amount='Amount to confirm';
  if(f.value!=null) {
    if(f.type==='income_multiplier') amount=`${number(f.value*100)}% of usual income`;
    else if(['expense_percent','household_bills_percent','investment_return'].includes(f.type)) amount=`${number(Math.abs(f.value))}% ${f.value<0?'decrease':'increase'}`;
    else if(f.type==='payment_delay_days') amount=`${number(f.value)} days`;
    else if(['income_delta','expense_delta','household_bills_delta','debt_payment_delta'].includes(f.type)) amount=`${money(Math.abs(f.value))} ${f.value<0?'less':'more'} per month`;
    else amount=money(f.value);
  }
  const start=f.start_month??1;
  const timing=start===0?'Immediately':`From month ${start}`;
  const duration=f.ongoing?'ongoing':f.duration_months?`for ${f.duration_months} months`:['one_off_cost','one_off_receipt'].includes(f.type)?'one time':'timing / duration to confirm';
  return {name,amount,timing:`${timing} · ${duration}`,source:sources[f.evidence||'judge_specified']||'Provided information'};
}

export function shortfall(path) {
  if(!path) return 'Unable to assess';
  if(path.first_shortfall_month==null) return path.funding_result_complete?'None in this period':'Not established';
  const prefix=path.funding_result_complete?'':'Known amounts: ';
  if(path.first_shortfall_month===0) return prefix+'Immediately';
  return `${prefix}${path.first_shortfall_phase==='start'?'Start':'End'} of month ${path.first_shortfall_month}`;
}

export function followupItems(run) {
  const result=run.result, plan=result?.plans?.crisis_plan;
  if(!plan) return [];
  const path=plan.applied_plan, items=[];
  if(!path || plan.runtime_validation?.status!=='passed') return [{id:'review_calculation',title:'Resolve the assessment issue',detail:'Review the recorded figures before using this assessment in a customer discussion.'}];
  if(path.opening_basis==='HISTORICAL_PROXY') items.push({id:'confirm_cash',title:'Confirm accessible cash',detail:'Obtain a current available balance; the projection currently starts from a historical estimate.'});
  if(!path.funding_result_complete || result.case.missing_details.length) items.push({id:'confirm_changes',title:'Confirm the missing amounts and dates',detail:'Resolve the information listed under “Information to confirm” and update the assessment.'});
  if(path.additional_cash_needed>0) items.push({id:'address_gap',title:'Discuss the remaining funding gap',detail:`The known amounts leave ${money(path.additional_cash_needed)} to cover. Record any agreed funding or spending changes before reassessing.`});
  if(run.request.scenario.effects.some(f=>['income_multiplier','income_delta'].includes(f.type) && f.value!=null && f.value<(f.type==='income_multiplier'?1:0) && f.duration_months)) items.push({id:'income_expiry',title:'Confirm income after temporary support ends',detail:'Check the expected amount and date of replacement income; recovery is not automatically assumed.'});
  if(result.customer.profile.features.active_loan || run.request.existing_transfers?.length) items.push({id:'payment_terms',title:'Confirm payment terms and any relief',detail:'Check due dates, fees and authority for any proposed pause or change before taking action.'});
  if(plan.recovery.status==='RECOVERY_UNVERIFIED' && (run.request.scenario.phase==='recovery' || plan.affected_modules.includes('M6'))) items.push({id:'recovery_figures',title:'Obtain updated recovery figures',detail:'Confirm cash, spending, stability, obligations and a supported contribution before setting a rebuild date. Record recurring inflow if known.'});
  items.push({id:'customer_discussion',title:'Record the customer discussion',detail:'Explain the proposed next steps, record the customer’s priorities, and agree when to review progress.'});
  return items;
}

export function reviewBrief(run) {
  const p=run.result?.plans?.crisis_plan, review=run.review||{}, details=run.request.review_details||{};
  const lines=['CUSTOMER FINANCIAL REVIEW',run.request.title,`Account: ${run.request.account_id}`,`Prepared: ${new Date(run.created_at).toLocaleString()}`,`Prepared by: ${details.prepared_by||'Not recorded'}`,`Customer priority: ${details.customer_priority||'Not recorded'}`,`Purpose: ${purposes[details.purpose]||'Financial review'}`,'','CIRCUMSTANCES',...run.request.scenario.effects.map(f=>{const s=effectSummary(f);return `${s.name}: ${s.amount}. ${s.timing}. ${s.source}.`;})];
  if(p?.no_action && p?.applied_plan) lines.push('','ASSESSMENT',`Suggested focus: ${focusNames[p.lead_module]||'Further review needed'}`,`Additional cash needed before changes: ${money(p.no_action.full_funding_need)}`,`Remaining cash need after supported changes: ${money(p.applied_plan.full_funding_need)}`,`First projected shortfall: ${shortfall(p.applied_plan)}`,`Closing cash based on known amounts: ${money(p.applied_plan.ending_cash)}`,`Supported monthly goal contribution: ${money(p.goal_contribution_revised)}`,`Goal: ${goalStatuses[p.goal_status]||plainNote(p.goal_status)}`,`Recovery: ${recoveryStatuses[p.recovery.status]||'Further review needed'}`,'','ASSUMPTIONS',`Customer records through ${run.result.customer.profile.as_of}.`, 'Figures are projections based on recorded and supplied amounts. Month-start/end balances do not establish day-to-day payment coverage.',...p.review_flags.map(plainNote));
  else lines.push('','Assessment figures are not available for a funding conclusion.');
  const comparison=run.result?.cash_comparison;
  if(comparison)lines.push('','CASH COMPARISON',comparison.summary,...comparison.actions,...comparison.evidence_notes);
  if(p?.recovery?.reserve_gap!=null)lines.push('','RECOVERY',`Reserve gap: ${money(p.recovery.reserve_gap)}`,`Supported contribution: ${money(p.recovery.monthly_contribution)} per month`,`Rebuild date: ${p.recovery.months_to_target==null?'Not established':p.recovery.months_to_target+' months'}`,...p.recovery.review_flags.map(plainNote));
  lines.push('','FOLLOW-UP',`Review status: ${reviewStatuses[review.status]||'In progress'}`,`Owner: ${review.owner||details.prepared_by||'Not recorded'}`,`Follow-up: ${review.follow_up_date||'Not scheduled'}`,...followupItems(run).map(i=>`${review.completed_items?.includes(i.id)?'[Recorded complete]':'[To do]'} ${i.title}: ${i.detail}`),'',`Staff notes: ${review.notes||'None recorded'}`,'','Review status and checklist completion record staff work; they do not approve or execute a financial action.');
  return lines.join('\n');
}

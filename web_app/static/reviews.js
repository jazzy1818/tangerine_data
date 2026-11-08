import {escapeHtml as e, money, badge, metric, notice, table} from './common.js';
import {cashPathChart} from './charts.js';
import {heading, noteList, reviewStatus, overdue} from './views.js';
import {purposes, reviewStatuses, goalStatuses, recoveryStatuses, focusNames, mainGoalNames, reasonLabels, plainNote, effectSummary, shortfall, followupItems} from './financial.js';

function followupForm(run) {
  const r=run.review||{version:0,status:'in_progress',owner:run.request.review_details?.prepared_by||'',completed_items:[]},items=followupItems(run);
  return `<section class="card"><h2>Record the discussion and next steps</h2><p class="help">Record what was discussed, what information is outstanding, and who will follow up.</p><form id="review-form" class="no-print"><input type="hidden" name="version" value="${r.version}"><div class="form-grid"><label>Review progress<select name="status">${Object.entries(reviewStatuses).map(([k,v])=>`<option value="${k}" ${r.status===k?'selected':''}>${v}</option>`).join('')}</select></label><label>Review owner<input name="owner" maxlength="120" value="${e(r.owner||'')}" placeholder="Employee name or reference"></label><label>Follow-up date<input type="date" name="follow_up_date" value="${e(r.follow_up_date||'')}"></label></div><div class="followup-list">${items.map(i=>`<label class="followup-item"><input type="checkbox" name="completed_items" value="${i.id}" ${r.completed_items?.includes(i.id)?'checked':''}><span><strong>${e(i.title)}</strong><small>${e(i.detail)}</small></span></label>`).join('')}</div><label>Discussion notes and agreed next step<textarea name="notes" maxlength="4000" rows="5" placeholder="Record the customer's priorities, information requested, and next contact.">${e(r.notes||'')}</textarea></label><div class="actions sticky-actions"><button type="submit" class="primary">Save review notes</button><button type="button" class="ghost" data-action="discard-review-edits">Discard edits / load saved notes</button><span id="review-save-status" class="help">${r.updated_at?`Last saved ${e(new Date(r.updated_at).toLocaleString())}`:'Notes not yet saved'}</span></div></form><div class="print-only"><p>Review progress: ${e(reviewStatuses[r.status]||'In progress')} · Owner: ${e(r.owner||'Not recorded')} · Follow-up: ${e(r.follow_up_date||'Not scheduled')}</p>${noteList(items.map(i=>`${r.completed_items?.includes(i.id)?'Recorded complete':'To do'}: ${i.title}`))}<p class="preserve-lines">${e(r.notes||'No discussion notes recorded.')}</p></div><p class="help">Checklist completion records staff work. To change the financial assessment, update the figures and reassess. No payment or product approval is made here.</p></section>`;
}

const actionStatus={SUPPORTED_MODELED:['Supported by the evidence','success'],CONDITIONAL_ONLY:['Needs approval first','warn'],TARGET_ONLY:['Amount to arrange',''],BLOCKED_OR_UNKNOWN:['Needs information','error'],MAINTAIN:['No change needed','success']};
const decisionLabel={selected:'Recommended',considered:'Also available',excluded:'Not used'};

function actionItem(a,index) {
  const [label,tone]=actionStatus[a.status]||[a.status,''];
  const facts=[a.amount_cad!=null?['Amount',`${money(a.amount_cad)}${a.frequency?` · ${a.frequency}`:''}`]:null,
    a.starts_at||a.ends_at?['When',[a.starts_at,a.ends_at].filter(Boolean).join(' → ')]:null,
    a.effect_on_first_shortfall?['First shortfall afterwards',a.effect_on_first_shortfall]:null,
    a.required_review?['Confirm',a.required_review]:null].filter(Boolean);
  return `<li class="plan-action"><div class="card-head"><h3>${index+1}. ${e(a.title)}</h3>${badge(label,tone)}</div><p>${e(a.instruction)}</p>
    ${facts.length?`<p class="help">${facts.map(([k,v])=>`${e(k)}: <b>${e(v)}</b>`).join(' · ')}</p>`:''}<p class="help">${e(a.cash_treatment)}</p></li>`;
}

export function optionsTable(ap) {
  return `<details class="card"><summary>All options considered (${ap.candidate_action_decisions.length})</summary>
    ${table(['Option','Type','Decision','Why'],ap.candidate_action_decisions.map(a=>[e(a.title),e((actionStatus[a.status]||[a.status])[0]),e(decisionLabel[a.decision]||a.decision),e(a.decision==='selected'?a.rationale:a.reason||a.rationale)]))}
    <p class="help">Recommended options are ordered by urgency: the earliest cash shortfall first, then obligations, then the monthly gap. Nothing here has been executed.</p></details>`;
}

function planCards(run,incomplete) {
  const r=run.result,ap=r.plans.action_plan;
  if(!ap||!ap.diagnosis)return legacyPlanCards(run,incomplete);
  const c=r.plans.crisis_plan,g=r.plans.goal_plan,normal=c.goal_before_crisis,goalName=mainGoalNames[normal.name]||normal.name;
  const change=run.request.scenario.effects.length>0,after=ap.comparison.supported_actions,d=ap.diagnosis;
  const remaining=after.full_funding_need,first=d.first_shortfall;
  return `<div class="grid-2"><section class="card"><div class="eyebrow">Normal conditions</div><h2>Main plan</h2><h3>${e(mainGoalNames[g.primary_goal]||'Review the customer’s goal')}</h3><p>${e(plainNote(g.recommendation))}</p>
    <div class="metric-grid">${metric(normal.kind==='LIQUID_RESERVE_EARMARK'?'Monthly reserve earmark':'Proposed monthly transfer',money(c.goal_contribution_before),'Before this shock')}${metric('Reserve target',money(normal.reserve_target))}</div>
    <p><strong>If the shock happens:</strong> ${e(ap.normal_goal_impact.summary)}</p>
    <p class="help">Goal: ${e(goalName)}. The main plan uses the customer’s normal history.</p></section>
    <section class="card"><div class="eyebrow">${change?'For the selected shock':run.request.scenario.phase==='recovery'?'For the recovery review':'For current circumstances · no new shock'}</div><h2>Backup plan</h2>
    <p><strong>${e(ap.headline)}</strong></p>
    <h3>Recommended actions</h3><ol class="plan-actions">${ap.prioritized_actions.map(actionItem).join('')}</ol>
    <div class="metric-grid">${metric('First shortfall',first?first.label:'None in the plan',first?`Short ${money(first.need)}`:'Cash stays above zero')}${metric('Still to fund after supported actions',remaining==null?'Not established':money(remaining),remaining==null?`Known amounts: ${money(after.known_components_need)}`:`Over ${ap.horizon_months} months`)}</div>
    <p class="help"><strong>Next review:</strong> ${e(ap.next_review_checkpoint)}</p>
    ${ap.comparison.identical&&ap.comparison.identical_reason?`<p class="help">${e(ap.comparison.identical_reason)}</p>`:''}</section></div>
    ${optionsTable(ap)}`;
}

function legacyPlanCards(run,incomplete) {
  const r=run.result,c=r.plans.crisis_plan,g=r.plans.goal_plan,normal=c.goal_before_crisis,comparison=r.cash_comparison;
  const change=run.request.scenario.effects.length>0,goalName=mainGoalNames[normal.name]||normal.name;
  return `<div class="grid-2"><section class="card"><div class="eyebrow">Normal conditions</div><h2>Main plan</h2><h3>${e(mainGoalNames[g.primary_goal]||'Review the customer’s goal')}</h3><p>${e(plainNote(g.recommendation))}</p>
    <div class="metric-grid">${metric(normal.kind==='LIQUID_RESERVE_EARMARK'?'Monthly reserve earmark':'Proposed monthly transfer',money(c.goal_contribution_before),'Before this shock; subject to confirmation')}${metric('Reserve target',money(normal.reserve_target))}</div>
    <p class="help">Goal: ${e(goalName)}. ${normal.kind==='LIQUID_RESERVE_EARMARK'?'Reserve earmarks stay in accessible cash.':'A proposed transfer leaves the account if made.'} The main plan uses normal planning history; its cash basis can differ from the shock projection.</p></section>
    <section class="card"><div class="eyebrow">${change?'For the selected shock':run.request.scenario.phase==='recovery'?'For the recovery review':'For current circumstances · no new shock'}</div><h2>Backup plan</h2><h3>${e(focusNames[c.lead_module]||'Confirm the missing information')}</h3>
    <p>${e(plainNote(c.advice?.cards?.gap||comparison?.summary||'Review the supported changes and outstanding information below.'))}</p>
    ${comparison?.actions?.length?noteList(comparison.actions):''}
    <div class="metric-grid">${metric('Monthly goal after the shock',money(c.goal_contribution_revised),goalStatuses[c.goal_status]||plainNote(c.goal_status))}${metric('Remaining funding gap',money(incomplete?null:c.applied_plan.full_funding_need),incomplete?`Known amounts leave ${money(c.applied_plan.additional_cash_needed)}`:'After supported changes')}</div>
    <p>First projected shortfall: <strong>${e(shortfall(c.applied_plan))}</strong>.</p><p class="help">The backup plan includes only supported actions. Changing a future savings proposal does not add cash to today’s balance.</p></section></div>`;
}

export function runView(run) {
  const details=run.request.review_details||{};
  const head=heading('Customer plans',run.request.title,`Account ${run.request.account_id} · Prepared ${new Date(run.created_at).toLocaleString()}`,
    `<button data-action="duplicate" class="ghost">Change shock / generate again</button>${run.status==='complete'?'<button data-action="brief">Download plans</button><button data-action="print" class="primary">Print / save PDF</button>':''}`);
  if(run.status==='running') return head+'<section class="card"><div class="loading">Generating the main and backup plans…</div><p class="help">You can return to these plans from your review history.</p></section>';
  if(run.status==='failed') return head+notice('This assessment could not be completed. Review the recorded circumstances before preparing a new assessment.','error')+`<details><summary>Information to review</summary><p>${e(plainNote(run.error))}</p></details><a class="button" href="#history">Return to reviews</a>`;
  const r=run.result,c=r.plans.crisis_plan,cls=r.classification,path=c.no_action,applied=c.applied_plan,goal=r.plans.goal_plan;
  let html=head;
  if(cls.fallback_used) html+=notice('Assisted assessment was unavailable. A standard rules-based assessment was used; review the suggested response before discussing it with the customer.','warn');
  html+=`<section class="card"><h2>Selected scenario</h2><p>${e(run.request.scenario.effects.map(f=>{const s=effectSummary(f);return `${s.name}: ${s.amount}, ${s.timing}.`;}).join(' ')||(run.request.scenario.phase==='recovery'?'Recovery review using supplied figures.':'No new shock. Review the customer’s current circumstances.'))}</p><p class="help">Plan period: ${run.request.scenario.horizon_months} months${details.customer_priority?` · Customer priority: ${e(details.customer_priority)}`:''}</p>${(details.shock_defaults||[]).length?`<p class="help"><strong>Defaults used:</strong> ${e(details.shock_defaults.join(' '))}</p>`:''}</section>`;
  if(!path||!applied) return html+notice('The figures need further review before a funding assessment can be used.','error')+noteList(c.review_flags)+followupForm(run);
  const comparison=r.cash_comparison;
  const incomplete=!(comparison?.complete??(path.funding_result_complete&&applied.funding_result_complete&&c.funding_result_complete));
  if(incomplete)html+=notice('Some amounts or dates are still unknown. These plans use known information only; the full funding gap is not established.','warn');
  html+=planCards(run,incomplete);
  if(r.case.missing_details.length)html+=`<section class="card"><h2>Information to confirm</h2>${noteList(r.case.missing_details)}</section>`;
  html+='<details class="card"><summary>Financial details and cash-flow comparison</summary>';
  const verdict=incomplete?'Confirm the outstanding information.':applied.additional_cash_needed>0?'A funding gap remains.':'No funding gap is projected at the monthly checkpoints.';
  html+=`<section class="card"><div class="card-head"><div><div class="eyebrow">Assessment summary</div><h2>${e(verdict)}</h2></div>${badge(incomplete?'Incomplete information':applied.additional_cash_needed>0?'Funding discussion needed':'Review with customer',incomplete||applied.additional_cash_needed>0?'warn':'')}</div><div class="metric-grid">${metric('Additional cash needed',money(incomplete?null:path.full_funding_need),incomplete?'Known amounts leave '+money(path.additional_cash_needed):'Before supported changes')}${metric('Remaining funding gap',money(incomplete?null:applied.full_funding_need),incomplete?'Known amounts leave '+money(applied.additional_cash_needed):'After supported changes')}${metric('First shortfall after changes',shortfall(applied))}${metric('Cash at period end',money(applied.ending_cash),incomplete?'Known amounts only':'After supported changes')}</div><p class="help">${path.opening_basis==='HISTORICAL_PROXY'?'Opening cash is a historical estimate; confirm the accessible balance.':'Opening cash uses the supplied scenario figure.'} Monthly checkpoints do not establish day-to-day payment coverage.</p></section>
    <div class="grid-2"><section class="card"><h2>Suggested focus</h2><h3>${e(focusNames[c.lead_module]||'Further financial review')}</h3><div class="chips">${cls.selection.reason_codes.map(code=>badge(reasonLabels[code]||plainNote(code))).join('')}</div>${c.support_modules.length?`<p class="help">Also consider: ${e(c.support_modules.map(id=>focusNames[id]).join('; '))}.</p>`:''}${c.lead_module!==cls.selection.lead_module?`<p class="help">The initial suggestion was “${e(focusNames[cls.selection.lead_module])}”. The cash and eligibility checks support the response shown here.</p>`:''}</section><section class="card"><h2>Impact on the savings goal</h2><h3>${e(goalStatuses[c.goal_status]||plainNote(c.goal_status))}</h3><div class="metric-grid">${metric('Before the change',money(c.goal_contribution_before),'Proposed monthly contribution')}${metric('Supported after the change',money(c.goal_contribution_revised),'Per month')}</div><p class="help">${c.goal_before_crisis.kind==='LIQUID_RESERVE_EARMARK'?'This amount stays in accessible cash reserves.':'This is a proposed savings transfer.'} Pausing a proposed contribution does not add cash to the existing balance.</p></section></div>
    <section class="card"><h2>Compare the financial paths</h2>${comparison?comparisonExplanation(comparison):''}<div class="path-controls no-print"><label class="check"><input type="checkbox" data-path="baseline_without_crisis" checked> Before the change</label><label class="check"><input type="checkbox" data-path="no_action" checked> Without additional action</label><label class="check"><input type="checkbox" data-path="applied_plan" checked> With supported changes</label><label class="check"><input type="checkbox" data-path="continue_goal"> Keep the original goal</label></div><div id="projection-chart">${projectionChart(c)}</div></section>`;
  if(c.required_monthly_improvement!=null&&path.additional_cash_needed>0) html+=`<section class="card"><h2>What would need to improve?</h2><p>The projection requires ${e(money(c.immediate_cash_target))} upfront and ${e(money(c.required_monthly_improvement))} of monthly improvement before any additional action.</p><p class="help">This is the calculated amount to address. It does not establish that spending can be cut or that funding is available. Record supported changes and reassess.</p></section>`;
  html+=`<div class="grid-2"><section class="card"><h2>Cash reserve goal</h2>${table(['Measure','Amount'],[['Three-month reserve target',e(money(goal.target_3mo))],['Reserve gap before the change',e(money(goal.needed_for_3mo))],['Baseline monthly reserve contribution',e(money(goal.recommended_contribution))]])}<p class="help">The contribution after the change is shown above. The reserve goal uses recorded spending and a planning target; confirm it with the customer.</p></section><section class="card"><h2>Recovery and rebuilding</h2>${badge(recoveryStatuses[c.recovery.status]||'Further review needed')}<p class="help">${e(plainNote(c.recovery.reason||'Obtain updated cash, income, spending and obligation figures before establishing a rebuild date.'))}</p>${c.recovery.reserve_gap!=null?`<p>Reserve gap: <strong>${e(money(c.recovery.reserve_gap))}</strong></p><p>Supported rebuild contribution: <strong>${e(money(c.recovery.monthly_contribution))} / month</strong></p>`:''}<p>Rebuild timeline: <strong>${c.recovery.months_to_target==null?'Not yet established':`${c.recovery.months_to_target} months`}</strong></p>${c.recovery.monthly_surplus===null?'<p class="help">Monthly inflow and surplus remain unknown. Any rebuild date uses only the supported contribution, confirmed cash-flow stability and covered obligations.</p>':''}</section></div>`;
  const adviceNames={diagnosis:'Cash position',cash_flow:'Income and spending',goal:'Savings goal',pause:'Scheduled payments',outcome:'Result after changes',funding_target:'Required improvement',gap:'Funding still needed',recovery:'Recovery'};
  if(c.advice?.cards)html+=`<details><summary>Full plan explanation</summary>${Object.entries(c.advice.cards).map(([k,v])=>`<h3>${e(adviceNames[k]||plainNote(k))}</h3><p>${e(plainNote(v))}</p>`).join('')}</details>`;
  html+='</details>';
  return html+`<details class="card"><summary>Discussion notes and follow-up (optional)</summary>${followupForm(run)}</details><details class="card"><summary>Figures and assumptions behind the plans</summary><details><summary>Changes included in this assessment</summary>${changesTable(run.request.scenario.effects)}${run.request.scenario.description?`<p class="preserve-lines">${e(run.request.scenario.description)}</p>`:''}</details><details><summary>Monthly cash-flow schedule</summary>${table(['Month','Money in','Regular spending','One-time costs','One-time receipts','Closing cash'],path.schedule.map(s=>[s.month===0?'Now':s.month,...['income','spending','one_off_cost','one_off_receipt','end_balance'].map(k=>e(money(s[k])))]))}<button class="no-print" data-action="cashflow-csv">Download cash-flow spreadsheet</button></details>${c.pause_decisions.length?`<details><summary>Payment pause decisions</summary>${table(['Payment','Outcome','Reason'],c.pause_decisions.map(d=>[e(d.event_id),e(plainNote(d.status)),e(plainNote(d.reason))]))}</details>`:''}<details><summary>Assumptions and limitations</summary>${noteList(c.review_flags)}</details><details><summary>Record details</summary>${table(['Record','Detail'],[['Customer records through',e(r.customer.profile.as_of)],['Purpose',e(purposes[details.purpose]||'Financial review')],['Prepared by',e(details.prepared_by||'Not recorded')],['Cash figure source',e(details.cash_source||(path.opening_basis==='HISTORICAL_PROXY'?'Historical account balances':'Source not recorded'))],['Assessment approach',e(cls.actual_backend==='rule_baseline'?'Standard rules-based assessment':cls.actual_backend==='jev'?'Jev-assisted assessment':'Gemini-assisted assessment')],['Prepared on',e(new Date(run.created_at).toLocaleString())]])}</details></details>`;
}

function comparisonExplanation(view) {
  const sides=[view.before,view.after],prefix=view.complete?'':'Known components · ';
  const first=side=>side.first?`Month ${side.first.month} (${side.first.phase})`:view.complete?'None at checkpoints':'Not established';
  return `${view.planning_status?`<p>${badge(view.planning_status.label)} ${e(view.planning_status.reason)}</p>`:''}
    ${notice(view.summary,view.complete?'info':'warn')}${noteList(view.actions)}
    ${view.evidence_notes.length?`<details><summary>Information behind this comparison</summary>${noteList(view.evidence_notes)}</details>`:''}
    ${view.pending.length?`<p class="help">${e(view.pending.map(([kind,month])=>`${plainNote(kind)} is scheduled for month ${month}, beyond this ${view.horizon}-month view.`).join(' '))}</p>`:''}
    <details><summary>Cash position at key checkpoints</summary>${table(['Measure','Without additional action','With supported changes'],[
      [prefix+'First shortfall',...sides.map(s=>e(first(s)))],
      [prefix+'Cash missing at first shortfall',...sides.map(s=>e(s.first?money(-s.first.cash):view.complete?money(0):'Not established'))],
      [prefix+'Lowest cash',...sides.map(s=>e(money(s.minimum_cash)))],
      [prefix+'Closing cash',...sides.map(s=>e(money(s.ending_cash)))],
      ['Full funding need',...sides.map(s=>e(money(view.complete?s.full_need:null)))],
    ])}</details>`;
}

export function changesTable(effects) {
  if(!effects.length) return '<p class="help">No new changes. The review uses the customer’s existing circumstances.</p>';
  return table(['Change','Amount','Timing','Information basis'],effects.map(f=>{const s=effectSummary(f);return [e(s.name),e(s.amount),e(s.timing),e(s.source)];}));
}
export function projectionChart(crisis,selected=['baseline_without_crisis','no_action','applied_plan']) {
  const names={baseline_without_crisis:'Before the change',no_action:'Without additional action',applied_plan:'With supported changes',continue_goal:'Keep the original goal'};
  if(!selected.length) return '<p class="help">Choose a cash-flow path to display.</p>';
  return cashPathChart(selected.filter(k=>names[k]&&crisis[k]).map(k=>({key:k,name:names[k],path:crisis[k]})));
}
export function historyView(items,filter='all') {
  const shown=filter==='all'?items:items.filter(r=>(r.review?.status||'in_progress')===filter);
  return heading('Review history','Pick up the customer conversation.','Reopen a review, compare alternatives, or follow up on outstanding information.','<button data-action="refresh">Refresh</button><button id="compare-button" data-action="compare" disabled>Compare selected</button>')+
    `<section class="card"><label class="filter-label">Review progress<select id="review-filter">${Object.entries({all:'All reviews',...reviewStatuses}).map(([k,v])=>`<option value="${k}" ${filter===k?'selected':''}>${v}</option>`).join('')}</select></label>${shown.length?table(['Compare','Customer review','Account','Owner','Remaining funding need','Progress','Follow-up',''],shown.map(r=>[
    r.status==='complete'?`<input type="checkbox" data-compare="${e(r.id)}" aria-label="Compare ${e(r.title)}">`:'',`<a class="route-link" href="#run/${e(r.id)}">${e(r.title)}</a><div class="help">${e(new Date(r.created_at).toLocaleDateString())}</div>`,e(r.account_id),e(r.review?.owner||'Unassigned'),e(r.funding_result_complete?money(r.remaining_cash_needed??r.additional_cash_needed):'To confirm'),reviewStatus(r),`${e(r.review?.follow_up_date||'Not scheduled')}${overdue(r)?' '+badge('Overdue','warn'):''}`,`<a class="button small" href="#run/${e(r.id)}">Open review →</a>`])):'<p>No reviews match this view. Start a customer review or choose a different progress filter.</p>'}<p class="help">Latest 100 saved assessments in this workspace.</p></section>`;
}
export function compareView(runs) {
  if(runs.some(r=>r.status!=='complete')) return notice('Wait for both assessments to finish before comparing them.','warn');
  const [a,b]=runs,paths=runs.map(r=>r.result.plans.crisis_plan.applied_plan);
  const rows=[['Account',...runs.map(r=>e(r.request.account_id))],['Review period',...runs.map(r=>`${r.request.scenario.horizon_months} months`)],['Suggested focus',...runs.map(r=>e(focusNames[r.result.plans.crisis_plan.lead_module]||'Further review'))],['Remaining funding need',...paths.map(p=>e(money(p?.full_funding_need)))],['Closing cash based on known amounts',...paths.map(p=>e(money(p?.ending_cash)))],['First projected shortfall',...paths.map(p=>e(shortfall(p)))],['Supported monthly goal contribution',...runs.map(r=>e(money(r.result.plans.crisis_plan.goal_contribution_revised)))]];
  let html=heading('Compare alternatives','Make the trade-offs clear.',a.request.account_id===b.request.account_id?'Review how different circumstances and supported actions affect this customer.':'These assessments concern different customers. Compare their circumstances before drawing conclusions.','<a class="button" href="#history">Return to reviews</a>')+`<section class="card">${table(['Measure',a.request.title,b.request.title],rows)}</section>`;
  if(paths.every(Boolean)) {
    html+=`<section class="card">${cashPathChart(paths.map((path,i)=>({key:i?'b':'a',name:runs[i].request.title,path})),'Cash after supported changes')}<p class="help">Unknown effects may leave the funding assessment incomplete. A projected balance does not confirm day-to-day payment coverage.</p></section>`;
  }
  return html+`<div class="grid-2">${runs.map(r=>`<section class="card"><h2>${e(r.request.title)}</h2>${changesTable(r.request.scenario.effects)}<p class="help">Opening cash: ${e(r.request.opening_cash==null?'Historical estimate':money(r.request.opening_cash))}</p><p>Scheduled payment records: ${r.request.existing_transfers?.length||0}. Recovery figures: ${r.request.recovery_snapshot?'supplied':'not supplied'}.</p><a class="button" href="#run/${r.id}">Open full review →</a></section>`).join('')}</div>`;
}

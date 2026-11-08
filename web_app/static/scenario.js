import {escapeHtml as e, money, notice, empty} from './common.js';
import {heading, previewView} from './views.js';
import {purposes, effectSummary, sources} from './financial.js';

export const effects={
  income_multiplier:['Income level','Income as a percentage of the usual amount',55,0],
  income_delta:['Regular income change','Change in CAD per month (negative for a decrease)',-500,null],
  expense_delta:['Regular spending change','Change in CAD per month (negative for a decrease)',250,null],
  expense_percent:['Regular spending percentage change','Change in percent (negative for a decrease)',15,-100],
  household_bills_percent:['Household-bill percentage change','Change in percent (negative for a decrease)',15,-100],
  household_bills_delta:['Household-bill amount change','Change in CAD per month (negative for a decrease)',250,null],
  debt_payment_delta:['Loan-payment change','Change in CAD per month (negative for a decrease)',100,null],
  one_off_cost:['One-time expense','Expense in CAD',1000,0],
  one_off_receipt:['Additional funds / windfall','Expected receipt in CAD',1000,0],
  liquidity_hold:['Cash temporarily unavailable','Cash held or inaccessible (CAD)',1000,0],
  payment_delay_days:['Payment delay','Delay in days',7,0],
  investment_return:['Investment-value change','Change in percent (not assumed available cash)',-25,-100],
  unspecified_event:['Change with an unknown financial impact','Amount to confirm',null,null],
};
const oneTime=new Set(['one_off_cost','one_off_receipt']);
const input=(name,label,value='',attrs='')=>`<label>${e(label)}<input name="${name}" value="${e(value??'')}" ${attrs}></label>`;
const numeric=(name,label,value='',attrs='')=>input(name,label,value,`type="number" step=".01" ${attrs}`);
const check=(name,label,checked=false)=>`<label class="check"><input name="${name}" type="checkbox" ${checked?'checked':''}>${e(label)}</label>`;

export function effectFields(type) {
  const [,label,value,min]=effects[type],unknown=type==='unspecified_event';
  const recurring=!oneTime.has(type)&&!['unspecified_event','investment_return'].includes(type),immediate=oneTime.has(type)||type==='liquidity_hold';
  return `<div class="form-grid">${numeric('value',label,'',`${min!=null?`min="${min}"`:''} ${unknown?'disabled':'required'}`)}${input('start_month','First month affected (0 = now)',immediate?0:1,`type="number" min="${immediate?0:1}" max="120" step="1" required`)}<label>Information basis<select name="evidence">${Object.entries(sources).map(([k,v])=>`<option value="${k}" ${k===(unknown?'unknown':'assumed')?'selected':''}>${v}</option>`).join('')}</select></label>${!unknown?check('unknown','Amount is not yet known'):''}${recurring?`<label>How long will this continue?<select name="duration_mode"><option value="known">A known number of months</option><option value="ongoing">Ongoing, as supplied</option><option value="unknown" selected>Not yet known</option></select></label>${input('duration_months','Number of months','','type="number" min="1" max="120" step="1" required disabled')}`:''}</div><p class="help">Month 1 is the first month of this review. Use 0 for an immediate expense, receipt or cash hold. Add this change to include it in the review.</p>
    ${type==='debt_payment_delta'?`<details open><summary>Payment details and deferral terms</summary><p class="help">A reduction must be supported by the existing payment record. A deferred amount is still owed.</p><div class="form-grid">${numeric('obligation_payment','Supplied existing payment, if different from the record (CAD/month)','','min="0"')}${input('obligation_source','Source of the supplied payment','','maxlength="500" placeholder="Record or customer confirmation"')}${check('payment_in_baseline','Payment is already included in recorded spending')}<label>Nature of the change<select name="debt_change_kind"><option value="payment_change">Payment amount change</option><option value="deferral">Temporary deferral</option></select></label>${input('repayment_month','Repayment month (deferral only)','','type="number" min="1" max="240" step="1"')}${numeric('repayment_amount','Full repayment amount (deferral only)','','min="0"')}${check('repayment_unresolved','Deferred repayment terms are not confirmed')}</div></details>`:''}`;
}

function transferSection(draft) {
  const transfers=draft.context.existing_transfers||[];
  return `<details><summary>Existing savings payments to review (${transfers.length})</summary><p class="help">Record an existing payment only once. Pausing it affects cash only when its inclusion in spending, permission and fees are supported.</p>${transfers.length?`<ul class="effect-list">${transfers.map((t,i)=>`<li><div><strong>${e(t.event_id)} · ${e(money(t.amount))} in month ${t.month}</strong><small>${e(t.source)} · ${t.pause_approved?'Pause authority recorded':'Pause authority unconfirmed'} · Fee ${t.pause_fee==null?'to confirm':e(money(t.pause_fee))}</small></div><button data-action="remove-transfer" data-index="${i}" class="small ghost">Remove</button></li>`).join('')}</ul>`:''}<form id="transfer-form" data-entry="Scheduled payment"><div class="form-grid">${input('event_id','Payment reference','','required maxlength="100" placeholder="Unique reference for this payment"')}${input('month','Payment due in month',1,'type="number" min="1" max="120" step="1" required')}${numeric('amount','Scheduled amount (CAD)','','min=".01" required')}${input('source','Source of the payment details','','required maxlength="500"')}${numeric('pause_fee','Fee to pause this payment (CAD; blank if unknown)','','min="0"')}${check('included_in_baseline','This payment is included in recorded spending')}${check('pause_approved','Authority to pause this payment is confirmed')}</div><div class="actions"><button type="submit">Add payment record</button><button type="button" class="ghost" data-action="clear-entry" data-form="transfer-form">Clear entry</button></div></form></details>`;
}

function recoverySection(draft) {
  const r=draft.context.recovery_snapshot||{};
  return `<details><summary>Updated figures for a recovery review ${draft.context.recovery_snapshot?'· recorded':'(optional)'}</summary><p class="help">Use updated figures to assess rebuilding. These figures are a separate checkpoint; they are not assumed to follow automatically from the current cash projection. If inflow is unknown, leave it blank. A rebuild date then requires a supported monthly contribution, confirmed stability and covered obligations.</p><form id="recovery-form" data-entry="Recovery figures"><div class="form-grid">${input('assessment_month','Month of these figures',r.assessment_month,'type="month" required')}${input('source','Source of the updated figures',r.source,'required maxlength="500"')}<label>Basis of these figures<select name="cash_basis">${[['judge_specified','Supplied circumstances'],['observed','Observed figures'],['simulated','Illustrative future figures']].map(([k,v])=>`<option value="${k}" ${r.cash_basis===k?'selected':''}>${v}</option>`).join('')}</select></label>${numeric('available_cash','Accessible cash (CAD)',r.available_cash,'required')}${numeric('monthly_inflow','Recurring monthly inflow (CAD; blank if unknown)',r.monthly_inflow,'min="0"')}${numeric('monthly_spending','Recurring monthly spending (CAD)',r.monthly_spending,'min=".01" required')}${numeric('supported_monthly_contribution','Supported monthly rebuild amount (CAD; blank if unknown)',r.supported_monthly_contribution,'min="0"')}${numeric('earmarked_near_term_cash','Cash already needed for near-term commitments (CAD)',r.earmarked_near_term_cash??0,'min="0" required')}${check('stable_cash_flow','Stable recurring cash flow has been confirmed',r.stable_cash_flow)}${check('obligations_covered','Upcoming obligations are covered',r.obligations_covered)}</div><div class="actions"><button type="submit">Save recovery figures</button><button type="button" class="ghost" data-action="clear-entry" data-form="recovery-form">Discard edits</button>${draft.context.recovery_snapshot?'<button type="button" class="ghost" data-action="remove-recovery">Remove recorded figures</button>':''}</div></form></details>`;
}

function goalSection(draft) {
  const g=draft.context.normal_goal||{};
  return `<details><summary>Existing savings objective ${draft.context.normal_goal?'· recorded':'(optional)'}</summary><p class="help">Leave this empty to use the calculated reserve goal. Record a different goal only when its amount and purpose are established.</p><form id="goal-form" data-entry="Savings objective"><div class="form-grid">${input('name','Savings objective',g.name,'required maxlength="200"')}${numeric('monthly_contribution','Proposed monthly amount (CAD)',g.monthly_contribution,'min="0" required')}${numeric('reserve_target','Cash reserve target (CAD)',g.reserve_target,'min="0" required')}${numeric('reserve_months','Months of spending to keep in reserve',g.reserve_months??3,'min=".01" max="24" required')}<label>Where does the contribution go?<select name="kind"><option value="LIQUID_RESERVE_EARMARK" ${g.kind==='LIQUID_RESERVE_EARMARK'?'selected':''}>Stays in accessible cash reserves</option><option value="PROPOSED_TRANSFER" ${g.kind==='PROPOSED_TRANSFER'?'selected':''}>Leaves the account as a savings transfer</option></select></label>${input('source','Source of the agreed objective',g.source,'required maxlength="500"')}</div><div class="actions"><button type="submit">Save savings objective</button><button type="button" class="ghost" data-action="clear-entry" data-form="goal-form">Discard edits</button>${draft.context.normal_goal?'<button type="button" class="ghost" data-action="remove-goal">Use calculated reserve goal</button>':''}</div></form></details>`;
}

export function savingsReviewApplies(draft) {
  const {normal_goal, existing_transfers, recovery_snapshot}=draft.context;
  return draft.reviewDetails?.purpose==='savings' && draft.scenario.phase==='normal'
    && !recovery_snapshot && !existing_transfers?.length && !(normal_goal?.monthly_contribution>0);
}

function savingsEvidenceSection(draft) {
  if(!savingsReviewApplies(draft))return '';
  const s=draft.savingsEvidence?.account_id===draft.accountId?draft.savingsEvidence:{};
  const dateField=(key,label)=>input(key,label,s[key],'type="date" data-savings-field');
  const cashField=(key,label)=>numeric(key,label,s[key],'min="0" max="1000000000000" data-savings-field');
  return `<details ${draft.savingsEvidence?'open':''}><summary>Check for a one-time emergency savings set-aside</summary>
    <p class="help">Confirm today’s accessible cash and its source above. Use the same snapshot below. Exclude deposits still pending and money already set aside from unallocated cash. Include every unpaid commitment through the selected date. Enter $0 only when confirmed.</p>
    <div class="form-grid">
      ${dateField('as_of','Cash snapshot date')}${dateField('protect_through','Cover commitments through this date')}
      ${cashField('unallocated_cash','Cleared, unallocated cash (CAD)')}${cashField('unpaid_commitments','Unpaid commitments through that date (CAD)')}
      ${cashField('cash_cushion','Cash cushion to keep after commitments (CAD)')}${cashField('remaining_reserve_goal','Amount still needed for the reserve goal (CAD)')}
    </div></details>`;
}

export function basicValues(scenario) {
  if(scenario.phase==='recovery')return null;
  const result={income:100,bills:0,cost:0,receipt:0,months:scenario.horizon_months};
  const names={income_multiplier:'income',household_bills_percent:'bills',one_off_cost:'cost',one_off_receipt:'receipt'},seen=new Set();
  for(const f of scenario.effects){
    const key=names[f.type],once=['one_off_cost','one_off_receipt'].includes(f.type);
    if(!key||seen.has(key)||f.value==null||f.evidence==='unknown'||f.start_month!==(once?0:1)||(!once&&!f.ongoing&&f.duration_months!==scenario.horizon_months))return null;
    seen.add(key);result[key]=Math.round(f.value*(key==='income'?100:1)*1e6)/1e6;
  }
  return scenario.phase==='active'&&!scenario.effects.length?null:result;
}

export function basicScenario(values,previous) {
  const v={};
  for(const name of ['income','bills','cost','receipt','months']){
    if(values[name]==null||String(values[name]).trim()===''||!Number.isFinite(Number(values[name])))throw new Error('Complete the basic shock amounts and plan period. Use zero for no change.');
    v[name]=Number(values[name]);
  }
  if(v.income<0||v.income>1000||v.bills< -100||v.bills>10000||v.cost<0||v.receipt<0||v.cost>1e12||v.receipt>1e12||!Number.isInteger(v.months)||v.months<1||v.months>120)throw new Error('Check the shock amounts and choose a whole plan period from 1 to 120 months.');
  const changes=[];
  for(const [type,value,neutral] of [['income_multiplier',v.income/100,1],['household_bills_percent',v.bills,0],['one_off_cost',v.cost,0],['one_off_receipt',v.receipt,0]]){
    if(value===neutral)continue;
    const once=['one_off_cost','one_off_receipt'].includes(type),old=previous.effects.find(f=>f.type===type);
    changes.push({type,value,start_month:once?0:1,evidence:'user_confirmed',...(once?{}:old?.ongoing?{ongoing:true}:{duration_months:v.months})});
  }
  return {phase:changes.length?'active':'normal',horizon_months:v.months,description:previous.description||'',effects:changes};
}

export function intakeState(draft) {
  if(!draft.intake)draft.intake={text:draft.scenario.description||'',handledText:draft.scenario.description||'',mode:draft.scenario.description?'note':'none'};
  return draft.intake;
}
export const descriptionPending=draft=>{const i=intakeState(draft);return i.text.trim()!==i.handledText.trim();};

export function shockSummaryView(draft) {
  const s=draft.scenario,i=intakeState(draft),read=['gemini','local'].includes(i.mode);
  const list=s.effects.length?`<ul class="review-list">${s.effects.map(f=>{const a=effectSummary(f);return `<li><strong>${e(a.name)}: ${e(a.amount)}</strong> · ${e(a.timing)}</li>`;}).join('')}</ul>`:'<p>No new shock. The plans use the customer’s normal circumstances.</p>';
  return `<h3>${read?'What we understood':'Shock included in the plan'}</h3>${list}
    ${read?`<p class="help">Read from your description${i.mode==='local'?' (offline reader)':''}. Plan period: ${s.horizon_months} months.</p>`:i.mode==='edited'?'<p class="help">You adjusted the settings after reading the description. Plans use the settings shown here.</p>':i.mode==='note'&&i.text.trim()?'<p class="help">The description is kept as a note. The settings shown here determine the plan.</p>':''}
    ${(i.assumptions||[]).length?`<p class="help"><strong>Defaults used:</strong></p><ul class="review-list">${i.assumptions.map(a=>`<li>${e(a)}</li>`).join('')}</ul>`:''}
    ${(i.questions||[]).length?notice('Amount still unknown: '+i.questions.join(' ')+' The plans show known amounts only until it is added.','warn'):''}`;
}

function advancedOptions(draft,customer) {
  const s=draft.scenario,details=draft.reviewDetails||{},unfinished=Object.keys(draft.formDrafts||{}).length;
  return `<details id="additional-details" ${unfinished?'open':''}><summary>More details (optional)</summary><p class="help">Use these only when the customer supplies extra information. Otherwise the plans use their recorded finances and the shock above.</p>
    <div class="form-grid two">${numeric('opening_cash','Current accessible cash (CAD; leave blank to use records)',draft.context.opening_cash,'id="opening-cash"')}${input('cash_source','Source and date of this cash figure',details.cash_source,'id="cash-source" maxlength="500"')}</div>
    ${transferSection(draft)}${goalSection(draft)}${recoverySection(draft)}
    <details ${draft.formDrafts?.['effect-form']?'open':''}><summary>Individual changes and special timing</summary><div class="form-grid">${input('horizon','Plan period (months)',s.horizon_months,'id="scenario-horizon" type="number" min="1" max="120" step="1" required')}<label>Customer circumstances<select id="scenario-phase">${[['normal','No new shock'],['active','A shock is happening'],['recovery','Rebuilding after a disruption']].map(([k,v])=>`<option value="${k}" ${s.phase===k?'selected':''}>${v}</option>`).join('')}</select></label></div>
    ${s.effects.length?`<ul class="effect-list">${s.effects.map((f,index)=>{const a=effectSummary(f);return `<li><div><strong>${e(a.name)} · ${e(a.amount)}</strong><small>${e(a.timing)}</small></div><div class="actions"><button class="small" data-action="edit-effect" data-index="${index}">Edit</button><button class="small ghost" data-action="remove-effect" data-index="${index}">Remove</button></div></li>`;}).join('')}</ul>`:''}
    <details id="add-effect-details" ${draft.formDrafts?.['effect-form']?'open':''}><summary>${draft.editingEffect!=null?'Edit this change':'Add another change'}</summary><form id="effect-form" data-entry="Customer circumstance"><label>What is changing?<select id="effect-type" name="type">${Object.entries(effects).map(([k,v])=>`<option value="${k}">${e(v[0])}</option>`).join('')}</select></label><div id="effect-fields">${effectFields('income_multiplier')}</div><div class="actions"><button type="submit">Save change</button><button type="button" class="ghost" data-action="clear-entry" data-form="effect-form">Discard entry</button></div></form></details></details>
    <details><summary>Review title and staff notes</summary><div class="form-grid">${input('title','Plan title',draft.title,'id="scenario-title" maxlength="120"')}<label>Purpose<select id="review-purpose">${Object.entries(purposes).map(([k,v])=>`<option value="${k}" ${details.purpose===k?'selected':''}>${v}</option>`).join('')}</select></label>${input('prepared_by','Prepared by',details.prepared_by,'id="prepared-by" maxlength="120"')}<label class="span-all">Customer priority<textarea id="customer-priority" rows="2" maxlength="2000">${e(details.customer_priority||'')}</textarea></label></div></details></details>`;
}

const examples=['Lost their job','Rent going up $300 a month','$2,000 car repair now','Lost job and bills up 15%','Income down 30% for 4 months','$5,000 bonus in 2 months'];

export function scenarioView(draft,customer,config,preview=null) {
  const i=intakeState(draft),basic=draft.basicDraft||basicValues(draft.scenario),pending=descriptionPending(draft);
  const accountForm=`<form id="plan-account" class="toolbar"><label>Account number<input name="account_id" type="number" min="1" step="1" required value="${e(draft.accountId||'')}" placeholder="e.g. 20111"></label><button type="submit">${customer?'Change account':'Select account'}</button><a href="#customers">Browse customers</a></form>`;
  if(!customer)return heading('Customer plans','Select an account.','Pick the customer, describe what happened, and get their main and backup plans.')+`<section class="card"><h2>1. Customer</h2>${accountForm}</section>`;
  const extras=[draft.context.opening_cash!=null?'supplied cash balance':null,draft.context.normal_goal?'supplied savings goal':null,draft.context.recovery_snapshot?'recovery figures':null,draft.context.existing_transfers?.length?`${draft.context.existing_transfers.length} scheduled payments`:null].filter(Boolean);
  const showSummary=!pending&&(['gemini','local','edited','note'].includes(i.mode)||draft.scenario.effects.length);
  return heading('Customer plans',`Plans for account ${customer.account_id}`,'Describe what happened in plain words. Everything else comes from the customer’s records.',`<a class="button ghost" href="#customer/${customer.account_id}">Customer overview</a>`)+
    `<section class="card"><div class="card-head"><h2>1. Customer</h2><span class="badge">Recorded monthly inflow ${e(money(customer.metrics.I))}</span></div>${accountForm}<p class="help">Income, spending, bills, loan payments and starting cash (${e(money(customer.metrics.B))}, historical estimate) come from the records automatically.${extras.length?` Additional information included: ${e(extras.join(', '))}.`:''}</p></section>
    <section class="card"><h2>2. What happened?</h2>
    <label class="sr-only" for="shock-description">Describe the shock</label><textarea id="shock-description" maxlength="2000" rows="4" placeholder="e.g. Lost their job and rent is going up $300 a month">${e(i.text)}</textarea>
    <div class="presets">${examples.map(t=>`<button class="small ghost" data-action="example" data-text="${e(t)}">${e(t)}</button>`).join('')}</div>
    <p class="help">Plain words are fine. Missing details use standard defaults: a job loss means income falls to 55% (Employment Insurance), “bills going up” means +15%, and changes last the plan period (6 months). Leave it empty for a plan with no shock.</p>
    <div id="description-status">${pending&&i.text.trim()?'<p class="help">Your description will be read when you generate the plans.</p>':''}</div>
    <div id="shock-summary">${showSummary?shockSummaryView(draft):''}</div></section>
    <section class="card"><h2>3. Get the plans</h2><div class="actions"><button class="primary" data-action="run">Generate main &amp; backup plans →</button></div><p class="help">The main plan covers normal conditions. The backup plan shows what to do if this shock happens.</p></section>
    ${draft.rawScenario!=null||draft.rawContext!=null?notice('An older unfinished entry is not included. Download it or discard it before continuing.','warn')+'<div class="actions"><button data-action="legacy-backup">Download unfinished entry</button><button data-action="discard-legacy">Discard unfinished entry</button></div>':''}
    <details class="card" ${draft.formDrafts&&Object.keys(draft.formDrafts).length?'open':''}><summary>Adjust the shock (optional)</summary>
    <div class="actions"><button data-action="interpret">Check what we understood</button><button data-action="description-note" class="ghost">Keep text as a note only</button><button class="ghost" data-action="preview">Preview cash impact</button></div>
    <p class="help">Start from an example or set the basic amounts directly. These replace what was read from the description.</p>
    <div class="presets">${[['normal','No new shock'],['layoff','Income drops'],['bills','Bills rise'],['repair','Unexpected expense'],['combined','Income + bills'],['windfall','Extra money']].map(([id,t])=>`<button data-action="preset" data-preset="${id}" class="small">${t}</button>`).join('')}</div>
    ${basic?`<form id="basic-shock"><div class="form-grid">${numeric('income','Income remaining (% of usual)',basic.income,'min="0" max="1000" required data-basic')}${numeric('bills','Household bills change (%)',basic.bills,'min="-100" max="10000" required data-basic')}${numeric('cost','One-time expense now (CAD)',basic.cost,'min="0" max="1000000000000" required data-basic')}${numeric('receipt','Extra money now (CAD)',basic.receipt,'min="0" max="1000000000000" required data-basic')}${input('months','Plan period (months)',basic.months,'type="number" min="1" max="120" step="1" required data-basic')}</div><p class="help">100% means income is unchanged; 55% means 55% remains. Use zero for no expense or extra money.</p></form>`:'<p class="help">This shock has specific timing; edit it under “More details” below.</p>'}
    ${advancedOptions(draft,customer)}${savingsEvidenceSection(draft)}</details>
    <div id="preview-slot">${preview?previewView(preview):''}</div>`;
}

export function effectFromForm(form,accountId) {
  const d=new FormData(form),type=d.get('type'),unknown=type==='unspecified_event'||d.has('unknown');
  if(!unknown&&!String(d.get('value')??'').trim()) throw new Error('Enter an amount or mark it as unknown.');
  const value=unknown?null:Number(d.get('value'))/(type==='income_multiplier'?100:1);
  const result={type,value,start_month:Number(d.get('start_month')),evidence:d.get('evidence'),effect_id:crypto.randomUUID()};
  if(!oneTime.has(type)&&!['unspecified_event','investment_return'].includes(type)) {result.ongoing=d.get('duration_mode')==='ongoing';result.duration_months=d.get('duration_mode')==='known'?Number(d.get('duration_months')):null;}
  if(type==='debt_payment_delta') {
    if(d.get('obligation_payment')!=='') {result.obligation_account_id=accountId;result.obligation_payment=Number(d.get('obligation_payment'));result.obligation_source=String(d.get('obligation_source')||'').trim()||null;result.payment_in_baseline=d.has('payment_in_baseline');}
    result.debt_change_kind=d.get('debt_change_kind');
    if(result.debt_change_kind==='deferral') {result.repayment_unresolved=d.has('repayment_unresolved');if(d.get('repayment_month')!=='')result.repayment_month=Number(d.get('repayment_month'));if(d.get('repayment_amount')!=='')result.repayment_amount=Number(d.get('repayment_amount'));}
  }
  return result;
}

export function contextFromForm(form,accountId) {
  const d=new FormData(form),num=k=>d.get(k)===''?null:Number(d.get(k)),text=k=>String(d.get(k)||'').trim();
  if(form.id==='transfer-form') return {event_id:text('event_id'),account_id:accountId,month:num('month'),amount:num('amount'),source:text('source'),included_in_baseline:d.has('included_in_baseline'),pause_approved:d.has('pause_approved'),pause_fee:num('pause_fee')};
  if(form.id==='recovery-form') return {account_id:accountId,assessment_month:text('assessment_month'),source:text('source'),cash_basis:text('cash_basis'),available_cash:num('available_cash'),monthly_inflow:num('monthly_inflow'),monthly_spending:num('monthly_spending'),supported_monthly_contribution:num('supported_monthly_contribution'),earmarked_near_term_cash:num('earmarked_near_term_cash'),stable_cash_flow:d.has('stable_cash_flow'),obligations_covered:d.has('obligations_covered')};
  return {name:text('name'),monthly_contribution:num('monthly_contribution'),reserve_target:num('reserve_target'),reserve_months:num('reserve_months'),kind:text('kind'),source:text('source')};
}

export function preset(name,customer) {
  const income={type:'income_multiplier',value:.55,start_month:1,duration_months:6,evidence:'judge_specified'},cost=customer.profile.baseline.S;
  const all={normal:[],layoff:[income],bills:[{type:'household_bills_percent',value:15,start_month:1,duration_months:6,evidence:'judge_specified'}],repair:[{type:'one_off_cost',value:cost,start_month:0,evidence:'judge_specified'}],combined:[income,{type:'household_bills_percent',value:15,start_month:1,ongoing:true,evidence:'judge_specified'}],raise:[{type:'income_multiplier',value:1.15,start_month:1,ongoing:true,evidence:'judge_specified'}],windfall:[{type:'one_off_receipt',value:cost,start_month:0,evidence:'judge_specified'}]};
  return {phase:name==='normal'?'normal':'active',horizon_months:6,description:'',effects:all[name]};
}

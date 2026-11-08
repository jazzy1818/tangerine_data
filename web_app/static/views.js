import {escapeHtml as e, money, number, percent, badge, metric, notice, table} from './common.js';
import {lineChart, barChart, cashPathChart} from './charts.js';
import {reviewStatuses, plainNote, shortfall} from './financial.js';

export function heading(step,title,description,actions='') {
  return `<div class="page-head"><div><div class="eyebrow">${e(step)}</div><h1>${e(title)}</h1><p>${e(description)}</p></div><div class="actions no-print">${actions}</div></div>`;
}
export const noteList = items => `<ul class="review-list">${items.map(i=>`<li>${e(plainNote(i))}</li>`).join('')}</ul>`;
export const reviewStatus = r => r.status==='running'?badge('Preparing assessment'):r.status==='failed'?badge('Needs attention','warn'):badge(reviewStatuses[r.review?.status]||'In progress',r.review?.status==='awaiting_information'?'warn':r.review?.status==='ready_to_discuss'?'success':'');
export const overdue = r => {
  const d=new Date(), today=`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  return r.review?.follow_up_date && r.review?.status!=='closed' && r.review.follow_up_date<today;
};

export function homeView(items,draft,showGuide=true) {
  const active=items.filter(r=>r.status==='complete'&&r.review?.status!=='closed');
  const followups=active.filter(r=>r.review?.follow_up_date).sort((a,b)=>a.review.follow_up_date.localeCompare(b.review.follow_up_date));
  return heading('Customer support','Your customer reviews.','Prepare for the conversation, assess a change in circumstances, and keep the next step clear.','<a class="button primary" href="#customers">Start a customer review →</a>')+
    `<div class="metric-grid">${metric('Open reviews',number(active.length))}${metric('Awaiting information',number(active.filter(r=>r.review?.status==='awaiting_information').length))}${metric('Follow-ups scheduled',number(followups.length))}${metric('Overdue follow-ups',number(followups.filter(overdue).length))}</div>
    ${showGuide?`<section class="card onboarding"><div class="card-head"><h2>A simple review from start to finish</h2><button class="small ghost" data-action="hide-guide">Hide guide</button></div><div class="grid-3"><div><span class="step-number">1</span><h3>Understand the customer</h3><p>Find the account. Review regular inflows, spending, cash reserves and existing payment pressure.</p></div><div><span class="step-number">2</span><h3>Record what is changing</h3><p>Enter the amounts and dates the customer provides. Keep estimates and missing information visible.</p></div><div><span class="step-number">3</span><h3>Agree the next step</h3><p>Review the funding gap and goal impact. Record your discussion, outstanding information and follow-up date.</p></div></div></section>`:'<button class="small ghost no-print" data-action="show-guide">Show getting-started guide</button>'}
    ${draft.accountId?`<section class="card resume-card"><div><h3>Continue reviewing account ${e(draft.accountId)}</h3><p class="help">${e(draft.title||'Draft customer review')}</p></div><a class="button" href="#scenario">Continue draft →</a></section>`:''}
    <div class="grid-2"><section class="card"><h2>Follow-up diary</h2>${followups.length?table(['Customer review','Due','Owner'],followups.slice(0,8).map(r=>[`<a href="#run/${e(r.id)}">${e(r.title)}</a><div class="help">Account ${r.account_id}</div>`,`${e(r.review.follow_up_date)} ${overdue(r)?badge('Overdue','warn'):''}`,e(r.review.owner||'Unassigned')])):'<p class="help">No follow-ups scheduled. Set a date when you record the outcome of a customer review.</p>'}</section><section class="card"><h2>Recent reviews</h2>${items.length?table(['Customer review','Progress'],items.slice(0,6).map(r=>[`<a href="#run/${e(r.id)}">${e(r.title)}</a><div class="help">Account ${r.account_id}</div>`,reviewStatus(r)])):'<p class="help">Your first saved assessment will appear here.</p>'}<a href="#history">View review history →</a></section></div><p class="section-caption">Worklist counts cover the latest 100 assessments saved in this workspace. Confirm current customer circumstances during the review.</p>`;
}

export function discoveryView(data) {
  const p=data.provenance,w=data.worklist,group=data.cohorts.find(c=>c.id===w.cohort);
  const evidence=r=>w.cohort==='recurring_shortfalls'?`${r.deficit_months} shortfall months out of 12`:w.cohort==='thin_reserves'?`${number(r.reserve_months)} months of reserves`:w.cohort==='payment_timing'?`${r.recovered_months} month(s) recovered after overdraft`:'Under 6 months of cover at 55% inflow';
  return heading('Portfolio insights','Understand the patterns behind customer needs.','Use these observations to guide questions about affordability and cash reserves. They are historical patterns, not individual risk ratings.','<a class="button primary" href="#customers">Find a customer →</a>')+
    `<section class="card"><div class="card-head"><div>${badge(p.label)} <span class="help">${e(p.status)}</span></div><button class="small" data-action="portfolio-refresh">Refresh insights</button></div><p class="help">Retrieved ${e(new Date(p.queried_at).toLocaleString())}. Records through ${e(data.period_end)}; this is historical data.</p></section>
    <section aria-label="Choose a customer group"><h2>Where could a customer conversation help?</h2><p class="help">Choose a group, review the recorded evidence, then open a customer overview. A customer may appear in more than one group.</p><div class="grid-2">${data.cohorts.map(c=>`<article class="card"><div class="card-head"><h3>${e(c.title)}</h3>${c.id===w.cohort?badge('Selected'):''}</div><div class="finding-number">${number(c.count)}</div><p>${e(c.description)}</p><p class="help">Of ${number(c.denominator)} eligible accounts.</p><a class="button ${c.id===w.cohort?'primary':''}" href="#discovery/${e(c.id)}" ${c.id===w.cohort?'aria-current="page"':''}>View customers →</a></article>`).join('')}</div></section>
    <section class="card"><h2>${e(group.title)}</h2><p>${e(group.prompt)}</p><p class="help">${number(w.total)} accounts. Showing ${w.items.length?w.offset+1:0}–${w.offset+w.items.length}. Ordered by shortfall months, then reserve coverage and account number.</p>
    ${w.items.length?table(['Account','Reason to review','Monthly surplus / gap','Cash reserve coverage','History through',''],w.items.map(r=>[`<a href="#customer/${r.account_id}">${r.account_id}</a>${r.loan_in_arrears?'<div class="help">Loan arrears recorded</div>':''}`,`${e(evidence(r))}<div class="help">${r.recent_months} of 12 recent months available</div>`,e(money(r.surplus)),r.reserve_months==null?'Not established':`${e(number(r.reserve_months))} months`,e(r.last_month),`<a class="button small" href="#customer/${r.account_id}">Review customer →</a>`])):'<p>No accounts meet this group’s criteria.</p>'}
    <div class="actions end"><button class="small" data-action="portfolio-page" data-cohort="${e(w.cohort)}" data-offset="${Math.max(0,w.offset-w.limit)}" ${w.offset===0?'disabled':''}>Previous</button><button class="small" data-action="portfolio-page" data-cohort="${e(w.cohort)}" data-offset="${w.offset+w.limit}" ${w.offset+w.items.length>=w.total?'disabled':''}>Next</button></div></section>
    <h2>Portfolio context</h2>
    <div class="metric-grid">${metric('Accounts',number(data.accounts))}${metric('Active loans',number(data.active_loans))}${metric('Records through',data.period_end)}</div>
    <div class="grid-3">${data.findings.map(f=>`<article class="card finding"><h3>${e(f.title)}</h3><div class="finding-number">${f.denominator?e(percent(f.numerator/f.denominator)):'Not established'}</div><p>${e(f.description)}</p><span class="badge">${e(number(f.numerator))} of ${e(number(f.denominator))}</span></article>`).join('')}</div>
    <div class="grid-2"><section class="card">${barChart(data.reserve_distribution,'Cash reserves relative to monthly spending')}<p class="help">Historical average balance divided by typical spending. Coverage is unavailable for ${number(data.reserve_undefined)} accounts.</p></section><section class="card"><h2>Questions for the customer conversation</h2>${noteList(['How much cash is accessible today?', 'Are regular payments concentrated before the next income date?', 'Are there upcoming costs or changes in income that are absent from the account history?', 'What does the customer most want to protect or achieve?'])}<a class="button" href="#customers">Open a customer review →</a></section></div>
    <section class="card">${lineChart(data.monthly_trend,[{key:'total_inflow',name:'Money in'},{key:'total_spending',name:'Money out'}],'month','Aggregate monthly cash flow')}<p class="help">${e(data.recent_start)} to ${e(data.period_end)}. Totals reflect accounts with records in each month.</p></section><details><summary>Observation period and interpretation</summary><p>Records from ${e(data.period_start)} to ${e(data.period_end)}.</p>${noteList(data.limitations.filter(s=>!s.includes('labelled best-plan')))}</details>`;
}

export function accountListView(data,query='',filter='all') {
  const options={all:'All customers',surplus:'Regular surplus',shortfall:'Regular cash shortfall',arrears:'Recorded loan arrears',no_loan:'No active loan'};
  return heading('Customer lookup','Find the customer.','Search by account number, or filter the accounts by their recorded financial circumstances.')+
    `<section class="card"><form id="account-search" class="toolbar"><label>Account number<input name="q" type="search" inputmode="numeric" value="${e(query)}" placeholder="Enter account number"></label><label>Financial circumstances<select name="filter">${Object.entries(options).map(([k,v])=>`<option value="${k}" ${filter===k?'selected':''}>${v}</option>`).join('')}</select></label><button type="submit" class="primary">Find customer</button></form>
    <p class="help">${number(data.total)} matching accounts. Showing ${data.total?data.offset+1:0}–${data.offset+data.items.length}.</p>
    ${data.items.length?table(['Account','Monthly inflow','Monthly spending','Monthly surplus / gap','Cash reserve coverage','Loan position',''],data.items.map(r=>[
      `<a class="route-link" href="#customer/${r.account_id}">${r.account_id}</a>`,e(money(r.money_in)),e(money(r.money_out)),e(money(r.surplus)),`${e(number(r.reserve_months))} months`,badge(r.loan_in_arrears?'Arrears recorded':r.active_loan?'Active loan':'No active loan',r.loan_in_arrears?'warn':''),`<a class="button small" href="#customer/${r.account_id}">Review customer →</a>`])):'<p>No matching accounts. Check the number or change the filter.</p>'}
    <div class="actions end"><button class="small" data-action="accounts-page" data-offset="${Math.max(0,data.offset-30)}" ${data.offset===0?'disabled':''}>Previous</button><button class="small" data-action="accounts-page" data-offset="${data.offset+30}" ${data.offset+data.items.length>=data.total?'disabled':''}>Next</button></div></section>`;
}

export function customerView(c,months=12) {
  const m=c.metrics,f=c.profile.features,history=months===0?c.history:c.history.slice(-months),issues=[];
  if(f.loan_in_arrears) issues.push('Loan arrears are recorded. Confirm the current position and upcoming payment dates.');
  if(m.S>m.I) issues.push(`Typical monthly spending exceeds inflow by ${money(m.S-m.I)}. Explore how the customer is covering the difference.`);
  if(f.negative_balance_month_share>0) issues.push('Negative-balance days appear in the recent history. Ask about income and bill timing.');
  issues.push('Confirm current accessible cash and any upcoming commitments before relying on a projection.');
  return heading('Customer overview',`Account ${c.account_id}`,`Prepare the customer conversation using records through ${c.profile.as_of}.`,'<a class="button ghost" href="#customers">Find another customer</a><a class="button primary" href="#scenario">Assess a change →</a>')+
    `<div class="metric-grid">${metric('Typical monthly inflow',money(m.I),'Bank credits; confirm income sources')}${metric('Typical monthly spending',money(m.S))}${metric('Monthly surplus / gap',money(m.I-m.S))}${metric('Historical cash estimate',money(m.B),'Average of the last six monthly balances')}</div>
    <div class="grid-2"><section class="card"><h2>Points for the conversation</h2>${noteList(issues)}</section><section class="card"><h2>Regular commitments and reserves</h2>${table(['Measure','Recorded amount'],[['Fixed costs',e(money(m.F))],['Household bills',e(money(m.H))],['Active loan payment',e(money(m.P))],['Loan position',e(c.loan_status||'No recorded loan')],['Cash reserves / typical spending',`${e(number(f.reserve_months))} months`]])}</section></div>
    <section class="card"><div class="card-head"><h2>Income, spending and balances</h2><label>History shown<select id="history-window">${[[6,'Last 6 observations'],[12,'Last 12 observations'],[24,'Last 24 observations'],[0,'All available history']].map(([v,t])=>`<option value="${v}" ${months===v?'selected':''}>${t}</option>`).join('')}</select></label></div>${lineChart(history,[{key:'money_in',name:'Money in'},{key:'money_out',name:'Money out'}],'month','Monthly cash flow')}${lineChart(history,[{key:'month_end_balance',name:'Month-end balance'},{key:'avg_daily_balance',name:'Average daily balance'}],'month','Balance history')}</section>
    <section class="card"><h2>How often has cash flow been under pressure?</h2><div class="metric-grid">${metric('Months spending exceeded inflow',percent(f.deficit_month_share),'Share of available recent months')}${metric('Months with a negative balance',percent(f.negative_balance_month_share),'At least one negative-balance day')}${metric('Recent months available',`${f.recent_months} / 12`)}</div><p class="help">Historical experience does not establish current affordability. Confirm income, commitments and accessible balances with the customer.</p>${f.quality_flags.length?notice(f.quality_flags.map(x=>x.replaceAll('_',' ')).join('; '),'warn'):''}</section>`;
}

export function savingsReviewCard(result) {
  if(!result)return '';
  const title='<h2>One-time emergency savings review</h2>';
  if(result.status==='needs_evidence'){
    return `<section class="card">${title}<p>Confirm these details before estimating an amount.</p>${noteList(result.outstanding)}</section>`;
  }
  const room=result.room_after_commitments_and_cushion;
  const messages={
    available:`Up to ${money(result.amount)} could be marked for emergency savings.`,
    no_room:room<0?`$0 available. Cash is ${money(-room)} short of covering commitments and the cushion.`:'$0 available after commitments and the cushion.',
    goal_met:'Emergency savings goal met.',
  };
  return `<section class="card">${title}<h3>${e(messages[result.status])}</h3>
    <p>Confirmed cash as of ${e(result.as_of)} with commitments protected through ${e(result.protect_through)}.</p>
    ${table(['Calculation','CAD'],[
      ['Cleared, unallocated cash',e(money(result.unallocated_cash))],
      ['Less unpaid commitments',e(money(result.unpaid_commitments))],
      ['Less the cash cushion',e(money(result.cash_cushion))],
      ['Room after commitments and cushion',e(money(room))],
      ['Remaining reserve goal from the supplied snapshot',e(money(result.remaining_reserve_goal))],
    ])}<p class="help">The set-aside stays liquid. Recheck the figures when cash or commitments change, including after a deposit clears.</p></section>`;
}

export function previewView(p) {
  const path=p.projection;
  return `<section class="card" id="preview-card"><div class="card-head"><h2>How do the changes affect cash?</h2>${badge('Before any proposed action')}</div><div class="metric-grid">${metric('First projected shortfall',shortfall(path))}${metric('Additional cash needed',money(path.full_funding_need),path.funding_result_complete?'Across the review period':'Known-amount estimate: '+money(path.additional_cash_needed))}${metric('Cash at the end of the period',money(path.ending_cash),path.funding_result_complete?'Based on the supplied assumptions':'Known amounts only')}</div>${!path.funding_result_complete?notice('Some amounts or dates are still unknown. Confirm them before drawing a complete funding conclusion.','warn'):''}${p.notes.filter(s=>!s.includes('description is context')).map(s=>notice(plainNote(s),'warn')).join('')}${cashPathChart([{key:'no_action',name:'Without additional action',path}])}<p class="help">Month 1 is the first month of the review. Monthly balances do not confirm that every payment can be met on its due date.</p><details><summary>Information to confirm and assumptions</summary>${noteList([...p.case.missing_details,...path.review_flags])}</details></section>`+savingsReviewCard(p.flexible_savings);
}

export function settingsView(config,backend) {
  return heading('Assessment preferences','Choose the assessment approach.','This choice applies to new assessments. Saved customer reviews keep the approach originally used.')+
    `<section class="card narrow"><label>Assessment approach<select id="backend">${Object.entries(config.providers).map(([k,p])=>`<option value="${k}" ${backend===k?'selected':''}>${k==='rules'?'Standard rules-based assessment':k==='jev'?'Jev-assisted assessment':'Gemini-assisted assessment'}${p.configured?'':' — unavailable'}</option>`).join('')}</select></label><p class="help">Assessments are prepared only when you select “Prepare customer review”. If assisted assessment is unavailable, a standard assessment is clearly identified in the result.</p>${!config.providers[backend]?.configured?notice('This approach is not available. Ask the workspace administrator to configure access, or choose the standard assessment.','warn'):''}<a class="button primary" href="#scenario">Return to customer review →</a></section>`;
}

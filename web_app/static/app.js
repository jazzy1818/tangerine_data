import {api,escapeHtml as e,notice,notify,download,downloadFile,blankDraft,readDraft,saveDraft} from './common.js';
import {homeView,discoveryView,accountListView,customerView,previewView,settingsView} from './views.js';
import {runView,projectionChart,historyView,compareView} from './reviews.js';
import {scenarioView,effectFields,effectFromForm,contextFromForm,preset} from './scenario.js';
import {reviewBrief,plainNote} from './financial.js';

const main=document.getElementById('main');
const readLocal=(key,fallback)=>{try{return JSON.parse(localStorage.getItem(key))??fallback;}catch{return fallback;}};
const writeLocal=(key,value)=>{try{localStorage.setItem(key,JSON.stringify(value));}catch{}};
const state={config:null,draft:readDraft(),customer:null,preview:null,run:null,query:'',filter:'all',offset:0,
  historyMonths:12,reviewFilter:'all',routeVersion:0,busy:false,poll:null,
  showGuide:readLocal('tangerine-guide-visible',true),reviewDrafts:readLocal('tangerine-review-notes',{}),
  customerDrafts:readLocal('tangerine-customer-drafts',{})};
const route=()=>location.hash.slice(1)||'workspace';
const entryNames={'effect-form':'customer circumstance','transfer-form':'scheduled payment','goal-form':'savings objective','recovery-form':'recovery figures'};

function sidebar() {
  const page=route().split('/')[0],active=page==='customer'?'customers':['run','compare'].includes(page)?'history':page;
  document.querySelectorAll('[data-nav]').forEach(a=>{const match=a.dataset.nav===active;a.classList.toggle('active',match);if(match)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
  document.getElementById('selected-customer').innerHTML=state.draft.accountId?`CURRENT CUSTOMER<a href="#customer/${e(state.draft.accountId)}">Account ${e(state.draft.accountId)}</a>Review draft saved.`:'Find a customer to start a review.';
}
function persist(){
  saveDraft(state.draft);
  if(state.draft.accountId){state.customerDrafts[state.draft.accountId]=structuredClone(state.draft);writeLocal('tangerine-customer-drafts',state.customerDrafts);}
  sidebar();
}
function invalidate(){state.preview=null;const slot=document.getElementById('preview-slot');if(slot?.innerHTML)slot.innerHTML=notice('The review has changed. Check the financial impact again to see the updated figures.');persist();}
function financialInput(){return {...state.draft.context,account_id:state.draft.accountId,scenario:state.draft.scenario};}
function currentInput(){
  if(!state.draft.accountId)throw new Error('Find the customer first.');
  if(state.draft.rawScenario!=null||state.draft.rawContext!=null)throw new Error('Resolve the unfinished entry from the previous editor before continuing.');
  const pending=Object.keys(state.draft.formDrafts||{});
  if(pending.length)throw new Error(`Save or discard the unfinished ${pending.map(id=>entryNames[id]).join(', ')} before continuing.`);
  if(state.draft.context.opening_cash!=null&&!(state.draft.reviewDetails.cash_source||'').trim())throw new Error('Record the source and date of the supplied cash figure.');
  return financialInput();
}
function capture(form){
  const data={};
  for(const field of form.querySelectorAll('[name]')){
    if(field.name==='completed_items')data.completed_items=[...form.querySelectorAll('[name="completed_items"]:checked')].map(x=>x.value);
    else data[field.name]=field.type==='checkbox'?field.checked:field.value;
  }
  return data;
}
function restore(form,values){
  if(!form)return;
  if(form.id==='effect-form'&&values.type){document.getElementById('effect-fields').innerHTML=effectFields(values.type);}
  for(const field of form.querySelectorAll('[name]')){
    if(!(field.name in values))continue;
    if(field.type==='checkbox')field.checked=field.name==='completed_items'?(values.completed_items||[]).includes(field.value):Boolean(values[field.name]);
    else field.value=values[field.name]??'';
  }
  if(form.id==='effect-form')syncEffectFields();
  if(form.closest('details'))form.closest('details').open=true;
}
function syncEffectFields(){
  const form=document.getElementById('effect-form');if(!form)return;
  const value=form.elements.namedItem('value'),unknown=form.elements.namedItem('unknown');
  if(value&&unknown)value.disabled=unknown.checked;
  const duration=form.elements.namedItem('duration_months'),mode=form.elements.namedItem('duration_mode');
  if(duration&&mode)duration.disabled=mode.value!=='known';
}
function restoreEdits(){
  for(const [id,values] of Object.entries(state.draft.formDrafts||{}))restore(document.getElementById(id),values);
  if(route().startsWith('run/')&&state.run){const notes=state.reviewDrafts[state.run.id];if(notes){restore(document.getElementById('review-form'),notes);const status=document.getElementById('review-save-status');if(status)status.textContent='Unsaved notes restored — save to update this review.';}}
}

async function render({quiet=false,refreshPortfolio=false}={}){
  const version=++state.routeVersion;clearTimeout(state.poll);sidebar();
  if(!quiet)main.innerHTML='<div class="loading">Opening the workspace…</div>';
  try{
    if(!state.config)state.config=await api('/config');
    if(version!==state.routeVersion)return;
    if(!state.config.providers[state.draft.backend]){state.draft.backend=state.config.default_backend;persist();}
    const [page,id,second]=route().split('/');let html;
    if(page==='workspace')html=homeView((await api('/runs')).items,state.draft,state.showGuide);
    else if(page==='discovery'){
      const params=new URLSearchParams({cohort:id||'recurring_shortfalls',offset:second||0,refresh:refreshPortfolio});
      const data=await api(`/discovery?${params}`);if(version!==state.routeVersion)return;
      html=discoveryView(data);
    }
    else if(page==='customers'){const params=new URLSearchParams({q:state.query,filter:state.filter,offset:state.offset});html=accountListView(await api(`/accounts?${params}`),state.query,state.filter);}
    else if(page==='customer'){
      const customer=await api(`/customers/${encodeURIComponent(id)}`);if(version!==state.routeVersion)return;
      state.customer=customer;
      if(state.draft.accountId!==customer.account_id){const old=state.draft;persist();const saved=state.customerDrafts[customer.account_id];state.draft=saved?structuredClone(saved):blankDraft(customer.account_id);if(!saved){state.draft.backend=old.backend;state.draft.reviewDetails.prepared_by=old.reviewDetails?.prepared_by||'';}state.preview=null;persist();}
      html=customerView(customer,state.historyMonths);
    }else if(page==='scenario'){
      if(state.draft.accountId&&state.customer?.account_id!==state.draft.accountId){const c=await api(`/customers/${state.draft.accountId}`);if(version!==state.routeVersion)return;state.customer=c;}
      html=scenarioView(state.draft,state.customer,state.config,state.preview);
    }else if(page==='history')html=historyView((await api('/runs')).items,state.reviewFilter);
    else if(page==='run'){
      const run=await api(`/runs/${encodeURIComponent(id)}`);if(version!==state.routeVersion)return;state.run=run;html=runView(run);
      if(run.status==='running')state.poll=setTimeout(()=>render({quiet:true}),1500);
    }else if(page==='compare')html=compareView(await Promise.all([api(`/runs/${encodeURIComponent(id)}`),api(`/runs/${encodeURIComponent(second)}`)]));
    else if(page==='settings')html=settingsView(state.config,state.draft.backend);
    else html=notice('This view is unavailable. Use the workspace navigation.','warn');
    if(version!==state.routeVersion)return;
    main.innerHTML=html;restoreEdits();
    if(!quiet){window.scrollTo(0,0);main.focus({preventScroll:true});}
    document.getElementById('connection-status').textContent='Customer review workspace';document.getElementById('connection-status').className='badge';sidebar();
  }catch(error){
    if(version!==state.routeVersion)return;
    main.innerHTML=`<section class="card error-panel"><h1>This view needs attention.</h1>${notice(plainNote(error.message),'error')}<div class="actions"><button data-action="refresh">Try again</button><a class="button" href="#customers">Find a customer</a></div></section>`;
  }
}

async function perform(action){
  if(state.busy)return;state.busy=true;
  const buttons=[...main.querySelectorAll('button')],old=buttons.map(b=>[b.disabled,b.textContent]);
  const controls=[...main.querySelectorAll('input,select,textarea')],disabled=controls.map(c=>c.disabled);
  buttons.forEach(b=>b.disabled=true);controls.forEach(c=>c.disabled=true);
  try{await action();}catch(error){notify(plainNote(error.message),true);}
  finally{state.busy=false;buttons.forEach((b,i)=>{b.disabled=old[i][0];b.textContent=old[i][1];});controls.forEach((c,i)=>c.disabled=disabled[i]);}
}
async function validateDraft(candidate){return api('/scenarios/preview',{method:'POST',body:JSON.stringify(candidate)});}

main.addEventListener('submit',event=>{
  event.preventDefault();if(state.busy)return;
  const form=event.target;
  if(form.id==='account-search'){const f=new FormData(form);state.query=String(f.get('q')).trim();state.filter=f.get('filter');state.offset=0;render();return;}
  try{
    if(form.id==='review-form'){
      const values=capture(form),runId=state.run.id;
      const update={version:Number(values.version),status:values.status,owner:values.owner.trim(),follow_up_date:values.follow_up_date||null,notes:values.notes,completed_items:values.completed_items||[]};
      perform(async()=>{const saved=await api(`/runs/${runId}/review`,{method:'PATCH',body:JSON.stringify(update)});delete state.reviewDrafts[runId];writeLocal('tangerine-review-notes',state.reviewDrafts);if(state.run?.id===runId)state.run.review=saved;await render({quiet:true});notify('Discussion notes and follow-up saved.');});
    }else if(form.id==='effect-form'){
      const effect=effectFromForm(form,state.draft.accountId),scenario=structuredClone(state.draft.scenario),editing=state.draft.editingEffect;
      if(editing!=null){effect.effect_id=scenario.effects[editing].effect_id||effect.effect_id;scenario.effects[editing]=effect;}else scenario.effects.push(effect);
      if(scenario.phase==='normal')scenario.phase='active';
      perform(async()=>{await validateDraft({...financialInput(),scenario});state.draft.scenario=scenario;delete state.draft.formDrafts[form.id];delete state.draft.editingEffect;invalidate();await render({quiet:true});notify('Customer circumstance saved.');});
    }else if(entryNames[form.id]){
      const entry=contextFromForm(form,state.draft.accountId),context=structuredClone(state.draft.context);
      if(form.id==='transfer-form')context.existing_transfers.push(entry);
      else context[form.id==='goal-form'?'normal_goal':'recovery_snapshot']=entry;
      perform(async()=>{await validateDraft({...context,account_id:state.draft.accountId,scenario:state.draft.scenario});state.draft.context=context;delete state.draft.formDrafts[form.id];invalidate();await render({quiet:true});notify('Financial details saved to this review.');});
    }
  }catch(error){notify(plainNote(error.message),true);}
});

main.addEventListener('input',event=>{
  const el=event.target,form=el.closest('form');
  if(form?.id==='review-form'&&state.run){state.reviewDrafts[state.run.id]=capture(form);writeLocal('tangerine-review-notes',state.reviewDrafts);document.getElementById('review-save-status').textContent='Unsaved notes — save to update the worklist.';return;}
  if(form?.dataset.entry){state.draft.formDrafts[form.id]=capture(form);invalidate();return;}
  const fields={
    'scenario-title':()=>state.draft.title=el.value,'scenario-horizon':()=>state.draft.scenario.horizon_months=Number(el.value),
    'scenario-description':()=>state.draft.scenario.description=el.value,'opening-cash':()=>state.draft.context.opening_cash=el.value===''?null:Number(el.value),
    'prepared-by':()=>state.draft.reviewDetails.prepared_by=el.value,'customer-priority':()=>state.draft.reviewDetails.customer_priority=el.value,
    'cash-source':()=>state.draft.reviewDetails.cash_source=el.value,
  };
  if(fields[el.id]){fields[el.id]();invalidate();}
});

main.addEventListener('change',event=>{
  const el=event.target,form=el.closest('form');
  if(el.id==='effect-type'){document.getElementById('effect-fields').innerHTML=effectFields(el.value);state.draft.formDrafts['effect-form']=capture(form);invalidate();}
  else if(el.name==='unknown'||el.name==='duration_mode')syncEffectFields();
  else if(el.id==='backend'){state.draft.backend=el.value;persist();render({quiet:true});}
  else if(el.id==='review-purpose'){state.draft.reviewDetails.purpose=el.value;persist();}
  else if(el.id==='scenario-phase'){state.draft.scenario.phase=el.value;invalidate();}
  else if(el.id==='history-window'){state.historyMonths=Number(el.value);main.innerHTML=customerView(state.customer,state.historyMonths);}
  else if(el.id==='review-filter'){state.reviewFilter=el.value;render({quiet:true});}
  else if(el.dataset.path){const selected=[...main.querySelectorAll('[data-path]:checked')].map(x=>x.dataset.path);document.getElementById('projection-chart').innerHTML=projectionChart(state.run.result.plans.crisis_plan,selected);}
  else if(el.dataset.compare){let checked=[...main.querySelectorAll('[data-compare]:checked')];if(checked.length>2){el.checked=false;notify('Choose two customer assessments to compare.');checked=checked.filter(x=>x!==el);}document.getElementById('compare-button').disabled=checked.length!==2;}
});

main.addEventListener('click',event=>{
  const button=event.target.closest('[data-action]');if(!button||button.disabled)return;
  const action=button.dataset.action;
  if(action==='refresh'){state.config=null;render();return;}
  if(action==='portfolio-refresh'){render({refreshPortfolio:true});return;}
  if(action==='portfolio-page'){location.hash=`discovery/${button.dataset.cohort}/${button.dataset.offset}`;return;}
  if(action==='accounts-page'){state.offset=Number(button.dataset.offset);render();return;}
  if(['show-guide','hide-guide'].includes(action)){state.showGuide=action==='show-guide';writeLocal('tangerine-guide-visible',state.showGuide);render({quiet:true});return;}
  if(action==='compare'){const ids=[...main.querySelectorAll('[data-compare]:checked')].map(x=>x.dataset.compare);if(ids.length===2)location.hash=`compare/${ids[0]}/${ids[1]}`;return;}
  if(['brief','print'].includes(action)){
    if(state.reviewDrafts[state.run.id]){notify('Save your discussion notes before exporting the review.',true);return;}
    if(action==='print')window.print();else downloadFile(`customer-review-${state.run.request.account_id}.txt`,reviewBrief(state.run));return;
  }
  if(action==='cashflow-csv'){
    const c=state.run.result.plans.crisis_plan;
    const rows=[['Month','Inflow CAD','Regular spending CAD','One-time cost CAD','One-time receipt CAD','Cash without additional action CAD','Cash with supported changes CAD'],...c.no_action.schedule.map((s,i)=>[s.month,s.income,s.spending,s.one_off_cost,s.one_off_receipt,s.end_balance,c.applied_plan.schedule[i].end_balance])];
    downloadFile(`cash-flow-${state.run.request.account_id}.csv`,rows.map(r=>r.map(v=>v??'').join(',')).join('\r\n'),'text/csv');return;
  }
  if(action==='legacy-backup'){download('unfinished-review-entry.json',{scenario:state.draft.rawScenario,commitments:state.draft.rawContext});return;}
  perform(async()=>{
    if(action==='discard-review-edits'){delete state.reviewDrafts[state.run.id];writeLocal('tangerine-review-notes',state.reviewDrafts);await render({quiet:true});notify('Saved notes loaded.');}
    else if(action==='preset'){state.draft.scenario=preset(button.dataset.preset,state.customer);state.draft.title=button.textContent;delete state.draft.formDrafts['effect-form'];delete state.draft.editingEffect;invalidate();await render({quiet:true});}
    else if(action==='edit-effect'){
      const index=Number(button.dataset.index),f=state.draft.scenario.effects[index];state.draft.editingEffect=index;
      state.draft.formDrafts['effect-form']={...f,value:f.value==null?'':f.value*(f.type==='income_multiplier'?100:1),unknown:f.value==null,duration_mode:f.ongoing?'ongoing':f.duration_months?'known':'unknown'};
      persist();await render({quiet:true});document.getElementById('add-effect-details').scrollIntoView({block:'start'});
    }else if(action==='remove-effect'){state.draft.scenario.effects.splice(Number(button.dataset.index),1);delete state.draft.formDrafts['effect-form'];delete state.draft.editingEffect;if(!state.draft.scenario.effects.length&&state.draft.scenario.phase==='active')state.draft.scenario.phase='normal';invalidate();await render({quiet:true});}
    else if(action==='clear-entry'){delete state.draft.formDrafts[button.dataset.form];if(button.dataset.form==='effect-form')delete state.draft.editingEffect;persist();await render({quiet:true});}
    else if(action==='remove-transfer'){state.draft.context.existing_transfers.splice(Number(button.dataset.index),1);invalidate();await render({quiet:true});}
    else if(action==='remove-goal'||action==='remove-recovery'){const goal=action==='remove-goal';state.draft.context[goal?'normal_goal':'recovery_snapshot']=null;delete state.draft.formDrafts[goal?'goal-form':'recovery-form'];invalidate();await render({quiet:true});}
    else if(action==='discard-legacy'){delete state.draft.rawScenario;delete state.draft.rawContext;persist();await render({quiet:true});}
    else if(action==='preview'){
      const payload=currentInput(),signature=JSON.stringify(payload),initial=route();button.textContent='Checking the figures…';
      const result=await validateDraft(payload);
      if(initial===route()&&signature===JSON.stringify(currentInput())){state.preview=result;const slot=document.getElementById('preview-slot');slot.innerHTML=previewView(result);slot.scrollIntoView({block:'start'});}
    }else if(action==='run'){
      const body={...currentInput(),backend:state.draft.backend,title:state.draft.title.trim(),review_details:state.draft.reviewDetails};
      if(!body.title)throw new Error('Give the customer review a title.');
      const signature=JSON.stringify(body),old=state.draft.pendingRequest,id=old?.signature===signature?old.id:crypto.randomUUID();
      state.draft.pendingRequest={id,signature};persist();button.textContent='Preparing review…';
      const accepted=await api('/runs',{method:'POST',body:JSON.stringify({...body,request_id:id})});delete state.draft.pendingRequest;persist();location.hash=`run/${accepted.id}`;
    }else if(action==='duplicate'){
      const r=state.run.request;state.draft={...blankDraft(r.account_id),title:`${r.title.slice(0,100)} · revision`,backend:r.backend,reviewDetails:structuredClone(r.review_details||blankDraft().reviewDetails),scenario:structuredClone(r.scenario),context:structuredClone({opening_cash:r.opening_cash,normal_goal:r.normal_goal,existing_transfers:r.existing_transfers||[],recovery_snapshot:r.recovery_snapshot})};state.preview=null;persist();location.hash='scenario';
    }
  });
});
window.addEventListener('hashchange',()=>render());
render();

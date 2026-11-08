export const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const money = value => value == null ? 'Not established' : new Intl.NumberFormat('en-CA', {style:'currency', currency:'CAD', maximumFractionDigits:2}).format(value);
export const number = value => value == null ? '—' : new Intl.NumberFormat('en-CA', {maximumFractionDigits:1}).format(value);
export const percent = value => value == null ? 'Not established' : `${number(value * 100)}%`;
export const human = value => String(value ?? 'Not established').toLowerCase().replaceAll('_', ' ');
export const badge = (text, tone='') => `<span class="badge ${tone}">${escapeHtml(text)}</span>`;
export const metric = (label, value, detail='') => `<div class="metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>${detail ? `<small>${escapeHtml(detail)}</small>` : ''}</div>`;
export const notice = (text, tone='info') => `<div class="notice ${tone}">${escapeHtml(text)}</div>`;
export const empty = (title, text, link='#customers', action='Choose a customer') => `<section class="empty-state"><div class="empty-icon">↗</div><h2>${escapeHtml(title)}</h2><p>${escapeHtml(text)}</p><a class="button primary" href="${escapeHtml(link)}">${escapeHtml(action)}</a></section>`;
export const jsonDetails = (title, value) => `<details><summary>${escapeHtml(title)}</summary><pre>${escapeHtml(JSON.stringify(value, null, 2))}</pre></details>`;

function fieldLabel(path) {
  const parts=path.split('.'), last=parts.at(-1);
  const labels={value:'Amount',start_month:'First month affected',duration_months:'Duration',horizon_months:'Review period',phase:'Review circumstances',opening_cash:'Accessible cash',existing_transfers:'Scheduled payments',recovery_snapshot:'Recovery figures',normal_goal:'Savings objective',follow_up_date:'Follow-up date',prepared_by:'Prepared by',customer_priority:'Customer priority',source:'Information source',notes:'Discussion notes',event_id:'Payment reference',monthly_contribution:'Monthly contribution',available_cash:'Accessible cash',assessment_month:'Month of the figures'};
  const group=parts.indexOf('effects');
  const prefix=group>=0&&/^\d+$/.test(parts[group+1])?`Change ${Number(parts[group+1])+1} · `:'';
  return prefix+(labels[last]||last.replaceAll('_',' '));
}

export function table(headers, rows, caption='') {
  return `<div class="table-wrap"><table>${caption ? `<caption>${escapeHtml(caption)}</caption>` : ''}<thead><tr>${headers.map(h=>`<th scope="col">${escapeHtml(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(cell=>`<td>${cell}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}

export async function api(path, options={}) {
  const controller = new AbortController();
  const timeout = setTimeout(()=>controller.abort(), 60000);
  try {
    const response = await fetch(`/api${path}`, {...options, headers:{'Content-Type':'application/json', ...options.headers}, signal:controller.signal});
    let data;
    try { data=await response.json(); }
    catch { throw new Error('This view is temporarily unavailable. Try reopening it, or contact the workspace administrator.'); }
    if (!response.ok) {
      const detail = typeof data.detail === 'string' ? data.detail : 'The request could not be accepted.';
      throw new Error(data.errors ? `${detail}\n${data.errors.map(e=>`${fieldLabel(e.field)}: ${e.message}`).join('\n')}` : detail);
    }
    return data;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('The assessment is taking longer than expected. Check Review history before submitting it again.');
    throw error;
  } finally { clearTimeout(timeout); }
}

export function notify(text, error=false) {
  const node = document.getElementById('notifications');
  node.textContent = text;
  node.className = error ? 'toast error' : 'toast';
  clearTimeout(notify.timer);
  notify.timer = setTimeout(()=>{ node.className=''; node.textContent=''; }, error ? 15000 : 6000);
}

export function download(name, value) {
  downloadFile(name,JSON.stringify(value,null,2),'application/json');
}
export function downloadFile(name,contents,type='text/plain') {
  const url = URL.createObjectURL(new Blob([contents], {type}));
  const a = document.createElement('a'); a.href=url; a.download=name; a.click();
  setTimeout(()=>URL.revokeObjectURL(url), 1000);
}

const STORAGE = 'tangerine-website-draft-v1';
export function blankDraft(accountId=null) {
  return {accountId,title:'Customer financial review',backend:null,reviewDetails:{purpose:'cash_flow',prepared_by:'',customer_priority:'',cash_source:''},formDrafts:{},scenario:{phase:'normal',horizon_months:6,description:'',effects:[]},context:{opening_cash:null,existing_transfers:[],normal_goal:null,recovery_snapshot:null}};
}
export function readDraft() {
  try { const d=JSON.parse(localStorage.getItem(STORAGE)); return d?.scenario && Array.isArray(d.scenario.effects) && d.context ? {...blankDraft(d.accountId),...d} : blankDraft(); }
  catch { return blankDraft(); }
}
export function saveDraft(draft) {
  try { localStorage.setItem(STORAGE, JSON.stringify(draft)); }
  catch { /* In-memory editing remains usable when local storage is unavailable. */ }
}

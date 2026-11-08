import {escapeHtml as e, number, table} from './common.js';

const colors = ['#d94d20','#237e80','#7c6bb4','#b08b30'];
export function lineChart(rows, series, labelKey, title) {
  if (!rows.length) return '<p class="muted">No observations available.</p>';
  const w=840, h=280, left=72, right=20, top=22, bottom=42;
  const values=rows.flatMap(r=>series.map(s=>r[s.key])).filter(v=>typeof v==='number' && Number.isFinite(v));
  if (!values.length) return '<p class="muted">These values are not established.</p>';
  let low=Math.min(0,...values), high=Math.max(0,...values);
  if (low===high) high=low+1;
  const pad=(high-low)*.08; low-=pad; high+=pad;
  const x=i=>left+(rows.length===1 ? .5 : i/(rows.length-1))*(w-left-right);
  const y=v=>h-bottom-(v-low)/(high-low)*(h-top-bottom);
  const ticks=Array.from({length:5},(_,i)=>low+(high-low)*i/4);
  const grid=ticks.map(v=>`<line x1="${left}" x2="${w-right}" y1="${y(v)}" y2="${y(v)}" class="chart-grid"/><text x="${left-10}" y="${y(v)+4}" text-anchor="end">${e(number(v))}</text>`).join('');
  const labels=rows.map((r,i)=>i===0 || i===rows.length-1 || i%Math.max(1,Math.ceil(rows.length/7))===0 ? `<text x="${x(i)}" y="${h-14}" text-anchor="middle">${e(r[labelKey])}</text>` : '').join('');
  const lines=series.map((s,si)=>{
    let d='', open=false;
    rows.forEach((r,i)=>{ const v=r[s.key]; if(typeof v!=='number' || !Number.isFinite(v)){open=false;return;} d+=`${open?'L':'M'}${x(i)},${y(v)} `;open=true; });
    const points=rows.map((r,i)=>typeof r[s.key]==='number' ? `<circle cx="${x(i)}" cy="${y(r[s.key])}" r="${rows.length>35?2:3.5}" fill="${colors[si%colors.length]}"><title>${e(`${s.name} · ${r[labelKey]}: ${number(r[s.key])} CAD`)}</title></circle>` : '').join('');
    return `<path d="${d}" fill="none" stroke="${colors[si%colors.length]}" stroke-width="2.5"/>${points}`;
  }).join('');
  return `<figure class="chart"><figcaption>${e(title)}</figcaption><div class="legend">${series.map((s,i)=>`<span><i class="series-${i%4}"></i>${e(s.name)}</span>`).join('')}</div><svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${e(title)}. Values in Canadian dollars; exact values are in the table below.">${grid}<line x1="${left}" x2="${w-right}" y1="${y(0)}" y2="${y(0)}" class="zero-line"/>${labels}${lines}</svg><details><summary>View chart data (CAD)</summary>${table([labelKey==='month'?'Month':labelKey,...series.map(s=>s.name)],rows.map(r=>[e(r[labelKey]),...series.map(s=>e(number(r[s.key])))]))}</details></figure>`;
}

export function barChart(rows, title, valueKey='count') {
  const max=Math.max(1,...rows.map(r=>r[valueKey]));
  return `<figure class="chart"><figcaption>${e(title)}</figcaption><div class="bars">${rows.map(r=>`<div class="bar-row"><span>${e(r.label)}</span><svg viewBox="0 0 100 12" preserveAspectRatio="none" aria-hidden="true"><rect width="100" height="12" rx="3" fill="#eee9e2"/><rect width="${r[valueKey]/max*100}" height="12" rx="3" fill="#d94d20"/></svg><strong>${e(number(r[valueKey]))}</strong></div>`).join('')}</div></figure>`;
}

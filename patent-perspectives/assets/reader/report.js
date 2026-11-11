(() => {
  'use strict';
  const data=JSON.parse(document.getElementById('reader-data').textContent), $=id=>document.getElementById(id);
  const state={role:'management',chapter:data.orders.management[0],search:'',product:'',kind:'technical',page:1};
  const records=data.records.map(p=>({...p,id:String(p.id)}));
  const sources=new Map(data.sources.map(s=>[s.id,s]));
  const el=(tag,text='',cls='')=>{const n=document.createElement(tag);n.textContent=text;n.className=cls;return n;};
  const action=(label,fn)=>{const b=el('button',label);b.type='button';b.onclick=fn;return b;};
  const fmt=n=>n.toLocaleString('zh-CN');
  const filtered=()=>records.filter(p=>(state.kind==='design'?p.type==='design':p.type!=='design')&&(!state.product||p.product===state.product)&&(!state.search||[p.title,p.publication,p.product].join(' ').toLowerCase().includes(state.search.toLowerCase())));
  let focusBefore;
  function showSources(ids,title){
    const body=$('evidence-body'),selected=[...new Set(ids)].map(id=>sources.get(id)).filter(Boolean);let sourcePage=0;
    function drawSources(){
    body.replaceChildren(el('h2',title));
    if(!selected.length)body.append(el('p','本条尚无可展示的原文，不能据此作进一步判断。'));
    if(selected.length>10){const controls=el('div','','list-pages'),prev=action('上一组来源',()=>{sourcePage--;drawSources();}),next=action('下一组来源',()=>{sourcePage++;drawSources();});prev.disabled=sourcePage===0;next.disabled=(sourcePage+1)*10>=selected.length;controls.append(prev,el('span',(sourcePage+1)+' / '+Math.ceil(selected.length/10)),next);body.append(controls);}
    for(const source of selected.slice(sourcePage*10,(sourcePage+1)*10)){
      body.append(el('h3',source.title),el('p',[source.publication,source.locator].filter(Boolean).join(' · '),'meta'),el('blockquote',source.quote));
      if(source.text){const detail=el('details');detail.append(el('summary','展开所引原文'));detail.ontoggle=()=>{if(detail.open&&!detail.querySelector('pre'))detail.append(el('pre',source.text));};body.append(detail);}
      if(source.version){const detail=el('details');detail.append(el('summary','查看来源版本信息'),el('pre',source.version));body.append(detail);}
      if(source.url && /^https?:\/\//.test(source.url)){const a=el('a','打开来源网页');a.href=source.url;a.target='_blank';a.rel='noopener noreferrer';body.append(a);}
    }
    $('evidence').scrollTop=0;}
    drawSources();focusBefore=document.activeElement;$('evidence').showModal();
  }
  $('close').onclick=()=>$('evidence').close();$('evidence').addEventListener('close',()=>focusBefore?.focus({preventScroll:true}));
  const evidenceButton=(ids,title='查看依据')=>action(title,()=>showSources(ids,title));
  function drawChart(rows){
    const chart=el('div','','chart');chart.append(el('h3','申请数量怎样变化'));
    const dated=rows.filter(p=>/^\d{4}/.test(p.filing_date||'')), unknown=rows.length-dated.length;
    const byYear=new Map();for(const p of dated){const y=p.filing_date.slice(0,4);byYear.set(y,(byYear.get(y)||0)+1);}
    const all=[...byYear].sort((a,b)=>a[0].localeCompare(b[0])), last=all.length?Number(all.at(-1)[0]):0, recent=all.length?Array.from({length:Math.min(6,last-Number(all[0][0])+1)},(_,i)=>{const y=String(Math.max(last-5,Number(all[0][0]))+i);return[y,byYear.get(y)||0];}):[], scale=Math.max(1,...recent.map(x=>x[1]));
    chart.append(el('p','按申请年份统计，默认展示截至最近有记录年份的连续六年（不足六年则全部展示）；* 为不完整年度。日期未知 '+fmt(unknown)+' 件另计。','meta'));
    const bars=el('div','','bars');
    for(const [year,n]of recent){const b=action('',()=>showSources(rows.filter(p=>p.filing_date?.startsWith(year)).flatMap(p=>p.evidence_ids),year+' 年对应申请'));
      b.className='bar';b.setAttribute('aria-label',year+'年，'+n+'件');b.append(el('strong',fmt(n)),el('i'),el('span',year+(data.scope.partial_years.includes(year)?' *':'')));b.style.setProperty('--height',(n/scale*150)+'px');bars.append(b);}
    chart.append(bars);if(!recent.length)chart.append(el('p','当前没有可按年比较的申请。'));
    if(all.some(([year])=>year<recent[0]?.[0])){const more=el('details');more.append(el('summary','查看全部有记录年份数量'));for(const[y,n]of all)more.append(el('p',y+' 年：'+n+' 件'));chart.append(more);}return chart;
  }
  function drawList(rows){
    const list=el('div'),pages=Math.max(1,Math.ceil(rows.length/20));state.page=Math.min(state.page,pages);
    const controls=el('div','','list-pages'),prev=action('上一页',()=>{state.page--;renderContent();}),next=action('下一页',()=>{state.page++;renderContent();});prev.disabled=state.page===1;next.disabled=state.page===pages;controls.append(prev,el('span',state.page+' / '+pages+' 页'),next);list.append(controls);
    for(const p of rows.slice((state.page-1)*20,state.page*20)){const card=el('article','','record');card.append(action(p.title,()=>showSources(p.evidence_ids,p.title)),el('div',[p.publication,p.product,p.filing_date,p.status||'状态未知'].filter(Boolean).join(' · '),'meta'));list.append(card);}return list;
  }
  function renderContent(){
    const chapter=data.chapters.find(c=>c.id===state.chapter),rows=filtered(),root=$('content');root.replaceChildren(el('h2',chapter.title));
    $('filter-state').textContent='当前 '+fmt(rows.length)+' 件'+(state.kind==='design'?'外观设计':'技术申请')+'；图表与目录共用此范围。';
    if(chapter.kind==='directory'){
      const pending=rows.filter(p=>p.read_complete!==true).length;
      const unknown=rows.filter(p=>!p.status||p.status==='未知').length;
      root.append(el('p',rows.length?'当前 '+fmt(rows.length)+' 件申请中，'+(unknown===rows.length?'法律状态均未核实':fmt(rows.filter(p=>p.status==='有效').length)+' 件记录为有效，'+fmt(unknown)+' 件状态未知')+(state.kind==='technical'?'；'+fmt(pending)+' 件技术解读待补齐':'')+'。逐件状态以注明的观察日期为准。':'当前筛选没有申请，不能形成该范围的分布判断。','finding'));
    }else{
      if($('overview').hidden)root.append(el('p',chapter.conclusion,'finding'));
      root.append(el('p','结论范围：'+chapter.scope_label+'。筛选改变图表和目录，不改写范围已注明的结论。','meta'));
      for(const paragraph of chapter.body||[])root.append(el('p',paragraph));root.append(evidenceButton(chapter.evidence_ids));
    }
    if(rows.length){if(chapter.kind==='trend')root.append(drawChart(rows));root.append(drawList(rows));}
    else root.append(el('p','没有匹配的申请。可重置筛选，或切换目录类型。','empty'));
  }
  function renderNavigation(){
    const order=data.orders[state.role];$('chapter').replaceChildren();$('outline').replaceChildren();
    for(const id of order){const chapter=data.chapters.find(c=>c.id===id),option=new Option(chapter.title,id,false,id===state.chapter);$('chapter').append(option);const b=action(chapter.title,()=>openChapter(id));if(id===state.chapter)b.setAttribute('aria-current','page');$('outline').append(b);}
    const i=order.indexOf(state.chapter);$('pager').replaceChildren();if(i>0)$('pager').append(action('上一章 · '+data.chapters.find(c=>c.id===order[i-1]).title,()=>openChapter(order[i-1])));if(i<order.length-1)$('pager').append(action('下一章 · '+data.chapters.find(c=>c.id===order[i+1]).title,()=>openChapter(order[i+1])));
  }
  function renderOverview(){
    const role=data.roles[state.role],root=$('overview');root.hidden=state.chapter!==data.orders[state.role][0];root.replaceChildren(el('h2',role.title),el('p',role.answer,'answer'));
    const reasons=el('div','','reasons');for(const point of role.reasons){const box=el('div');box.append(el('h3',point.title),el('p',point.text),evidenceButton(point.evidence_ids));reasons.append(box);}root.append(reasons,el('p','概览依据：'+role.scope_label,'meta'));
  }
  function openChapter(id,scroll=true){state.chapter=id;renderNavigation();renderOverview();renderContent();if(scroll)$('content').scrollIntoView({block:'start'});}
  for(const b of document.querySelectorAll('[data-role]'))b.onclick=()=>{const y=scrollY;state.role=b.dataset.role;for(const x of document.querySelectorAll('[data-role]'))x.setAttribute('aria-pressed',String(x===b));openChapter(state.chapter,false);window.scrollTo(0,y);};
  $('home').onclick=()=>{openChapter(data.orders[state.role][0],false);window.scrollTo(0,0);};
  $('chapter').onchange=()=>openChapter($('chapter').value);
  $('layout').onchange=()=>{document.body.dataset.layout=$('layout').value;$('filters').open=$('layout').value==='workbench';};
  let timer;const apply=()=>{state.search=$('search').value;state.product=$('product').value;state.kind=$('kind').value;state.page=1;renderContent();};
  $('search').oninput=()=>{clearTimeout(timer);timer=setTimeout(apply,180);};$('product').onchange=apply;$('kind').onchange=apply;
  $('reset').onclick=()=>{clearTimeout(timer);$('search').value='';$('product').value='';$('kind').value='technical';apply();};
  $('product').append(new Option('全部产品线',''),...[...new Set(records.map(p=>p.product))].sort().map(p=>new Option(p,p)));
  $('identity').append(el('h1',data.company+'专利报告'),el('p',data.business),el('p',(data.scope.mode==='materials'?'材料范围：':'检索范围：')+data.scope.label,'scope'));
  const methods=el('details');methods.append(el('summary','范围、日期与术语'),el('p','公开记录收录至 '+data.scope.as_of+'；法律状态观察：'+data.scope.status_observed_at+'；企业披露期间：'+(data.scope.disclosure_date||'本报告未采用企业披露数量')+'。'),el('p','技术申请指发明和实用新型；外观设计单列。同一申请的公开与授权版本合计一件，跨国同族不自动合并。依据完整权利要求解读，不代表已经读过说明书。'));$('identity').append(methods);
  if(data.synthetic)$('identity').prepend(el('p','合成示例 · 仅展示模板，不代表真实公司或专利','scope'));
  new ResizeObserver(()=>document.documentElement.style.setProperty('--header',document.querySelector('header').offsetHeight+'px')).observe(document.querySelector('header'));
  document.querySelector('[data-role=management]').setAttribute('aria-pressed','true');document.body.dataset.layout='reading';openChapter(state.chapter,false);
})();

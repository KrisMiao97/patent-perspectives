(function(){
 'use strict';
 const ids=['timeline-overview-canvas','timeline-line-canvas','product-patent-canvas'],states=new Map();
 const E=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
 const date=(s,n)=>s.model.date==='publication'?window.PP_TIMELINES.nodes[n.p.id]?.document_publication_date:n.p.filing_date;
 const routeKey=l=>[l.module||'',l.sub||'',l.label].join('|');
 const color=(lane,i)=>['#2869c0','#248e97','#8b73bd','#b48037','#427ca0','#699452','#a06e8b','#5c7bb0'][(lane.colorIndex??i)%8];
 function install(id){
  const canvas=document.getElementById(id),panel=canvas?.closest('.tl-panel');if(!panel)return;
  const title=panel.querySelector('h3')?.textContent||'技术时间图',tools=E('div','tl-reading-tools'),modes=E('div','tl-reading-modes');modes.setAttribute('role','group');modes.setAttribute('aria-label',title+'：阅读方式');
  const s={canvas,panel,tools,view:'compact',route:'',year:'',model:null,board:null,content:null};states.set(id,s);
  const button=(text,fn)=>{const b=E('button','',text);b.type='button';b.onclick=fn;return b;};
  const compact=button('紧凑阅读',()=>changeView(s,'compact')),proportional=button('按时间比例',()=>changeView(s,'proportional'));compact.dataset.readingMode='compact';proportional.dataset.readingMode='proportional';modes.append(compact,proportional);
  const routeLabel=E('label','','本图路线'),route=E('select');route.setAttribute('aria-label',title+'：筛选展示技术线');route.onchange=()=>{s.route=route.value;s.year='';render(s,true);};routeLabel.append(route);
  const yearLabel=E('label','','本图年份'),year=E('select');year.setAttribute('aria-label',title+'：筛选展示年份');year.onchange=()=>{s.year=year.value;render(s,true);};yearLabel.append(year);
  const latest=button('最近展示年份',()=>{const years=yearsFor(s);s.year=years.at(-1)||'';render(s,true);});latest.className='tl-reading-latest';
  const count=E('span','tl-reading-count');count.setAttribute('role','status');const note=E('p','tl-reading-note');
  tools.append(modes,routeLabel,yearLabel,latest,count,note);panel.querySelector('.tl-toolbar').append(tools);
  Object.assign(s,{compact,proportional,routeSelect:route,yearSelect:year,latest,count,note,routeLabel,yearLabel});
  const sync=()=>{const model=canvas.ppTimelineReading,board=canvas.querySelector(':scope > .tl-board');if(!model)return;if(s.model===model&&s.board===board&&s.content?.parentNode===canvas)return;s.model=model;s.board=board;s.content=null;render(s,true);};
  new MutationObserver(sync).observe(canvas,{childList:true});sync();
 }
 function allNodes(s){return s.model.lanes.flatMap((lane,i)=>lane.nodes.map(n=>({...n,route:routeKey(lane),routeName:lane.label,color:color(lane,i)})));}
 function routeNodes(s){return allNodes(s).filter(n=>!s.route||n.route===s.route);}
 function yearsFor(s){return [...new Set(routeNodes(s).map(n=>date(s,n)?.slice(0,4)).filter(Boolean))].sort();}
 function options(select,entries,value){select.replaceChildren(...entries.map(([v,t])=>{const o=E('option','',t);o.value=v;return o;}));select.value=value;}
 function changeView(s,view){s.view=view;render(s,true);requestAnimationFrame(()=>window.PP_TIMELINE_ZOOM?.refresh?.());}
 function render(s,resetScroll){
  if(!s.model)return;
  const all=allNodes(s),routes=s.model.lanes.map(l=>[routeKey(l),l.label+' · '+l.nodes.length+'个节点']);if(s.route&&!routes.some(([key])=>key===s.route))s.route='';
  const years=yearsFor(s);if(s.year&&!years.includes(s.year))s.year='';
  options(s.routeSelect,[['','全部技术线（'+routes.length+'条）'],...routes],s.route);options(s.yearSelect,[['','全部展示年份'],...years.map(y=>[y,y+'年'])],s.year);
  const compact=s.view==='compact';s.panel.dataset.timelineView=s.canvas.dataset.timelineView=s.view;
  s.compact.setAttribute('aria-pressed',String(compact));s.proportional.setAttribute('aria-pressed',String(!compact));
  const shown=routeNodes(s).filter(n=>!s.year||date(s,n)?.startsWith(s.year)).sort((a,b)=>date(s,a).localeCompare(date(s,b))||a.route.localeCompare(b.route,'zh-CN')||a.p.id.localeCompare(b.p.id));
  const filterKey=JSON.stringify([s.route,s.year]);
  if(!compact&&(s.proportionalModel!==s.model||s.proportionalFilter!==filterKey)){
   const model=s.model,lanes=model.lanes.filter(l=>!s.route||routeKey(l)===s.route).map(l=>({...l,nodes:l.nodes.filter(n=>!s.year||date(s,n)?.startsWith(s.year))})).filter(l=>l.nodes.length);
   window.PP_TIMELINE_VIEW.redrawView(s.canvas.id,lanes,model.kind,model.date);s.canvas.ppTimelineReading=model;s.board=s.canvas.querySelector(':scope > .tl-board');s.content=null;s.proportionalModel=model;s.proportionalFilter=filterKey;
  }
  if(s.board)s.board.hidden=compact;
  s.count.textContent='当前 '+shown.length+' / 本图 '+all.length+' 个节点';
  s.note.textContent=compact?'按日期先后分年排列，只列本图有节点的年份；年份间距不表示经过时长。这里筛选展示节点，不改变原图的选读或分页范围。':'横向距离反映实际时间间隔；范围取当前所选节点的最早至最晚日期。两种视图共用上方路线与年份筛选，可用下方缩放查看整体或细节。';
  if(!s.content){s.content=E('div','tl-reading-content');s.canvas.append(s.content);}s.content.hidden=!compact;
  if(compact){s.content.replaceChildren();const lanes=s.model.lanes.filter(l=>!s.route||routeKey(l)===s.route);if(lanes.length){const notes=E('details','tl-reading-route-notes');notes.append(E('summary','','本图路线与选读说明 · '+lanes.length+'条'));lanes.forEach(l=>{const row=E('div','tl-reading-route-note');row.append(E('strong','',l.label),E('span','',l.total+'件 · 本图 '+l.nodes.length+'个节点'));if(l.selection_reason)row.append(E('p','','选读依据：'+l.selection_reason));if(l.note)row.append(E('p','',l.note));if(l.module){const link=E('button','text-button','进入该技术线 →');link.type='button';link.onclick=()=>window.PP_TIMELINE_VIEW.openTimelineLine(l.module,l.sub||'');row.append(link);}notes.append(row);});s.content.append(notes);}const groups=new Map();shown.forEach(n=>{const y=date(s,n).slice(0,4);if(!groups.has(y))groups.set(y,[]);groups.get(y).push(n);});
   groups.forEach((nodes,year)=>{const section=E('section','tl-reading-year');section.dataset.year=year;const label=E('h4','tl-reading-year-label',year);label.append(E('small','',nodes.length+'个节点'));const cards=E('div','tl-reading-year-cards');nodes.forEach(n=>cards.append(card(s,n)));section.append(label,cards);s.content.append(section);});
   if(!shown.length)s.content.append(E('p','tl-reading-empty','当前范围没有可展示节点。可以调整上方技术线或年份，或返回技术分析筛选。'));
  }
  if(resetScroll){s.canvas.scrollLeft=0;s.canvas.scrollTop=0;}
 }
 function card(s,n){
  const source=window.PP_TIMELINES.nodes[n.p.id],b=E('button','tl-reading-card');b.type='button';b.dataset.applicationId=n.p.id;b.style.setProperty('--line-color',n.color);b.onclick=()=>window.PP_TIMELINE_VIEW.openTimelineNode(n.p.id,n.authored);
  const when=date(s,n),title=n.authored?.title||n.p.title,body=n.authored?.body||source.means.join('；');b.setAttribute('aria-label',when+'，'+title+'，查看技术方案和原文');
  const meta=E('span','tl-reading-meta');meta.append(E('span','',when+' · '+(s.model.date==='publication'?'文献公开':'申请')),E('span','',window.PP_TIMELINE_VIEW.statusLabel(n.p.legal_status)));
  b.append(meta,E('span','tl-reading-route',n.routeName),E('strong','tl-reading-title',title),E('span','tl-reading-body',body));
  const owners=n.p.original_assignees;if(Array.isArray(owners)&&owners.length)b.append(E('span','tl-reading-owner','原申请人：'+owners.join('、')));
  b.append(E('span','tl-reading-number',source.publication_number),E('span','tl-reading-open','查看方案、条件与原文 →'));return b;
 }
 ids.forEach(install);
 window.PP_TIMELINE_READING={snapshot(){return [...states].map(([id,s])=>({id,view:s.view,route:s.route,year:s.year,totalNodes:s.model?allNodes(s).length:0,visibleIds:[...(s.view==='compact'?s.content?.querySelectorAll('.tl-reading-card')||[]:s.board?.querySelectorAll('.tl-card')||[])].map(n=>n.dataset.applicationId),years:[...(s.content?.querySelectorAll('.tl-reading-year')||[])].map(n=>n.dataset.year)}));}};
})();

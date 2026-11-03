/* Original company-centred research reader. No inference or network calls. */
(function(){
'use strict';
const data=window.PP_INDUSTRY,host=document.getElementById('industry-research'),nav=document.querySelector('[data-industry-link]');
if(!host||!data||!Array.isArray(data.companies)||!Array.isArray(data.routes))return;
const list=v=>Array.isArray(v)?v:[],words=v=>Array.isArray(v)?v.join('；'):v==null?'':String(v);
const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=words(text);return n;};
const btn=(text,fn,cls='ir-button')=>{const b=el('button',cls,text);b.type='button';b.addEventListener('click',fn);return b;};
const p=(text,cls='ir-note')=>el('p',cls,text);
const types={F:'已读完整权利要求',D:'已读完整说明书',P:'官方产品 / 手册',R:'论文 / 研究',O:'企业自述',L:'目录线索',U:'待补证'};
const tasks={project:'立项研究',competition:'竞争格局',profile:'公司画像',selection:'路线选择',forecast:'技术预测'};
const sources=new Map(list(data.sources).map(s=>[s.id,s]));
const companies=[...data.companies].sort((a,b)=>Number(b.id===data.target_company_id)-Number(a.id===data.target_company_id));
const cells=new Map(list(data.matrix).map(c=>[JSON.stringify([c.company_id,c.route_id]),c]));
const state={company:'',route:'',kind:''};
function scopeText(value){if(!value||typeof value!=='object')return words(value);if(Array.isArray(value))return value.map(scopeText).join('、');const labels={claim_number:'权利要求',paragraph:'段落',paragraph_number:'段落编号',page:'页码',section:'章节',jurisdictions:'地域',technical_types:'专利类型',selection:'选择范围',kind:'类型',count:'数量',from:'起始',through:'截止',filing_window:'申请期间',company:'公司',geography:'地域',period:'期间',mode:'研究范围',date_basis:'日期口径',oldest_filing_date:'最早申请日',latest_filing_date:'最晚申请日'};return Object.entries(value).map(([k,v])=>(labels[k]||k)+'：'+scopeText(v)).join('；');}
let opener=null;
const dialog=el('dialog','ir-dialog');dialog.setAttribute('aria-labelledby','ir-source-title');
const dialogTop=el('div','ir-dialog-top'),dialogBody=el('div','ir-dialog-body');
dialogTop.append(el('strong','','来源与适用范围'),btn('关闭 ×',()=>dialog.close()));dialog.append(dialogTop,dialogBody);document.body.append(dialog);
dialog.addEventListener('close',()=>opener?.focus());
function safeLink(value,local){
 if(typeof value!=='string'||/[\u0000-\u0020\\]/.test(value))return null;
 if(local)return !value.startsWith('/')&&!value.includes('..')&&!/[?:#%]/.test(value)&&/\.(pdf|txt|json|csv|png|jpe?g|webp)$/i.test(value)?value:null;
 try{const u=new URL(value);return ['https:','http:'].includes(u.protocol)&&!u.username&&!u.password?u.href:null;}catch(_){return null;}
}
function sourceDialog(id){
 const s=sources.get(id);if(!s)return;opener=document.activeElement;
 const title=el('h2','',s.title);title.id='ir-source-title';dialogBody.replaceChildren(title,p(id+' · '+(types[s.kind]||'来源')),p('定位：'+s.locator));
 for(const [k,l] of [['publication_number','公开号'],['document_id','文献版本标识'],['version','公开 / 授权版本'],['observed_at','观察日期'],['publication_date','来源发布日期'],['quote','原文摘录']])if(s[k])dialogBody.append(p(l+'：'+words(s[k])));
 list(s.evidence).forEach(e=>{const q=el('blockquote','ir-quote',e.quote);dialogBody.append(p('证据 '+e.id+' · '+(e.locator?scopeText(e.locator):('权利要求 '+(e.claim_number||'')))),q);});
 if(s.corpus_company)dialogBody.append(p('原文所属研究：'+s.corpus_company));
 if(s.corpus_as_of)dialogBody.append(p('原文研究截止日：'+s.corpus_as_of));
 if(s.corpus_scope)dialogBody.append(p('原文研究范围：'+scopeText(s.corpus_scope)));
 if(s.corpus_review_note)dialogBody.append(p(s.corpus_review_note,'ir-temporal'));
 if(s.corpus_id&&s.corpus_id!=='main')dialogBody.append(p('此原文来自独立参考研究，不计入目标公司的专利统计。'));
 if(s.application_id)dialogBody.append(p('独立申请标识：'+s.application_id));
 if(s.kind==='F')dialogBody.append(p('完整权利要求支持所引版本的披露内容；不直接证明产品采用、实测性能或权利有效。'));
 if(s.kind==='D')dialogBody.append(p('本项来自已完整阅读的说明书；不能据此代替未取得的权利要求或推断保护范围。'));
 if(s.publication_after_cutoff)dialogBody.append(p('后验资料：此来源发表于研究截止日之后，仅用于回顾解释，不作为截止日时已经可知的预测依据。','ir-temporal'));
 else if(s.observed_after_cutoff)dialogBody.append(p('此来源在研究截止日之后取得；观察时间与来源发布日期分别记录。','ir-temporal'));
 if(s.kind==='L')dialogBody.append(p('此项仅为目录线索，尚不能据此确认具体技术机制。'));
 if(s.kind==='O')dialogBody.append(p('此项为企业自述，需与独立证据分开理解。'));
 const actions=el('div','ir-source-actions');
 for(const [k,l,local] of [['local_path','打开随包来源',true],['url','打开原始网页 ↗',false]]){const href=safeLink(s[k],local);if(href){const a=el('a','ir-button',l);a.href=href;a.target='_blank';a.rel='noopener noreferrer';actions.append(a);}}
 if(s.application_id&&(!s.corpus_id||s.corpus_id==='main')&&typeof window.PP_OPEN_PATENT==='function')actions.append(btn('查看本件专利与原文',()=>{dialog.close();window.PP_OPEN_PATENT(s.application_id,list(s.evidence_ids));}));
 dialogBody.append(actions);if(!dialog.open)dialog.showModal();dialog.scrollTop=0;
}
function refs(ids){const box=el('span','ir-refs');list(ids).forEach(id=>{if(sources.has(id)){const b=btn('['+id+']'+(sources.get(id).publication_after_cutoff?' 后验':''),()=>sourceDialog(id),'ir-ref');b.setAttribute('aria-label','查看来源 '+id+'：'+sources.get(id).title);box.append(b);}});return box;}
function field(container,label,value){if(words(value)){const n=p('','ir-field');n.append(el('strong','',label+'：'),document.createTextNode(words(value)));container.append(n);}}
function tag(k){return el('span','ir-tag ir-kind-'+k,k+' · '+(types[k]||'未知'));}
host.hidden=false;if(nav)nav.hidden=false;
const heading=el('div','section-heading'),headingText=el('div');headingText.append(el('h2','','公司研究与技术路线研判'),p(data.scope.topic+' · 截至 '+data.scope.as_of,'section-context'));heading.append(headingText);host.append(heading);
host.append(p('目标公司：'+(companies.find(c=>c.id===data.target_company_id)?.name||data.target_company_id)+'。'+data.scope.selection_basis,'ir-scope'));
const roleNote=p('','ir-role-note'),tasksHost=el('div','ir-task-grid');host.append(roleNote,tasksHost);
const matrixHeading=el('div','ir-subheading');matrixHeading.append(el('h3','','公司 × 技术方向矩阵'),p('逐格阅读已取得的证据；颜色表示来源类别，不是技术实力评分。'));host.append(matrixHeading);
const controls=el('div','ir-controls');
function select(label,key,options){const l=el('label','',label),s=el('select');s.setAttribute('aria-label',label);options.forEach(([v,t])=>{const o=el('option','',t);o.value=v;s.append(o);});s.addEventListener('change',()=>{state[key]=s.value;renderMatrix();renderRoutes();});l.append(s);controls.append(l);return s;}
const companySelect=select('公司','company',[['','全部公司'],...companies.map(c=>[c.id,c.name])]);
const routeSelect=select('技术方向','route',[['','全部技术方向'],...data.routes.map(r=>[r.id,r.name])]);
const kindSelect=select('证据来源','kind',[['','全部来源'],...Object.entries(types).map(([k,v])=>[k,k+' · '+v])]);
controls.append(btn('重置筛选',()=>{state.company=state.route=state.kind='';companySelect.value=routeSelect.value=kindSelect.value='';renderMatrix();renderRoutes();}));host.append(controls);
host.append(p('本模块使用上述研究范围。公司与来源筛选只作用于矩阵；技术方向筛选同时作用于路线卡。页面其他专利统计筛选不改变本模块的结论。','ir-filter-note'));
const count=p('','ir-count');count.setAttribute('role','status');count.setAttribute('aria-live','polite');count.setAttribute('aria-atomic','true');host.append(count);
const matrixHost=el('div','ir-scroll');matrixHost.tabIndex=0;matrixHost.setAttribute('aria-label','公司技术方向矩阵，可横向滚动');host.append(matrixHost);
const legend=el('div','ir-legend');Object.keys(types).forEach(k=>legend.append(tag(k)));host.append(legend,p('未知不等于没有；目录线索不等于读过完整文本。单格可包含多种来源，点击编号查看出处。'));
const routeHost=el('div','ir-route-list');host.append(el('h3','ir-block-title','主要路线：借鉴、演进与选择'),routeHost);
function renderMatrix(){
 const rows=companies.filter(c=>!state.company||c.id===state.company),cols=data.routes.filter(r=>!state.route||r.id===state.route);
 count.textContent=rows.length+' 家公司 × '+cols.length+' 个技术方向'+(state.kind?'；显示 '+types[state.kind]+'，同时保留待补证信息':'');
 const table=el('table','ir-matrix'),thead=el('thead'),tr=el('tr');table.append(el('caption','ir-sr','公司与技术方向的证据矩阵'));const first=el('th','','企业 / 角色');first.scope='col';tr.append(first);
 cols.forEach(r=>{const th=el('th','',r.name);th.scope='col';tr.append(th);});thead.append(tr);table.append(thead);
 const tbody=el('tbody');rows.forEach(c=>{const row=el('tr'),th=el('th','ir-company');th.scope='row';th.append(el('strong','',c.name),el('small','',c.role));if(c.id===data.target_company_id)th.append(el('span','ir-target','目标公司'));row.append(th);
 cols.forEach(r=>{const td=el('td'),claims=list(cells.get(JSON.stringify([c.id,r.id]))?.claims),visible=claims.filter(cl=>!state.kind||cl.kind===state.kind||cl.kind==='U');
 if(!claims.length){td.className='ir-kind-U';td.append(tag('U'),p('本次范围未取得足以判断的证据。','ir-claim-text'));}
 else if(!visible.length){td.className='ir-filtered';td.append(p('当前来源筛选未展示此格证据。','ir-claim-text'));}
 else{const kinds=new Set(visible.map(cl=>cl.kind));if(kinds.size===1)td.className='ir-kind-'+visible[0].kind;visible.forEach(cl=>{const box=el('div','ir-claim');box.append(tag(cl.kind),p(cl.text,'ir-claim-text'),refs(cl.source_ids));td.append(box);});}row.append(td);
 });tbody.append(row);});table.append(tbody);matrixHost.replaceChildren(table);
}
function module(route,key,title){
 const m=route[key],section=el('section','ir-module');section.append(el('h4','',title));
 if(!m){section.append(p('本次尚未形成该项研究。'));return section;}
 section.append(p(m.summary||m.reason,'ir-module-summary'),refs(m.source_ids));if(m.status==='unknown')section.append(el('span','ir-unknown','证据不足 · 保留未知'));
 field(section,'成立条件',m.conditions);field(section,'尚待确认',m.unknowns);if(m.reason&&m.reason!==m.summary)field(section,'原因',m.reason);
 if(key==='transfer')list(m.candidates).forEach(item=>{const card=el('div','ir-item');card.append(el('h5','',item.domain));for(const [f,l] of [['shared_function','共同功能'],['mechanism','借鉴机制'],['differences','场景差异'],['adaptation','迁移改动'],['test','验证方式']])field(card,l,item[f]);card.append(refs(item.source_ids));section.append(card);});
 if(key==='forecast')list(m.hypotheses).forEach(item=>{const card=el('div','ir-item');card.append(el('h5','',item.horizon+' · 条件预测'));for(const [f,l] of [['change','可能变化'],['driver','支持因素'],['blocker','阻碍因素'],['trigger','观察触发信号'],['falsifier','推翻或修正条件']])field(card,l,item[f]);card.append(refs(item.source_ids));section.append(card);});
 if(key==='maturity'){field(section,'评价尺度',m.rubric);list(m.dimensions).forEach(item=>{const card=el('div','ir-item');card.append(el('h5','',item.name+' · '+item.stage));field(card,'依据',item.basis);if(item.status==='unknown')field(card,'待补证',item.reason);card.append(refs(item.source_ids));section.append(card);});}
 if(key==='selection'){field(section,'应用场景',m.scenario);list(m.criteria).forEach(item=>{const card=el('div','ir-item');card.append(el('h5','',item.name));field(card,'重要程度',item.priority);field(card,'测量或判断方法',item.measure);if(item.status==='unknown')field(card,'待补证',item.reason);card.append(refs(item.source_ids));section.append(card);});field(section,'选择意见',m.recommendation);field(section,'改变选择的条件',m.reversal);}
 return section;
}
function renderRoutes(){
 const routes=data.routes.filter(r=>r.major&&(!state.route||r.id===state.route));routeHost.replaceChildren();if(!routes.length){routeHost.append(p('当前选择下没有纳入重点研究的技术路线。'));return;}
 routes.forEach((r,i)=>{const card=el('details','ir-route');card.open=routes.length===1;const summary=el('summary');summary.append(el('span','ir-route-number',String(i+1).padStart(2,'0')),el('strong','',r.name),el('span','ir-expand','展开研究'));card.append(summary);
 const content=el('div','ir-route-content');field(content,'研究问题',r.problem);field(content,'结构与工作过程',r.mechanism);field(content,'选为主要路线的依据',r.selection_reason);content.append(refs(r.source_ids));
 const modules=el('div','ir-module-grid');[['transfer','跨行业借鉴'],['forecast','技术演进预测'],['maturity','成熟度评价'],['selection','选型框架']].forEach(([k,l])=>modules.append(module(r,k,l)));content.append(modules);card.append(content);routeHost.append(card);});
}
function renderTasks(){
 const role=document.body.dataset.readerRole||'management',orders={management:['project','profile','competition','selection','forecast'],rd:['selection','forecast','competition','profile','project'],ip:['competition','profile','selection','project','forecast']},order=orders[role]||orders.management;
 roleNote.textContent=({management:'管理层阅读：先看研究问题、立项条件与公司的相对位置。',rd:'研发阅读：先看路线取舍、迁移条件与需要验证的机制。',ip:'知识产权阅读：先看公司间的证据差异，再沿来源核查具体申请与版本。'}[role]||'')+' 三种视角共用同一套事实与证据。';
 tasksHost.replaceChildren();[...list(data.tasks)].sort((a,b)=>order.indexOf(a.kind)-order.indexOf(b.kind)).forEach(t=>{const card=el('article','ir-task');card.dataset.kind=t.kind;card.append(el('span','ir-task-kind',tasks[t.kind]||t.kind),el('h3','',t.question),p(t.answer,'ir-task-answer'));if(t.status==='unknown')card.append(el('span','ir-unknown','尚不能形成确定结论'));field(card,'适用条件',t.conditions);field(card,'待补资料',t.reason);card.append(refs(t.source_ids));tasksHost.append(card);});
}
function renderJurisdictions(){
 const cases=list(data.jurisdiction_cases);if(!cases.length)return;
 host.append(el('h3','ir-block-title','选定案例的同族地域记录'),p('仅展示所选案例的已查同族记录，不代表公司整体布局、目标市场或有效权利；国家登记成员不重复计为独立发明。'));
 const codes=[...new Set(cases.flatMap(c=>list(c.authorities).map(a=>a.code)))],wrap=el('div','ir-scroll');wrap.tabIndex=0;wrap.setAttribute('aria-label','选定案例同族地域记录，可横向滚动');
 const table=el('table','ir-jurisdictions'),head=el('thead'),tr=el('tr'),first=el('th','','仅选定案例');first.scope='col';tr.append(first);codes.forEach(code=>{const th=el('th','',code);th.scope='col';tr.append(th);});head.append(tr);table.append(head);const body=el('tbody');
 cases.forEach(c=>{const row=el('tr'),th=el('th','ir-company');th.scope='row';th.append(el('strong','',c.label),el('small','','观察于 '+c.observed_at),refs(c.source_ids));row.append(th);
 codes.forEach(code=>{const a=list(c.authorities).find(x=>x.code===code),td=el('td'),status=a?.status||'unknown';td.append(el('span','ir-geo-symbol',status==='simple'?'●':status==='extended'?'△':'?'),el('span','ir-geo-label',status==='simple'?'简单同族记录':status==='extended'?'扩展同族记录':'未见 / 未查'));if(list(a?.member_publication_numbers).length)td.append(p(a.member_publication_numbers.join('、'),'ir-member-numbers'));if(a?.note)td.append(p(a.note));if(a)td.append(refs(a.source_ids));row.append(td);});body.append(row);});
 table.append(body);wrap.append(table);host.append(wrap,p('● 简单同族记录中存在；△ 仅扩展同族记录中存在；? 本次未见或未查。以上符号均不表示授权、有效或保护范围。'));
}
renderTasks();renderMatrix();renderRoutes();renderJurisdictions();
new MutationObserver(records=>{if(records.some(r=>r.attributeName==='data-reader-role'))renderTasks();}).observe(document.body,{attributes:true,attributeFilter:['data-reader-role']});
window.PP_INDUSTRY_VIEW={state,sourceDialog,renderMatrix,renderRoutes,renderTasks};
}());

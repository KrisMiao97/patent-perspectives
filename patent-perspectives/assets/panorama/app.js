/* Original patent-perspectives offline viewer. No network data fetches or external runtime. */
(function () {
  'use strict';
  const raw = window.PP_DATA && typeof window.PP_DATA === 'object' ? window.PP_DATA : {};
  const asArray = value => Array.isArray(value) ? value : value == null || value === '' ? [] : [value];
  const asObject = value => value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  const text = value => {
    if (value == null || value === '') return '未知';
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value);
    if (Array.isArray(value)) return value.map(text).join('；');
    for (const key of ['text', 'label', 'name', 'summary', 'body', 'value']) if (value[key] != null) return text(value[key]);
    return Object.entries(value).map(([key, item]) => labelFor(key) + '：' + text(item)).join('；');
  };
  const knownText = value => value == null || value === '' || value === 'unknown' ? '未知' : text(value);
  const nfmt = value => new Intl.NumberFormat('zh-CN').format(Number(value) || 0);
  const $ = id => document.getElementById(id);
  const el = (tag, className, value) => { const node = document.createElement(tag); if (className) node.className = className; if (value !== undefined) node.textContent = text(value); return node; };
  const add = (node, ...children) => { children.flat().forEach(child => { if (child != null) node.append(child); }); return node; };
  const button = (label, className, action) => { const node = el('button', className, label === '' ? undefined : label); node.type = 'button'; if (action) node.addEventListener('click', action); return node; };
  const replace = (node, ...children) => node.replaceChildren(...children.flat().filter(Boolean));
  const labels = {
    summary:'技术概述', application_field:'应用领域', technical_problem:'技术问题', technical_means:'技术手段', components:'组成要素', relationships:'组成关系', steps:'步骤与控制过程', conditions:'适用条件与限定', claimed_effects:'文献宣称的功效', effects:'文献宣称的功效', limitations:'未知与限制', primary_module:'技术大类', tags:'交叉技术标签', role_notes:'角色解读', confidence:'分析置信信息', evidence_ids:'证据引用',
    company:'研究对象', run_id:'运行编号', as_of_date:'数据截止日', started_at:'开始时间', status:'运行状态', scope:'研究范围', coverage:'覆盖情况', completion:'完成情况', entities:'主体', source:'来源', sources:'来源', query:'检索式', queries:'检索记录', query_partitions:'查询分片', retrieval_date:'采集日期', retrieved_at:'采集时间', methodology:'统计方法', unknown:'未知',
    entity_count:'主体数', patent_count:'申请数', application_count:'独立申请数', unique_applications:'独立申请数', documents:'文献数', technical_total:'技术申请数', technical_completed:'技术解读完成数', fulltext_completed:'合格全文数', description_count:'说明书依据数', claims_count:'权利要求依据数', pending:'待处理数', design_total:'外观设计数', legal_status_verified:'法律状态已核验数', family_covered:'同族覆盖数', images_covered:'图片覆盖数', percent:'比例', current:'当前持有', historical:'历史申请', include:'纳入', exclude:'排除', start_date:'起始日期', end_date:'截止日期', database:'数据库', jurisdictions:'地域', countries:'国家或地区', evidence:'证据', evidence_references:'证据引用', notes:'说明', parent:'上级主体', name:'名称', id:'标识', original_assignees:'原始申请人', current_assignees:'当前申请人', source_url:'来源链接', relation:'关系', group_members:'集团成员', scope_basis:'边界依据', type:'类型', basis:'依据', reason:'理由', checked_at:'核验时间', verified_at:'核验时间', family:'同族', citations:'引用', images:'图片', legal_status:'法律状态', description:'说明书', claims:'权利要求', source_type:'来源类型', locator:'原文位置', publication_number:'文献号', application_number:'申请号', evidence_id:'证据编号', title:'标题', total:'总计', complete:'完成', incomplete:'未完成', blocked:'受阻', verified:'已核验', unverified:'未核验', required:'要求', available:'可得', missing:'缺失', count:'数量', fraction:'占比', ratio:'比例', technical:'技术专利', excluded:'排除', design:'外观设计', patents:'专利', failed:'失败', passed:'通过', description_fulltext:'说明书全文', claims_fulltext:'权利要求全文',
    full_text:'完整技术文本', semantic_analysis:'技术分析', legal:'法律状态', searches:'检索对账', claims_only:'仅权利要求', modules:'技术大类', source_documents:'来源文献', analyzed:'已分析', awaiting:'待处理', verified_entities:'已核验主体', applications:'独立申请数', publications:'文献数', technical_applications:'技术申请数', design_applications:'外观设计申请数', unknown_type_applications:'类型未知申请数', technical_fulltext:'文本候选（已通过结构检查）', technical_analyzed:'技术解读完成数', description_based:'说明书依据数', claims_based:'完整权利要求依据数', technical_completion:'技术解读完成率（%）', completed_queries:'已完成检索数', legal_status_known:'状态可汇总的申请数', legal_status_observed_publications:'已取得状态的文献数', legal_status_conflict_applications:'文献状态冲突的申请数', family_observed_publications:'已取得同族记录的文献数', abstract_image_observed_publications:'已取得摘要图记录的文献数', abstract_image_local_publications:'已核验本地摘要图的文献数', rejected_documents:'因正文缺陷停止使用的版本数', document_rejection_reviews:'正文缺陷审阅记录数', invalidated_analyses:'已失效分析数', retained_evidence:'留存的全部原文证据数', scope_confirmed:'研究范围已确认', claim_number:'权利要求编号', paragraph:'说明书段落', paragraph_number:'说明书段落号', page:'页码', figure:'图号', figure_number:'附图编号', design_mode:'外观设计处理方式', technical_types:'技术专利类型', synthetic:'合成测试标记', count_unit:'统计单位',
    fields:'官方原始字段', acquired_at:'取得时间', sha256:'原件SHA256', reviewer:'审阅者', mapping_id:'映射编号', member_application_id:'国家登记成员', canonical_filing_application_id:'规范独立申请', application_delta:'独立申请计数调整', technical_application_delta:'技术申请计数调整', raw_included_application_records:'范围内原始申请 / 登记记录数', raw_technical_application_records:'原始技术申请 / 登记记录数', independent_application_units:'规范独立申请单位数', independent_technical_application_units:'规范独立技术申请单位数', registration_member_records:'国家登记成员数', registration_count_bridge:'原始记录至独立单位桥接', source_rows_preserved:'原始记录保留', member_legal_owner_and_text_independent:'成员权属、状态和文本独立', table_id:'官方表格标识', row_index:'行索引（从0开始）', field_cell:'字段列标识', value_cell:'原值列标识', field:'字段', value:'原值'
  };
  function labelFor(key) { return labels[key] || String(key).replace(/_/g, ' '); }
  const run = asObject(raw.run);
  const company = text(run.company || '竞争对手');
  const patents = asArray(raw.patents).filter(item => item && item.id != null).map(item => ({ ...item, id:String(item.id) }));
  const byId = new Map(patents.map(item => [item.id,item]));
  const registrationMembers = asArray(raw.registration_members);
  const jurisdictions = patent => [...new Set([...asArray(patent.jurisdictions),patent.authority].filter(Boolean).map(String))];
  const membersOf = patent => asArray(patent.registration_members).length ? asArray(patent.registration_members) : registrationMembers.filter(member=>String(member.canonical_filing_application_id)===patent.id);
  const modules = asArray(raw.modules);
  const moduleNames = new Map(modules.map(item => [String(item.id), text(item.label || item.id)]));
  const insights = asArray(raw.insights);
  const relations = asArray(raw.relations);
  const details = new Map(Object.entries(asObject(window.PP_DETAILS)));
  const shardPromises = new Map();
  const state = { role:'management', library:'technical', graphMode:'products', search:'', module:'', entity:'', authority:'', type:'', status:'', basis:'', quality:'', from:'', to:'', sort:'filing-desc', page:1, zoom:1, expanded:null };
  const roleInfo = {
    management:{ label:'管理层', description:'看清公开专利中的技术布局、持续变化与值得进一步研究的方向。', focus:['技术组合与布局','地域与时间变化','有条件的观察与建议'] },
    rd:{ label:'研发', description:'理解文献披露的技术问题、实现方案、限定条件与待验证问题。', focus:['技术问题与实现手段','结构、步骤与条件','方案比较与验证线索'] },
    ip:{ label:'专利工程师', description:'定位值得优先阅读的申请、权利要求、关联案件及待核查证据。', focus:['权利要求与文本版本','同族、引用及案件关系','重点阅读与核查任务'] }
  };
  let filtered = [];
  let dialogToken = 0;
  let lastFocused = null;
  let toastTimer;
  const typeLabel = value => ({ invention:'发明', utility:'实用新型', utility_model:'实用新型', 'utility model':'实用新型', design:'外观设计', 'industrial design':'外观设计' }[String(value || '').toLowerCase()] || knownText(value));
  const isDesign = patent => /design|外观/i.test(String(patent.patent_type || ''));
  const isTechnical = patent => /invention|utility|发明|实用新型/i.test(String(patent.patent_type || ''));
  const complete = patent => /^(complete|completed|done|已完成|完成)$/i.test(String(patent.analysis_status || ''));
  const statusValue = patent => text(patent.legal_status || 'unknown');
  const statusLabel = value => ({'有效':'授权有效','审中':'申请中 / 审查中', unknown:'未知', granted:'已授权', pending:'审查中', expired:'期限届满', lapsed:'权利终止', withdrawn:'已撤回', rejected:'已驳回', published:'已公开', active:'登记为存续', invalidated:'已被宣告无效', partially_invalidated:'部分被宣告无效' }[String(value).toLowerCase()] || knownText(value));
  const basisLabel = value => ({ description:'说明书', specification:'说明书', full_description:'说明书', claims:'完整权利要求', claims_only:'仅完整权利要求', claims_fallback:'完整权利要求回退', abstract:'仅摘要', none:'无合格全文', unknown:'未知' }[String(value || 'unknown').toLowerCase()] || knownText(value));
  const isClaimsBasis = patent => /claim|权利要求/i.test(String(patent.text_basis || ''));
  const isDescriptionBasis = patent => /description|specification|说明书/i.test(String(patent.text_basis || ''));
  const moduleLabel = value => moduleNames.get(String(value)) || knownText(value);
  const assignees = patent => [...new Set([...asArray(patent.original_assignees),...asArray(patent.current_assignees)].map(text))];
  const short = (value, limit=18) => { const string = text(value); return Array.from(string).length > limit ? Array.from(string).slice(0,limit).join('') + '…' : string; };
  const percent = (numerator, denominator) => denominator ? Math.round(numerator / denominator * 100) + '%' : '—';
  function safeUrl(value) {
    if (typeof value !== 'string' || !/^https?:\/\//i.test(value) || /[\u0000-\u0020]/.test(value)) return null;
    try { const url = new URL(value); return /^https?:$/.test(url.protocol) && !url.username && !url.password ? url.href : null; } catch (_) { return null; }
  }
  function safeLocalImage(value) { return typeof value === 'string' && !value.includes('..') && !/[\\:%?#\u0000-\u001f]/.test(value) && /^(?:[a-zA-Z0-9_ -]+\/)*[a-zA-Z0-9_ .@%()+-]+\.(?:png|jpe?g|gif|webp)$/i.test(value) ? value : null; }
  function safeLocalPdf(value) { return typeof value === 'string' && /^source-documents\/[a-f0-9]{64}\.pdf$/.test(value) ? value : null; }
  function safeShard(value) { return typeof value === 'string' && /^data\/(?:[a-zA-Z0-9_-]+\/)*[a-zA-Z0-9_-]+\.js$/.test(value) ? value : null; }
  function externalLink(url, label='打开原始来源 ↗') { const safe = safeUrl(url); if (!safe) return null; const node = el('a','source-link',label); node.href = safe; node.target = '_blank'; node.rel = 'noopener noreferrer'; return node; }
  function chip(label, variant='') { return el('span','chip ' + variant,label); }
  function empty(title, note) { return add(el('div','empty-state'),el('div','empty-icon','◌'),el('strong','',title),el('p','',note)); }
  function showToast(message) { $('toast').textContent = message; $('toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => {$('toast').hidden=true;},4500); }
  function hasFilters() { return ['search','productGroup','productLine','module','entity','authority','type','status','basis','quality','from','to'].some(key => !!state[key]); }
  function latestSelection(value=run) {
    const selection=asObject(asObject(value.scope).selection);
    return selection.kind==='latest_technical_applications'?selection:null;
  }
  function selectionLabel(selection) {
    const count=Number.isInteger(selection.count)&&selection.count>0?String(selection.count):'数量未知';
    return '按申请日最新的'+count+'件技术申请';
  }
  function validScopeDate(item) {
    if(typeof item!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(item))return null;
    const date=new Date(item+'T00:00:00Z');
    return !Number.isNaN(date.getTime())&&date.toISOString().slice(0,10)===item?item:null;
  }
  function scopeSummary(value=run) {
    const scope=asObject(value.scope),coverage=asObject(value.coverage),selection=latestSelection(value),parts=[];
    const region=scope.jurisdictions;
    if(region==='all')parts.push('全球公开记录');
    else if(region){
      const regions=asArray(region).map(item=>{
        const code=String(item).toUpperCase();
        const names={EP:'欧洲专利（EP）',WO:'国际公开（WO）',EU:'欧盟'};
        if(names[code])return names[code];
        if(!/^[A-Z]{2}$/.test(code))return '地域未知';
        try{return new Intl.DisplayNames(['zh-CN'],{type:'region'}).of(code) || code;}catch(_){return code;}
      });
      parts.push([...new Set(regions)].join('、'));
    }else parts.push('地域未知');
    const kinds=asArray(scope.technical_types).filter(item=>['invention','utility_model','design'].includes(item)).map(typeLabel);
    if(!selection&&scope.design_mode==='catalogue'&&!kinds.includes('外观设计'))kinds.push('外观设计另列');
    parts.push(kinds.length?kinds.join('、'):'专利类型未知');
    if(selection){
      parts.push(selectionLabel(selection));
      const oldest=validScopeDate(selection.oldest_filing_date),latest=validScopeDate(selection.latest_filing_date);
      parts.push(oldest&&latest&&oldest<=latest?'实际申请日 '+oldest+' 至 '+latest:'实际申请日期范围未知');
      parts.push(selection.tie_break==='application_id_asc'?'同日按申请标识升序':'同日排序规则待核查');
      parts.push('外观设计不占名额');
      return parts.join(' · ');
    }
    const candidate=scope.analysis_window || value.analysis_window || coverage.analysis_window;
    if(candidate){
      const window=asObject(candidate),from=validScopeDate(window.from),through=validScopeDate(window.through);
      parts.push(window.basis==='filing_date'&&from&&through&&from<=through?'申请日 '+from+' 至 '+through:'申请日期范围未知');
    }else if(Object.prototype.hasOwnProperty.call(scope,'start_date')&&scope.start_date===null)parts.push('申请时间不设起始年份');
    else if(typeof scope.start_date==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(scope.start_date))parts.push('申请日自 '+scope.start_date+' 起');
    else parts.push('申请日期范围未知');
    return parts.join(' · ');
  }
  function initialize() {
    document.title = company + ' · 专利棱镜｜企业专利三视角分析';
    $('page-title').textContent=company+'专利报告';
    $('breadcrumb-company').textContent = company;
    $('as-of').textContent = '数据截止：' + knownText(run.as_of_date);
    $('scope-chip').textContent = report.settings.analysis_label;
    $('scope-chip').title = scopeSummary();
    const accepted = run.status === 'complete',selection=latestSelection();
    $('run-badge').textContent=report.settings.analysis_label;
    $('run-badge').classList.toggle('incomplete', !accepted);
    $('status-notice').classList.toggle('completed',accepted);
    $('status-notice').textContent = report.settings.coverage_note;
    if (!run.company) $('status-notice').textContent = '专利资料尚未加载，请保留完整报告文件夹后重新打开。';
    $('technical-total').textContent = nfmt(patents.filter(p => !isDesign(p)).length);
    $('design-total').textContent = nfmt(patents.filter(isDesign).length);
    $('footer-run').textContent = '公开记录截至 '+run.as_of_date+' · 状态观察：'+report.settings.status_observed_at;
    setupFilters();
    document.querySelectorAll('.role-button').forEach(node => node.addEventListener('click',() => { state.role=node.dataset.role; renderRole(); renderAnalysis(); renderProductFacts(); }));
    document.querySelectorAll('#library-mode button').forEach(node => node.addEventListener('click',() => { state.library=node.dataset.mode; state.type=''; state.page=1; state.expanded=null; $('filter-type').value=''; if(state.library==='design'){state.quality='';$('filter-quality').value='';} render(); }));
    document.querySelectorAll('#graph-mode button').forEach(node => node.addEventListener('click',() => {state.graphMode=node.dataset.mode; state.zoom=1; renderGraph(); updatePressed('#graph-mode','mode',state.graphMode);}));
    $('search').addEventListener('input',() => {state.search=$('search').value.trim(); state.page=1; render();});
    ['from','to'].forEach(key => $('year-'+key).addEventListener('input',() => {state[key]=$('year-'+key).value; state.page=1; render();}));
    $('sort').addEventListener('change',() => {state.sort=$('sort').value; state.page=1; render();});
    $('clear-filters').addEventListener('click',clearFilters);
    $('page-prev').addEventListener('click',() => {if(state.page>1){state.page--;renderList();$('patent-library').scrollIntoView({block:'start'});}});
    $('page-next').addEventListener('click',() => {if(state.page<Math.ceil(filtered.length/50)){state.page++;renderList();$('patent-library').scrollIntoView({block:'start'});}});
    $('graph-reset').addEventListener('click',() => {state.expanded=null;state.zoom=1;renderGraph();});
    $('zoom-in').addEventListener('click',() => {state.zoom=Math.min(2.4,state.zoom+.2);updateViewBox();});
    $('zoom-out').addEventListener('click',() => {state.zoom=Math.max(.7,state.zoom-.2);updateViewBox();});
    ['scope-button','coverage-button','footer-source'].forEach(id => $(id).addEventListener('click',openScope));
    $('help-button').addEventListener('click',openHelp);
    $('dialog-close').addEventListener('click',closeDialog);
    $('detail-dialog').addEventListener('click',event => {if(event.target===$('detail-dialog')){const bounds=$('detail-dialog').getBoundingClientRect();if(event.clientX<bounds.left||event.clientX>bounds.right||event.clientY<bounds.top||event.clientY>bounds.bottom)closeDialog();}});
    $('detail-dialog').addEventListener('close',() => {dialogToken++;if(lastFocused && lastFocused.isConnected)lastFocused.focus();});
    document.addEventListener('keydown',event => { if(event.key==='/' && !$('detail-dialog').open && !['INPUT','SELECT','TEXTAREA'].includes(document.activeElement.tagName)){event.preventDefault();$('search').focus();$('patent-library').scrollIntoView({block:'start'});} });
    render();
  }
  function updatePressed(selector,key,value) {document.querySelectorAll(selector+' button').forEach(node => {const active=node.dataset[key]===value;node.classList.toggle('active',active);node.setAttribute('aria-pressed',String(active));});}
  function setupFilters() {
    const unique = values => [...new Set(values.filter(Boolean).map(String))].sort((a,b)=>a.localeCompare(b,'zh-CN'));
    const setOptions = (id,items,formatter) => items.forEach(value=>{const node=el('option','',formatter(value));node.value=value;$(id).append(node);});
    setOptions('filter-module',unique(patents.map(p=>p.primary_module)),moduleLabel);
    setOptions('filter-entity',unique(patents.flatMap(assignees)),text);
    setOptions('filter-authority',unique(patents.flatMap(jurisdictions)),knownText);
    setOptions('filter-type',unique(patents.filter(p=>!isDesign(p)).map(p=>p.patent_type)),typeLabel);
    setOptions('filter-status',unique(patents.map(statusValue)),statusLabel);
    setOptions('filter-basis',unique(patents.map(p=>p.text_basis || 'unknown')),basisLabel);
    ['module','entity','authority','type','status','basis','quality'].forEach(key => $('filter-'+key).addEventListener('change',() => {state[key]=$('filter-'+key).value;state.page=1;if(key==='module')state.expanded=null;render();}));
  }
  function clearFilters() {['search','productGroup','productLine','module','entity','authority','type','status','basis','quality','from','to'].forEach(key=>{state[key]='';});$('search').value='';['module','entity','authority','type','status','basis','quality'].forEach(key=>{$('filter-'+key).value='';});$('year-from').value='';$('year-to').value='';state.page=1;state.expanded=null;render();}
  function selectPatents() {
    const query = state.search.toLocaleLowerCase();
    return patents.filter(p=>{
      if(isDesign(p)!==(state.library==='design'))return false;
      if(state.productGroup&&productOf(p).group!==state.productGroup)return false;
      if(state.productLine&&productOf(p).line!==state.productLine)return false;
      if(state.module && String(p.primary_module)!==state.module)return false;
      if(state.entity && !assignees(p).includes(state.entity))return false;
      if(state.authority && !jurisdictions(p).includes(state.authority))return false;
      if(state.type && String(p.patent_type)!==state.type)return false;
      if(state.status && statusValue(p)!==state.status)return false;
      if(state.basis && String(p.text_basis || 'unknown')!==state.basis)return false;
      if(state.quality && (state.quality==='complete')!==complete(p))return false;
      const year=String(p.filing_date || '').slice(0,4);
      if((state.from || state.to) && !/^\d{4}$/.test(year))return false;
      if(state.from && Number(year)<Number(state.from))return false;
      if(state.to && Number(year)>Number(state.to))return false;
      if(query && ![productOf(p).group,productOf(p).line,p.title,p.id,p.application_number,...asArray(p.publication_numbers),...assignees(p),moduleLabel(p.primary_module),...asArray(p.tags),...membersOf(p).flatMap(member=>[member.id,member.application_number,...asArray(member.publication_numbers)])].map(v=>v == null ? '' : text(v)).join(' ').toLocaleLowerCase().includes(query))return false;
      return true;
    }).sort((a,b)=>{
      if(state.sort==='title')return text(a.title).localeCompare(text(b.title),'zh-CN') || a.id.localeCompare(b.id);
      const ad=String(a.filing_date || ''),bd=String(b.filing_date || '');
      if(!ad && bd)return 1;if(ad && !bd)return -1;
      return (state.sort==='filing-asc'?ad.localeCompare(bd):bd.localeCompare(ad)) || a.id.localeCompare(b.id);
    });
  }
  function render() {filtered=selectPatents();state.page=Math.min(state.page,Math.max(1,Math.ceil(filtered.length/50)));renderMetrics();renderRole();renderGraph();renderFilters();renderList();renderTimelines();renderProductSelectors();renderProductEvents();renderProductFacts();renderRevision06();updatePressed('#library-mode','mode',state.library);$('filter-type').disabled=state.library==='design';$('filter-quality').disabled=state.library==='design';}
  function renderFilters() {
    const values=[['productGroup',state.productGroup],['productLine',state.productLine],['search','搜索：'+state.search],['module',moduleLabel(state.module)],['entity',state.entity],['authority',state.authority],['type',typeLabel(state.type)],['status',statusLabel(state.status)],['basis',basisLabel(state.basis)],['quality',state.quality==='complete'?'技术解读已完成':'技术解读未完成'],['from','申请年份 ≥ '+state.from],['to','申请年份 ≤ '+state.to]].filter(([key])=>state[key]);
    $('active-filters').hidden=!values.length;
    replace($('active-filters'),values.map(([key,label])=>{const node=button(label,'filter-chip',()=>{state[key]='';if(key==='search')$('search').value='';else if(key==='from'||key==='to')$('year-'+key).value='';else if(key==='productGroup'){state.productLine='';}else if(key!=='productLine') $('filter-'+key).value='';state.page=1;render();});node.append(el('span','','×'));node.setAttribute('aria-label','移除筛选：'+label);return node;}));
  }
  function renderList() {
    const total=filtered.length,start=(state.page-1)*50,pageCount=Math.max(1,Math.ceil(total/50));
    replace($('results-count'),el('strong','',nfmt(total)),document.createTextNode(' 件独立申请'+(hasFilters()?' · 筛选结果':' · 当前目录')));
    const selectedMembers=filtered.flatMap(membersOf).filter(member=>!state.authority || String(member.authority)===state.authority);
    if(selectedMembers.length)$('results-count').append(document.createTextNode(' · 关联 '+nfmt(selectedMembers.length)+' 条'+(state.authority?' '+state.authority:'')+'国家登记成员记录'));
    $('patent-list').classList.toggle('design-list',state.library==='design');
    replace($('patent-list'),total?filtered.slice(start,start+50).map(renderPatentRow):empty('没有匹配的申请',patents.length?'调整搜索词或筛选条件，也可以重置筛选。':'暂无可展示的专利目录。'));
    $('page-info').textContent=total?'第 '+nfmt(start+1)+'–'+nfmt(Math.min(start+50,total))+' 件 / 共 '+nfmt(total)+' 件 · '+state.page+' / '+pageCount+' 页':'0 件申请';
    $('directory-jump').value=String(state.page);$('directory-jump').max=String(pageCount);
    $('page-prev').disabled=state.page<=1;$('page-next').disabled=state.page>=pageCount;
    $('library-footnote').textContent=state.library==='design'?'外观设计独立列示，不计入技术全文分析完成率。图片缺失时显示“暂无本地图片”；详情保留可获得的原始来源。':'每页 50 件独立申请单位。地域筛选包含官方确认的国家登记成员，成员不另计独立申请；状态、主体与申请年份筛选使用独立单位自身的信息。各成员自己的权属、状态及原文缺件在详情中单列。申请年份筛选会排除日期未知的记录。';
  }
  function renderPatentRow(p) {
    const row=el('article','patent-row'),main=el('div','patent-main');
    if(isDesign(p)){
      const thumb=el('div','design-thumb'),first=asArray(p.images)[0],imgPath=safeLocalImage(typeof first==='string'?first:first && (first.path || first.src));
      if(imgPath){const image=el('img');image.src=imgPath;image.alt=text(first.alt || first.caption || p.title);image.loading='lazy';image.addEventListener('error',()=>replace(thumb,document.createTextNode('本地图片不可用')));thumb.append(image);}else thumb.textContent='暂无本地图片 · 可在详情核查来源';
      main.append(thumb);
    }
    const typeVariant=isDesign(p)?'design':/utility|实用/i.test(String(p.patent_type))?'utility':'';
    const topline=add(el('div','patent-topline'),el('span','patent-number',p.application_number || p.id),chip(typeLabel(p.patent_type),typeVariant),chip(statusLabel(statusValue(p)),'state'));
    if(!complete(p))topline.append(chip('技术解读待补齐','pending'));

    if(membersOf(p).length)topline.append(chip('登记成员 '+membersOf(p).map(member=>member.authority).join(' / '),'state'));
    main.append(topline,button(p.title || '标题未知','patent-title',()=>openPatent(p.id)));
    const people=assignees(p);
    main.append(add(el('div','patent-meta'),el('span','',people.length?people.join('；'):'申请主体未知'),el('span','','申请 '+knownText(p.filing_date)),el('span','',knownText(p.authority))));
    const tags=[p.primary_module?moduleLabel(p.primary_module):null,...asArray(p.tags)].filter(Boolean).slice(0,5);
    if(tags.length)main.append(add(el('div','patent-tags'),tags.map(value=>el('span','',value))));
    const action=button('详情','row-action',()=>openPatent(p.id));action.append(el('span','',' ↗'));action.setAttribute('aria-label','查看 '+text(p.title || p.application_number)+' 的详情');
    const product=productOf(p);main.append(add(el('div','product-lineage'),el('span','',product.group+' / '+product.line),button('产品归类依据','text-button',()=>productEvidence(p.id))));
    return add(row,main,action);
  }
  window.PP_registerDetails = function (map) { Object.entries(asObject(map)).forEach(([id,value])=>{if(value && typeof value==='object')details.set(String(id),value);}); };
  async function loadDetail(id) {
    if(details.has(id))return details.get(id);
    const index=byId.get(id);
    if(!index)throw new Error('当前索引中没有该申请。');
    const candidate=index.detail_shard || asObject(raw.detail_shards)[id];
    const path=safeShard(asObject(raw.detail_shards)[candidate] || candidate);
    if(!path)throw new Error('该申请暂无可用的本地详情。');
    if(!shardPromises.has(path))shardPromises.set(path,new Promise((resolve,reject)=>{const script=document.createElement('script');script.src=path;script.async=true;const timeout=setTimeout(()=>{script.remove();reject(new Error('本地详情读取超时，请确认 data 文件夹完整。'));},20000);script.onload=()=>{clearTimeout(timeout);resolve();};script.onerror=()=>{clearTimeout(timeout);script.remove();reject(new Error('本地详情不可用。请确认已完整解压并保留目录结构。'));};document.head.append(script);}));
    await shardPromises.get(path);
    if(!details.has(id))throw new Error('未找到该申请的详情。');
    return details.get(id);
  }
  function showDialog(eyebrow) {lastFocused=document.activeElement;$('dialog-eyebrow').textContent=eyebrow;replace($('dialog-body'));if(!$('detail-dialog').open)$('detail-dialog').showModal();$('detail-dialog').scrollTop=0;return ++dialogToken;}
  function closeDialog() {$('detail-dialog').close();}
  function detailFact(label,value) {return add(el('div','fact-item'),el('small','',label),el('span','',knownText(value)));}
  async function openPatent(id,evidenceIds=[]) {
    id=String(id);const index=byId.get(id);if(!index){showToast('该申请未包含在当前索引中。');return;}
    const token=showDialog('PATENT / TRACEABLE EVIDENCE');
    const body=$('dialog-body');body.append(el('h2','',index.title || '专利详情'),el('p','','正在读取本地证据…'));
    let detail,error;
    try {detail=await loadDetail(id);}catch(caught){error=caught;detail={};}
    if(token!==dialogToken || !$('detail-dialog').open)return;
    renderPatentDetail({...index,...detail,id},evidenceIds,error);
  }
  function addEvidenceRefs(container,ids,onClick) {const values=asArray(ids);if(!values.length)return;container.append(add(el('div','evidence-links'),values.map(id=>button('证据 '+text(id),'evidence-ref',()=>onClick(String(id))))));}
  function analysisBlock(label,value,onEvidence) {
    const block=add(el('section','analysis-block'),el('h4','',label));
    if(Array.isArray(value)){const list=el('ul');value.forEach(item=>{const li=el('li','',text(item));addEvidenceRefs(li,asObject(item).evidence_ids,onEvidence);list.append(li);});block.append(list);}
    else{block.append(el('p','',knownText(value)));addEvidenceRefs(block,asObject(value).evidence_ids,onEvidence);}
    return block;
  }
  function renderPatentDetail(p,evidenceIds,error) {
    const body=$('dialog-body');replace(body,el('div','patent-number',p.application_number || p.id),el('h2','',p.title || '标题未知'));
    const badges=add(el('div','detail-chips'),chip(typeLabel(p.patent_type),isDesign(p)?'design':''),chip(statusLabel(statusValue(p)),'state'),chip(basisLabel(p.text_basis),isClaimsBasis(p)?'claims':''));
    if(!isDesign(p))badges.append(chip(complete(p)?'技术解读已完成':'技术解读未完成',complete(p)?'complete':'pending'));
    body.append(badges);
    if(error)body.append(el('div','detail-banner',error.message+' 当前仅显示索引中已有的事实；未加载的内容不记为完整证据。'));
    if(isClaimsBasis(p))body.append(el('div','detail-banner','本件技术解读以完整权利要求为主'+(asArray(asObject(p.analysis).support_documents).length?'，并按需补读同一公开号说明书的相关段落':'')+'。未明确披露的实施细节、技术问题或功效保留为未知。涉及授权保护范围时，还需核对对应授权版本。'));
    const tabs=el('div','detail-tabs'),content=el('div','detail-content');
    const tabItems=isDesign(p)?[['overview','著录信息'],['evidence','证据与原文'],['relations','关系与图片']]:[['overview','技术解读'],['evidence','证据与原文'],['claims','权利要求'],['relations','关系与图片']];
    tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','专利详情内容');body.append(tabs,content);
    const switchTab=(name,focusId)=>{tabs.querySelectorAll('button').forEach(node=>{const active=node.dataset.tab===name;node.classList.toggle('active',active);node.setAttribute('aria-selected',String(active));});replace(content);if(name==='overview')renderOverview(content,p,id=>switchTab('evidence',id));else if(name==='evidence')renderEvidence(content,p,focusId);else if(name==='claims')renderClaims(content,p,id=>switchTab('evidence',id));else renderRelations(content,p,id=>switchTab('evidence',id));};
    tabItems.forEach(([key,label])=>{const node=button(label,'',()=>switchTab(key));node.dataset.tab=key;node.setAttribute('role','tab');node.setAttribute('aria-selected','false');tabs.append(node);});
    const matching=asArray(p.evidence).find(item=>evidenceIds.map(String).includes(String(item.id)));
    switchTab(matching?'evidence':'overview',matching && String(matching.id));
  }
  function renderOverview(container,p,onEvidence) {
    container.append(add(el('div','detail-facts'),detailFact('原始申请人',asArray(p.original_assignees).length?asArray(p.original_assignees).map(text).join('；'):null),detailFact('当前申请人 / 登记主体',asArray(p.current_assignees).length?asArray(p.current_assignees).map(text).join('；'):null),detailFact('申请地域',p.authority),detailFact('申请日',p.filing_date),detailFact('公开日',p.publication_date),detailFact('文献版本',asArray(p.publication_numbers).length?asArray(p.publication_numbers).map(text).join('；'):null)));
    renderLegalObservations(container,p);
    renderRegistrationMembers(container,p);
    if(isDesign(p)){container.append(el('p','','外观设计独立列示。请在“关系与图片”中查看可得视图，未取得的图片不补造。'));return;}
    const analysis=asObject(p.analysis),keys=Object.keys(analysis).filter(key=>!['evidence_ids','primary_module','tags','role_notes','confidence','limitations','document_id','text_basis','support_documents'].includes(key));
    if(!keys.length)container.append(empty('本件尚无结构化技术解读','待取得合格的完整说明书或完整权利要求，并完成逐件分析与证据绑定。'));
    else{
      const ordered=['summary','application_field','technical_problem','technical_means','components','relationships','steps','conditions','claimed_effects','effects'];
      keys.sort((a,b)=>(ordered.includes(a)?ordered.indexOf(a):100)-(ordered.includes(b)?ordered.indexOf(b):100));
      container.append(add(el('div','analysis-grid'),keys.map(key=>analysisBlock(labelFor(key),analysis[key],onEvidence))));
      addEvidenceRefs(container,analysis.evidence_ids,onEvidence);
    }
    const notes=asObject(analysis.role_notes)[state.role];if(notes){container.append(el('h3','',roleInfo[state.role].label+'视角'),analysisBlock('阅读提示',notes,onEvidence));}
    const limits=[...asArray(analysis.limitations),...asArray(p.limitations)];if(limits.length){container.append(el('h3','','未知与限制'),add(el('ul','limitations-list'),limits.map(value=>el('li','',value))));}
  }
  function renderRegistrationMembers(container,p) {
    const members=membersOf(p);if(!members.length)return;
    container.append(el('h3','','国家登记成员'),el('p','','以下成员经官方同记录身份字段确认，关联到本独立申请单位，保留自己的地域、著录、权属和法律观察。成员不增加独立申请或技术任务；本申请的原文与分析也不会冒充成员本件全文。'));
    members.forEach(member=>{
      const card=el('article','analysis-block registration-member-card');card.dataset.memberId=String(member.id);
      card.append(el('h4','',knownText(member.authority)+' · '+knownText(member.application_number)),add(el('div','detail-chips'),chip('国家登记成员','state'),chip('不另计独立申请','state')));
      card.append(add(el('div','detail-facts'),detailFact('成员文献标识',asArray(member.publication_numbers).join('；')),detailFact('成员自己的当前申请人 / 登记主体',asArray(member.current_assignees).join('；')),detailFact('成员自己的状态',statusLabel(statusValue(member))),detailFact('成员本件可展示完整文本',member.own_fulltext_available?'已取得本件文本，见下方版本':'未知 / 尚无可展示的合格全文'),detailFact('成员原始申请人',asArray(member.original_assignees).join('；')),detailFact('成员记录申请日',member.filing_date)));
      card.append(el('p','unknown-text','成员文献标识按原始提供者保留；登记映射本身不证明存在独立发布的该国公报。状态按本件来源单独展示，未同步给 '+knownText(p.authority)+'。'));
      renderLegalObservations(card,member);
      const mapping=asObject(member.identity_mapping),proof=asObject(mapping.validated_proof),register=asObject(proof.official_register),canonical=asObject(proof.canonical_filing_evidence);
      const source=el('details','document-block');source.append(el('summary','','官方身份依据与精确定位'));
      source.append(readableTable({fields:register.fields,acquired_at:register.acquired_at,sha256:register.sha256,reviewer:mapping.reviewer,basis:mapping.basis}));
      Object.entries(asObject(register.locators)).forEach(([field,location])=>source.append(el('h4','',field+' · 官方原文位置'),readableTable(location)));
      source.append(el('h4','','规范申请原文身份与定位'),readableTable({publication_number:canonical.publication_number,application_number:canonical.application_number,locator:canonical.locators}));
      const registerLink=externalLink(register.source_url,'查看本成员的官方登记记录 ↗');if(registerLink)source.append(registerLink);
      card.append(source);
      card.append(el('div','detail-banner','关联原文仍为 '+knownText(canonical.publication_number || asObject(member.canonical_evidence_link).publication_number)+'（'+knownText(asObject(member.canonical_evidence_link).source_authority)+'）。该链接用于阅读规范申请的原文，不代表已取得 '+knownText(member.authority)+' 本件原文，也不替代其权属或法律状态。'));
      const canonicalLink=externalLink(canonical.source_url,'阅读 '+knownText(canonical.publication_number)+' 的 EP 原文 ↗');if(canonicalLink)card.append(canonicalLink);
      asArray(member.documents).forEach(doc=>{const block=el('details','document-block');block.append(el('summary','',knownText(doc.publication_number)+' · '+labelFor(doc.document_type)+' · '+(doc.complete?'本件完整文本':'本件不完整 / 未交付')));if(doc.display_notice)block.append(el('p','detail-banner',doc.display_notice));if(doc.text)block.append(el('pre','document-text',doc.text));const link=externalLink(doc.source_url,'核验成员本件文本来源 ↗');if(link)block.append(link);card.append(block);});
      container.append(card);
    });
  }
  function renderLegalObservations(container,p) {
    const summary=asObject(p.legal_status_details),observations=asArray(summary.publication_observations);
    container.append(el('h3','','法律状态与取得时间'));
    const sources=asArray(p.auxiliary_sources).filter(item=>item.kind==='legal_status');
    if(!sources.length){container.append(el('p','unknown-text','尚未取得独立法律状态记录；已有著录标签不代表截止日的历史状态。'));return;}
    container.append(el('p','','以下为各文献在列示取得时间的简单法律状态，不代表检索截止日的历史状态，也不构成有效性或侵权判断。'));
    if(summary.conflict)container.append(el('div','detail-banner','不同文献或来源的状态存在冲突，申请汇总显示“未知”；逐文献原值仍保留。'));
    const table=el('table','scope-table'),head=el('tr');['文献','简单状态','最近取得时间'].forEach(label=>head.append(el('th','',label)));table.append(head);
    observations.forEach(item=>{const row=el('tr');row.append(el('td','',item.publication_number),el('td','',statusLabel(item.status)),el('td','',knownText(item.latest_observed_at)));table.append(row);});container.append(table);
    const provenance=el('details','document-block');provenance.append(el('summary','','查看全部法律状态来源（'+sources.length+'条）'));
    sources.forEach(source=>provenance.append(el('p','',source.publication_number+' · '+text(asObject(source.normalized).provider_statuses)+' · '+source.acquired_at+' · '+source.source_provider)));
    container.append(provenance);
  }
  function renderEvidence(container,p,focusId) {
    container.append(el('p','','以下保留原文片段、位置和文献身份。技术分析与权利判断应依据对应申请、地域及文本版本。'));
    const evidence=asArray(p.evidence);
    if(evidence.length){container.append(el('h3','','可追溯证据片段'));evidence.forEach(item=>{
      const card=el('article','evidence-card');card.dataset.evidenceId=String(item.id);card.id='evidence-'+String(item.id).replace(/[^a-zA-Z0-9_-]/g,'_');
      add(card,add(el('div','evidence-meta'),el('span','','证据 '+knownText(item.id)+' · '+knownText(item.publication_number)),el('span','',labelFor(item.source_type || 'source_type')+' · '+knownText(item.version)+' · '+knownText(item.language)+' · '+knownText(item.locator))),el('blockquote','',item.text || item.quote || '原文片段未取得'));
      const source=externalLink(item.url || item.source_url);if(source)card.append(source);else card.append(el('span','unknown-text','未取得可用的原始来源链接'));
      container.append(card);
    });}else container.append(empty('本件尚无可定位的证据片段','证据缺失不会被视作分析已完成。可以继续核查已取得的原文资料。'));
    const documents=asArray(p.documents);container.append(el('h3','','文本版本与全文'));
    if(!documents.length)container.append(el('p','unknown-text','尚未取得可展示的全文版本。'));
    documents.forEach(doc=>{
      const block=el('details','document-block');block.append(el('summary','',knownText(doc.publication_number)+' · '+labelFor(doc.document_type || 'document')+' · '+knownText(doc.version)));
      if(asArray(doc.rejection_review_ids).length){block.append(el('div','detail-banner','该版本已因正文缺陷停止用于技术完成判断，保留原文供复查。'));asArray(p.document_reviews).filter(item=>item.document_id===doc.id).forEach(item=>block.append(el('p','',item.reason)));}
      const meta=add(el('div','document-meta'),el('span','','语言：'+knownText(doc.language)),el('span','','版本：'+knownText(doc.version)));const link=externalLink(doc.source_url);if(link)meta.append(link);block.append(meta,el('pre','document-text',doc.text || '该版本未取得正文。'));container.append(block);
      if(doc.original_document){const original=asObject(doc.original_document),notice=el('div','detail-banner');notice.append(el('p','',knownText(original.source_label)+'。'+knownText(original.source_notice)),el('p','','本件 '+knownText(original.publication_number)+' · 权利要求位于PDF第 '+asArray(original.claims_pdf_pages).map(text).join('、')+' 页。'));const pdf=safeLocalPdf(original.offline_pdf_path);if(pdf){const local=el('a','source-link','离线查看原始公报 PDF ↗');local.href=pdf;local.target='_blank';local.rel='noopener noreferrer';notice.append(local);}const locators=asArray(original.claim_page_locators);if(locators.length){const positions=el('details','original-page-locators');positions.append(el('summary','','权利要求与PDF页码对照'));locators.forEach(locator=>positions.append(el('p','','权利要求 '+knownText(locator.claim_number)+'：PDF第 '+asArray(locator.pdf_pages).map(text).join('、')+' 页')));notice.append(positions);}block.insertBefore(notice,block.querySelector('.document-text'));}
      if(doc.normalization_notice)block.insertBefore(el('p','detail-banner','原文嵌图含人工转写，原图可在“关系与图片”中核阅。转写说明：'+text(doc.normalization_notice)),block.querySelector('.document-text'));
      if(doc.text_format_note)block.insertBefore(el('p','unknown-text','原文的上标和下标分别以 ^{…} 和 _{…} 标明，保留指数、单位及符号含义。此标记是明示的文本提取格式，原公报可由来源链接复核。'),block.querySelector('.document-text'));
    });
    if(focusId){const card=[...container.querySelectorAll('.evidence-card')].find(node=>node.dataset.evidenceId===String(focusId));if(card){card.classList.add('highlight');requestAnimationFrame(()=>card.scrollIntoView({block:'center'}));}else container.prepend(el('div','detail-banner','本地详情未找到所请求的证据编号 '+focusId+'，请复核结论与证据的关联。'));}
  }
  function renderClaims(container,p,onEvidence) {
    container.append(el('div','detail-banner','权利要求按可获得的具体文本版本展示。公开文本与授权文本可能不同，不能跨版本替代。'));
    const claims=asArray(p.claims);
    if(!claims.length){container.append(empty('没有结构化权利要求','可在“证据与原文”中检查是否已经取得权利要求文档。没有文本时，保护范围保持未知。'));return;}
    const documents=new Map(asArray(p.documents).map(doc=>[doc.id,doc])),groups=new Map();
    claims.forEach((claim,index)=>{const data=typeof claim==='string'?{text:claim}:asObject(claim),key=data.document_id||'unknown';if(!groups.has(key))groups.set(key,[]);groups.get(key).push({data,index});});
    const primary=asObject(p.analysis).document_id;
    [...groups].sort((a,b)=>(a[0]===primary?-1:b[0]===primary?1:0)).forEach(([key,items])=>{
      const source=documents.get(key),group=el('details','document-block claim-version-group');group.dataset.documentId=key;group.open=key===primary;
      group.append(el('summary','',source?knownText(source.publication_number)+' · '+knownText(source.version)+' · '+(source.complete?'来源可用':'正文缺陷 / 未完成'):'文献版本关联未知'));
      if(!source||!source.complete)group.append(el('p','detail-banner',source?'该版本保留供复核，当前不用于技术完成判断。':'这组权项缺少准确版本关联，请从原文版本核查。'));
      if(source&&key===primary)group.append(el('p','unknown-text','本次技术解读使用的主文本。语言：'+knownText(source.language)));
      const original=asObject(source&&source.original_document),locators=new Map(asArray(original.claim_page_locators).map(item=>[item.claim_number,item.pdf_pages]));
      items.forEach(({data,index})=>{const number=data.number||data.claim_number||index+1,card=el('article','claim-card');card.append(el('strong','','权利要求 '+knownText(number)+(asArray(data.depends_on).length?' · 引用 '+asArray(data.depends_on).map(text).join('、'):'')),el('p','',data.text||data.content||'权利要求正文未知'));if(locators.has(number))card.append(el('small','unknown-text','原始PDF第 '+asArray(locators.get(number)).map(text).join('、')+' 页'));addEvidenceRefs(card,data.evidence_ids,onEvidence);group.append(card);});
      container.append(group);
    });
  }
  function renderRelations(container,p,onEvidence) {
    container.append(el('h3','','专利关系'));
    const local=asArray(p.relations),combined=[...local,...relations.filter(rel=>String(rel.source)===p.id || String(rel.target)===p.id)],seen=new Set(),records=combined.filter(rel=>{const key=rel.id || [rel.source,rel.target,rel.type,rel.kind].join('|');if(seen.has(key))return false;seen.add(key);return true;});
    if(!records.length)container.append(el('p','unknown-text','尚无已记录的同族、引用或其他关系。未知不会被解释为没有关系。'));
    records.forEach(rel=>{
      const card=el('article','relation-card'),info=el('div'),fact=rel.kind==='fact';info.append(chip(fact?'事实关系':'分析推断',fact?'state':'claims'),document.createTextNode(text(rel.label || rel.type || '关系类型未知')));
      const target=String(String(rel.source)===p.id?rel.target:rel.source),targetPatent=byId.get(target);info.append(el('div','',targetPatent?text(targetPatent.title)+' · '+text(targetPatent.application_number):moduleNames.has(target)?moduleNames.get(target)+'（技术大类）':knownText(target))); if(rel.basis)info.append(el('div','unknown-text','判断依据：'+text(rel.basis))); if(rel.source_locator)info.append(el('div','unknown-text','来源位置：'+text(rel.source_locator))); card.append(info);
      if(targetPatent)card.append(button('查看关联申请 ↗','text-button',()=>openPatent(target)));
      addEvidenceRefs(card,rel.evidence_ids,onEvidence);
      const source=externalLink(rel.url || rel.source_url);if(source)card.append(source);container.append(card);
    });
    const families=asArray(p.auxiliary_sources).filter(item=>item.kind==='family');
    container.append(el('h3','','同族来源与口径'));
    if(!families.length)container.append(el('p','unknown-text','尚未取得独立同族记录；不能据此认定没有同族。'));
    families.forEach(source=>{
      const block=el('details','document-block');block.append(el('summary','',source.publication_number+' · 取得于 '+source.acquired_at));
      [['simple','简单同族'],['inpadoc','INPADOC同族'],['patsnap','PatSnap同族']].forEach(([key,label])=>{const group=asObject(asObject(source.normalized)[key]);block.append(el('h4','',label+' · '+(group.coverage==='available'?asArray(group.members).length+'件文献':'未知')),el('p','',group.coverage==='available'?asArray(group.members).map(member=>member.publication_number).join('；') || '来源返回空列表':'未取得该口径的记录'));});
      block.append(el('p','unknown-text','以上分别保留提供者的三种同族口径，不推断转让、保护范围或可替代的技术文本。'));container.append(block);
    });
    container.append(el('h3','','附图与外观视图'));
    const images=asArray(p.images);
    if(!images.length){container.append(el('p','unknown-text','尚未取得可展示的本地图片。'));return;}
    const grid=el('div','image-grid');images.forEach((image,index)=>{
      const data=typeof image==='string'?{path:image}:asObject(image),safe=safeLocalImage(data.path || data.src),figure=el('figure','image-card');
      if(safe){const node=el('img');node.src=safe;node.alt=text(data.alt || data.caption || '专利附图 '+(index+1));node.loading='lazy';node.addEventListener('error',()=>replace(figure,el('figcaption','','本地图片不可用，请检查完整导出包。')));const original=el('a','image-original-link');original.href=safe;original.target='_blank';original.rel='noopener';original.setAttribute('aria-label','在新标签页查看原图：'+node.alt);original.append(node,el('span','image-open-label','查看原图 ↗'));figure.append(original);}else figure.append(el('div','design-thumb','没有安全可用的本地图片'));
      figure.append(el('figcaption','',data.caption || data.alt || '附图 '+(index+1)));const source=externalLink(data.source_url || data.url,'核验原始图片来源 ↗');if(source)figure.append(source);grid.append(figure);
    });container.append(grid);
  }
  function openInsight(insight) {
    showDialog('INSIGHT / EVIDENCE CHAIN');const body=$('dialog-body');
    body.append(el('h2','',insight.title || '角色解读'),el('p','',insight.body || '未知'),el('div','detail-banner','适用范围：'+text(insight.scope || run.scope || '未注明')+'。结论采用原始分析范围，不随目录筛选自动改变。'));
    if(asArray(insight.limitations).length)body.append(el('h3','','未知与判断限制'),add(el('ul','limitations-list'),asArray(insight.limitations).map(value=>el('li','',value))));
    body.append(el('h3','','结论 → 相关申请 → 原文证据'));
    const ids=asArray(insight.patent_ids).map(String),list=el('div','insight-patents');
    if(!ids.length)body.append(el('p','unknown-text','本条结论没有绑定可用的申请编号，需要补齐证据链。'));
    ids.forEach(id=>{const p=byId.get(id),node=button('','',()=>openPatent(id,asArray(insight.evidence_ids)));const label=el('span','',p?p.title:'索引外申请：'+id);label.append(el('small','',p?p.application_number || id:'当前索引未包含此申请'));node.append(label,el('span','','查看依据 ↗'));node.disabled=!p;list.append(node);});body.append(list);
    body.append(el('h3','','关联证据编号'),el('p','',asArray(insight.evidence_ids).length?asArray(insight.evidence_ids).map(text).join('、'):'未绑定证据编号'));
    if(!asArray(insight.evidence_ids).length)body.append(el('div','detail-banner','该结论缺少明确证据引用，不能作为已完成证据核查的结论。'));
  }
  function readableTable(value) {
    const table=el('table','scope-table'),body=el('tbody');
    const obj=asObject(value);Object.entries(obj).forEach(([key,item])=>{const row=el('tr');row.append(el('th','',labelFor(key)),el('td','',text(item)));body.append(row);});
    table.append(body);return table;
  }
  function scopeBlock(title,value) {return add(el('section','analysis-block'),el('h4','',title),el('p','',knownText(value)));}
  function openScope(){readerScope();}
  function openHelp(){showDialog('阅读说明');$('dialog-body').append(el('h2','','阅读说明'),el('p','','公司概览与技术分析分别标明统计边界。先看产品大类，再选择具体产品线；技术大类与实现方向均可进入技术梳理及时间图。'),el('p','','三种角色共用事实与筛选。技术时间图可选申请日或所引文献公开日，年度首末选读与全部申请分页可切换。'),el('p','','图谱和时间图支持全屏；专利目录支持筛选、页码跳转与CSV导出。未知、未披露和待补齐资料分别显示。'));}
  const report=window.PP_REPORT, portfolio=report.portfolio;
  const countBy=(items,key)=>{const m=new Map();items.forEach(p=>{const k=typeof key==='function'?key(p):p[key];m.set(k,(m.get(k)||0)+1);});return [...m].sort((a,b)=>b[1]-a[1]||String(a[0]).localeCompare(String(b[0]),'zh-CN'));};
  const ratio=(n,d)=>d?(100*n/d).toFixed(1)+'%':'—';
  const names={CN:'中国大陆',TW:'中国台湾',HK:'中国香港',WO:'PCT 国际申请',EP:'欧洲专利局',KR:'韩国',JP:'日本',US:'美国',AU:'澳大利亚',VN:'越南'};
  const statuses=['有效','审中','失效','PCT指定期内','PCT指定期满','unknown'];
  const statusName=s=>({'有效':'授权有效','审中':'申请中 / 审查中','失效':'失效','PCT指定期内':'PCT 指定期内','PCT指定期满':'PCT 指定期满','unknown':'状态未知'}[s]||statusLabel(s));
  const statusColors={'有效':'#2769c1','审中':'#20a0a4','失效':'#91a0b4','PCT指定期内':'#9a7ec4','PCT指定期满':'#c6b0dc','unknown':'#dfc482'};
  const colors=['#2869c0','#29a0a7','#9279c7','#da9a49','#7295c9','#74aaa0'];
  const getCount=(arr,value,key)=>arr.filter(p=>p[key]===value).length;
  const makeCard=(label,value,note,action)=>{const node=add(el('article','metric-card'),el('div','metric-label',label),el('div','metric-number',nfmt(value)),el('div','metric-note',note));if(action){const b=button('查看申请','text-button',action);node.append(b);}return node;};
  const header=(title,subtitle)=>add(el('div','report-panel-heading'),el('h3','',title),el('p','chart-note',subtitle));
  const panel=(title,subtitle)=>add(el('section','panel report-panel'),header(title,subtitle));
  function bars(container,values,denominator,formatter=x=>x,onClick=null){
    const max=Math.max(1,...values.map(x=>x[1]));
    values.forEach(([key,n],i)=>{const row=el('div','hbar-row');const label=onClick?button(formatter(key),'bar-label',()=>onClick(key)):el('span','bar-label',formatter(key));
      const track=el('div','bar-track'),fill=el('div','bar-fill');fill.style.width=(n/max*100)+'%';fill.style.background=colors[i%colors.length];track.append(fill);
      row.append(label,track,el('span','bar-value',nfmt(n)+(denominator?' · '+ratio(n,denominator):'')));container.append(row);});
  }
  function table(headers,rows){const wrap=el('div','table-scroll'),t=el('table','report-table'),thead=el('thead'),tr=el('tr'),body=el('tbody');headers.forEach(h=>tr.append(el('th','',h)));thead.append(tr);rows.forEach(values=>{const r=el('tr');values.forEach(v=>r.append(add(el('td'),v instanceof Node?v:document.createTextNode(String(v)))));body.append(r);});t.append(thead,body);wrap.append(t);return wrap;}
  function inspectRows(title,items,notice=report.settings.analysis_label+'；当前筛选已应用。'){
    showDialog('统计依据');const body=$('dialog-body');body.append(el('h2','',title),el('p','',notice+' 共 '+nfmt(items.length)+' 件。'));
    let shown=0;const list=el('div','inspection-list'),more=button('再显示 50 件','subtle-button',draw);body.append(list,more);draw();
    function draw(){items.slice(shown,shown+50).forEach(p=>{const b=button(p.title||p.id,'inspection-row',()=>byId.has(p.id)?openPatent(p.id):showPortfolioRecord(p));b.append(el('small','',p.application_number+' · '+(p.filing_date||'日期未知')+' · '+statusName(p.legal_status)));list.append(b);});shown+=50;more.hidden=shown>=items.length;}
  }
  function showPortfolioRecord(p){showDialog('公开申请著录');$('dialog-body').append(el('h2','',p.title),readableTable({application_number:p.application_number,publication_number:p.publication_numbers.join('；'),type:typeLabel(p.patent_type),legal_status:statusName(p.legal_status),original_assignees:p.original_assignees,current_assignees:p.current_assignees,filing_date:p.filing_date}),el('p','',portfolio.scope),el('p','','此条仅提供著录与状态，当前技术分析范围以目录为准。'));}
  function renderPortfolio(){
    const rows=portfolio.rows;$('portfolio-scope').textContent=portfolio.scope;
    replace($('portfolio-metrics'),makeCard('范围内公开申请',rows.length,portfolio.count_note,()=>inspectRows('公开申请',rows,portfolio.scope)),...['有效','审中','失效'].map(s=>makeCard(statusName(s),getCount(rows,s,'legal_status'),'法律状态观察：'+report.settings.status_observed_at,()=>inspectRows(statusName(s),rows.filter(p=>p.legal_status===s),portfolio.scope))));
    $('portfolio-note').textContent='此处统计范围：'+portfolio.scope+'。状态未知 '+getCount(rows,'unknown','legal_status')+' 件；PCT及其他状态 '+rows.filter(p=>!['有效','审中','失效','unknown'].includes(p.legal_status)).length+' 件。公开申请记录与当前拥有量分别列示。';
    const types=panel('专利类型结构','独立申请计数，未知类型保留。');bars(types,countBy(rows,'patent_type'),rows.length,typeLabel,k=>inspectRows(typeLabel(k),rows.filter(p=>p.patent_type===k),portfolio.scope));
    const years=panel('历年申请量','按申请年归组。近期年度存在公开滞后，件数不直接等于研发投入。');bars(years,countBy(rows,p=>p.filing_date.slice(0,4)||'日期未知').sort((a,b)=>a[0].localeCompare(b[0])),rows.length,x=>x,y=>inspectRows(y+'年',rows.filter(p=>(p.filing_date.slice(0,4)||'日期未知')===y),portfolio.scope));replace($('portfolio-charts'),types,years);
  }
  function renderMetrics(){replace($('metrics'),makeCard('发明申请',getCount(filtered,'invention','patent_type'),'当前筛选'),makeCard('实用新型申请',getCount(filtered,'utility_model','patent_type'),'当前筛选'),makeCard('授权有效',getCount(filtered,'有效','legal_status'),'状态观察：'+report.settings.status_observed_at),makeCard('申请中 / 审查中',getCount(filtered,'审中','legal_status'),'已公开且来源标记在审'));$('selected-scope').textContent=report.settings.analysis_label+' · 当前 '+nfmt(filtered.length)+' 件 · '+report.settings.date_note;$('selected-state-note').textContent='日期未知 '+filtered.filter(p=>!p.filing_date).length+' 件；状态未知 '+getCount(filtered,'unknown','legal_status')+' 件。公司概览不随本区筛选变化。';renderAnalysis();}
  function selectModule(module){state.module=module;state.page=1;$('filter-module').value=module;render();}
  function renderAnalysis(){
    const area=$('role-analysis');replace(area);
    if(!filtered.length){replace($('product-analysis-content'));area.append(empty('筛选范围内没有申请','重置或调整筛选后显示分析。'));return;}
    replace($('product-analysis-content'));renderProductAnalysis($('product-analysis-content'));
    if(state.role==='management')renderManagement(area);
    else if(state.role==='rd')renderResearch(area);
    else renderIP(area);
  }
  function renderManagement(area){
    const grid=el('div','report-grid'),mix=panel('技术布局集中在哪里','每件一个技术大类，未完成解读单列。');bars(mix,countBy(filtered,'primary_module'),filtered.length,x=>x,selectModule);
    const geo=panel('申请覆盖哪些地域','按受理机构计数，PCT及区域局分别保留。');bars(geo,countBy(filtered,'authority'),filtered.length,x=>names[x]||x,k=>inspectRows(names[k]||k,filtered.filter(p=>p.authority===k)));
    const ent=panel('申请关联主体','共同申请可能关联多个主体，件数不可加总。');bars(ent,countBy(filtered.flatMap(p=>p.verified_entity_names.map(name=>({name}))),'name'),null,x=>x,k=>inspectRows(k,filtered.filter(p=>p.verified_entity_names.includes(k))));
    const yearly=panel('每年申请的类型构成','* 表示不完整年度。缺失日期的申请不纳入年度统计。');yearly.append(table(['申请年','发明','实用新型','外观设计','合计'],report.settings.years.map(y=>{const ps=filtered.filter(p=>p.filing_date.startsWith(y));return [y+(report.settings.partial_years.includes(y)?' *':''),getCount(ps,'invention','patent_type'),getCount(ps,'utility_model','patent_type'),getCount(ps,'design','patent_type'),button(nfmt(ps.length),'table-link',()=>inspectRows(y+'年',ps))];})));renderTrend(area);grid.append(mix,geo,ent,yearly);area.append(grid);
  }
  let trendMeasure='share';
  function renderTrend(area){
    const box=panel('技术方向怎样变化','件数与占比并列观察。* 为不完整年度；公开滞后可能影响近期数量。'),controls=el('div','segmented chart-switch');['share','count'].forEach(k=>{const b=button(k==='share'?'年度占比':'申请件数',k===trendMeasure?'active':'',()=>{trendMeasure=k;renderAnalysis();});b.setAttribute('aria-pressed',String(k===trendMeasure));controls.append(b);});box.append(controls);
    const yrs=report.settings.years,den=Object.fromEntries(yrs.map(y=>[y,filtered.filter(p=>p.filing_date.startsWith(y)).length])),pair=report.settings.comparison_years;
    const stats=countBy(filtered,'primary_module').map(([name])=>{const by=Object.fromEntries(yrs.map(y=>[y,filtered.filter(p=>p.primary_module===name&&p.filing_date.startsWith(y)).length]));return {name,by,delta:pair.length===2&&den[pair[0]]&&den[pair[1]]?100*(by[pair[1]]/den[pair[1]]-by[pair[0]]/den[pair[0]]):null};});
    const max=Math.max(1,...stats.flatMap(s=>yrs.map(y=>trendMeasure==='share'?(den[y]?100*s.by[y]/den[y]:0):s.by[y])));
    box.append(table(['技术大类',...yrs.map(y=>y+(report.settings.partial_years.includes(y)?' *':'')+' · '+nfmt(den[y])+'件'),pair.length===2?pair[1]+'较'+pair[0]:'年度比较'],stats.map(s=>[button(s.name,'table-link',()=>selectModule(s.name)),...yrs.map(y=>{const value=trendMeasure==='share'?(den[y]?100*s.by[y]/den[y]:0):s.by[y],b=button(nfmt(s.by[y])+'件 · '+ratio(s.by[y],den[y]),'heat-cell data-heat',()=>inspectRows(s.name+' · '+y,filtered.filter(p=>p.primary_module===s.name&&p.filing_date.startsWith(y))));b.style.background=s.by[y]?'rgba(38,104,199,'+(.07+value/max*.46)+')':'#f7f9fc';return b;}),s.delta===null?'—':(s.delta>0?'+':'')+s.delta.toFixed(1)+' 个百分点'])));
    box.append(el('p','chart-note','年度占比分母为当年当前筛选内的全部申请。比较年份仅选自已确认边界内的完整年份；完整年份仍可能存在未公开申请。占比上升不必然意味着申请量增加。'));area.append(box);
  }
  function appendSourceComparisons(area){const examples=(report.comparisons||[]).filter(v=>v.application_ids.every(id=>filtered.some(p=>p.id===id)));if(!examples.length)return;const box=panel('方案之间的技术差别','每项比较均保留所涉申请与原文依据。');examples.forEach(v=>box.append(el('h4','',v.title),el('p','',v.body),...v.application_ids.map(id=>button(byId.get(id).title,'text-button',()=>openPatent(id,v.evidence_ids)))));area.append(box);}
  function familyGroups(items){
    const ids=new Set(items.map(p=>p.id)),groups=new Map();
    report.simple_families.filter(f=>ids.has(f.application_id)&&f.family_id).forEach(f=>{if(!groups.has(f.family_id))groups.set(f.family_id,{id:f.family_id,apps:new Set(),members:new Set(),regions:new Set(),sources:new Set()});const g=groups.get(f.family_id);g.apps.add(f.application_id);f.members.forEach(m=>{g.members.add(m.publication_number);g.regions.add(m.authority);});g.sources.add(f.source_id);});return [...groups.values()].sort((a,b)=>b.regions.size-a.regions.size||b.apps.size-a.apps.size||String(a.id).localeCompare(String(b.id)));
  }
  function renderIP(area){
    const box=panel('技术分类 × 法律状态','当前筛选内独立申请。有效是采集时授权有效，失效可能包括终止、撤回、驳回；不能用这张表计算授权成功率。');
    box.append(table(['技术分类','授权有效','审中','失效','PCT阶段','未知','合计'],countBy(filtered,'primary_module').map(([m,n])=>{const ps=filtered.filter(p=>p.primary_module===m);return [button(m,'table-link',()=>selectModule(m)),...['有效','审中','失效'].map(s=>button(nfmt(getCount(ps,s,'legal_status')),'table-link',()=>inspectRows(m+' · '+statusName(s),ps.filter(p=>p.legal_status===s)))),ps.filter(p=>p.legal_status.startsWith('PCT')).length,getCount(ps,'unknown','legal_status'),n];})));area.append(box);
    const types=panel('发明与实用新型的状态不同','两个类型使用同一批申请和同一状态取得时间，授权有效占比不是审查质量或获权概率。');types.append(table(['专利类型','授权有效','审中','失效','PCT阶段','未知','合计'],['invention','utility_model'].map(t=>{const ps=filtered.filter(p=>p.patent_type===t);return [typeLabel(t),...['有效','审中','失效'].map(s=>getCount(ps,s,'legal_status')),ps.filter(p=>p.legal_status.startsWith('PCT')).length,getCount(ps,'unknown','legal_status'),ps.length];})));area.append(types);
    const fg=familyGroups(filtered),multi=fg.filter(g=>g.regions.size>1),family=panel('简单同族及跨地域成员','仅使用来源提供的简单同族编号；同族成员文献的地域不等于该地现有有效权利。');
    family.append(el('p','fact-text','当前筛选对应 '+nfmt(fg.length)+' 个已知简单同族，其中 '+nfmt(multi.length)+' 个的返回成员涉及多个受理机构；有同族记录的申请 '+nfmt(new Set(report.simple_families.filter(f=>filtered.some(p=>p.id===f.application_id)&&f.family_id).map(f=>f.application_id)).size)+' 件。'));
    family.append(table(['同族中的技术内容','当前范围申请','返回成员地域','成员文献数'],fg.slice(0,18).map(g=>{const ids=[...g.apps],p=byId.get(ids[0]);return [button(p.secondary_technology+' · '+p.title,'table-link',()=>inspectRows('简单同族 '+g.id,ids.map(id=>byId.get(id)),'来源简单同族成员中纳入本次筛选的独立申请。')),+g.apps.size,[...g.regions].map(x=>names[x]||x).join('、'),g.members.size];})));
    family.append(el('p','chart-note','按返回成员地域数排序展示前18组；同族编号与来源在各申请详情的“关系”中。引证质量、审查意见、稳定性或侵权风险未形成可核实的组合结论。'));area.append(family);
  }
  function renderRole(){const info=roleInfo[state.role];document.querySelectorAll('.role-button').forEach(n=>{n.classList.toggle('active',n.dataset.role===state.role);n.setAttribute('aria-pressed',String(n.dataset.role===state.role));});$('role-description').textContent={management:'专利规模、产品线结构与技术变化',rd:'技术问题、实现路线与结构条件',ip:'法律状态、权利要求与同族布局'}[state.role];$('insights-title').textContent=state.role==='management'?'关键事实':info.label+' · 技术事实与案例';replace($('role-focus'));replace($('insight-grid'));$('insight-scope').hidden=true;if(state.role==='management')return;const insights=asArray(raw.insights).filter(i=>i.role===state.role);replace($('insight-grid'),insights.map(i=>add(el('article','insight-card'),el('h3','',i.title),el('p','',i.body),el('small','',text(i.scope)),button('查看依据','text-button',()=>openInsight(i)))));if(insights.length){$('insight-scope').hidden=false;$('insight-scope').textContent='文字结论保留各自注明的原始范围；筛选不会自动改写结论。';}}
  let openBranches=new Set(),leafLimits=new Map(),fullscreen=false;
  function mapNode(label,count,depth,action,extra){const node=el('div','mind-node depth-'+depth),b=button(label,'mind-label',action);if(count!=null)b.append(el('span','mind-count',nfmt(count)+' 件'));node.append(b);if(extra)node.append(el('small','mind-extra',extra));return node;}
  function leaf(p){const node=mapNode(p.title,null,3,()=>openPatent(p.id));node.append(el('p','mind-description',p.summary||'本件技术解读待补齐，尚无技术归纳。'),el('small','mind-pn',p.publication_numbers.join(' / ')+' · '+statusName(p.legal_status)),button('归类依据','mind-basis',()=>{showDialog('技术分类依据');$('dialog-body').append(el('h2','',p.primary_module+' / '+p.secondary_technology),el('p','',(p.secondary_basis||{}).matched_text?'细分导航匹配了技术解读中的“'+(p.secondary_basis||{}).matched_text+'”。该索引用于组织阅读，不表示官方分类或权利保护范围。':'该件未匹配明确的细分导航词，保留“其他”或“技术解读待补齐”，未补造细分技术。'),el('blockquote','',p.summary||'技术解读待补齐'),button('打开对应申请与原文 ↗','text-button',()=>openPatent(p.id)));}));return node;}
  function treeBranch(key,label,items,depth,childFactory){
    const li=el('li','mind-branch'),row=mapNode((openBranches.has(key)?'− ':'+ ')+label,items.length,depth,()=>{if(openBranches.has(key))openBranches.delete(key);else openBranches.add(key);renderGraph();});
    if(key.startsWith('m:')&&label!=='待分析'){const parts=key.slice(2).split('|');row.append(button('技术梳理','mind-timeline',()=>openRoute(parts[0],parts[1]||'')));row.append(button('技术时间图 ↗','mind-timeline',()=>openTimelineLine(parts[0],parts[1]||'')));}
    row.querySelector('button').setAttribute('aria-expanded',String(openBranches.has(key)));row.querySelector('button').dataset.mapKey=key;li.append(row);
    if(openBranches.has(key)){const ul=el('ul','mind-children');childFactory(ul);li.append(ul);}return li;
  }
  function appendLeaves(ul,key,items){const limit=leafLimits.get(key)||12;items.slice(0,limit).forEach(p=>{const li=el('li','mind-branch');li.append(leaf(p));ul.append(li);});if(items.length>limit){const li=el('li','mind-branch');li.append(button('再展开 '+Math.min(12,items.length-limit)+' 件（尚余 '+(items.length-limit)+'）','mind-more',()=>{leafLimits.set(key,limit+12);renderGraph();}));ul.append(li);}}
  function renderGraph(){
    if(state.graphMode==='products'){renderProductGraph();return;}
    const canvas=$('graph-canvas'),x=canvas.scrollLeft,y=canvas.scrollTop,focusKey=document.activeElement&&document.activeElement.dataset.mapKey,tree=el('div','mindmap'),root=mapNode(state.graphMode==='modules'?company+'技术布局':'简单同族',filtered.length,0,()=>{openBranches.clear();renderGraph();},report.settings.analysis_label+' · 当前筛选'),branches=el('ul','mind-children root-branches');tree.append(root,branches);
    if(!filtered.length){replace(canvas,empty('没有匹配申请','调整筛选后展示技术分类。'));return;}
    if(state.graphMode==='modules'){
      countBy(filtered,'primary_module').forEach(([module],i)=>{const ps=filtered.filter(p=>p.primary_module===module),key='m:'+module;
        const branch=treeBranch(key,module,ps,1,ul=>countBy(ps,'secondary_technology').forEach(([sub])=>{const ss=ps.filter(p=>p.secondary_technology===sub),sk=key+'|'+sub;ul.append(treeBranch(sk,sub,ss,2,leaves=>appendLeaves(leaves,sk,ss)));}));branch.style.setProperty('--branch-color',colors[i%colors.length]);branches.append(branch);});
    }else{
      const groups=familyGroups(filtered),lim=leafLimits.get('families')||20;
      groups.slice(0,lim).forEach((g,i)=>{const ps=[...g.apps].map(id=>byId.get(id)),key='f:'+g.id,p=ps[0];const branch=treeBranch(key,p.secondary_technology+' · '+p.title,ps,1,ul=>appendLeaves(ul,key,ps));branch.style.setProperty('--branch-color',colors[i%colors.length]);branch.querySelector('.mind-node').append(el('small','mind-extra','简单同族 '+g.id+' · '+[...g.regions].map(x=>names[x]||x).join(' / ')));branches.append(branch);});
      if(groups.length>lim)branches.append(add(el('li','mind-branch'),button('再显示20组同族','mind-more',()=>{leafLimits.set('families',lim+20);renderGraph();})));
      if(!groups.length)branches.append(el('li','chart-note','当前筛选没有可用的简单同族编号。'));
    }
    tree.classList.toggle('fact-tree',state.graphMode==='relations');replace(canvas,tree);updateViewBox();canvas.scrollLeft=x;canvas.scrollTop=y;
    if(focusKey){const same=[...canvas.querySelectorAll('button')].find(b=>b.dataset.mapKey===focusKey);if(same)same.focus({preventScroll:true});}
    $('graph-caption').textContent=state.graphMode==='modules'?'技术大类 → 技术细分 → 具体方案。虚线表示技术导航归类；点击方案打开原文。':'实线表示来源返回的简单同族关系；每件申请的状态与权利文本独立。';
    $('graph-count').textContent=nfmt(filtered.length)+' 件 · '+Math.round(state.zoom*100)+'%';
  }
  function updateViewBox(){const tree=$('graph-canvas').querySelector('.mindmap');if(tree)tree.style.zoom=String(state.zoom);$('graph-count').textContent=nfmt(filtered.length)+' 件 · '+Math.round(state.zoom*100)+'%';}
  async function toggleFullscreen(){const panel=$('mindmap-panel');fullscreen=!fullscreen;panel.classList.toggle('map-fullscreen',fullscreen);document.body.classList.toggle('map-is-fullscreen',fullscreen);$('graph-fullscreen').textContent=fullscreen?'退出全屏 ⛶':'全屏展开 ⛶';$('graph-fullscreen').setAttribute('aria-pressed',String(fullscreen));
    if(fullscreen){panel.append($('detail-dialog'));if(panel.requestFullscreen)try{await panel.requestFullscreen();}catch(_){/* CSS full-window mode remains available. */}}else{if(document.fullscreenElement&&document.exitFullscreen)try{await document.exitFullscreen();}catch(_){}document.body.append($('detail-dialog'));}
  }
  function initializeReport(){
    renderPortfolio();$('graph-fullscreen').addEventListener('click',toggleFullscreen);
    $('graph-reset').addEventListener('click',()=>{openBranches.clear();leafLimits.clear();state.zoom=1;renderGraph();});
    document.addEventListener('keydown',event=>{if(event.key==='Escape'&&fullscreen&&!$('detail-dialog').open)toggleFullscreen();});
    document.addEventListener('fullscreenchange',()=>{if(!document.fullscreenElement&&fullscreen){fullscreen=false;$('mindmap-panel').classList.remove('map-fullscreen');document.body.classList.remove('map-is-fullscreen');$('graph-fullscreen').textContent='全屏展开 ⛶';$('graph-fullscreen').setAttribute('aria-pressed','false');document.body.append($('detail-dialog'));}});
    $('portfolio-source').addEventListener('click',readerScope);
    window.PP_CASE_TEST={selectPatents,render,renderGraph,renderAnalysis,familyGroups,state,patents,portfolio,toggleFullscreen,inspectRows};
  }

  // Case-only timelines: dates, text versions and evidence remain separate.
  const timelineData=window.PP_TIMELINES;
  const timelineState={module:'',sub:'',date:'filing',mode:'sample',year:'',page:1,scale:64};
  const timelineColors=['#2869c0','#248e97','#8b73bd','#b48037','#427ca0','#699452','#a06e8b','#5c7bb0'];
  let timelineFullscreen=null;
  const timelineDate=p=>timelineState.date==='publication'?timelineData.nodes[p.id]?.document_publication_date:p.filing_date;
  const timelineSorted=ps=>[...ps].sort((a,b)=>timelineDate(a).localeCompare(timelineDate(b))||a.id.localeCompare(b.id));
  const timelineReady=()=>filtered.filter(p=>timelineData.nodes[p.id]&&/^\d{4}-\d{2}-\d{2}$/.test(timelineDate(p)||''));
  function timelineSample(ps){
    const years=new Map();timelineSorted(ps).forEach(p=>{const y=timelineDate(p).slice(0,4);if(!years.has(y))years.set(y,[]);years.get(y).push(p);});
    return [...years.values()].flatMap(list=>list.length>1?[list[0],list[list.length-1]]:list);
  }
  function lineSelection(){return timelineSorted(timelineReady().filter(p=>(!timelineState.module||p.primary_module===timelineState.module)&&(!timelineState.sub||p.secondary_technology===timelineState.sub)&&(!timelineState.year||timelineDate(p).startsWith(timelineState.year))));}
  function timelineDomain(lanes){
    const ps=lanes?lanes.flatMap(l=>l.nodes.map(n=>n.p)):timelineReady(),dates=ps.map(timelineDate).filter(Boolean).sort();
    if(!dates.length)return {start:Date.parse(run.as_of_date+'T00:00:00Z')-86400000,end:Date.parse(run.as_of_date+'T00:00:00Z')+86400000};
    const a=new Date(dates[0]+'T00:00:00Z'),b=new Date(dates[dates.length-1]+'T00:00:00Z');
    return {start:Date.UTC(a.getUTCFullYear(),a.getUTCMonth(),1),end:Date.UTC(b.getUTCFullYear(),b.getUTCMonth()+1,1)};
  }
  function timelineGeometry(lanes){
    const domain=timelineDomain(lanes),pixelsPerDay=timelineState.scale/30.4375,width=Math.max(480,(domain.end-domain.start)/86400000*pixelsPerDay),cardWidth=282;
    const x=date=>Math.round((Date.parse(date+'T00:00:00Z')-domain.start)/86400000*pixelsPerDay);
    const layout=lanes.map(lane=>{const ends=[],nodes=lane.nodes.map(n=>{const px=x(timelineDate(n.p));let row=ends.findIndex(end=>end+18<=px);if(row<0)row=ends.length;ends[row]=px+cardWidth;return {...n,x:px,row};});return {...lane,nodes,height:Math.max(260,ends.length*224+65)};});
    return {...domain,width,cardWidth,x,lanes:layout};
  }
  function timelineCard(n,color){
    const p=n.p,source=timelineData.nodes[p.id],card=button('','tl-card',()=>openTimelineNode(p.id,n.authored));
    card.dataset.applicationId=p.id;card.style.left=n.x+'px';card.style.top=(48+n.row*224)+'px';card.style.setProperty('--line-color',color);
    card.setAttribute('aria-label',timelineDate(p)+'，'+(n.authored?.title||p.tags?.[0]||p.title)+'，查看技术方案和原文');
    card.append(el('span','tl-date',timelineDate(p)+' · '+(timelineState.date==='filing'?'申请':'文献公开')),el('strong','tl-node-title',n.authored?.title||p.tags?.[0]||p.secondary_technology),el('span','tl-node-body',n.authored?.body||source.means.join('；')),el('span','tl-node-pn',source.publication_number+' · '+statusName(p.legal_status)),el('span','tl-open','查看完整方案与原文 ↗'));
    card.title=n.authored?.body||source.means.join('；');return card;
  }
  function drawTimeline(target,lanes,kind){
    const canvas=$(target),scrollX=canvas.scrollLeft,scrollY=canvas.scrollTop;
    canvas.ppTimelineReading={lanes,kind,date:timelineState.date};
    if(!lanes.length){replace(canvas,empty('当前范围没有可展示的技术节点','时间图跟随上方筛选；技术解读待补齐的申请没有推定方案。'));return;}
    const g=timelineGeometry(lanes),board=el('div','tl-board');board.style.width=(240+g.width+305)+'px';
    const axis=el('div','tl-axis'),corner=el('div','tl-axis-label','技术路线 / '+(timelineState.date==='filing'?'申请时间':'所引文献公开时间')),ticks=el('div','tl-axis-track');ticks.style.width=(g.width+305)+'px';axis.append(corner,ticks);
    let d=new Date(g.start);const tickDates=[];
    while(d.getTime()<g.end){tickDates.push(d.toISOString().slice(0,10));d=new Date(Date.UTC(d.getUTCFullYear(),d.getUTCMonth()+1,1));}
    tickDates.forEach((date,i)=>{const month=Number(date.slice(5,7)),major=month===1||i===0,label=major?date.slice(0,4)+'年 '+month+'月':month===4||month===7||month===10?month+'月':'';if(!label)return;const tick=el('span','tl-axis-tick'+(major?' year':''),label);tick.style.left=g.x(date)+'px';ticks.append(tick);});board.append(axis);
    g.lanes.forEach((lane,i)=>{
      const color=timelineColors[(lane.colorIndex??i)%timelineColors.length],row=el('div','tl-lane'),label=el('div','tl-lane-label'),track=el('div','tl-track');row.style.height=lane.height+'px';row.style.setProperty('--line-color',color);track.style.width=(g.width+305)+'px';
      label.append(el('strong','',lane.label),el('span','tl-lane-count',lane.total+' 件 · 图中 '+lane.nodes.length+' 个节点'));
      if(lane.note)label.append(el('p','tl-lane-note',lane.note));
      if(kind==='important')label.append(button('展开该技术线 ↗','tl-line-link',()=>openTimelineLine(lane.module,lane.sub)));
      else if(lane.sub&&timelineState.sub!==lane.sub)label.append(button('单独查看这条线 ↗','tl-line-link',()=>openTimelineLine(lane.module,lane.sub)));
      tickDates.filter(date=>Number(date.slice(5,7))%3===1).forEach(date=>{const line=el('div','tl-gridline');line.style.left=g.x(date)+'px';track.append(line);});
      const rail=el('div','tl-chronology');rail.style.width=g.width+'px';track.append(rail);
      lane.nodes.forEach(n=>{const dot=el('span','tl-date-dot'),stem=el('span','tl-stem');dot.style.left=(n.x-4)+'px';stem.style.left=n.x+'px';stem.style.height=(22+n.row*224)+'px';track.append(stem,dot,timelineCard(n,color));});
      row.append(label,track);board.append(row);
    });replace(canvas,board);canvas.scrollLeft=scrollX;canvas.scrollTop=scrollY;
  }
  function updateTimelineSelect(id,options,value){const node=$(id);replace(node,...options.map(([key,label])=>{const option=el('option','',label);option.value=key;return option;}));node.value=value;}
  function renderTimelines(){
    if(!$('timeline-overview-canvas'))return;
    const ready=timelineReady(),available=countBy(ready,'primary_module');
    if(!available.some(([m])=>m===timelineState.module)){timelineState.module=available[0]?.[0]||'';timelineState.sub='';timelineState.page=1;}
    const moduleRows=ready.filter(p=>p.primary_module===timelineState.module),subs=countBy(moduleRows,'secondary_technology');
    if(timelineState.sub&&!subs.some(([s])=>s===timelineState.sub))timelineState.sub='';
    updateTimelineSelect('timeline-module',available.map(([m,n])=>[m,m+' · '+n+'件']),timelineState.module);
    updateTimelineSelect('timeline-sub',[['','全部技术细分'],...subs.map(([s,n])=>[s,s+' · '+n+'件'])],timelineState.sub);
    const years=[...new Set(moduleRows.map(p=>timelineDate(p).slice(0,4)))].sort();
    if(timelineState.year&&!years.includes(timelineState.year))timelineState.year='';
    updateTimelineSelect('timeline-year',[['','全部年份'],...years.map(y=>[y,y+'年'])],timelineState.year);
    ['date','mode'].forEach(k=>$('timeline-'+k).value=timelineState[k]);$('timeline-date-overview').value=timelineState.date;
    const readyIds=new Set(ready.map(p=>p.id));
    const featured=timelineData.featured.map((group,i)=>({...group,colorIndex:i,total:ready.filter(p=>p.primary_module===group.module&&(!group.sub||p.secondary_technology===group.sub)).length,nodes:group.nodes.filter(n=>readyIds.has(n.id)).map(n=>({p:byId.get(n.id),authored:n})),note:group.difference})).filter(l=>l.nodes.length);
    featured.forEach(l=>l.nodes.sort((a,b)=>timelineDate(a.p).localeCompare(timelineDate(b.p))||a.p.id.localeCompare(b.p.id)));
    drawTimeline('timeline-overview-canvas',featured,'important');
    $('timeline-overview-scope').textContent=report.settings.analysis_label+' · 重点方案选读 · 当前显示 '+featured.length+' 条线、'+featured.reduce((n,l)=>n+l.nodes.length,0)+' 个节点'+(hasFilters()?' · 已应用页面筛选':'')+'。节点按技术内容选取，不作为价值或性能排名。';
    const selected=lineSelection(),groups=countBy(selected,'secondary_technology'),pageSize=48,totalPages=Math.max(1,Math.ceil(selected.length/pageSize));timelineState.page=Math.min(timelineState.page,totalPages);
    const pageSet=new Set(selected.slice((timelineState.page-1)*pageSize,timelineState.page*pageSize).map(p=>p.id));
    const lanes=groups.map(([sub,total],i)=>{const all=selected.filter(p=>p.secondary_technology===sub),shown=timelineState.mode==='all'?all.filter(p=>pageSet.has(p.id)):timelineSample(all);return {label:sub,module:timelineState.module,sub,total,colorIndex:i,nodes:shown.map(p=>({p})),note:sub.startsWith('其他')?'保留既有“其他”归类，节点逐件显示具体方案。':''};}).filter(l=>l.nodes.length);
    drawTimeline('timeline-line-canvas',lanes,'line');
    $('timeline-line-title').textContent=(timelineState.module||'技术线')+(timelineState.sub?' / '+timelineState.sub:'');
    $('timeline-line-scope').textContent='当前技术线 '+selected.length+' 件 · '+(timelineState.mode==='sample'?'按每个细分、每年取首末申请，展示 '+lanes.reduce((n,l)=>n+l.nodes.length,0)+' 个节点；这是一种时间采样，不代表技术突破。':'全部申请模式：按时间排序，每页最多48件。')+(timelineState.year?' · '+timelineState.year+'年':'');
    $('timeline-pagination').hidden=timelineState.mode!=='all';$('timeline-page').textContent=timelineState.page+' / '+totalPages+' 页';$('timeline-prev').disabled=timelineState.page<=1;$('timeline-next').disabled=timelineState.page>=totalPages;
    $('timeline-count-note').textContent='时间轴：'+(timelineState.date==='filing'?'申请日':'所引文献公开日')+'。专利技术时间图沿用上方产品、主体、年份、类型及状态筛选；公司产品与业务节点仅跟随产品选择。“技术线”选择仅作用于本图。横线用于日期对齐，不表示技术继承、替代或效果提高。';
  }
  async function openTimelineLine(module,sub=''){
    if(fullscreen)await toggleFullscreen();
    if(timelineFullscreen&&timelineFullscreen!=='timeline-line-panel')await toggleTimelineFullscreen(timelineFullscreen);
    timelineState.module=module;timelineState.sub=sub;timelineState.year='';timelineState.page=1;renderTimelines();
    $('timeline-line-panel').scrollIntoView({behavior:'smooth',block:'start'});$('timeline-module').focus({preventScroll:true});
  }
  async function openTimelineNode(id,authored){
    const p=byId.get(id),n=timelineData.nodes[id],token=showDialog('技术时间图 · 方案与依据'),body=$('dialog-body');
    body.append(el('h2','',authored?.title||p.tags?.[0]||p.title),el('p','tl-modal-meta','申请 '+p.filing_date+' · 所引文献公开 '+n.document_publication_date+' · '+n.publication_number),el('p','',authored?.body||n.means.join('；')),
      el('p','chart-note','时间图默认按申请日排列，技术文字来自下列具体文献版本。先后排列不证明相互继承，也不表示申请当日已公开该版本文字。'),
      button('打开该节点依据原文 ↗','primary-button',()=>openPatent(id,authored?.evidence_ids||n.evidence_ids)),button('查看完整专利详情 ↗','text-button',()=>openPatent(id)),el('h3','','完整技术概述'),el('p','tl-full-summary',p.summary));
    let d;try{d=await loadDetail(id);}catch(e){body.append(el('p','',e.message));return;}
    if(token!==dialogToken||!$('detail-dialog').open)return;
    body.append(el('h3','','原文摘录 · '+basisLabel(n.document_type)+' · '+n.version));
    const refs=authored?.evidence_ids||n.evidence_ids;d.evidence.filter(e=>refs.includes(e.id)).slice(0,3).forEach(e=>body.append(el('p','tl-evidence-locator',e.publication_number+' · '+(e.locator.claim_number?'权利要求 '+e.locator.claim_number:JSON.stringify(e.locator))),el('blockquote','tl-source-quote',e.quote)));
    if(refs.length>3)body.append(el('p','chart-note','本节点关联 '+refs.length+' 处原文，以上展示前3处；完整依据保留在专利详情中。'));
    const conditions=d.analysis.conditions||[];if(conditions.length)body.append(el('h3','','本件条件与限定'),...conditions.map(c=>el('p','',c.text)));
    if(d.images?.length)body.append(button('查看该申请附图与关系 ↗','text-button',()=>openPatent(id)));
  }
  async function toggleTimelineFullscreen(id){
    if(fullscreen)await toggleFullscreen();
    if(timelineFullscreen&&timelineFullscreen!==id)await toggleTimelineFullscreen(timelineFullscreen);
    const panel=$(id),isOpen=timelineFullscreen===id;
    if(isOpen){timelineFullscreen=null;panel.classList.remove('tl-fullscreen');document.body.classList.remove('tl-is-fullscreen');panel.querySelector('.tl-fullscreen-button').textContent='全屏展开 ⛶';panel.querySelector('.tl-fullscreen-button').setAttribute('aria-pressed','false');if(document.fullscreenElement&&document.exitFullscreen)try{await document.exitFullscreen();}catch(_){}document.body.append($('detail-dialog'));}
    else{timelineFullscreen=id;panel.classList.add('tl-fullscreen');document.body.classList.add('tl-is-fullscreen');panel.querySelector('.tl-fullscreen-button').textContent='退出全屏 ⛶';panel.querySelector('.tl-fullscreen-button').setAttribute('aria-pressed','true');panel.append($('detail-dialog'));if(panel.requestFullscreen)try{await panel.requestFullscreen();}catch(_){/* Full-window layout remains usable. */}}
  }
  function initializeTimelines(){
    for(const key of ['module','sub','date','mode','year'])$('timeline-'+key).addEventListener('change',event=>{timelineState[key]=event.target.value;timelineState.page=1;if(key==='module'){timelineState.sub='';timelineState.year='';}renderTimelines();});
    $('timeline-date-overview').addEventListener('change',event=>{timelineState.date=event.target.value;timelineState.page=1;renderTimelines();});
    $('timeline-prev').addEventListener('click',()=>{timelineState.page--;renderTimelines();});$('timeline-next').addEventListener('click',()=>{timelineState.page++;renderTimelines();});
    ['timeline-overview-panel','timeline-line-panel'].forEach(id=>{$(id).querySelector('.tl-fullscreen-button').addEventListener('click',()=>toggleTimelineFullscreen(id));});
    document.querySelectorAll('.tl-panel .tl-footer a').forEach(link=>{const href=link.getAttribute('href');if(href?.startsWith('#'))link.addEventListener('click',async event=>{event.preventDefault();if(timelineFullscreen)await toggleTimelineFullscreen(timelineFullscreen);$(href.slice(1))?.scrollIntoView({behavior:'smooth',block:'start'});});});
    document.querySelectorAll('.tl-scale-button').forEach(b=>b.addEventListener('click',()=>{timelineState.scale=Number(b.dataset.scale);document.querySelectorAll('.tl-scale-button').forEach(v=>v.setAttribute('aria-pressed',String(v.dataset.scale===b.dataset.scale)));renderTimelines();}));
    $('timeline-all-records').addEventListener('click',()=>inspectRows((timelineState.module||'技术')+' · 按时间排列',lineSelection(),'本图范围内的全部独立申请，按'+(timelineState.date==='filing'?'申请日':'所引文献公开日')+'从旧到新排列。'));
    document.addEventListener('keydown',e=>{if(e.key==='Escape'&&timelineFullscreen&&!$('detail-dialog').open)toggleTimelineFullscreen(timelineFullscreen);});
    document.addEventListener('fullscreenchange',()=>{if(!document.fullscreenElement&&timelineFullscreen){const id=timelineFullscreen;timelineFullscreen=null;$(id).classList.remove('tl-fullscreen');document.body.classList.remove('tl-is-fullscreen');$(id).querySelector('.tl-fullscreen-button').textContent='全屏展开 ⛶';$(id).querySelector('.tl-fullscreen-button').setAttribute('aria-pressed','false');document.body.append($('detail-dialog'));}});
    renderTimelines();window.PP_TIMELINE_VIEW=window.PP_TIMELINE_TEST={statusLabel:statusName,timelineState,timelineSample,timelineSorted,lineSelection,timelineGeometry,renderTimelines,redrawView(target,lanes,kind,dateMode){const previous=timelineState.date;timelineState.date=dateMode;try{drawTimeline(target,lanes,kind);}finally{timelineState.date=previous;}},openTimelineLine,openTimelineNode,toggleTimelineFullscreen,timelineReady};
  }

  const productData=window.PP_PRODUCTS,productEvents=window.PP_PRODUCT_EVENTS;
  Object.assign(state,{productGroup:'',productLine:''});
  const productOf=p=>productData.applications[p.id]||{group:'跨品类与待明确',line:'应用产品待明确'};
  function chooseProduct(group,line=''){
    if(fullscreen)toggleFullscreen();
    state.productGroup=group;state.productLine=line;state.module='';state.page=1;$('filter-module').value='';render();
    $('product-analysis')?.scrollIntoView({behavior:'smooth',block:'start'});
  }
  function renderProductSelectors(){
    updateTimelineSelect('filter-product-group',[['','全部产品大类'],...productData.groups.map(g=>[g,g])],state.productGroup);
    const rows=patents.filter(p=>!state.productGroup||productOf(p).group===state.productGroup);
    updateTimelineSelect('filter-product-line',[['','全部产品线'],...countBy(rows,p=>productOf(p).line).map(([l])=>[l,l])],state.productLine);
  }
  function renderProductAnalysis(area){
    const section=el('section','product-analysis');section.classList.add('product-analysis-inner');
    const top=panel(state.productGroup?'产品大类内的构成 · '+state.productGroup:'产品大类的专利布局','全部统计来自本次分析范围及当前筛选。按文献应用场景建立阅读分类；每件进入一个主产品类别，通用和跨产品用途保留单列。');
    const cards=el('div','product-cards');countBy(filtered,p=>productOf(p).group).forEach(([group,n],i)=>{const ps=filtered.filter(p=>productOf(p).group===group),card=button('','product-card',()=>chooseProduct(group));card.style.setProperty('--product-color',timelineColors[i%timelineColors.length]);card.append(el('strong','',group),el('span','product-value',nfmt(n)+' 件'),el('span','',ratio(n,filtered.length)+' · 发明 '+getCount(ps,'invention','patent_type')+' 件'),el('small','',countBy(ps,p=>productOf(p).line).slice(0,2).map(([l,n])=>l+' '+n+'件').join('；')));cards.append(card);});top.append(cards,productYearTable(filtered,'group'));section.append(top);
    const detail=panel(state.productLine?'具体产品线 · '+state.productLine:state.productGroup?'拆开产品线 · '+state.productGroup:'各产品线的年度布局','点击产品大类或产品线后，下方的技术分析、两类时间图、思维导图及专利目录同步缩小范围。* 标记年份为不完整年度，年度占比分母是当年当前筛选内的全部申请。');
    detail.append(productYearTable(filtered,'line'));
    if(state.productGroup||state.productLine){
      const counts=countBy(filtered,'primary_module'),ps=timelineSorted(filtered.filter(p=>timelineData.nodes[p.id]));
      detail.append(el('p','fact-text','该范围技术内容较集中的技术大类：'+counts.slice(0,3).map(([m,n])=>m+' '+n+'件').join('；')+'。'+(ps.length?'本次入选申请的日期为 '+ps.map(p=>p.filing_date).sort()[0]+' 至 '+ps.map(p=>p.filing_date).sort().at(-1)+'。':'')));
      detail.append(button('进入该产品线的技术时间图 ↓','primary-button',()=>$('product-patent-panel').scrollIntoView({behavior:'smooth'})));
    }
    detail.append(el('p','chart-note','通用技术用途与具体产品分别归类。未明确用途的零部件不强行摊入产品线。产品分类依据可在逐件目录查看。'));section.append(detail);area.append(section);
  }
  function renderProductFacts(){if(state.role!=='management'||!filtered.length)return;const groups=countBy(filtered,p=>productOf(p).group),top=groups[0],pair=report.settings.comparison_years,types=countBy(filtered,'patent_type');const cards=[{title:'当前范围 '+nfmt(filtered.length)+' 件申请',body:types.map(([t,n])=>typeLabel(t)+' '+nfmt(n)+' 件（'+ratio(n,filtered.length)+'）').join('；')+'。',rows:filtered},{title:top[0]+'占 '+ratio(top[1],filtered.length),body:'按所引文献应用场景归类，共 '+nfmt(top[1])+' 件；通用用途与待明确类别单列。',rows:filtered.filter(p=>productOf(p).group===top[0])}];if(pair.length===2){const [a,b]=pair,pa=filtered.filter(p=>p.filing_date.startsWith(a)),pb=filtered.filter(p=>p.filing_date.startsWith(b));if(pa.length&&pb.length){const changes=groups.map(([g])=>({g,a:pa.filter(p=>productOf(p).group===g).length,b:pb.filter(p=>productOf(p).group===g).length})).sort((x,y)=>Math.abs(y.b/pb.length-y.a/pa.length)-Math.abs(x.b/pb.length-x.a/pa.length)),v=changes[0];cards.push({title:v.g+'的年度构成变化',body:a+'年 '+v.a+'件（'+ratio(v.a,pa.length)+'）；'+b+'年 '+v.b+'件（'+ratio(v.b,pb.length)+'）。这是已公开申请的构成变化。',rows:[...pa,...pb].filter(p=>productOf(p).group===v.g)});}}replace($('insight-grid'),cards.map(v=>add(el('article','insight-card'),el('h3','',v.title),el('p','',v.body),button('查看构成申请','text-button',()=>inspectRows(v.title,v.rows)))));}
  function applicableProductEvents(){return productEvents.events.filter(e=>(!state.productGroup||e.groups.includes(state.productGroup))&&(!state.productLine||e.lines.includes(state.productLine)));}
  function renderProductEvents(){
    const events=applicableProductEvents(),canvas=$('company-product-canvas'),board=el('div','business-history');
    $('company-product-scope').textContent=(state.productLine||state.productGroup||'全部产品方向')+' · '+events.length+' 个已查证节点 · 按事件顺序排布，卡片间距不代表年数。';
    events.forEach(e=>{const source=productEvents.sources[e.source],card=el('article','business-event');const badge=el('span','event-kind',e.kind);badge.dataset.kind=e.kind;card.append(el('time','',e.date),badge,el('h4','',e.title),el('p','',e.body),el('small','',e.precision==='reporting_year'?'按报告年度归位；不是上市日期。':e.precision==='period'?'公司披露的发展阶段。':'来源仅精确至年份，未补造月日。'),button('查看来源与节点说明','text-button',()=>{showDialog('公司产品线节点 · 官方披露');$('dialog-body').append(el('h2','',e.title),el('p','',e.date+' · '+e.kind),el('p','',e.body),el('p','','来源：'+source.title+'；'+source.locator),el('p','','来源披露日期：'+(source.publication_date||'网页未标注，见来源记录的查证日期')),externalLink(source.url,'打开来源 ↗'),el('p','chart-note','该事件与下方同主题专利并置阅读，不表示产品实施了某一专利，也不表示该事件导致专利数量变化。'));}));board.append(card);});
    replace(canvas,events.length?board:empty('该产品线暂无已查证的年份节点','可以继续阅读该产品线的专利技术时间图。'));
    const dateBefore=timelineState.date;timelineState.date='filing';
    const rows=timelineReady(),selection=state.productGroup||state.productLine,keys=countBy(rows,p=>selection?p.primary_module:productOf(p).group);
    const lanes=keys.map(([key,n],i)=>{const ps=rows.filter(p=>(selection?p.primary_module:productOf(p).group)===key),nodes=timelineSample(ps);return {label:key,module:selection?key:'',sub:'',total:n,colorIndex:i,nodes:nodes.map(p=>({p})),note:selection?'本产品范围内的该技术路线。':'本产品大类，按年选首末申请。'};});
    drawTimeline('product-patent-canvas',lanes,'product');
    timelineState.date=dateBefore;
    $('product-patent-scope').textContent=(state.productLine||state.productGroup||'各产品大类')+' · 本图按申请日排列，每条线每年选首末申请，展示具体方案；下方细分技术时间图可切到全部申请。';
  }
  function productEvidence(id){const p=byId.get(id),v=productOf(p);showDialog('产品归类依据');$('dialog-body').append(el('h2','',v.group+' / '+v.line),el('p','',v.method),el('p','','依据字段：'+(v.field||'尚无技术依据')),el('blockquote','tl-source-quote',v.text||'未明确对应产品。'),el('p','','匹配词：'+((v.matches||[]).join('、')||'无')),button('打开该申请与依据 ↗','text-button',()=>openPatent(id,v.evidence_ids)));}
  function renderProductGraph(){
    const canvas=$('graph-canvas'),sx=canvas.scrollLeft,sy=canvas.scrollTop,focusKey=document.activeElement?.dataset.mapKey,tree=el('div','mindmap'),root=mapNode(company+'产品线专利布局',filtered.length,0,()=>{openBranches.clear();renderGraph();},'产品大类 → 产品线 → 技术 → 方案'),branches=el('ul','mind-children root-branches');tree.append(root,branches);
    countBy(filtered,p=>productOf(p).group).forEach(([group],i)=>{const ps=filtered.filter(p=>productOf(p).group===group),gkey='pg:'+group;
      const branch=treeBranch(gkey,group,ps,1,ul=>countBy(ps,p=>productOf(p).line).forEach(([line])=>{const lp=ps.filter(p=>productOf(p).line===line),lk=gkey+'|'+line;
        const lineBranch=treeBranch(lk,line,lp,2,lu=>countBy(lp,'primary_module').forEach(([module])=>{const mp=lp.filter(p=>p.primary_module===module),mk=lk+'|'+module;
          const mb=treeBranch(mk,module,mp,2,mu=>countBy(mp,'secondary_technology').forEach(([sub])=>{const sp=mp.filter(p=>p.secondary_technology===sub),sk=mk+'|'+sub;mu.append(treeBranch(sk,sub,sp,2,su=>{const li=el('li');li.append(button('技术梳理','mind-timeline',()=>{chooseProduct(group,line);openRoute(module,sub);}));su.append(li);appendLeaves(su,sk,sp);}));}));
          if(module!=='待分析')mb.querySelector('.mind-node').append(button('该产品的技术梳理','mind-timeline',()=>{chooseProduct(group,line);openRoute(module);}),button('该产品的技术时间图 ↗','mind-timeline',async()=>{chooseProduct(group,line);await openTimelineLine(module);}));lu.append(mb);
        }));lineBranch.querySelector('.mind-node').append(button('产品线分析与节点 ↗','mind-timeline',()=>chooseProduct(group,line)));ul.append(lineBranch);
      }));branch.style.setProperty('--branch-color',timelineColors[i%timelineColors.length]);branches.append(branch);
    });replace(canvas,filtered.length?tree:empty('没有匹配申请','调整筛选后展示产品线。'));updateViewBox();canvas.scrollLeft=sx;canvas.scrollTop=sy;if(focusKey){const same=[...canvas.querySelectorAll('button')].find(b=>b.dataset.mapKey===focusKey);if(same)same.focus({preventScroll:true});}$('graph-caption').textContent='产品大类 → 产品线 → 技术大类 → 技术细分 → 具体方案。分类依据随申请保存；不是实际产品采用关系。';
  }
  function initializeProducts(){
    ['product-group','product-line'].forEach(k=>$('filter-'+k).addEventListener('change',()=>{const g=k==='product-group';state[g?'productGroup':'productLine']=$('filter-'+k).value;if(g)state.productLine='';state.module='';$('filter-module').value='';state.page=1;render();}));
    ['company-product-panel','product-patent-panel'].forEach(id=>$(id).querySelector('.tl-fullscreen-button').addEventListener('click',()=>toggleTimelineFullscreen(id)));
    renderProductSelectors();renderProductEvents();window.PP_PRODUCT_TEST={productOf,chooseProduct,applicableProductEvents,productEvidence};
  }

  const routeData=window.PP_ROUTES,official=window.PP_OFFICIAL;
  const routeState={module:'',direction:''};
  let productHeatMeasure='count';
  function heatButton(n,den,max,title,action){const value=productHeatMeasure==='share'?(den?n/den:0):n,b=button(nfmt(n)+'件 · '+ratio(n,den),'heat-cell data-heat',action),strength=max?value/max:0;b.style.background=n?'rgba(38,104,199,'+(0.07+0.46*strength).toFixed(3)+')':'#f7f9fc';b.title=title+'；'+n+' / '+den+' 件；颜色按'+(productHeatMeasure==='share'?'年度占比':'申请件数');b.dataset.heatValue=String(value);return b;}
  function productYearTable(ps,key){
    const years=report.settings.years,den=Object.fromEntries(years.map(y=>[y,ps.filter(p=>p.filing_date.startsWith(y)).length]));
    const bucket=p=>key==='group'?productOf(p).group:productOf(p).group+'\u0000'+productOf(p).line;
    const sets=countBy(ps,bucket).map(([token,n])=>({token,n,rows:ps.filter(p=>bucket(p)===token)}));
    const max=Math.max(0,...sets.flatMap(s=>years.map(y=>{const n=s.rows.filter(p=>p.filing_date.startsWith(y)).length;return productHeatMeasure==='share'?(den[y]?n/den[y]:0):n;})));
    const box=el('div','heat-table-block'),controls=el('div','heat-legend');controls.append(el('span','','颜色依据：'));
    ['count','share'].forEach(k=>{const b=button(k==='count'?'申请件数':'年度占比','heat-mode',()=>{productHeatMeasure=k;renderAnalysis();});b.setAttribute('aria-pressed',String(productHeatMeasure===k));controls.append(b);});
    controls.append(el('span','heat-swatch light','少'),el('span','heat-swatch mid'),el('span','heat-swatch dark','多'),el('small','','同表统一色阶；零值留白。'));box.append(controls);
    box.append(table([key==='group'?'产品大类':'产品线',...years.map(y=>y+(report.settings.partial_years.includes(y)?' *':'')),'合计','授权有效','审中'],sets.map(({rows,n})=>{const v=productOf(rows[0]),name=key==='group'?v.group:v.line,label=key==='line'&&!state.productGroup?v.group+' / '+name:name;return [button(label,'table-link',()=>chooseProduct(v.group,key==='line'?name:'')),...years.map(y=>{const yp=rows.filter(p=>p.filing_date.startsWith(y));return heatButton(yp.length,den[y],max,label+' · '+y,()=>inspectRows(label+' · '+y,yp));}),n,getCount(rows,'有效','legal_status'),getCount(rows,'审中','legal_status')];})));
    return box;
  }
  function shareCard(label,value,note,basis,action){return add(el('article','metric-card headline-card'),el('span','metric-basis',basis),el('div','metric-label',label),el('strong','metric-number',value),el('p','metric-note',note),button('查看口径与来源','text-button',action));}
  function showOfficial(){showDialog('企业披露拥有量');const body=$('dialog-body');if(!official.owned){body.append(el('h2','','尚无核验的企业拥有量'),el('p','','检索范围内的公开申请数量不能替代当前拥有量。'));return;}body.append(el('h2','',official.source_title),el('p','','统计截至 '+official.period_end+'；'+official.definition),table(['类别','拥有量'],[['合计',official.owned.total],...['invention','utility_model','design'].map(k=>[typeLabel(k),official.owned[k]??'未知'])]),el('p','',official.locator),externalLink(official.url,'查看原始披露 ↗'));}
  function geoBuckets(rows){const home=report.settings.home_authorities;return {home:rows.filter(p=>home.includes(p.authority)),pct:rows.filter(p=>p.authority==='WO'),outside:rows.filter(p=>p.authority&&!['WO','unknown',...home].includes(p.authority)),unknown:rows.filter(p=>!p.authority||p.authority==='unknown')};}
  function showGeography(){showDialog('地域布局口径');const rows=portfolio.rows,g=geoBuckets(rows),home=report.settings.home_authorities;$('dialog-body').append(el('h2','','境外申请布局'),el('p','',home.length?'本土受理机构：'+home.join('、')+'。境外 '+g.outside.length+' / '+rows.length+' 件；PCT '+g.pct.length+' 件单列；受理机构未知 '+g.unknown.length+' 件。':'本土地域尚未定义，境外占比保持未知。'),el('p','',portfolio.scope),table(['受理机构','申请数'],countBy(rows,'authority').map(([a,n])=>[button(names[a]||a,'table-link',()=>inspectRows(names[a]||a,rows.filter(p=>p.authority===a),portfolio.scope)),n])),el('p','chart-note','每件独立申请计一次。受理机构代表申请布局，有效权利另看各法域状态；PCT不计作一个境外国家。受理机构存在未知值时，不给出完整境外占比。'));}
  function headlineTypeSource(owned,records){
    const keys=['invention','utility_model','design'],valid=n=>Number.isSafeInteger(n)&&n>=0;
    const completeOwned=Boolean(owned&&valid(owned.total)&&keys.every(k=>valid(owned[k]))&&keys.reduce((n,k)=>n+owned[k],0)===owned.total);
    if(completeOwned)return {source:'official_owned',total:owned.total,counts:Object.fromEntries(keys.map(k=>[k,owned[k]])),unknown:0,hasRatio:owned.total>0};
    const rows=Array.isArray(records)?records:[];
    if(rows.length){const counts=Object.fromEntries(keys.map(k=>[k,rows.filter(p=>p.patent_type===k).length]));return {source:'verified_portfolio',total:rows.length,counts,unknown:rows.filter(p=>!keys.includes(p.patent_type)).length,hasRatio:true};}
    return {source:'none',total:null,counts:Object.fromEntries(keys.map(k=>[k,null])),unknown:null,hasRatio:false};
  }
  function renderHeadlines(){
    const o=official.owned,rows=portfolio.rows,g=geoBuckets(rows),types=headlineTypeSource(o,rows),ownedKnown=Boolean(o&&Number.isSafeInteger(o.total)&&o.total>=0),cards=[];
    if(ownedKnown)cards.push(shareCard('企业披露拥有量',nfmt(o.total)+' 项','截至 '+official.period_end+'；'+official.definition+'。','企业披露 · 独立口径',showOfficial));
    if(types.source!=='none'){
      const disclosed=types.source==='official_owned',basis=disclosed?'企业披露 · 拥有量':'已核验公开申请 · '+portfolio.scope;
      for(const key of ['invention','utility_model','design']){
        const count=types.counts[key],label=typeLabel(key)+(types.hasRatio?(disclosed?'拥有占比':'申请占比'):'拥有量'),value=types.hasRatio?ratio(count,types.total):nfmt(count)+' 项';
        const note=nfmt(count)+' / '+nfmt(types.total)+'；'+(disclosed?'同一披露时点的三类型拥有量。':'本次目录全部申请，含外观设计。')+(types.unknown?'其中 '+nfmt(types.unknown)+' 件类型未明确，当前数值仅计已识别记录。':'')+(!types.hasRatio?'分母为零，不计算占比。':'');
        cards.push(shareCard(label,value,note,basis,disclosed?showOfficial:()=>inspectRows(typeLabel(key)+'申请',rows.filter(p=>p.patent_type===key),portfolio.scope)));
      }
    }
    if(rows.length&&report.settings.home_authorities.length&&!g.unknown.length)cards.push(shareCard('境外申请占比',ratio(g.outside.length,rows.length),'本土：'+report.settings.home_authorities.join('、')+'；PCT单列。','已核验公开申请 · '+portfolio.scope,showGeography));
    replace($('executive-metrics'),...cards);
    const facts=el('div','executive-facts');
    facts.append(el('p','',rows.length?'公开申请统计 '+nfmt(rows.length)+' 件；'+portfolio.scope+'。':'尚无可用于类型构成计算的已核验公开申请记录。'));
    if(types.source==='verified_portfolio'&&o)facts.append(el('p','','三种类型统一以本次目录 '+nfmt(types.total)+' 件为分母；企业披露拥有量另按披露时点和定义列示，两种口径不混算。'));
    if(types.source==='official_owned')facts.append(el('p','','类型构成采用同一披露时点、可对账的发明、实用新型和外观拥有量；本次公开申请目录另行统计。'));
    if(types.unknown)facts.append(el('p','','目录中 '+nfmt(types.unknown)+' 件类型尚未明确，保留在全部申请分母及来源中，不补定类型。'));
    if(!ownedKnown||types.source!=='official_owned')facts.append(button('企业披露与缺失字段说明','text-button',showOfficial));
    if(!rows.length||!report.settings.home_authorities.length||g.unknown.length)facts.append(button('地域布局的范围与缺失信息','text-button',showGeography));
    if(report.settings.coverage_note)facts.append(el('p','',report.settings.coverage_note));
    replace($('executive-facts'),facts);
  }
  function routeRows(){return filtered.filter(p=>routeData.nodes[p.id]&&p.primary_module===routeState.module&&(!routeState.direction||p.secondary_technology===routeState.direction));}
  function routeCases(rows){const sorted=[...rows].sort((a,b)=>a.filing_date.localeCompare(b.filing_date)||a.id.localeCompare(b.id)),chosen=new Map();for(const y of [...new Set(sorted.map(p=>p.filing_date.slice(0,4)))]){const ys=sorted.filter(p=>p.filing_date.startsWith(y));for(const p of [ys[0],ys.at(-1)])chosen.set(p.id,p);}return [...chosen.values()].sort((a,b)=>a.filing_date.localeCompare(b.filing_date)||a.id.localeCompare(b.id));}
  function routeExcerpt(p){const n=routeData.nodes[p.id];return n.technical_means[0]?.text||p.summary;}
  function evidenceParagraph(body,label,values,id){if(!values.length)return;body.append(el('h4','',label));values.forEach(v=>body.append(add(el('div','route-evidence'),el('p','',v.text),button('对应原文','text-button',()=>openPatent(id,v.evidence_ids)))));}
  function openRouteCase(id){const p=byId.get(id),n=routeData.nodes[id];showDialog('技术方案与依据');const body=$('dialog-body');body.append(el('h2','',p.title),el('p','tl-modal-meta',p.filing_date+' 申请 · '+timelineData.nodes[id].publication_number),el('p','',p.summary));evidenceParagraph(body,'应用位置',n.application_field,id);evidenceParagraph(body,'文献记载的技术问题',n.technical_problem,id);evidenceParagraph(body,'结构与作用过程',n.technical_means,id);evidenceParagraph(body,'条件与限定',n.conditions,id);if(!n.technical_problem.length)body.append(el('p','chart-note','本件已提取内容中未明确技术问题，保留结构与过程说明。'));body.append(button('查看完整专利与文献版本','primary-button',()=>openPatent(id)));}
  async function openRoute(module,direction=''){
    if(fullscreen)await toggleFullscreen();if(timelineFullscreen)await toggleTimelineFullscreen(timelineFullscreen);
    routeState.module=module;routeState.direction=direction;renderRoutes();$('technical-review').scrollIntoView({behavior:'smooth',block:'start'});$('route-module').focus({preventScroll:true});
  }
  function renderRoutes(){
    const available=countBy(filtered.filter(p=>routeData.nodes[p.id]),'primary_module');
    if(!available.some(([m])=>m===routeState.module)){routeState.module=available[0]?.[0]||'';routeState.direction='';}
    const all=filtered.filter(p=>routeData.nodes[p.id]&&p.primary_module===routeState.module),dirs=countBy(all,'secondary_technology');
    if(routeState.direction&&!dirs.some(([d])=>d===routeState.direction))routeState.direction='';
    updateTimelineSelect('route-module',available.map(([m,n])=>[m,m+' · '+n+'件']),routeState.module);
    updateTimelineSelect('route-direction',[['','全部实现方向'],...dirs.map(([d,n])=>[d,d+' · '+n+'件'])],routeState.direction);
    const rows=routeRows(),body=$('route-content');replace(body);if(!rows.length){body.append(empty('当前筛选没有已完成技术解读的申请','调整筛选后查看技术梳理。'));return;}
    const focus=routeData.modules.find(m=>m.module===routeState.module)?.focus||'技术内容按实现方向与申请时间组织。',dates=rows.map(p=>p.filing_date).sort(),years=report.settings.years;
    body.append(el('h3','',routeState.direction||routeState.module),el('p','route-focus',focus),el('p','','当前范围 '+nfmt(rows.length)+' 件，申请日 '+dates[0]+' 至 '+dates.at(-1)+'。应用产品主要涉及 '+countBy(rows,p=>productOf(p).line).slice(0,3).map(([p,n])=>p+'（'+n+'件）').join('、')+'。'));
    const controls=el('div','route-actions');controls.append(button('查看对应技术时间图 ↓','primary-button',()=>openTimelineLine(routeState.module,routeState.direction)),button('查看全部 '+rows.length+' 件申请','text-button',()=>inspectRows(routeState.direction||routeState.module,rows)));body.append(controls);
    if(!routeState.direction){
      body.append(el('h4','','实现方向与技术内容'));
      const t=table(['实现方向','涉及的结构或过程（具体方案）','申请数','阅读'],dirs.map(([d,n])=>{const ps=all.filter(p=>p.secondary_technology===d),cases=routeCases(ps),p=cases.at(-1);return [button(d,'table-link',()=>openRoute(routeState.module,d)),add(el('div','route-cell'),el('p','',routeExcerpt(p)),button('方案原文 · '+timelineData.nodes[p.id].publication_number,'text-button',()=>openRouteCase(p.id))),n,button('梳理与时间','table-link',()=>openRoute(routeState.module,d))];}));t.classList.add('route-table');body.append(t);
    }
    body.append(el('h4','','申请时间与技术内容'),table(['申请年','件数','发明','授权有效','审中'],years.map(y=>{const ys=rows.filter(p=>p.filing_date.startsWith(y));return [y+(report.settings.partial_years.includes(y)?' *':''),ys.length,getCount(ys,'invention','patent_type'),getCount(ys,'有效','legal_status'),getCount(ys,'审中','legal_status')];})),el('p','chart-note','* 标记年份为不完整年度。下列方案按各年首末申请选取，用于对照结构、动作和条件；同年只有一件时展示该件。'));
    const cases=el('div','route-cases');routeCases(rows).forEach(p=>{const n=routeData.nodes[p.id],card=el('article','route-case');card.append(el('time','',p.filing_date+' · 申请'),el('h4','',p.tags?.[0]||p.title),el('p','route-direction',p.secondary_technology),el('p','',n.application_field.map(v=>v.text).join('；')),el('strong','','结构与作用过程'),el('p','',n.technical_means.map(v=>v.text).join('；')));if(n.conditions.length)card.append(el('strong','','条件与限定'),el('p','',n.conditions.map(v=>v.text).join('；')));else card.append(el('small','','已提取内容中无单列条件，完整范围见所引权利要求。'));card.append(el('small','',timelineData.nodes[p.id].publication_number+' · '+statusName(p.legal_status)),button('查看完整技术梳理与原文','text-button',()=>openRouteCase(p.id)));cases.append(card);});body.append(cases);
    const branches=countBy(rows,p=>p.secondary_technology);if(branches.length>1)body.append(el('p','chart-note','上述节点来自 '+branches.length+' 个实现方向。分支间的结构和条件按各件文献分别呈现，时间顺序仅表示申请先后。'));
  }
  function renderResearch(area){
    const box=panel('技术大类与实现方向','每个技术大类及实现方向均提供结构、过程、条件与申请时间的梳理。');
    const groups=countBy(filtered,p=>p.primary_module+'｜'+p.secondary_technology);
    const t=table(['技术大类','实现方向','申请数','发明','授权有效'],groups.map(([key,n])=>{const [m,s]=key.split('｜'),ps=filtered.filter(p=>p.primary_module===m&&p.secondary_technology===s);return [m==='待分析'?m:button(m,'table-link',()=>openRoute(m)),m==='待分析'?s:button(s,'table-link',()=>openRoute(m,s)),n,getCount(ps,'invention','patent_type'),getCount(ps,'有效','legal_status')];}));t.classList.add('route-index-table');box.append(t);area.append(box);appendSourceComparisons(area);renderTrend(area);
  }
  function readerScope(){showDialog('范围与来源');const b=$('dialog-body');b.append(el('h2','','统计范围'),table(['口径','范围'],[['公司概览',portfolio.scope],['技术分析',report.settings.analysis_label],['申请日期',report.settings.date_note],['公开截止',run.as_of_date],['法律状态观察',report.settings.status_observed_at]]),el('p','',report.settings.coverage_note),el('p','','技术梳理优先采用完整权利要求，按需补读说明书。图中的申请先后与产品发布时间分别保留。'),el('p','','产品与技术大类每件一项，交叉标签可多选；通用或未明确用途不强行归入具体产品。'));if(official.owned)b.append(externalLink(official.url,official.source_title+' ↗'));Object.values(productEvents.sources).forEach(s=>b.append(externalLink(s.url,s.title+' ↗')));}
  function scopeChips(target,kind){const node=$(target);replace(node);node.append(el('strong','',kind==='business'?'跟随产品选择':'跟随分析范围筛选'));const labels=[state.productGroup,state.productLine,...(kind==='business'?[]:[state.module,state.entity,state.authority,state.type?typeLabel(state.type):'',state.status?statusName(state.status):'',state.from||state.to?(state.from||'不限')+'—'+(state.to||'不限'):'',state.search?'搜索：'+state.search:'',state.basis?basisLabel(state.basis):'',state.quality?state.quality==='complete'?'已完成解读':'待补齐':''])].filter(Boolean);node.append(el('span','',labels.length?labels.join(' · '):'全部'));}
  function renderRevision06(){renderHeadlines();renderRoutes();['product-patent','timeline-overview','timeline-line','graph','route'].forEach(id=>scopeChips(id+'-filter-scope','patent'));scopeChips('company-product-filter-scope','business');document.body.dataset.readerRole=state.role;$('reader-view-note').textContent={management:'管理层视角 · 拥有量、专利类型、地域布局与产品线变化。',rd:'研发视角 · 技术大类、实现方向、结构、过程与限定条件。',ip:'专利工程师视角 · 法律状态、权利要求、文献版本与同族关系。'}[state.role];}
  function directoryCSV(rows=filtered){const cells=[['申请号','标题','产品大类','产品线','技术大类','实现方向','申请日','专利类型','法律状态','受理机构'],...rows.map(p=>[p.application_number,p.title,productOf(p).group,productOf(p).line,p.primary_module,p.secondary_technology,p.filing_date,typeLabel(p.patent_type),statusName(p.legal_status),p.authority])];const quote=v=>{let s=String(v??'');if(/^[\s]*[=+@-]/.test(s))s="'"+s;return '"'+s.replace(/"/g,'""')+'"';};return '\ufeff'+cells.map(r=>r.map(quote).join(',')).join('\r\n');}
  function initializeRevision06(){
    ['module','direction'].forEach(k=>$('route-'+k).addEventListener('change',()=>{routeState[k]=$('route-'+k).value;if(k==='module')routeState.direction='';renderRoutes();}));
    $('directory-jump').addEventListener('change',()=>{state.page=Math.min(Math.max(1,Number($('directory-jump').value)||1),Math.max(1,Math.ceil(filtered.length/50)));renderList();});
    $('download-directory').addEventListener('click',()=>{const url=URL.createObjectURL(new Blob([directoryCSV()],{type:'text/csv;charset=utf-8'})),a=el('a');a.href=url;a.download=company+'-专利目录-当前筛选.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
    document.querySelectorAll('.role-button').forEach(b=>b.addEventListener('click',()=>{if(state.role==='ip'){timelineState.mode='all';renderTimelines();}else{timelineState.mode='sample';renderTimelines();}renderRevision06();}));
    renderRevision06();window.PP_REVISION06_TEST={routeState,routeRows,routeCases,openRoute,openRouteCase,renderRoutes,renderHeadlines,geoBuckets,showOfficial,showGeography,readerScope,renderRevision06,directoryCSV};
  }

  $('route-intro').textContent=routeData.modules.length+'个技术大类、'+routeData.directions.length+'个实现方向；应用位置、结构、过程、条件与申请时间分别呈现。';
  $('event-count-intro').textContent=productEvents.events.length+'个已查证产品与业务节点；未提供来源的事件不补造。';
  $('overview-count-intro').textContent=timelineData.featured.length+'个重点主题；各条技术线可展开全部申请。';
  initialize();
  initializeReport();
  initializeTimelines();
  initializeProducts();
  initializeRevision06();
}());

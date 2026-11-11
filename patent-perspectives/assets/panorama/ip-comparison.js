(function () {
  'use strict';
  const data = window.PP_CLAIM_COMPARISONS || {groups: []};
  const groups = Array.isArray(data.groups) ? data.groups : [];
  const host = document.getElementById('claim-element-comparison');
  if (!host) return;
  const links = [...document.querySelectorAll('[data-ip-comparison-link]')];
  const role = () => document.body.dataset.readerRole || document.querySelector('.role-button.active')?.dataset.role || 'management';
  const create = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const note = text => create('p', 'ipcmp-note', text);
  const button = (text, onClick, className = 'text-button') => {
    const node = create('button', className, text);
    node.type = 'button'; node.addEventListener('click', onClick); return node;
  };
  const names = {components: '部件组成', position: '安装位置', connection: '连接关系', process: '步骤与动作', conditions: '触发与限制', claim_scope: '权项层级', other: '其他要素'};
  const states = {disclosed: '所引权利要求已披露', not_disclosed: '所引完整权利要求中未披露', not_acquired: '对应版本正文未取得'};
  const narrow = matchMedia('(max-width:580px)');
  let groupIndex = 0, selected = new Set(), category = '', layout = narrow.matches ? 'cards' : 'table', chosenLayout = false, mounted = false;
  const dialog = create('dialog', 'ipcmp-dialog'); dialog.id = 'claim-comparison-dialog';
  const dialogTop = create('div', 'ipcmp-dialog-top'), dialogBody = create('div', 'ipcmp-dialog-body');
  dialogTop.append(create('strong', '', '权利要求原文与版本'), button('关闭 ×', () => dialog.close()));
  dialog.append(dialogTop, dialogBody); document.body.append(dialog);
  let dialogFocus = null;
  dialog.addEventListener('close', () => { dialogFocus?.focus({preventScroll: true}); });
  function active() { return groups[groupIndex]; }
  function showDocument(column, evidence) {
    if (!column.document) return;
    const doc = column.document, chars = Array.from(doc.text);
    dialogBody.replaceChildren(create('h2', '', doc.publication_number), note('文献版本：' + doc.version + '；原文语言：' + doc.language));
    if (evidence && chars.slice(evidence.start, evidence.end).join('') !== evidence.quote) {
      dialogBody.append(note('当前引文与此版本的原文位置不一致，暂停展示该引文。'));
    } else {
      if (evidence) dialogBody.append(note('权利要求 ' + evidence.claim_number + ' · 证据 ' + evidence.evidence_id), create('blockquote', 'ipcmp-quote', evidence.quote));
      const original = create('div', 'ipcmp-original'); original.dataset.documentId = doc.id;
      if (evidence) {
        const mark = create('mark', '', evidence.quote); mark.dataset.quoteMatched = 'true';
        original.append(document.createTextNode(chars.slice(0, evidence.start).join('')), mark, document.createTextNode(chars.slice(evidence.end).join('')));
      } else original.textContent = doc.text;
      dialogBody.append(original, note('本格依据与以上公开号、文献版本和权项绑定；未取得的版本不由其他同族文本替代。'));
    }
    dialogFocus = document.activeElement;
    if (!dialog.open) dialog.showModal();
    dialog.scrollTop = 0;
    if (evidence) requestAnimationFrame(() => dialogBody.querySelector('mark')?.scrollIntoView({block: 'center'}));
  }
  function cellContent(cell, column) {
    const node = create('div', 'ipcmp-cell');
    node.append(create('span', 'ipcmp-state' + (cell.state === 'disclosed' ? '' : ' ipcmp-state-absent'), states[cell.state]), create('p', '', cell.text));
    if (cell.state === 'not_disclosed') node.append(create('small', 'ipcmp-scope', '仅限已声明读完的权利要求 ' + cell.reviewed_claim_numbers.join('、') + '；不是对全部专利或实施方式的否定。'));
    cell.evidence.forEach(evidence => {
      const link = button(evidence.publication_number + ' · 权 ' + evidence.claim_number + ' ↗', () => showDocument(column, evidence), 'ipcmp-evidence');
      link.dataset.evidenceId = evidence.evidence_id; link.dataset.documentId = evidence.document_id; link.title = evidence.quote;
      node.append(link);
    });
    return node;
  }
  function renderRows() {
    if (!mounted) return;
    const group = active(), columns = group.cases.filter(c => selected.has(c.id));
    const rows = group.rows.filter(r => !category || r.category === category);
    const table = create('table', 'ipcmp-table'), head = create('thead'), heading = create('tr'), body = create('tbody');
    table.style.minWidth = Math.max(650, 180 + 280 * columns.length) + 'px';
    heading.append(create('th', '', '比较要素'));
    columns.forEach(c => heading.append(create('th', '', c.label + ' · ' + c.publication_number)));
    head.append(heading); table.append(head, body);
    const cards = host.querySelector('#ipcmp-cards'); cards.replaceChildren();
    rows.forEach(row => {
      const tr = create('tr'), label = create('td'), card = create('article', 'ipcmp-row-card'), cells = create('div', 'ipcmp-cell-cards');
      label.append(create('strong', '', row.label), note(row.question)); tr.append(label);
      card.append(create('h4', '', row.label), note(row.question)); card.dataset.rowId = row.id;
      columns.forEach(column => {
        const cell = row.cells.find(c => c.case_id === column.id), td = create('td'), mini = create('div', 'ipcmp-mini');
        td.append(cellContent(cell, column)); tr.append(td);
        mini.append(create('strong', '', column.label + ' · ' + column.publication_number), cellContent(cell, column)); cells.append(mini);
      });
      body.append(tr); card.append(cells); cards.append(card);
    });
    const wrap = host.querySelector('#ipcmp-table'); wrap.replaceChildren(table); wrap.hidden = layout !== 'table'; cards.hidden = layout !== 'cards';
    host.querySelector('#ipcmp-case-count').textContent = columns.length + ' / ' + group.cases.length + ' 列 · ' + rows.length + ' 行要素';
    host.querySelectorAll('[data-category]').forEach(n => n.setAttribute('aria-pressed', String(n.dataset.category === category)));
    host.querySelectorAll('input[data-case]').forEach(input => { input.checked = selected.has(input.dataset.case); input.disabled = input.checked && selected.size <= 2; });
  }
  function mount() {
    mounted = true; const group = active();
    if (!selected.size) group.cases.forEach(c => selected.add(c.id));
    host.replaceChildren();
    const heading = create('div', 'section-heading'); heading.append(create('h2', '', '权利要求要素对照')); host.append(heading);
    if (groups.length > 1) {
      const label = create('label', 'ipcmp-group-label', '对照主题 '), chooser = create('select'); chooser.id = 'ipcmp-group';
      groups.forEach((g, i) => { const option = create('option', '', g.title); option.value = String(i); chooser.append(option); });
      chooser.value = String(groupIndex); chooser.addEventListener('change', () => { groupIndex = Number(chooser.value); selected = new Set(); category = ''; mount(); });
      label.append(chooser); host.append(label);
    }
    const intro = create('div', 'ipcmp-intro'); intro.append(create('h3', '', group.title), note(group.summary), note('适用范围：' + group.scope), note('选案理由：' + group.selection_reason));
    intro.append(note(group.mode === 'versions' ? '各列属于同一申请的不同公开号。逐要素阅读文本差异，不据差异自动判断保护范围变化。' : '各列属于不同独立申请。分别保留部件、关系和条件，不拼接成单个装置。'));
    host.append(intro);
    const chooser = create('fieldset', 'ipcmp-chooser'), list = create('div', 'ipcmp-case-list'); chooser.append(create('legend', '', '选择比较列（至少两列）'));
    group.cases.forEach(column => {
      const label = create('label', 'ipcmp-case-option'), input = create('input'), caption = create('span');
      input.type = 'checkbox'; input.dataset.case = column.id; input.checked = selected.has(column.id);
      input.addEventListener('change', () => { if (input.checked) selected.add(column.id); else if (selected.size > 2) selected.delete(column.id); renderRows(); });
      caption.append(create('strong', '', column.label), create('small', '', column.publication_number + ' · ' + column.version));
      label.append(input, caption); list.append(label);
    });
    const bottom = create('div', 'ipcmp-choice-bottom'), count = create('span', 'ipcmp-note'); count.id = 'ipcmp-case-count';
    bottom.append(count, button('恢复全部对照', () => { group.cases.forEach(c => selected.add(c.id)); renderRows(); })); chooser.append(list, bottom); host.append(chooser);
    const sources = create('div', 'ipcmp-source-cards');
    group.cases.forEach(column => {
      const card = create('article'); card.append(create('h4', '', column.label), note(column.publication_number + ' · ' + column.version));
      if (column.document) card.append(note(column.document.claim_numbers.length + ' 项完整权利要求'), button('查看完整权利要求 →', () => showDocument(column)));
      else card.append(note('该公开号已有同申请著录身份，完整权利要求未取得；不据此声称没有变化。'));
      sources.append(card);
    }); host.append(sources);
    const tools = create('div', 'ipcmp-tools'), filters = create('div', 'ipcmp-filters');
    ['', ...new Set(group.rows.map(r => r.category))].forEach(key => { const b = button(key ? names[key] || key : '全部要素', () => { category = key; renderRows(); }, 'ipcmp-filter'); b.dataset.category = key; filters.append(b); });
    const mode = create('label', '', '阅读方式 '), select = create('select'); select.id = 'ipcmp-layout';
    [['table', '并排对照'], ['cards', '逐项卡片']].forEach(([value, label]) => { const option = create('option', '', label); option.value = value; select.append(option); });
    select.value = layout; select.addEventListener('change', () => { chosenLayout = true; layout = select.value; renderRows(); });
    mode.append(select); tools.append(filters, mode); host.append(tools);
    const wrap = create('div', 'ipcmp-table-wrap'), cards = create('div'); wrap.id = 'ipcmp-table'; wrap.tabIndex = 0; wrap.setAttribute('aria-label', '权利要求要素并排对照，可横向滚动'); cards.id = 'ipcmp-cards';
    host.append(wrap, cards); renderRows();
  }
  function sync() {
    const show = groups.length > 0;
    host.hidden = !show; links.forEach(link => { link.hidden = !show; });
    if (show) { if (!mounted) mount(); }
    else {
      if (dialog.open) dialog.close(); dialogBody.replaceChildren(); host.replaceChildren(); mounted = false;
      if (location.hash === '#claim-element-comparison') history.replaceState(null, '', location.pathname + location.search + '#selected-analysis');
    }
  }
  new MutationObserver(sync).observe(document.body, {attributes: true, attributeFilter: ['data-reader-role']});
  document.querySelectorAll('.role-button').forEach(node => node.addEventListener('click', sync));
  window.addEventListener('hashchange', sync);
  narrow.addEventListener('change', () => { if (!chosenLayout) { layout = narrow.matches ? 'cards' : 'table'; if (mounted) { host.querySelector('#ipcmp-layout').value = layout; renderRows(); } } });
  const requested = new URL(location.href).searchParams.get('role');
  if (['management', 'rd', 'ip'].includes(requested)) document.querySelector('.role-button[data-role="' + requested + '"]')?.click();
  sync();
  if (groups.length && location.hash === '#claim-element-comparison') requestAnimationFrame(() => host.scrollIntoView());
  window.PP_CLAIM_COMPARE = {snapshot: () => ({role: role(), visible: !host.hidden, mounted, groupIndex, selected: [...selected], category, layout, dialogOpen: dialog.open})};
}());

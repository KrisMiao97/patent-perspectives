(() => {
  'use strict';
  const documentTypes = {claims:'权利要求', description:'说明书'};
  const kinds = {observation:'原文观察', hypothesis:'待核假设', research_action:'后续验证'};

  function add(container, tag, value, className) {
    const node = document.createElement(tag);
    node.className = className;
    node.textContent = value;
    container.append(node);
    return node;
  }

  function appendBoundary(container, boundary, fact) {
    if (!boundary) return;
    const block = add(container, 'div', '', 'role-evidence-boundary');
    if (fact) add(block, 'p', fact.statement, 'role-shared-fact');
    const scope = [kinds[boundary.kind], boundary.scope,
      Number.isInteger(boundary.application_count) ? `${boundary.application_count} 件关联申请` : ''].filter(Boolean);
    if (scope.length) add(block, 'p', scope.join(' · '), 'role-evidence-scope');
    if (boundary.versions?.length) {
      const versions = boundary.versions.map(source =>
        [source.publication, source.version, documentTypes[source.document_type]].filter(Boolean).join(' / '));
      add(block, 'p', '原文版本 ' + versions.join('；'), 'role-evidence-versions');
    }
    if (boundary.limitations?.length) {
      const limits = add(block, 'ul', '', 'role-evidence-limitations');
      for (const limit of boundary.limitations) add(limits, 'li', limit, '');
    }
  }

  const verifiedStatus = record => record.verified_legal_status || 'unknown';

  function statusCoverage(rows) {
    const counts = new Map();
    for (const row of rows) {
      const status = verifiedStatus(row);
      counts.set(status, (counts.get(status) || 0) + 1);
    }
    const unknown = counts.get('unknown') || 0;
    return {known:rows.length - unknown, unknown, count:status => counts.get(status) || 0};
  }

  window.PP_ROLE_EVIDENCE = {appendBoundary, verifiedStatus, statusCoverage};
})();

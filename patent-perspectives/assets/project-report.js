(() => {
  'use strict';
  const root = document.getElementById('project-report');
  if (!root) return;
  const pages = Array.from(root.querySelectorAll('.project-module'));
  const roles = Array.from(root.querySelectorAll('[data-project-role]'));
  const picker = root.querySelector('#project-module');
  const sources = Array.from(root.querySelectorAll('[data-project-material]'));
  const last = new Map();
  let active;
  const readerNav=document.getElementById('chapter')?.closest('aside');
  const topBar=document.querySelector(readerNav?'body>header':'.topbar');
  function updateStickyNav() {
    const fixed=topBar && ['sticky','fixed'].includes(getComputedStyle(topBar).position);
    const inset=fixed?topBar.offsetHeight:0;
    root.style.setProperty('--project-top',inset+'px');
    if(readerNav){
      const box=root.getBoundingClientRect();
      document.body.classList.toggle('project-in-view',!root.hidden && box.top<innerHeight && box.bottom>inset+60);
    }
  }
  if(readerNav)root.classList.add('project-in-reader');
  if(topBar)new ResizeObserver(updateStickyNav).observe(topBar);
  window.addEventListener('scroll',updateStickyNav,{passive:true});

  function choose(role, key) {
    const choices = pages.filter(p => p.dataset.projectKey.split('/')[0] === role);
    root.hidden = choices.length === 0;
    updateStickyNav();
    if (root.hidden) return;
    active = choices.find(p => p.dataset.projectKey === (key || last.get(role))) || choices[0];
    last.set(role, active.dataset.projectKey);
    roles.forEach(b => b.setAttribute('aria-pressed', String(b.dataset.projectRole === role)));
    picker.replaceChildren();
    for (const [track, label] of [['near','近期预研'],['reserve','中长期储备']]) {
      const group = document.createElement('optgroup'); group.label = label;
      for (const p of choices.filter(p => p.dataset.track === track)) group.append(new Option(p.dataset.title, p.dataset.projectKey));
      if (group.children.length) picker.append(group);
    }
    picker.value = active.dataset.projectKey;
    pages.forEach(p => p.hidden = p !== active);
  }
  function open(key, scroll, updateHash) {
    const page = pages.find(p => p.dataset.projectKey === key);
    if (!page) return;
    const role = key.split('/')[0];
    document.dispatchEvent(new CustomEvent('reader-role', {detail:role}));
    choose(role, key);
    if (updateHash) history.replaceState(null,'','#project/'+key);
    if (scroll) root.scrollIntoView({block:'start'});
  }
  function fromHash() {
    if (location.hash.startsWith('#project/')) open(location.hash.slice(9), true, false);
  }
  choose(root.dataset.initialRole);
  picker.addEventListener('change', () => open(picker.value, true, true));
  for (const b of roles) b.addEventListener('click', () => {
    const role = b.dataset.projectRole;
    open(last.get(role) || pages.find(p => p.dataset.projectKey.startsWith(role+'/')).dataset.projectKey, false, true);
  });
  document.addEventListener('click', event => {
    const role = event.target.closest('[data-role],[data-guide-role]');
    if (!role) return;
    const selected = role.dataset.role || role.dataset.guideRole;
    choose(selected);
    if (location.hash.startsWith('#project/')) history.replaceState(null,'',root.hidden ? location.pathname+location.search : '#project/'+active.dataset.projectKey);
  });
  const dialog = root.querySelector('.project-dialog');
  root.addEventListener('click', event => {
    const button = event.target.closest('button');
    if (!button) return;
    if (button.hasAttribute('data-project-source')) {
      const note = sources.find(n => n.dataset.projectMaterial === button.dataset.projectSource);
      if (note) {note.open = true;note.querySelector('summary').focus();note.scrollIntoView({block:'center'});}
    } else if (button.classList.contains('project-zoom')) {
      const fig = button.closest('figure'), img = button.querySelector('img'), large = dialog.querySelector('img');
      large.src = img.src; large.alt = img.alt;
      dialog.querySelector('h3').textContent = fig.querySelector('figcaption').textContent;
      dialog.querySelector('p').textContent = img.alt;
      dialog.showModal();
      const viewport=large.parentElement;
      viewport.scrollLeft = Math.max(0,(Number(button.dataset.cx)||img.naturalWidth/2)-viewport.clientWidth/2);
      viewport.scrollTop = Math.max(0,(Number(button.dataset.cy)||img.naturalHeight/2)-viewport.clientHeight/2);
    } else if (button.classList.contains('project-close')) dialog.close();
  });
  const search = root.querySelector('.project-search');
  const input = search.querySelector('input');
  const results = search.querySelector('[role=status]');
  input.addEventListener('input', () => {
    const query=input.value.trim().toLocaleLowerCase(); results.replaceChildren();
    if (!query) return;
    for (const p of pages) {
      const match = Array.from(p.querySelectorAll('h2,h3,p,strong')).find(n => n.textContent.toLocaleLowerCase().includes(query));
      if (!match) continue;
      const b = document.createElement('button'); b.type = 'button';
      b.textContent = p.querySelector('.project-meta').textContent+' · '+p.dataset.title+' — '+match.textContent;
      b.addEventListener('click', () => {
        open(p.dataset.projectKey,false,true);match.tabIndex=-1;match.focus({preventScroll:true});
        match.scrollIntoView({block:'center'});
      });
      results.append(b);
    }
    if (!results.children.length) results.textContent='没有找到相符的项目章节。';
  });
  window.addEventListener('hashchange',fromHash);
  function start() {
    if (location.hash.startsWith('#project/')) fromHash();
    else document.dispatchEvent(new CustomEvent('reader-role', {detail:root.dataset.initialRole}));
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',start,{once:true});
  else start();
})();

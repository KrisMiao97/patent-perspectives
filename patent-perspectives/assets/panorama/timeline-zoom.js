(function(){
 'use strict';
 const MIN=.001, MAX=2, states=new Map();
 const nodes=['timeline-overview-canvas','timeline-line-canvas','product-patent-canvas'];
 const make=(tag,cls,text)=>{const el=document.createElement(tag);if(cls)el.className=cls;if(text!==undefined)el.textContent=text;return el;};
 const clamp=v=>Math.min(MAX,Math.max(MIN,v));
 function install(id){
  const canvas=document.getElementById(id),panel=canvas?.closest('.tl-panel');if(!panel)return;
  const toolbar=panel.querySelector('.tl-toolbar'), title=toolbar.querySelector('h3')?.textContent||'技术时间图';
  const controls=make('div','tl-zoom-controls');controls.setAttribute('role','group');controls.setAttribute('aria-label',title+' · 视图缩放');
  const s={canvas,panel,controls,scale:1,mode:'manual',board:null,raf:0};states.set(id,s);canvas.dataset.zoomReady='true';
  const act=(text,label,handler)=>{const b=make('button','',text);b.type='button';b.setAttribute('aria-label',title+'：'+label);b.onclick=handler;return b;};
  const minus=act('− 缩小','缩小时间图',()=>setZoom(s,s.scale/1.25));minus.dataset.zoomAction='out';
  const plus=act('+ 放大','放大时间图',()=>setZoom(s,s.scale*1.25));plus.dataset.zoomAction='in';
  const range=make('input');range.type='range';range.min='0.1';range.max='200';range.step='0.1';range.value='100';range.setAttribute('aria-label',title+'：缩放比例');range.oninput=()=>setZoom(s,Number(range.value)/100);
  const output=make('output','','100%');output.setAttribute('aria-live','polite');
  const fit=act('看全图','缩放至完整图形',()=>setFit(s,'fit'));fit.dataset.zoomAction='fit';fit.setAttribute('aria-pressed','false');
  const width=act('适应宽度','缩放至窗口宽度',()=>setFit(s,'width'));width.dataset.zoomAction='width';width.setAttribute('aria-pressed','false');
  const reset=act('100%','恢复原始大小',()=>setZoom(s,1));reset.dataset.zoomAction='reset';
  controls.append(make('span','tl-zoom-title','视图缩放'),minus,range,plus,output,fit,width,reset,make('span','tl-zoom-hint','看全图查看整体分布；放大或点击节点阅读方案。'));
  toolbar.append(controls);Object.assign(s,{minus,plus,range,output,fit,width,reset});
  const schedule=()=>{if(s.raf)return;s.raf=requestAnimationFrame(()=>{s.raf=0;refresh(s);});};
  new MutationObserver(schedule).observe(canvas,{childList:true});
  new ResizeObserver(schedule).observe(canvas);
  canvas.addEventListener('wheel',event=>{if(!event.ctrlKey||!s.board||canvas.dataset.timelineView==='compact')return;event.preventDefault();const rect=canvas.getBoundingClientRect();setZoom(s,s.scale*Math.exp(-event.deltaY*.004),{x:event.clientX-rect.left,y:event.clientY-rect.top});},{passive:false});
  refresh(s);
 }
 function updateControls(s){
  const available=Boolean(s.board),value=s.scale*100;
  s.range.disabled=s.fit.disabled=s.width.disabled=s.reset.disabled=!available;
  s.minus.disabled=!available||s.scale<=MIN+.00001;s.plus.disabled=!available||s.scale>=MAX-.00001;
  s.output.value=available?(value<10?value.toFixed(1):Math.round(value))+'%':'—';s.range.value=String(value);s.range.setAttribute('aria-valuetext',s.output.value);
  s.fit.setAttribute('aria-pressed',String(s.mode==='fit'));s.width.setAttribute('aria-pressed',String(s.mode==='width'));
  s.canvas.dataset.zoomScale=String(s.scale);s.canvas.dataset.zoomMode=s.mode;
 }
 function apply(s,value,anchor,resetScroll=false){
  const old=s.scale,next=clamp(value),x=anchor?.x??s.canvas.clientWidth/2,y=anchor?.y??s.canvas.clientHeight/2;
  const pointX=(s.canvas.scrollLeft+x)/old,pointY=(s.canvas.scrollTop+y)/old;
  s.scale=next;if(s.board)s.board.style.zoom=String(next);
  if(resetScroll){s.canvas.scrollLeft=0;s.canvas.scrollTop=0;}
  else {s.canvas.scrollLeft=Math.max(0,pointX*next-x);s.canvas.scrollTop=Math.max(0,pointY*next-y);}
  updateControls(s);
 }
 function setZoom(s,value,anchor){s.mode='manual';apply(s,value,anchor);}
 function setFit(s,mode){s.mode=mode;refresh(s);}
 function refresh(s){
  const board=s.canvas.querySelector(':scope > .tl-board'),changed=s.board!==board;s.board=board;
  if(!board){updateControls(s);return;}
  if(changed)board.style.zoom=String(s.scale);
  const w=board.offsetWidth,h=board.offsetHeight,cw=s.canvas.clientWidth,ch=s.canvas.clientHeight;
  if(cw>0&&ch>0&&w>0&&h>0&&s.mode!=='manual'){
   const x=(cw-16)/w,y=(ch-16)/h;apply(s,Math.min(1,x,s.mode==='fit'?y:Infinity),null,true);
  }else updateControls(s);
 }
 nodes.forEach(install);
 window.PP_TIMELINE_ZOOM={refresh(){states.forEach(refresh);},snapshot(){return [...states].map(([id,s])=>({id,scale:s.scale,mode:s.mode,nodes:s.board?.querySelectorAll('.tl-card').length||0,canvasWidth:s.canvas.clientWidth,canvasHeight:s.canvas.clientHeight,boardWidth:s.board?.getBoundingClientRect().width||0,boardHeight:s.board?.getBoundingClientRect().height||0}));}};
 const target=location.hash.slice(1);
 if(['technology-timelines','company-product-timeline','timeline-overview-panel','timeline-line-panel','product-patent-panel'].includes(target)){const node=document.getElementById(target);if(node){for(let parent=node.parentElement;parent;parent=parent.parentElement)if(parent.tagName==='DETAILS')parent.open=true;requestAnimationFrame(()=>node.scrollIntoView({block:'start'}));}}
})();

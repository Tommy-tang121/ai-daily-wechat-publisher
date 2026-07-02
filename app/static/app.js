(function(){
  const state = {selDate:'', eventSource:null, calY:0, calM:0};

  const pad=n=>String(n).padStart(2,'0');
  const fmt=d=>`${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
  const fmtS=d=>`${d.getFullYear()}/${pad(d.getMonth()+1)}/${pad(d.getDate())}`;
  const wk=d=>['周日','周一','周二','周三','周四','周五','周六'][d.getDay()];

  /* ---- Calendar ---- */
  function renderCal(y, m){
    const now=new Date();
    if(y===undefined){y=now.getFullYear();m=now.getMonth()}
    state.calY=y; state.calM=m;
    const fd=new Date(y,m,1).getDay();
    const dim=new Date(y,m+1,0).getDate();
    const ws=['日','一','二','三','四','五','六'];
    const ms=['一月','二月','三月','四月','五月','六月','七月','八月','九月','十月','十一月','十二月'];

    document.getElementById('calMonth').textContent=ms[m]+' '+y;
    document.getElementById('calToday').textContent=fmtS(now);

    let h='';
    ws.forEach(w=>h+=`<div class="w">${w}</div>`);
    for(let i=0;i<fd;i++)h+='<div class="d empty"></div>';
    for(let d=1;d<=dim;d++){
      const ds=`${y}-${pad(m+1)}-${pad(d)}`;
      const isToday=d===now.getDate()&&m===now.getMonth()&&y===now.getFullYear();
      const cls=isToday?'d today':'d';
      h+=`<div class="${cls}" data-date="${ds}">${d}</div>`;
    }
    document.getElementById('calGrid').innerHTML=h;

    document.querySelectorAll('.cal-grid .d:not(.empty)').forEach(el=>{
      el.addEventListener('click',()=>pickDate(el.dataset.date));
    });

    if(!state.selDate){pickDate(fmt(now));return}
    const existing=document.querySelector(`.cal-grid .d[data-date="${state.selDate}"]`);
    if(existing)existing.classList.add('sel');
  }

  function pickDate(ds){
    document.querySelectorAll('.cal-grid .d').forEach(d=>d.classList.remove('sel'));
    const el=document.querySelector(`.cal-grid .d[data-date="${ds}"]`);
    if(el&&!el.classList.contains('empty'))el.classList.add('sel');
    state.selDate=ds;

    const d=new Date(ds+'T00:00:00');
    document.getElementById('fetchDate').textContent=fmtS(d);
    document.getElementById('inputTitle').value='AI 行业热点新闻 | '+ds;
    saveCfg('title', 'AI 行业热点新闻 | '+ds);
    document.getElementById('fetchWeekday').textContent=wk(d);
    document.getElementById('btnFetch').disabled=false;
  }

  document.getElementById('calPrev').addEventListener('click',()=>{
    const nm=state.calM-1; renderCal(nm<0?state.calY-1:state.calY, nm<0?11:nm);
  });
  document.getElementById('calNext').addEventListener('click',()=>{
    const nm=state.calM+1; renderCal(nm>11?state.calY+1:state.calY, nm>11?0:nm);
  });

  /* ---- Config ---- */
  function saveCfg(k,v){
    fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({[k]:v})});
  }

  document.getElementById('inputMaxWords').addEventListener('change',function(){
    saveCfg('max_words',parseInt(this.value)||200);
  });

  document.getElementById('inputTitle').addEventListener('change',function(){
    saveCfg('title',this.value);
  });

  document.getElementById('inputAuthor').addEventListener('change',function(){
    saveCfg('author',this.value);
  });

  document.getElementById('btnSaveTime').addEventListener('click',function(){
    const t=document.getElementById('scheduleTime').value;
    if(t){saveCfg('schedule_time',t);toast('定时已保存','success')}
  });

  async function loadCfg(){
    try{const r=await fetch('/api/config');const c=await r.json();
      if(c.title)document.getElementById('inputTitle').value=c.title;
      if(c.author)document.getElementById('inputAuthor').value=c.author;
      if(c.max_words)document.getElementById('inputMaxWords').value=c.max_words;
      if(c.schedule_time)document.getElementById('scheduleTime').value=c.schedule_time;
    }catch(e){}
  }

  /* ---- Fetch ---- */
  document.getElementById('btnFetch').addEventListener('click',async function(){
    if(!state.selDate)return;
    this.disabled=true; resetProg();
    setStatus('running','处理中...','正在抓取并改写...');
    document.getElementById('cornerTag').classList.add('show');
    document.getElementById('cornerBadge').textContent='BUSY';
    const mw=document.getElementById('inputMaxWords').value||200;
    try{
      const r=await fetch('/api/fetch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({date:state.selDate,max_words:parseInt(mw)})});
      const d=await r.json();
      if(d.error){toast(d.error,'error');this.disabled=false;setStatus('idle','等待操作','选择日期后点击「抓取」开始');document.getElementById('cornerTag').classList.remove('show');return}
      startSSE();
    }catch(e){toast('请求失败','error');this.disabled=false;setStatus('idle','等待操作','选择日期后点击「抓取」开始');document.getElementById('cornerTag').classList.remove('show')}
  });

  /* ---- SSE ---- */
  function startSSE(){
    if(state.eventSource)state.eventSource.close();
    state.eventSource=new EventSource('/api/progress');
    state.eventSource.addEventListener('stage',function(e){
      const d=JSON.parse(e.data);
      updateProg(d);
      if(d.stage==='done'){
        state.eventSource.close();state.eventSource=null;
        setStatus('done','运行成功','已推送到公众号草稿箱 · media_id 已记录');
        document.getElementById('cornerBadge').textContent='DONE';
        loadPreview();
        document.getElementById('btnFetch').disabled=false;
        document.getElementById('btnPublish').disabled=false;
      }
      if(d.stage==='error'){
        state.eventSource.close();state.eventSource=null;
        setStatus('fail','运行失败',d.message||'处理出错');
        document.getElementById('cornerBadge').textContent='FAIL';
        toast(d.message||'处理出错','error');
        document.getElementById('btnFetch').disabled=false;
      }
    });
    state.eventSource.onerror=function(){
      toast('连接中断','error');
      state.eventSource.close();state.eventSource=null;
      document.getElementById('btnFetch').disabled=false;
      setStatus('idle','等待操作','连接中断，请重试');
      document.getElementById('cornerTag').classList.remove('show');
    }
  }

  const stepNames=['scraping','rewriting','formatting','cover','done'];
  const stepLabels={scraping:'抓取中...',rewriting:'重写中...',formatting:'排版中...',cover:'生成封面...',done:'完成!'};

  function setStep(step, cls, msg){
    const el=document.querySelector(`.tl-step[data-step="${step}"]`);
    if(!el)return;
    el.className='tl-step';
    if(cls)el.classList.add(cls);
    const status=el.querySelector('.tl-status');
    if(msg!==undefined)status.textContent=msg;
  }

  function resetSteps(){
    stepNames.forEach(s=>setStep(s,'','等待中'));
    document.querySelectorAll('.tl-step').forEach(el=>el.className='tl-step');
  }

  function updateProg(d){
    document.getElementById('progCard').style.display='';
    document.getElementById('errCard').style.display='none';
    const stage=d.stage||'', status=d.status||'', msg=d.message||'';
    setStatus('running','处理中...',msg);

    if(stage==='scraping'&&status==='complete'){
      setStep('scraping','done','完成');
      setStep('rewriting','active','重写中...');
    }
    else if(stage==='rewriting'&&status==='progress'){
      setStep('rewriting','active',msg);
    }
    else if(stage==='rewriting'&&status==='complete'){
      setStep('rewriting','done','完成');
      setStep('formatting','active','排版中...');
    }
    else if(stage==='formatting'&&status==='complete'){
      setStep('formatting','done','完成');
      setStep('cover','active','生成中...');
    }
    else if(stage==='done'){
      setStep('cover','done','完成');
      setStep('done','done','完成');
      document.getElementById('fetchHint').textContent='处理完成';
    }
    else if(stage==='error'){
      const active=stepNames.find(s=>{
        const el=document.querySelector(`.tl-step[data-step="${s}"]`);
        return el&&el.classList.contains('active');
      });
      if(active)setStep(active,'fail',msg);
    }
  }

  function resetProg(){
    document.getElementById('errCard').style.display='none';
    resetSteps();
    setStep('scraping','active','准备中...');
    document.getElementById('btnPublish').disabled=true;
    document.getElementById('pvContent').innerHTML='<div style="text-align:center;padding:40px 0;color:var(--ink-faint);font-style:italic;">处理中...</div>';
  }

  function setStatus(state, label, detail){
    const bar=document.getElementById('statusBar');
    const text=document.getElementById('statusText');
    const det=document.getElementById('statusDetail');
    bar.className='status-bar';
    if(state==='running'){bar.classList.add('status');bar.textContent='RUNNING...'}
    else if(state==='done'){bar.classList.add('status-done');bar.textContent='✓ DONE'}
    else if(state==='fail'){bar.classList.add('status-fail');bar.textContent='FAILED'}
    else {bar.classList.add('status');bar.textContent='IDLE'}
    text.textContent=label;
    det.textContent=detail;
  }

  /* ---- View switching ---- */
  document.querySelectorAll('.pv-btn').forEach(btn=>{
    btn.addEventListener('click',function(){
      document.querySelectorAll('.pv-btn').forEach(b=>b.classList.remove('active'));
      this.classList.add('active');
      const v=this.dataset.view;
      document.getElementById('pvContent').style.display=v==='preview'?'':'none';
      document.getElementById('pvCover').style.display=v==='cover'?'':'none';
      if(v==='preview')loadPreviewHtml();
      if(v==='cover')loadCoverPreview();
    });
  });

  /* ---- Preview ---- */
  async function loadPreview(){
    await loadPreviewHtml();
  }

  async function loadPreviewHtml(){
    try{
      const r=await fetch('/api/preview');const d=await r.json();
      if(d.error)return;
      document.querySelector('.pv-btn[data-view="preview"]').classList.add('active');
      document.querySelector('.pv-btn[data-view="cover"]').classList.remove('active');
      document.getElementById('pvContent').style.display='';
      document.getElementById('pvCover').style.display='none';
      let h='';
      if(d.opening){
        h+=`<div style="font-weight:700;color:var(--spray-orange);margin:10px 0 4px;font-size:14px;">今日观察</div>`;
        h+=`<div style="margin-bottom:10px;">${d.opening}</div>`;
      }
      let cat='';
      (d.items||[]).forEach(i=>{
        if(i.category!==cat){
          cat=i.category;
          h+=`<div style="font-weight:700;color:var(--spray-orange);margin:12px 0 4px;font-size:14px;">【${cat}】</div>`;
        }
        h+=`<div style="margin-bottom:6px;"><strong>${i.title}</strong><br>${i.body}<br><span style="font-size:10px;color:var(--ink-faint);">来源：${i.source}</span></div>`;
      });
      if(d.closing){
        h+=`<div style="font-weight:700;color:var(--spray-orange);margin:12px 0 4px;font-size:14px;">小编短评</div>`;
        h+=`<div>${d.closing}</div>`;
      }
      document.getElementById('pvContent').innerHTML=h;
    }catch(e){}
  }

  async function loadCoverPreview(){
    const ds=state.selDate;
    if(!ds)return;
    document.getElementById('coverPreviewImg').src='/static/covers/'+ds+'.png?t='+Date.now();
  }

  /* ---- Copy ---- */
  document.getElementById('btnCopy').addEventListener('click',function(){
    navigator.clipboard.writeText(document.getElementById('pvContent').innerText).then(()=>toast('已复制到剪贴板','success')).catch(()=>toast('复制失败','error'));
  });

  /* ---- Publish ---- */
  document.getElementById('btnPublish').addEventListener('click',async function(){
    this.disabled=true;
    try{const r=await fetch('/api/publish',{method:'POST'});const d=await r.json();if(d.success)toast('草稿已创建成功！','success');else toast('发布失败: '+(d.error||''),'error')}catch(e){toast('发布请求失败','error')}
    this.disabled=false;
  });

  /* ---- Toast ---- */
  function toast(msg,type){
    const b=document.getElementById('toastBox');
    const t=document.createElement('div');
    t.className='toast '+(type==='error'?'error':'success');
    t.textContent=msg;b.appendChild(t);
    setTimeout(()=>t.remove(),3000);
  }

  renderCal();loadCfg();
  document.querySelectorAll('.tl-step').forEach(el=>el.className='tl-step');
  stepNames.forEach(s=>{
    const el=document.querySelector(`.tl-step[data-step="${s}"]`);
    if(el)el.querySelector('.tl-status').textContent='等待中';
  });
  document.getElementById('tlScraping').textContent='点击「抓取」开始';
})();

window.Predicta = (() => {
  function pollRun(url, initial){if(!['PENDING','RUNNING'].includes(initial))return;const log=document.getElementById('run-log'),badge=document.getElementById('run-badge'),state=document.getElementById('run-state'),rc=document.getElementById('return-code');const tick=async()=>{try{const r=await fetch(url,{headers:{'X-Requested-With':'XMLHttpRequest'}});const d=await r.json();if(log){log.textContent=d.log||'';log.scrollTop=log.scrollHeight}if(state)state.textContent=d.status;if(badge){badge.textContent=d.status;badge.className='badge status-'+d.status.toLowerCase()}if(rc)rc.textContent=d.return_code??'—';if(['PENDING','RUNNING'].includes(d.status))setTimeout(tick,1800)}catch(e){setTimeout(tick,3000)}};setTimeout(tick,900)}

  function bindAlgorithmForm(selectId,boxId){const s=document.getElementById(selectId),b=document.getElementById(boxId);if(!s||!b)return;const sync=()=>{b.hidden=s.value!=='xgboost'};s.addEventListener('change',sync);sync()}

  function allCoords(geom,out=[]){if(!geom)return out;const walk=a=>{if(Array.isArray(a)&&a.length>=2&&typeof a[0]==='number'&&typeof a[1]==='number'){out.push([a[0],a[1]]);return}if(Array.isArray(a))a.forEach(walk)};walk(geom.coordinates);return out}
  function makeProject(features,W,H){const coords=[];features.forEach(f=>allCoords(f.geometry,coords));let minX=Math.min(...coords.map(c=>c[0])),maxX=Math.max(...coords.map(c=>c[0])),minY=Math.min(...coords.map(c=>c[1])),maxY=Math.max(...coords.map(c=>c[1]));const pad=24,sx=(W-2*pad)/(maxX-minX),sy=(H-2*pad)/(maxY-minY),scale=Math.min(sx,sy),usedW=(maxX-minX)*scale,usedH=(maxY-minY)*scale,ox=(W-usedW)/2,oy=(H-usedH)/2;return ([x,y])=>[ox+(x-minX)*scale,oy+(maxY-y)*scale]}
  function ringPath(ring,project){return ring.map((c,i)=>{const [x,y]=project(c);return `${i?'L':'M'}${x.toFixed(2)},${y.toFixed(2)}`}).join(' ')+' Z'}
  function geomPath(geom,project){if(!geom)return '';if(geom.type==='Polygon')return geom.coordinates.map(r=>ringPath(r,project)).join(' ');if(geom.type==='MultiPolygon')return geom.coordinates.flatMap(poly=>poly.map(r=>ringPath(r,project))).join(' ');return ''}
  function clsRegion(region){return String(region||'').replace('/','').replace(/[^A-Za-z0-9]/g,'').toLowerCase()}
  function money(v){const n=Number(v);return Number.isFinite(n)?`R$ ${n.toFixed(4)}/kWh`:'—'}

  async function bindConcessionMap(opts){
    const svg=document.getElementById('concession-map');if(!svg)return;
    const tooltip=document.getElementById('map-tooltip'),search=document.getElementById('distributor-search'),cnpjInput=document.getElementById('cnpj-input'),regionInput=document.getElementById('region-input'),distInput=document.getElementById('distributor-input'),profile=document.getElementById('profile-select'),title=document.getElementById('location-title'),detail=document.getElementById('location-detail'),button=document.getElementById('simulate-button');
    const mode=document.getElementById('simulation-mode'),replay=document.getElementById('replay-date'),replayField=document.getElementById('replay-date-field'),issueDate=document.getElementById('issue-date'),issueTime=document.getElementById('issue-time'),issueAvailability=document.getElementById('issue-availability');
    const te=document.getElementById('preview-te'),tusd=document.getElementById('preview-tusd'),total=document.getElementById('preview-total'),effective=document.getElementById('preview-effective');
    let signalAvailable=false;let geo;try{geo=await (await fetch(opts.geoUrl)).json()}catch(e){svg.innerHTML='<text x="20" y="40">Não foi possível carregar o GeoJSON.</text>';return}
    const features=geo.features||[],project=makeProject(features,920,720),ns='http://www.w3.org/2000/svg',paths=new Map();
    const bg=document.createElementNS(ns,'rect');bg.setAttribute('x','0');bg.setAttribute('y','0');bg.setAttribute('width','920');bg.setAttribute('height','720');bg.setAttribute('class','map-bg');svg.appendChild(bg);
    function resetPreview(){if(te)te.textContent='—';if(tusd)tusd.textContent='—';if(total)total.textContent='—';if(effective)effective.textContent='—';if(distInput)distInput.value=''}
    function updatePreview(){const o=profile?.selectedOptions?.[0];if(!o||!o.value){resetPreview();if(button)button.disabled=true;return}if(distInput)distInput.value=o.dataset.distributor||'';if(te)te.textContent=money(o.dataset.te);if(tusd)tusd.textContent=money(o.dataset.tusd);if(total)total.textContent=money(o.dataset.base);if(effective)effective.textContent=o.dataset.effective||'—';if(button)button.disabled=!cnpjInput?.value||!signalAvailable||((mode?.value||'replay')==='replay'&&!replay?.value)}
    function syncIssuePicker(){
      if(!replay||!issueDate||!issueTime)return false;
      const option=Array.from(replay.options).find(item=>item.dataset.date===issueDate.value&&item.dataset.time===issueTime.value);
      replay.value=option?.value||'';
      const available=Boolean(option);
      if(issueAvailability){issueAvailability.classList.toggle('unavailable',!available);issueAvailability.textContent=available?`Janela disponível · H24 até ${option.dataset.end}.`:'Não há previsão completa para esta data e hora.'}
      signalAvailable=available;
      updatePreview();
      return available;
    }
    const initialWindow=replay?.querySelector('option[selected]')||replay?.selectedOptions?.[0];
    if(initialWindow&&issueDate&&issueTime){initialWindow.selected=true;issueDate.value=initialWindow.dataset.date||issueDate.value;issueTime.value=initialWindow.dataset.time||issueTime.value}
    async function selectFeature(feature,path){
      paths.forEach(p=>p.classList.remove('selected'));if(path)path.classList.add('selected');const p=feature.properties||{},cnpj=p.cnpj_digits||String(p.cnpj||'').replace(/\D/g,''),region=p.subsystem_id||'';
      if(cnpjInput)cnpjInput.value=cnpj;if(regionInput)regionInput.value=region;if(search)search.value=cnpj;if(title)title.textContent=`${p.sigla||'Distribuidora'} · ${p.uf||''}`;if(detail)detail.textContent=`${p.razao_social||''} · CNPJ ${p.cnpj||cnpj} · subsistema ${region}`;resetPreview();
      if(profile){profile.innerHTML='<option value="">Carregando perfis…</option>';signalAvailable=false;try{const params=new URLSearchParams({cnpj,region,mode:mode?.value||'replay'});if(replay?.value)params.set('replay_issue',replay.value);const r=await fetch(`${opts.profilesUrl}?${params.toString()}`),d=await r.json();if(replay&&(mode?.value||'replay')==='replay'&&d.replay_windows){const requestedKey=replay.value;replay.innerHTML='';d.replay_windows.forEach(window=>{const option=document.createElement('option');option.value=window.key;option.textContent=window.selection_label||window.label;option.dataset.date=window.issue_local_date;option.dataset.time=window.issue_local_time;option.dataset.end=window.local_end_label;option.dataset.effective=window.local_date;option.selected=window.key===(requestedKey||d.selected_replay);replay.appendChild(option)});if(!issueDate?.value&&replay.selectedOptions[0])issueDate.value=replay.selectedOptions[0].dataset.date||'';if(!issueTime?.value&&replay.selectedOptions[0])issueTime.value=replay.selectedOptions[0].dataset.time||''}profile.innerHTML='<option value="">Selecione…</option>';if(!d.profiles?.length){profile.innerHTML='<option value="">Nenhum perfil UNIQUE vigente encontrado</option>';if(button)button.disabled=true;return}signalAvailable=Boolean(d.signal_available);d.profiles.forEach(x=>{const o=document.createElement('option');o.value=x.id;o.textContent=`${x.label} · ${money(x.base_total_rs_kwh)}`;o.dataset.distributor=x.distributor_id;o.dataset.base=x.base_total_rs_kwh;o.dataset.te=x.base_te_rs_kwh;o.dataset.tusd=x.base_tusd_rs_kwh;o.dataset.effective=x.effective_date||'';o.dataset.validFrom=x.valid_from||'';o.dataset.validTo=x.valid_to||'';if(opts.selectedProfile&&x.id===opts.selectedProfile&&(!opts.selectedDistributor||x.distributor_id===opts.selectedDistributor))o.selected=true;profile.appendChild(o)});syncIssuePicker();updatePreview()}catch(e){profile.innerHTML='<option value="">Erro ao carregar tarifas</option>'}}
    }
    features.forEach(feature=>{const p=feature.properties||{},cnpj=p.cnpj_digits||String(p.cnpj||'').replace(/\D/g,''),path=document.createElementNS(ns,'path');path.setAttribute('d',geomPath(feature.geometry,project));path.setAttribute('class',`concession-area region-${clsRegion(p.subsystem_id)}`);path.setAttribute('data-cnpj',cnpj);path.setAttribute('vector-effect','non-scaling-stroke');path.addEventListener('click',()=>selectFeature(feature,path));path.addEventListener('mousemove',ev=>{if(!tooltip)return;tooltip.hidden=false;tooltip.innerHTML=`<b>${p.sigla||''}</b><br>${p.razao_social||''}<br>${p.uf||''} · ${p.subsystem_id||''}`;const rect=svg.getBoundingClientRect();tooltip.style.left=(ev.clientX-rect.left+12)+'px';tooltip.style.top=(ev.clientY-rect.top+12)+'px'});path.addEventListener('mouseleave',()=>{if(tooltip)tooltip.hidden=true});svg.appendChild(path);paths.set(cnpj,path)});
    if(profile)profile.addEventListener('change',updatePreview);
    const syncMode=()=>{const isReplay=(mode?.value||'replay')==='replay';if(replay)replay.disabled=!isReplay;if(issueDate)issueDate.disabled=!isReplay;if(issueTime)issueTime.disabled=!isReplay;if(replayField)replayField.classList.toggle('disabled',!isReplay)};
    async function reloadSelected(){const c=cnpjInput?.value;if(!c)return;const path=paths.get(c),f=features.find(x=>(x.properties?.cnpj_digits||String(x.properties?.cnpj||'').replace(/\D/g,''))===c);if(f)await selectFeature(f,path)}
    if(mode){mode.addEventListener('change',async()=>{syncMode();await reloadSelected()});syncMode()}
    [issueDate,issueTime].forEach(input=>input?.addEventListener('change',async()=>{if(syncIssuePicker())await reloadSelected()}));
    if(search)search.addEventListener('change',()=>{const c=search.value,path=paths.get(c),f=features.find(x=>(x.properties?.cnpj_digits||String(x.properties?.cnpj||'').replace(/\D/g,''))===c);if(f)selectFeature(f,path)});
    const filterRegion=()=>{const selected=regionInput?.value||'';if(search)Array.from(search.options).forEach(option=>{if(!option.value)return;const visible=!selected||option.dataset.region===selected;option.hidden=!visible;option.disabled=!visible});paths.forEach((path,cnpj)=>{const feature=features.find(item=>(item.properties?.cnpj_digits||String(item.properties?.cnpj||'').replace(/\D/g,''))===cnpj);path.classList.toggle('region-filtered-out',Boolean(selected&&feature?.properties?.subsystem_id!==selected))})};
    if(regionInput)regionInput.addEventListener('change',()=>{filterRegion();const selectedOption=search?.selectedOptions?.[0];if(selectedOption?.value&&selectedOption.dataset.region!==regionInput.value){search.value='';cnpjInput.value='';resetPreview();if(title)title.textContent='Selecione uma concessão';if(detail)detail.textContent='As áreas fora do subsistema escolhido foram atenuadas no mapa';if(button)button.disabled=true}});
    filterRegion();
    if(opts.selectedCnpj){const c=String(opts.selectedCnpj).replace(/\D/g,'').padStart(14,'0'),path=paths.get(c),f=features.find(x=>(x.properties?.cnpj_digits||String(x.properties?.cnpj||'').replace(/\D/g,''))===c),serverSelected=profile&&Array.from(profile.options).some(option=>option.value===opts.selectedProfile&&option.selected);if(f&&serverSelected){if(path)path.classList.add('selected');if(search)search.value=c;signalAvailable=true;updatePreview()}else if(f){await selectFeature(f,path);}}
    // If the server rendered a selected profile after POST, preserve it and update tariff preview.
    const serverSelected=profile?.querySelector('option[selected]');if(serverSelected){serverSelected.selected=true;syncIssuePicker();updatePreview()}
  }


  function makeProjectFromPoints(points,W,H){
    const coords=(points||[]).filter(p=>Number.isFinite(Number(p.longitude))&&Number.isFinite(Number(p.latitude))).map(p=>[Number(p.longitude),Number(p.latitude)]);
    if(!coords.length)return ()=>[W/2,H/2];
    let minX=Math.min(...coords.map(c=>c[0])),maxX=Math.max(...coords.map(c=>c[0])),minY=Math.min(...coords.map(c=>c[1])),maxY=Math.max(...coords.map(c=>c[1]));
    if(minX===maxX){minX-=1;maxX+=1} if(minY===maxY){minY-=1;maxY+=1}
    const pad=24,sx=(W-2*pad)/(maxX-minX),sy=(H-2*pad)/(maxY-minY),scale=Math.min(sx,sy),usedW=(maxX-minX)*scale,usedH=(maxY-minY)*scale,ox=(W-usedW)/2,oy=(H-usedH)/2;
    return ([x,y])=>[ox+(x-minX)*scale,oy+(maxY-y)*scale]
  }

  function bindTerritoryMap(svgId,payload,tooltipId){
    const svg=document.getElementById(svgId); if(!svg)return;
    const tooltip=document.getElementById(tooltipId||'territory-tooltip');
    const ns='http://www.w3.org/2000/svg'; svg.innerHTML='';
    const W=920,H=720; const features=payload?.features||[]; const allPoints=[...(payload?.plants||[]),...(payload?.events||[])];
    const project=features.length?makeProject(features,W,H):makeProjectFromPoints(allPoints,W,H);
    const bg=document.createElementNS(ns,'rect'); bg.setAttribute('x','0');bg.setAttribute('y','0');bg.setAttribute('width',String(W));bg.setAttribute('height',String(H));bg.setAttribute('class','map-bg');svg.appendChild(bg);
    features.forEach(feature=>{const path=document.createElementNS(ns,'path');path.setAttribute('d',geomPath(feature.geometry,project));path.setAttribute('class',`concession-area region-${clsRegion(feature.properties?.subsystem_id)}`);path.setAttribute('vector-effect','non-scaling-stroke');svg.appendChild(path)});
    const shape=(name,attrs,parent)=>{const node=document.createElementNS(ns,name);Object.entries(attrs).forEach(([key,value])=>node.setAttribute(key,value));parent.appendChild(node);return node};
    const marker=(className,x,y,filter)=>{const group=document.createElementNS(ns,'g');group.setAttribute('class',`territory-point ${className}`);group.setAttribute('transform',`translate(${x} ${y})`);group.dataset.filter=filter;return group};
    const sourceKey=plant=>{const raw=String(plant.source_key||plant.source||'').toLowerCase();if(raw.includes('hydro')||raw.includes('hídr'))return'hydro';if(raw.includes('wind')||raw.includes('eól'))return'wind';if(raw.includes('solar'))return'solar';if(raw.includes('fossil')||raw.includes('térm'))return'fossil';if(raw.includes('nuclear'))return'nuclear';return'other'};
    const showTooltip=(event,html)=>{if(!tooltip)return;tooltip.hidden=false;tooltip.innerHTML=html;const rect=svg.getBoundingClientRect();tooltip.style.left=(event.clientX-rect.left+12)+'px';tooltip.style.top=(event.clientY-rect.top+12)+'px'};
    const bindTooltip=(node,render)=>{node.addEventListener('mousemove',event=>showTooltip(event,render()));node.addEventListener('mouseleave',()=>{if(tooltip)tooltip.hidden=true})};
    const eventIcon=(group,type,color)=>{
      if(type==='heat'){shape('circle',{cx:0,cy:0,r:5,fill:color},group);for(let angle=0;angle<360;angle+=45){const rad=angle*Math.PI/180;shape('line',{x1:(7*Math.cos(rad)).toFixed(2),y1:(7*Math.sin(rad)).toFixed(2),x2:(10*Math.cos(rad)).toFixed(2),y2:(10*Math.sin(rad)).toFixed(2),stroke:color,'stroke-width':2},group)}}
      else if(type==='rain')shape('path',{d:'M0 -10 C5 -4 8 0 8 4 A8 8 0 1 1 -8 4 C-8 0 -5 -4 0 -10Z',fill:color},group);
      else if(type==='wind')[-5,0,5].forEach((offset,index)=>shape('path',{d:`M-10 ${offset} C-3 ${offset-4} 2 ${offset+4} ${index===1?10:7} ${offset}`,fill:'none',stroke:color,'stroke-width':2.4,'stroke-linecap':'round'},group));
      else if(type==='storm')shape('path',{d:'M2 -11 L-7 2 L-1 2 L-4 11 L8 -4 L2 -4 Z',fill:color},group);
      else if(type==='cold'){[0,60,120].forEach(angle=>shape('line',{x1:-9,y1:0,x2:9,y2:0,stroke:color,'stroke-width':2,transform:`rotate(${angle})`},group));shape('circle',{cx:0,cy:0,r:2.5,fill:color},group)}
      else shape('circle',{cx:0,cy:0,r:4,fill:color},group);
    };
    const plantIcon=(group,type,color)=>{
      if(type==='hydro')shape('path',{d:'M0 -7 L7 0 L0 7 L-7 0 Z',fill:color},group);
      else if(type==='wind'){shape('circle',{cx:0,cy:-2,r:2,fill:color},group);shape('line',{x1:0,y1:0,x2:0,y2:8,stroke:color,'stroke-width':2},group);[-90,30,150].forEach(angle=>shape('line',{x1:0,y1:-2,x2:0,y2:-9,stroke:color,'stroke-width':2,transform:`rotate(${angle} 0 -2)`},group))}
      else if(type==='solar')shape('rect',{x:-6,y:-6,width:12,height:12,rx:1,fill:color,transform:'rotate(12)'},group);
      else if(type==='fossil')shape('path',{d:'M-6 -4 L0 -8 L6 -4 L6 4 L0 8 L-6 4 Z',fill:color},group);
      else if(type==='nuclear'){shape('circle',{cx:0,cy:0,r:7,fill:'white',stroke:color,'stroke-width':2},group);shape('circle',{cx:0,cy:0,r:3,fill:color},group)}
      else shape('circle',{cx:0,cy:0,r:5,fill:color},group);
    };
    (payload?.events||[]).forEach(ev=>{
      if(!Number.isFinite(Number(ev.longitude))||!Number.isFinite(Number(ev.latitude)))return;
      const [x,y]=project([Number(ev.longitude),Number(ev.latitude)]),type=ev.event_type||'none',group=marker(`event ${type}`,x,y,`event-${type}`);
      if(type==='none')group.hidden=true;eventIcon(group,type,ev.color||'#94a3b8');
      bindTooltip(group,()=>`<span class="tooltip-kicker">Evento climático</span><b>${ev.event_label||'Sem evento'} · ${ev.name||'Ponto representativo'}</b><span>${ev.state||''}</span><dl>${Number.isFinite(Number(ev.temperature_max_anomaly_c))?`<dt>Anomalia de temperatura</dt><dd>${Number(ev.temperature_max_anomaly_c).toFixed(1)} °C</dd>`:''}${Number.isFinite(Number(ev.precipitation_sum))?`<dt>Chuva no dia</dt><dd>${Number(ev.precipitation_sum).toFixed(1)} mm</dd>`:''}${Number.isFinite(Number(ev.wind_gusts_10m_max))?`<dt>Rajada máxima</dt><dd>${Number(ev.wind_gusts_10m_max).toFixed(1)} km/h</dd>`:''}</dl>`);
      svg.appendChild(group);
    });
    (payload?.plants||[]).forEach(pl=>{
      if(!Number.isFinite(Number(pl.longitude))||!Number.isFinite(Number(pl.latitude)))return;
      const [x,y]=project([Number(pl.longitude),Number(pl.latitude)]),type=sourceKey(pl),group=marker(`plant source-${type} ${pl.near_event?'exposed':''}`,x,y,`plant-${type}`);
      if(pl.near_event)shape('circle',{cx:0,cy:0,r:11,fill:'none',stroke:'#dc2626','stroke-width':2},group);plantIcon(group,type,pl.near_event?'#991b1b':'#253047');
      bindTooltip(group,()=>`<span class="tooltip-kicker">Usina · ${pl.source||'fonte não informada'}</span><b>${pl.name||'Usina'}</b><span>${pl.uf||''}</span><dl>${Number.isFinite(Number(pl.capacity_mw))?`<dt>Capacidade instalada</dt><dd>${Number(pl.capacity_mw).toFixed(0)} MW</dd>`:''}${Number.isFinite(Number(pl.generation_avg_mw))?`<dt>Geração média</dt><dd>${Number(pl.generation_avg_mw).toFixed(0)} MW</dd>`:''}${pl.near_event?`<dt>Evento próximo</dt><dd>${pl.event_label||'Evento'} · ${Number.isFinite(Number(pl.distance_to_event_km))?Number(pl.distance_to_event_km).toFixed(0)+' km':'distância indisponível'}</dd>`:'<dt>Exposição</dt><dd>Sem evento próximo</dd>'}</dl>`);
      svg.appendChild(group);
    });
    document.querySelectorAll('[data-map-filter]').forEach(button=>button.addEventListener('click',()=>{const active=button.getAttribute('aria-pressed')!=='true';button.setAttribute('aria-pressed',String(active));button.classList.toggle('is-active',active);svg.querySelectorAll(`[data-filter="${button.dataset.mapFilter}"]`).forEach(node=>{node.hidden=!active})}));
  }

  return {pollRun,bindAlgorithmForm,bindConcessionMap,bindTerritoryMap};
})();

// Playground sidebar toggle + how-drawer exclusividade
(function(){
  const toggle=document.getElementById('playground-toggle'),sidebar=document.getElementById('playground-sidebar'),backdrop=document.getElementById('playground-backdrop'),close=document.getElementById('playground-close');
  if(toggle&&sidebar&&backdrop){
    const setOpen=open=>{sidebar.hidden=false;backdrop.hidden=!open;sidebar.classList.toggle('open',open);toggle.setAttribute('aria-expanded',String(open));try{localStorage.setItem('predicta-playground',open?'1':'0')}catch(e){}};
    toggle.addEventListener('click',()=>setOpen(!sidebar.classList.contains('open')));
    if(close)close.addEventListener('click',()=>setOpen(false));
    backdrop.addEventListener('click',()=>setOpen(false));
    document.addEventListener('keydown',e=>{if(e.key==='Escape')setOpen(false)});
  }
  // Apenas um drawer "Como funciona?" aberto por vez; Esc fecha.
  document.addEventListener('toggle',e=>{
    const d=e.target;
    if(!(d instanceof HTMLDetailsElement)||!d.classList.contains('how-drawer')||!d.open)return;
    document.querySelectorAll('details.how-drawer[open]').forEach(o=>{if(o!==d)o.open=false});
  },true);
  document.addEventListener('keydown',e=>{if(e.key==='Escape')document.querySelectorAll('details.how-drawer[open]').forEach(o=>o.open=false)});
})();

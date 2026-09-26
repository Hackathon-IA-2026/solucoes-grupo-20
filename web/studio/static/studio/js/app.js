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
    const mode=document.getElementById('simulation-mode'),replay=document.getElementById('replay-date'),replayField=document.getElementById('replay-date-field');
    const te=document.getElementById('preview-te'),tusd=document.getElementById('preview-tusd'),total=document.getElementById('preview-total'),effective=document.getElementById('preview-effective');
    let signalAvailable=false;let geo;try{geo=await (await fetch(opts.geoUrl)).json()}catch(e){svg.innerHTML='<text x="20" y="40">Não foi possível carregar o GeoJSON.</text>';return}
    const features=geo.features||[],project=makeProject(features,920,720),ns='http://www.w3.org/2000/svg',paths=new Map();
    const bg=document.createElementNS(ns,'rect');bg.setAttribute('x','0');bg.setAttribute('y','0');bg.setAttribute('width','920');bg.setAttribute('height','720');bg.setAttribute('class','map-bg');svg.appendChild(bg);
    function resetPreview(){if(te)te.textContent='—';if(tusd)tusd.textContent='—';if(total)total.textContent='—';if(effective)effective.textContent='—';if(distInput)distInput.value=''}
    function updatePreview(){const o=profile?.selectedOptions?.[0];if(!o||!o.value){resetPreview();if(button)button.disabled=true;return}if(distInput)distInput.value=o.dataset.distributor||'';if(te)te.textContent=money(o.dataset.te);if(tusd)tusd.textContent=money(o.dataset.tusd);if(total)total.textContent=money(o.dataset.base);if(effective)effective.textContent=o.dataset.effective||'—';if(button)button.disabled=!cnpjInput?.value||!signalAvailable}
    async function selectFeature(feature,path){
      paths.forEach(p=>p.classList.remove('selected'));if(path)path.classList.add('selected');const p=feature.properties||{},cnpj=p.cnpj_digits||String(p.cnpj||'').replace(/\D/g,''),region=p.subsystem_id||'';
      if(cnpjInput)cnpjInput.value=cnpj;if(regionInput)regionInput.value=region;if(search)search.value=cnpj;if(title)title.textContent=`${p.sigla||'Distribuidora'} · ${p.uf||''}`;if(detail)detail.textContent=`${p.razao_social||''} · CNPJ ${p.cnpj||cnpj} · subsistema ${region}`;resetPreview();
      if(profile){profile.innerHTML='<option value="">Carregando perfis…</option>';try{const params=new URLSearchParams({cnpj,region,mode:mode?.value||'replay'});if(replay?.value)params.set('replay_issue',replay.value);const eff=replay?.selectedOptions?.[0]?.dataset?.effective;if(eff&&(mode?.value||'replay')==='replay')params.set('effective_date',eff);const r=await fetch(`${opts.profilesUrl}?${params.toString()}`),d=await r.json();profile.innerHTML='<option value="">Selecione…</option>';if(!d.profiles?.length){profile.innerHTML='<option value="">Nenhum perfil UNIQUE vigente encontrado</option>';if(button)button.disabled=true;return}signalAvailable=Boolean(d.signal_available);d.profiles.forEach(x=>{const o=document.createElement('option');o.value=x.id;o.textContent=`${x.label} · ${money(x.base_total_rs_kwh)}`;o.dataset.distributor=x.distributor_id;o.dataset.base=x.base_total_rs_kwh;o.dataset.te=x.base_te_rs_kwh;o.dataset.tusd=x.base_tusd_rs_kwh;o.dataset.effective=x.effective_date||'';o.dataset.validFrom=x.valid_from||'';o.dataset.validTo=x.valid_to||'';if(opts.selectedProfile&&x.id===opts.selectedProfile&&(!opts.selectedDistributor||x.distributor_id===opts.selectedDistributor))o.selected=true;profile.appendChild(o)});updatePreview();if(!signalAvailable){const o=document.createElement('option');o.disabled=true;o.textContent='⚠ Não há janela dinâmica válida para esta região/data';profile.appendChild(o)}}catch(e){profile.innerHTML='<option value="">Erro ao carregar tarifas</option>'}}
    }
    features.forEach(feature=>{const p=feature.properties||{},cnpj=p.cnpj_digits||String(p.cnpj||'').replace(/\D/g,''),path=document.createElementNS(ns,'path');path.setAttribute('d',geomPath(feature.geometry,project));path.setAttribute('class',`concession-area region-${clsRegion(p.subsystem_id)}`);path.setAttribute('data-cnpj',cnpj);path.setAttribute('vector-effect','non-scaling-stroke');path.addEventListener('click',()=>selectFeature(feature,path));path.addEventListener('mousemove',ev=>{if(!tooltip)return;tooltip.hidden=false;tooltip.innerHTML=`<b>${p.sigla||''}</b><br>${p.razao_social||''}<br>${p.uf||''} · ${p.subsystem_id||''}`;const rect=svg.getBoundingClientRect();tooltip.style.left=(ev.clientX-rect.left+12)+'px';tooltip.style.top=(ev.clientY-rect.top+12)+'px'});path.addEventListener('mouseleave',()=>{if(tooltip)tooltip.hidden=true});svg.appendChild(path);paths.set(cnpj,path)});
    if(profile)profile.addEventListener('change',updatePreview);
    const syncMode=()=>{const isReplay=(mode?.value||'replay')==='replay';if(replay)replay.disabled=!isReplay;if(replayField)replayField.classList.toggle('disabled',!isReplay)};
    async function reloadSelected(){const c=cnpjInput?.value;if(!c)return;const path=paths.get(c),f=features.find(x=>(x.properties?.cnpj_digits||String(x.properties?.cnpj||'').replace(/\D/g,''))===c);if(f)await selectFeature(f,path)}
    if(mode){mode.addEventListener('change',async()=>{syncMode();await reloadSelected()});syncMode()}
    if(replay)replay.addEventListener('change',reloadSelected);
    if(search)search.addEventListener('change',()=>{const c=search.value,path=paths.get(c),f=features.find(x=>(x.properties?.cnpj_digits||String(x.properties?.cnpj||'').replace(/\D/g,''))===c);if(f)selectFeature(f,path)});
    if(opts.selectedCnpj){const c=String(opts.selectedCnpj).replace(/\D/g,'').padStart(14,'0'),path=paths.get(c),f=features.find(x=>(x.properties?.cnpj_digits||String(x.properties?.cnpj||'').replace(/\D/g,''))===c);if(f){await selectFeature(f,path);}}
    // If the server rendered a selected profile after POST, preserve it and update tariff preview.
    const serverSelected=profile?.querySelector('option[selected]');if(serverSelected){serverSelected.selected=true;updatePreview()}
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
    (payload?.events||[]).forEach(ev=>{
      if(!Number.isFinite(Number(ev.longitude))||!Number.isFinite(Number(ev.latitude)))return;
      const [x,y]=project([Number(ev.longitude),Number(ev.latitude)]); const c=document.createElementNS(ns,'circle');
      c.setAttribute('cx',x); c.setAttribute('cy',y); c.setAttribute('r', ev.has_event?9:6); c.setAttribute('fill', ev.color||'#94a3b8'); c.setAttribute('class',`territory-point event ${ev.event_type||'none'}`);
      c.addEventListener('mousemove',e=>{if(!tooltip)return; tooltip.hidden=false; tooltip.innerHTML=`<b>${ev.name||'Ponto climático'}</b><br>${ev.event_label||'Sem evento'}${ev.state?` · ${ev.state}`:''}${Number.isFinite(Number(ev.temperature_max_anomaly_c))?`<br>anomalia Tmax: ${Number(ev.temperature_max_anomaly_c).toFixed(1)}°C`:''}${Number.isFinite(Number(ev.precipitation_sum))?`<br>chuva diária: ${Number(ev.precipitation_sum).toFixed(1)} mm`:''}${Number.isFinite(Number(ev.wind_gusts_10m_max))?`<br>rajada máx: ${Number(ev.wind_gusts_10m_max).toFixed(1)} km/h`:''}`; const rect=svg.getBoundingClientRect(); tooltip.style.left=(e.clientX-rect.left+12)+'px'; tooltip.style.top=(e.clientY-rect.top+12)+'px'});
      c.addEventListener('mouseleave',()=>{if(tooltip)tooltip.hidden=true}); svg.appendChild(c);
    });
    (payload?.plants||[]).forEach(pl=>{
      if(!Number.isFinite(Number(pl.longitude))||!Number.isFinite(Number(pl.latitude)))return;
      const [x,y]=project([Number(pl.longitude),Number(pl.latitude)]); const c=document.createElementNS(ns,'circle');
      c.setAttribute('cx',x); c.setAttribute('cy',y); c.setAttribute('r', pl.near_event?4.8:3.8); c.setAttribute('fill', pl.color||'#334155'); c.setAttribute('class',`territory-point plant ${pl.near_event?'exposed':''}`);
      c.addEventListener('mousemove',e=>{if(!tooltip)return; tooltip.hidden=false; tooltip.innerHTML=`<b>${pl.name||'Usina'}</b><br>${pl.source||''}${pl.uf?` · ${pl.uf}`:''}${Number.isFinite(Number(pl.capacity_mw))?`<br>capacidade: ${Number(pl.capacity_mw).toFixed(0)} MW`:''}${Number.isFinite(Number(pl.generation_avg_mw))?`<br>geração média: ${Number(pl.generation_avg_mw).toFixed(0)} MW`:''}${pl.near_event?`<br><span style="color:#fecaca">próxima de ${pl.event_label||'evento'}${pl.event_point?` (${pl.event_point})`:''}${Number.isFinite(Number(pl.distance_to_event_km))?` · ${Number(pl.distance_to_event_km).toFixed(0)} km`:''}</span>`:''}`; const rect=svg.getBoundingClientRect(); tooltip.style.left=(e.clientX-rect.left+12)+'px'; tooltip.style.top=(e.clientY-rect.top+12)+'px'});
      c.addEventListener('mouseleave',()=>{if(tooltip)tooltip.hidden=true}); svg.appendChild(c);
    });
  }

  return {pollRun,bindAlgorithmForm,bindConcessionMap,bindTerritoryMap};
})();

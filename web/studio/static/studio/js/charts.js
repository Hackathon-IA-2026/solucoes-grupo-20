window.PredictaCharts = (() => {
  const NS='http://www.w3.org/2000/svg';
  const palette=['#4f46e5','#059669','#dc6b18','#b42370','#64748b'];
  function el(name,attrs={}){const n=document.createElementNS(NS,name);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));return n;}
  function fmt(v,o={}){if(v===null||v===undefined||Number.isNaN(v))return '';const num=Number(v);return (o.prefix||'')+num.toFixed(Math.abs(num)<1?3:2)+(o.suffix||'');}
  function multiLine(id,labels,series,o={}){
    const root=document.getElementById(id); if(!root||!labels?.length)return;
    root.innerHTML=''; const W=Math.max(760,root.clientWidth||900),H=root.classList.contains('tall')?390:300,p={l:60,r:20,t:32,b:54};
    const vals=series.flatMap(s=>s.values.filter(v=>v!==null&&v!==undefined&&Number.isFinite(Number(v))).map(Number)); if(!vals.length)return;
    let ymin=o.minZero?0:Math.min(...vals), ymax=Math.max(...vals); if(ymax===ymin){ymax=ymin+1} const pad=(ymax-ymin)*.12; if(!o.minZero)ymin-=pad; ymax+=pad;
    const x=i=>p.l+(i/(Math.max(1,labels.length-1)))*(W-p.l-p.r), y=v=>p.t+(ymax-v)/(ymax-ymin)*(H-p.t-p.b);
    const svg=el('svg',{viewBox:`0 0 ${W} ${H}`,role:'img'}); root.appendChild(svg);
    for(let i=0;i<=4;i++){const yy=p.t+i*(H-p.t-p.b)/4;svg.appendChild(el('line',{x1:p.l,x2:W-p.r,y1:yy,y2:yy,stroke:'#e5e9f0','stroke-width':1}));const t=el('text',{x:p.l-8,y:yy+4,'text-anchor':'end',fill:'#7a8495','font-size':11});t.textContent=fmt(ymax-i*(ymax-ymin)/4,o);svg.appendChild(t)}
    const tickStep=Math.max(1,Math.ceil(labels.length/8)); labels.forEach((lab,i)=>{if(i%tickStep&&i!==labels.length-1)return;const t=el('text',{x:x(i),y:H-22,'text-anchor':'middle',fill:'#7a8495','font-size':10});t.textContent=String(lab).replace('T',' ').slice(0,13);svg.appendChild(t)});
    series.forEach((s,si)=>{let d='';s.values.forEach((v,i)=>{if(v===null||v===undefined||!Number.isFinite(Number(v)))return;d+=(d?' L ':'M ')+x(i)+' '+y(Number(v))});svg.appendChild(el('path',{d,fill:'none',stroke:palette[si%palette.length],'stroke-width':2.5,'stroke-linejoin':'round','stroke-linecap':'round'}));});
    let lx=p.l;series.forEach((s,si)=>{svg.appendChild(el('line',{x1:lx,x2:lx+18,y1:14,y2:14,stroke:palette[si%palette.length],'stroke-width':3}));const t=el('text',{x:lx+24,y:18,fill:'#4c5668','font-size':11});t.textContent=s.name;svg.appendChild(t);lx+=24+(s.name.length*8)+28;});
  }
  function lineFromJson(id,jsonId,o={}){const d=JSON.parse(document.getElementById(jsonId).textContent);multiLine(id,d.x,[{name:d.y_label||'valor',values:d.y}],o)}
  return {multiLine,lineFromJson};
})();

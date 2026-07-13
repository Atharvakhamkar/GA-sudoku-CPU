"""
main.py (dashboard)
-------------------
A live web dashboard. Reads the shared results volume and serves:
  GET /              -> the HTML page (auto-refreshing)
  GET /api/status    -> latest per-generation status (incl. best grid)
  GET /api/result    -> final result when the run is done
  GET /api/puzzle    -> the puzzle + given mask

This is the human-facing visual: watch the Sudoku grid fill in, the fitness
curve climb, and the worker count change as the scaler reacts.
"""

import os
import json
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

RESULTS = os.getenv("RESULTS_DIR", "/results")
app = FastAPI(title="Sudoku GA Dashboard")


def _read(name):
    try:
        with open(os.path.join(RESULTS, name)) as f:
            return json.load(f)
    except Exception:
        return None


@app.get("/api/status")
def status():
    return JSONResponse(_read("status.json") or {})


@app.get("/api/result")
def result():
    return JSONResponse(_read("result.json") or {})


@app.get("/api/puzzle")
def puzzle():
    return JSONResponse(_read("puzzle.json") or {})


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML


HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Sudoku GA — Live</title>
<style>
:root{--bg:#0f1117;--card:#1a1d27;--ink:#e8eaf0;--muted:#8b93a7;
--accent:#4a9eff;--good:#3ddc84;--warn:#ffb454;--given:#2b3147;--line:#39405a;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;padding:24px}
h1{font-size:20px;margin:0 0 2px} .sub{color:var(--muted);font-size:13px;margin-bottom:20px}
.wrap{display:flex;gap:24px;flex-wrap:wrap;align-items:flex-start}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px}
table.grid{border-collapse:collapse}
table.grid td{width:42px;height:42px;text-align:center;font-size:20px;
border:1px solid var(--line);color:var(--accent);font-variant-numeric:tabular-nums}
table.grid td.given{color:var(--ink);background:var(--given);font-weight:700}
table.grid td.conflict{color:#ff6b6b}
table.grid td.bl{border-left:2px solid var(--muted)}
table.grid td.bt{border-top:2px solid var(--muted)}
.metrics{display:grid;grid-template-columns:1fr 1fr;gap:12px;min-width:300px}
.metric{background:#12151e;border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.metric .v{font-size:26px;font-weight:700} .metric .l{font-size:11px;color:var(--muted);
text-transform:uppercase;letter-spacing:.05em;margin-top:2px}
.bar{height:10px;background:#12151e;border-radius:6px;overflow:hidden;margin-top:14px;border:1px solid var(--line)}
.bar > div{height:100%;background:linear-gradient(90deg,var(--accent),var(--good));width:0%}
.pill{display:inline-block;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600}
.pill.run{background:rgba(74,158,255,.15);color:var(--accent)}
.pill.solved{background:rgba(61,220,132,.15);color:var(--good)}
.pill.stuck{background:rgba(255,180,84,.15);color:var(--warn)}
svg{display:block} .chart-l{font-size:11px;color:var(--muted)}
</style></head><body>
<h1>Sudoku GA — Live Dashboard</h1>
<div class="sub">Single-island GA · scalable fitness pool · auto-refresh every 1.2s</div>
<div class="wrap">
  <div class="card"><div id="status-pill"></div>
    <table class="grid" id="grid"></table>
  </div>
  <div class="card" style="min-width:320px">
    <div class="metrics">
      <div class="metric"><div class="v" id="m-best">—</div><div class="l">Best / 162</div></div>
      <div class="metric"><div class="v" id="m-pct">—</div><div class="l">Percent</div></div>
      <div class="metric"><div class="v" id="m-gen">—</div><div class="l">Generation</div></div>
      <div class="metric"><div class="v" id="m-workers">—</div><div class="l">Pool workers</div></div>
      <div class="metric"><div class="v" id="m-rate">—</div><div class="l">Improve rate</div></div>
      <div class="metric"><div class="v" id="m-restarts">—</div><div class="l">Restarts</div></div>
    </div>
    <div class="bar"><div id="bar"></div></div>
    <div style="margin-top:20px" class="chart-l">Best fitness over generations</div>
    <svg id="chart" width="320" height="140"></svg>
  </div>
</div>
<script>
let givenMask=null, puzzleLoaded=false;
const GRID=9;
async function loadPuzzle(){
  try{const r=await fetch('/api/puzzle');const p=await r.json();
    if(p&&p.given_mask){givenMask=p.given_mask;puzzleLoaded=true;}}catch(e){}
}
function conflicts(flat){
  // mark cells whose column or box has a duplicate of its value
  const bad=new Array(81).fill(false);
  const idx=(r,c)=>r*9+c;
  for(let c=0;c<9;c++){const seen={};for(let r=0;r<9;r++){const v=flat[idx(r,c)];
    (seen[v]=seen[v]||[]).push(idx(r,c));}
    for(const v in seen)if(seen[v].length>1)seen[v].forEach(i=>bad[i]=true);}
  for(let br=0;br<9;br+=3)for(let bc=0;bc<9;bc+=3){const seen={};
    for(let i=0;i<3;i++)for(let j=0;j<3;j++){const v=flat[idx(br+i,bc+j)];
      (seen[v]=seen[v]||[]).push(idx(br+i,bc+j));}
    for(const v in seen)if(seen[v].length>1)seen[v].forEach(i=>bad[i]=true);}
  return bad;
}
function renderGrid(flat){
  const t=document.getElementById('grid');t.innerHTML='';
  const bad=conflicts(flat);
  for(let r=0;r<9;r++){const tr=document.createElement('tr');
    for(let c=0;c<9;c++){const td=document.createElement('td');
      const i=r*9+c;td.textContent=flat[i]||'';
      if(givenMask&&givenMask[i])td.classList.add('given');
      else if(bad[i])td.classList.add('conflict');
      if(c%3===0&&c!==0)td.classList.add('bl');
      if(r%3===0&&r!==0)td.classList.add('bt');
      tr.appendChild(td);}t.appendChild(tr);}
}
const histPts=[];
function renderChart(){
  const svg=document.getElementById('chart');const W=320,H=140,pad=20;
  svg.innerHTML='';
  if(histPts.length<2)return;
  const xs=histPts.map(p=>p.g),ys=histPts.map(p=>p.f);
  const xmin=Math.min(...xs),xmax=Math.max(...xs);
  const ymin=Math.min(...ys),ymax=162;
  const sx=g=>pad+(W-2*pad)*((g-xmin)/Math.max(1,xmax-xmin));
  const sy=f=>H-pad-(H-2*pad)*((f-ymin)/Math.max(1,ymax-ymin));
  let d='';histPts.forEach((p,k)=>{d+=(k?'L':'M')+sx(p.g)+' '+sy(p.f);});
  const path='<path d="'+d+'" fill="none" stroke="#4a9eff" stroke-width="2"/>';
  const target='<line x1="'+pad+'" y1="'+sy(162)+'" x2="'+(W-pad)+'" y2="'+sy(162)+
    '" stroke="#3ddc84" stroke-dasharray="4 3" stroke-width="1"/>';
  svg.innerHTML=target+path;
}
async function tick(){
  if(!puzzleLoaded)await loadPuzzle();
  try{
    const r=await fetch('/api/status');const s=await r.json();
    if(s&&s.best_grid){renderGrid(s.best_grid);
      document.getElementById('m-best').textContent=s.best_fitness;
      document.getElementById('m-pct').textContent=(s.percent||0)+'%';
      document.getElementById('m-gen').textContent=s.generation;
      document.getElementById('m-workers').textContent=s.worker_count;
      document.getElementById('m-rate').textContent=(s.improvement_rate==null?'—':s.improvement_rate);
      document.getElementById('m-restarts').textContent=s.restarts||0;
      document.getElementById('bar').style.width=(s.percent||0)+'%';
      const pill=document.getElementById('status-pill');
      if(s.best_fitness>=162)pill.innerHTML='<span class="pill solved">SOLVED ✓</span>';
      else if(s.stagnating)pill.innerHTML='<span class="pill stuck">STAGNATING — scaler may add workers</span>';
      else pill.innerHTML='<span class="pill run">EVOLVING…</span>';
      if(!histPts.length||histPts[histPts.length-1].g!==s.generation){
        histPts.push({g:s.generation,f:s.best_fitness});
        if(histPts.length>400)histPts.shift();renderChart();}
    }
  }catch(e){}
}
setInterval(tick,1200);tick();
</script></body></html>"""

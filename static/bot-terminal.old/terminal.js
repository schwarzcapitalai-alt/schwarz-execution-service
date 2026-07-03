const $ = id => document.getElementById(id);

async function getJson(url){
  const r = await fetch(url,{cache:"no-store"});
  if(!r.ok) throw new Error(url+" "+r.status);
  return await r.json();
}

function setText(id,text,cls){
  const el=$(id);
  if(!el) return;
  el.innerText=text;
  if(cls) el.className="big "+cls;
}

function money(v){
  if(v===undefined||v===null||v==="") return "—";
  const n=Number(String(v).replace(/,/g,""));
  if(Number.isNaN(n)) return String(v);
  return "$"+n.toLocaleString(undefined,{maximumFractionDigits:2});
}

function accountTag(data,tag){
  const rows=data.cash||data.account||[];
  const row=rows.find(x=>x.tag===tag);
  return row?row.value:null;
}

function tableRows(items,empty,cols){
  if(!items||!items.length) return `<tr><td colspan="${cols}">${empty}</td></tr>`;
  return items.join("");
}

async function refresh(){
  $("updated").innerText=new Date().toLocaleString();

  let botState="WAITING";

  try{
    const ib=await getJson("/ibkr/shared/status");
    setText("ibkr",ib.connected?"CONNECTED":"OFFLINE",ib.connected?"green":"red");
  }catch(e){
    setText("ibkr","ERROR","red");
  }

  try{
    const mode=await getJson("/system/mode");
    const m=mode.execution_mode||mode.mode||"UNKNOWN";
    setText("mode",m,m.includes("PAPER")?"green":"yellow");
  }catch(e){
    setText("mode","ERROR","red");
  }

  try{
    const risk=await getJson("/risk/status");
    const killed=risk.kill_switch_enabled||risk.kill_switch||false;
    setText("risk",killed?"KILL SWITCH":"ACTIVE",killed?"red":"green");
  }catch(e){
    setText("risk","UNKNOWN","yellow");
  }

  try{
    const account=await getJson("/account/snapshot");
    $("netLiq").innerText=money(accountTag(account,"NetLiquidation"));
    $("buyingPower").innerText=money(accountTag(account,"BuyingPower"));
    $("availableFunds").innerText=money(accountTag(account,"AvailableFunds"));
    $("totalCash").innerText=money(accountTag(account,"TotalCashValue"));
  }catch(e){
    $("netLiq").innerText="Unavailable";
  }

  try{
    const decision=await getJson("/decision/current");
    $("decisionPayload").innerText=JSON.stringify(decision,null,2);

    const action=decision.execution||decision.action||"WAIT";
    const direction=decision.direction||decision.market_direction||decision.desk_call||"—";
    const confidence=decision.confidence||decision.confidence_score||decision.score||"—";
    const regime=decision.market_regime||decision.gamma_regime||decision.regime||"—";

    $("decisionAction").innerText=action;
    $("direction").innerText=direction;
    $("confidence").innerText=confidence==="—"?"—":confidence+"%";
    $("regime").innerText=regime;

    botState = action==="WAIT" ? "WAITING" : "SIGNAL LIVE";
    setText("botState",botState,action==="WAIT"?"yellow":"green");
  }catch(e){
    $("decisionPayload").innerText="Decision endpoint unavailable";
    $("decisionAction").innerText="—";
    setText("botState","NO DECISION","yellow");
  }

  try{
    const orders=await getJson("/ibkr/shared/open-orders");
    const list=orders.open_orders||orders.orders||[];
    $("orders").innerHTML=tableRows(
      list.map(o=>`<tr><td>${o.symbol||""}</td><td>${o.action||o.side||""}</td><td>${o.quantity||o.qty||""}</td><td>${o.status||""}</td></tr>`),
      "No open orders",
      4
    );
  }catch(e){
    $("orders").innerHTML='<tr><td colspan="4">Orders unavailable</td></tr>';
  }

  try{
    const pos=await getJson("/ibkr/shared/positions");
    const list=pos.positions||[];
    $("positions").innerHTML=tableRows(
      list.map(p=>`<tr><td>${p.symbol||p.contract||""}</td><td>${p.position||p.qty||""}</td><td>${p.avgCost||p.avg_cost||""}</td><td>${p.marketValue||p.market_value||""}</td></tr>`),
      "No positions",
      4
    );
  }catch(e){
    $("positions").innerHTML='<tr><td colspan="4">Positions unavailable</td></tr>';
  }

  try{
    const health=await getJson("/health");
    $("health").innerText=JSON.stringify(health,null,2);
  }catch(e){
    $("health").innerText="Health unavailable";
  }
}

refresh();
setInterval(refresh,5000);

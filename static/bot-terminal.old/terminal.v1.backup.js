async function getJson(url){
  const r = await fetch(url,{cache:"no-store"});
  if(!r.ok) throw new Error(url+" "+r.status);
  return await r.json();
}

function setValue(id,text,status){
  const el=document.getElementById(id);
  el.innerText=text;
  el.className="value "+status;
}

function pretty(x){
  return JSON.stringify(x,null,2);
}

async function refresh(){
  document.getElementById("updated").innerText=new Date().toLocaleString();

  try{
    const ib=await getJson("/ibkr/shared/status");
    setValue("ibkr",ib.connected?"CONNECTED":"DISCONNECTED",ib.connected?"green":"red");
  }catch(e){
    setValue("ibkr","ERROR","red");
  }

  try{
    const mode=await getJson("/system/mode");
    const m=mode.execution_mode||mode.mode||"UNKNOWN";
    setValue("mode",m,m.includes("PAPER")?"green":"yellow");
  }catch(e){
    setValue("mode","ERROR","red");
  }

  try{
    const d=await getJson("/decision/current");
    document.getElementById("decisionPayload").innerText=pretty(d);
    const action=d.execution||d.action||"WAIT";
    setValue("decision",action,action==="WAIT"?"yellow":"green");
  }catch(e){
    setValue("decision","NO DATA","yellow");
    document.getElementById("decisionPayload").innerText="Decision endpoint unavailable";
  }

  try{
    const a=await getJson("/account/snapshot");
    document.getElementById("account").innerText=pretty(a);
  }catch(e){
    document.getElementById("account").innerText="Account snapshot unavailable";
  }

  try{
    const r=await getJson("/risk/status");
    const killed=r.kill_switch_enabled||r.kill_switch||false;
    setValue("risk",killed?"KILL SWITCH ON":"ACTIVE",killed?"red":"green");
  }catch(e){
    setValue("risk","UNKNOWN","yellow");
  }

  try{
    const h=await getJson("/health");
    document.getElementById("health").innerText=pretty(h);
  }catch(e){
    document.getElementById("health").innerText="Health endpoint unavailable";
  }
}

refresh();
setInterval(refresh,5000);

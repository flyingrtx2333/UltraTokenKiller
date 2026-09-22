import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

type Client = {name:string; detected:boolean; enabled:boolean; supported:boolean}
type Status = {headroom:boolean;rtk:boolean;profile:string;profile_controlled:boolean;caveman:string;clients:Client[]}
type Metrics = {model_requests:number;tool_commands:number;tool_optimized:number;input_tokens:number|null;output_tokens:number|null;cached_tokens:number|null;rtk_saved_tokens:number;headroom_saved_tokens:number}
type EventItem = {id:number;created_at:number;kind:string;client:string;model?:string;duration_ms?:number;success:boolean;saved_tokens:number|null;metadata:{optimized?:boolean;original_bytes?:number;rendered_bytes?:number;upstream_status?:number}}
const format = (value:number|null|undefined) => value == null ? '—' : new Intl.NumberFormat('zh-CN').format(value)
const profiles:Record<string,string> = {safe:'稳妥',aggressive:'积极',off:'关闭'}
const modes:Record<string,string> = {lite:'简洁',full:'精简',ultra:'极简',off:'关闭','wenyan-lite':'文言 · 简洁','wenyan-full':'文言 · 精简','wenyan-ultra':'文言 · 极简'}
const clientNames:Record<string,string> = {codex:'Codex',hermes:'Hermes',cli:'终端'}
const clientName = (name:string) => clientNames[name]||name

function App(){
  const [status,setStatus]=useState<Status|null>(null)
  const [metrics,setMetrics]=useState<Metrics|null>(null)
  const [events,setEvents]=useState<EventItem[]>([])
  const [token,setToken]=useState('')
  const [hours,setHours]=useState(24)
  const [error,setError]=useState('')
  const [busy,setBusy]=useState('')
  const [refresh,setRefresh]=useState(0)
  const [updated,setUpdated]=useState<Date|null>(null)

  useEffect(()=>{
    const controller=new AbortController()
    const options={signal:controller.signal}
    let disposed=false
    async function json(url:string){
      const response=await fetch(url,options)
      if(!response.ok)throw new Error('数据加载失败')
      return response.json()
    }
    async function load(){
      try{
        const [s,m,e,c]=await Promise.all([
          json('/api/v1/status'),json(`/api/v1/metrics?hours=${hours}`),
          json(`/api/v1/events?limit=40&hours=${hours}`),json('/api/v1/config')
        ])
        if(disposed)return
        setStatus(s);setMetrics(m.local);setEvents(e);setToken(c.session_token||'')
        setUpdated(new Date());setError('')
      }catch(e){
        if(!disposed)setError('连接中断，正在重连')
      }
    }
    void load()
    const source=new EventSource(`/api/v1/stream?hours=${hours}`)
    source.onerror=()=>{if(!disposed)setError('连接中断，正在重连')}
    source.addEventListener('snapshot',async event=>{
      try{
        const payload=JSON.parse((event as MessageEvent).data)
        const e=await json(`/api/v1/events?limit=40&hours=${hours}`)
        if(disposed)return
        setStatus(payload.status);setMetrics(payload.metrics.local);setEvents(e)
        setUpdated(new Date());setError('')
      }catch{if(!disposed)setError('数据加载失败')}
    })
    return()=>{disposed=true;controller.abort();source.close()}
  },[hours,refresh])

  async function update(path:string, method:string, key:string, data?:object){
    setBusy(key)
    try{
      const response=await fetch(path,{method,headers:{'Content-Type':'application/json','X-UTK-Token':token},body:data?JSON.stringify(data):undefined})
      if(!response.ok)throw new Error((await response.json()).detail||'操作失败')
      setRefresh(v=>v+1);setError('')
    }catch(e){setError(e instanceof Error?e.message:'操作失败')}
    finally{setBusy('')}
  }

  return <>
    <a className="skip" href="#main">跳到主要内容</a>
    <header className="topbar">
      <div className="brand"><img className="brand-mark" src="/brand/utk-icon.svg" alt="" width="44" height="44"/><h1>UltraTokenKiller</h1></div>
      <div className="top-actions"><label>时间范围<select value={hours} onChange={e=>setHours(Number(e.target.value))}><option value="24">24 小时</option><option value="168">7 天</option><option value="720">30 天</option></select></label><button className="quiet" onClick={()=>setRefresh(v=>v+1)}>刷新</button></div>
    </header>
    <main id="main">
      {error&&<div className="alert" role="alert"><span>{error}</span><button onClick={()=>setRefresh(v=>v+1)}>重试</button></div>}
      <section aria-labelledby="overview-title">
        <div className="section-head"><h2 id="overview-title">用量与节省</h2><time>{updated?.toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'})||'加载中'}</time></div>
        <div className="metrics">
          <Metric label="模型请求" value={format(metrics?.model_requests)} />
          <Metric label="输入 Token" value={format(metrics?.input_tokens)} />
          <Metric label="输出 Token" value={format(metrics?.output_tokens)} />
          <Metric label="输入节省（估算 Token）" value={format(metrics?.headroom_saved_tokens)} />
          <Metric label="工具节省（估算 Token）" value={format(metrics?.rtk_saved_tokens)} />
          <Metric label="已压缩 / 工具命令" value={metrics?`${format(metrics.tool_optimized)} / ${format(metrics.tool_commands)}`:'—'} />
        </div>
      </section>

      <div className="workspace">
        <section aria-labelledby="layers-title"><div className="section-head"><h2 id="layers-title">功能</h2>{status&&!token&&<span className="state">只读</span>}</div>
          <div className="layer-list">
            <Layer name="输入压缩" active={status?status.headroom&&status.profile!=='off':null} />
            <Layer name="工具输出" active={status?status.rtk:null} />
            <Layer name="回答精简" active={status?status.caveman!=='off':null} />
          </div>
          {token?<><fieldset disabled={!status||!!busy||!status.profile_controlled}><legend>压缩档位</legend><div className="segmented">
            {Object.entries(profiles).map(([v,label])=><button key={v} className={status?.profile===v?'selected':''} aria-pressed={status?.profile===v} onClick={()=>update('/api/v1/config','PATCH','config',{profile:v})}>{label}</button>)}
          </div></fieldset>
          <label className="field">回答精简<select value={status?.caveman||'off'} onChange={e=>update('/api/v1/config','PATCH','config',{caveman:e.target.value})} disabled={!status||!!busy}>{Object.entries(modes).map(([v,label])=><option value={v} key={v}>{label}</option>)}</select></label></>:
          <div className="settings-summary"><span>压缩档位 <strong>{profiles[status?.profile||'']||'—'}</strong></span><span>回答精简 <strong>{modes[status?.caveman||'']||'—'}</strong></span></div>}
        </section>

        <section aria-labelledby="clients-title"><div className="section-head"><h2 id="clients-title">客户端</h2></div>
          <div className="client-list">{status?.clients.map(client=><article className="client" key={client.name}>
            <div className="client-name"><StatusDot ok={client.enabled}/><h3>{clientName(client.name)}</h3></div>
            <span className="state">{!client.detected?'未安装':!client.supported?'暂不支持':client.enabled?'已接入':'未接入'}</span>
            {token&&client.detected&&client.supported&&<button disabled={!!busy} onClick={()=>update(`/api/v1/clients/${client.name}/${client.enabled?'disable':'enable'}`,'POST',client.name)}>{busy===client.name?'处理中…':client.enabled?'断开':'接入'}</button>}
          </article>)||<p className="empty">加载中…</p>}</div>
        </section>
      </div>

      <section aria-labelledby="events-title"><div className="section-head"><h2 id="events-title">最近活动</h2></div>
        {events.length?<div className="table-wrap"><table><thead><tr><th>时间</th><th>类型</th><th>客户端</th><th>模型 / 输出</th><th>节省 Token</th><th>结果</th></tr></thead><tbody>{events.map(item=>{
          const tool=['tool','rtk'].includes(item.kind)
          const {original_bytes:before,rendered_bytes:after}=item.metadata
          const size=before!=null&&after!=null?`${format(before)} → ${format(after)} B`:null
          const status=item.metadata.upstream_status
          const label=item.success?'成功':tool?'命令失败':status?`上游 ${status}`:'失败'
          return <tr key={item.id}><td>{new Date(item.created_at*1000).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'})}</td><td>{tool?'工具命令':'模型请求'}</td><td>{clientName(item.client)}</td><td>{tool?size||'—':item.model||'—'}</td><td>{format(item.saved_tokens)}</td><td><span className={item.success?'result ok':'result bad'}>{label}</span></td></tr>
        })}</tbody></table></div>:<div className="empty-state"><strong>{updated?'暂无活动':'加载中…'}</strong></div>}
      </section>
    </main>
  </>
}

function Metric({label,value}:{label:string;value:string}){return <article className="metric"><span>{label}</span><strong>{value}</strong></article>}
function StatusDot({ok}:{ok:boolean}){return <span className={ok?'dot on':'dot'} aria-label={ok?'已开启':'未开启'} />}
function Layer({name,active}:{name:string;active:boolean|null}){return <article className="layer"><StatusDot ok={active===true}/><h3>{name}</h3><span className="state">{active===null?'加载中':active?'已开启':'已关闭'}</span></article>}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>)

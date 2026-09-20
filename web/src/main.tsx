import React, { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

type Client = {name:string; detected:boolean; enabled:boolean; supported:boolean; detail:string}
type Status = {service:boolean;headroom:boolean;rtk:boolean;profile:string;profile_controlled:boolean;caveman:string;auto_start:boolean;ports:{dashboard:number;headroom:number};clients:Client[]}
type Metrics = {requests:number;model_requests?:number;tool_commands?:number;tool_optimized?:number;known_input_usage?:number;input_tokens:number|null;output_tokens:number|null;cached_tokens:number|null;rtk_saved_tokens:number;headroom_saved_tokens:number;average_duration_ms:number;failures:number;error_rate:number}
type EventItem = {id:number;created_at:number;kind:string;client:string;model?:string;duration_ms?:number;success:boolean;metadata:Record<string,unknown>}
type CapabilityState = 'not_implemented'|'implemented_unverified'|'offline_passed'|'real_client_passed'|'upstream_parity_passed'
type CapabilityReport = {summary:Record<CapabilityState,number>;total_core_capabilities:number;discovered_command_variants:number;reviewed_command_contracts:number;verified_command_contracts:number;parity_certified:boolean;upstream_comparisons_missing:boolean;verification:{ledger_present:boolean;suite_passed:boolean;generated_at?:string;source_bound_capabilities:number;real_client_source_bound:number;stale_capabilities:string[]}}
type BenchmarkReport = {status:string;kind?:string;created_at?:string;summary?:Record<string,unknown>;fixtures?:unknown[];pairs?:unknown[]}

const emptyMetrics: Metrics = {requests:0,input_tokens:0,output_tokens:0,cached_tokens:0,rtk_saved_tokens:0,headroom_saved_tokens:0,average_duration_ms:0,failures:0,error_rate:0}
const formatter = new Intl.NumberFormat('zh-CN')
const number = {format: (value:number|null) => value == null ? '未知' : formatter.format(value)}

function App(){
  const [status,setStatus]=useState<Status|null>(null)
  const [metrics,setMetrics]=useState<Metrics>(emptyMetrics)
  const [events,setEvents]=useState<EventItem[]>([])
  const [token,setToken]=useState('')
  const [hours,setHours]=useState(24)
  const [error,setError]=useState('')
  const [busy,setBusy]=useState('')
  const [readiness,setReadiness]=useState<CapabilityReport|null>(null)
  const [recovery,setRecovery]=useState<{used_bytes:number;capacity_bytes:number}|null>(null)
  const [benchmarks,setBenchmarks]=useState<{compression:BenchmarkReport|null;response:BenchmarkReport|null}>({compression:null,response:null})

  async function load(){
    try{
      const [s,m,e,c]=await Promise.all([
        fetch('/api/v1/status'),fetch(`/api/v1/metrics?hours=${hours}`),fetch('/api/v1/events?limit=40'),fetch('/api/v1/config')
      ])
      if(!s.ok||!m.ok||!e.ok||!c.ok) throw new Error('服务返回错误')
      setStatus(await s.json()); setMetrics((await m.json()).local); setEvents(await e.json()); setToken((await c.json()).session_token); setError('')
      const [cap,mem,compression,response]=await Promise.all([
        fetch('/api/v1/capabilities'),fetch('/api/v1/recovery/status'),
        fetch('/api/v1/benchmarks/latest?kind=compression'),fetch('/api/v1/benchmarks/latest?kind=response')
      ])
      if(cap.ok)setReadiness(await cap.json())
      if(mem.ok)setRecovery(await mem.json())
      setBenchmarks({compression:compression.ok?await compression.json():null,response:response.ok?await response.json():null})
    }catch(e){ setError(e instanceof Error?e.message:'无法连接本地服务') }
  }
  useEffect(()=>{
    load()
    const source=new EventSource(`/api/v1/stream?hours=${hours}`)
    source.addEventListener('snapshot',async event=>{
      try{
        const payload=JSON.parse((event as MessageEvent).data)
        setStatus(payload.status); setMetrics(payload.metrics.local); setError('')
        const response=await fetch('/api/v1/events?limit=40')
        if(response.ok)setEvents(await response.json())
      }catch{ /* Native EventSource retries transient failures. */ }
    })
    return()=>source.close()
  },[hours])

  async function updateConfig(data:Record<string,string>){
    setBusy('config')
    try{
      const response=await fetch('/api/v1/config',{method:'PATCH',headers:{'Content-Type':'application/json','X-UTK-Token':token},body:JSON.stringify(data)})
      if(!response.ok) throw new Error((await response.json()).detail||'保存失败')
      setStatus(await response.json()); setError('')
    }catch(e){setError(e instanceof Error?e.message:'保存失败')}finally{setBusy('')}
  }
  async function toggleClient(client:Client){
    setBusy(client.name)
    try{
      const action=client.enabled?'disable':'enable'
      const response=await fetch(`/api/v1/clients/${client.name}/${action}`,{method:'POST',headers:{'X-UTK-Token':token}})
      if(!response.ok) throw new Error((await response.json()).detail||'操作失败')
      await load()
    }catch(e){setError(e instanceof Error?e.message:'操作失败')}finally{setBusy('')}
  }

  const coverage=useMemo(()=>{
    if(!metrics.tool_commands)return null
    return Math.round(100*(metrics.tool_optimized||0)/metrics.tool_commands)
  },[metrics])

  return <>
    <a className="skip" href="#main">跳到主要内容</a>
    <header className="topbar">
      <div className="brand"><img className="brand-mark" src="/brand/utk-icon.svg" alt="" width="44" height="44"/><div><h1>UltraTokenKiller</h1><p>本地 Token 控制台</p></div></div>
      <div className="top-actions"><label>时间范围<select value={hours} onChange={e=>setHours(Number(e.target.value))}><option value="24">24 小时</option><option value="168">7 天</option><option value="720">30 天</option></select></label><button className="quiet" onClick={load}>刷新</button></div>
    </header>
    <main id="main">
      {error&&<div className="alert" role="alert"><span>{error}</span><button onClick={load}>重试</button></div>}
      <section aria-labelledby="overview-title">
        <div className="section-head"><div><h2 id="overview-title">运行概览</h2><p>{status?`看板 :${status.ports.dashboard} · 数据代理 :${status.ports.headroom}`:'正在读取服务状态'}</p></div><time>{new Date().toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'})}</time></div>
        <div className="metrics">
          <Metric label="模型请求" value={number.format(metrics.model_requests??metrics.requests)} note={metrics.requests?`${metrics.tool_commands||0} 条工具命令记录`:'尚无真实请求'} />
          <Metric label="输入 Token" value={number.format(metrics.input_tokens)} note={`缓存 ${number.format(metrics.cached_tokens)}`} />
          <Metric label="输出 Token" value={number.format(metrics.output_tokens)} note="提供商 usage" />
          <Metric label="已记录命令压缩率" value={coverage===null?'—':`${coverage}%`} note={coverage===null?'尚无命令记录':'分母仅含经过 UTK 的命令'} />
        </div>
        <div className="savings-note"><strong>节省口径分开显示</strong><span>输入压缩估算 {number.format(metrics.headroom_saved_tokens)} · 工具输出估算 {number.format(metrics.rtk_saved_tokens)}。按 UTF-8 字节数估算，两项不合并为账单节省。</span></div>
        <div className="savings-note"><strong>{readiness?.parity_certified?'核心对标已验收':'完整对标尚未验收'}</strong><span>已发现 {readiness?.discovered_command_variants??'—'} 个上游命令枚举项，发现不等于实现。原文仅保存在内存，重启失效。{recovery?` 当前使用 ${(recovery.used_bytes/1048576).toFixed(1)} / ${(recovery.capacity_bytes/1048576).toFixed(0)} MiB。`:''}</span></div>
        <div className="savings-note"><strong>能力证据</strong><span>核心能力 {readiness?.total_core_capabilities??'—'} 项：上游对标 {readiness?.summary.upstream_parity_passed??0}、真实客户端 {readiness?.summary.real_client_passed??0}、离线通过 {readiness?.summary.offline_passed??0}、待验证 {readiness?.summary.implemented_unverified??0}、未实现 {readiness?.summary.not_implemented??0}。当前源码绑定 {readiness?.verification.source_bound_capabilities??0} 项；旧实机证据未绑定当前源码时自动降级。命令契约已验证 {readiness?.verified_command_contracts??0} / 已审阅 {readiness?.reviewed_command_contracts??'—'}；发现的 {readiness?.discovered_command_variants??'—'} 个枚举项不作为覆盖率分母。</span></div>
        <div className="savings-note"><strong>验证报告</strong><span>压缩对照：{benchmarks.compression?'已有报告':'未运行'}；回答成对评测：{benchmarks.response?'已有报告':'未运行'}。原文只存内存且重启失效。{recovery?` 当前使用 ${(recovery.used_bytes/1048576).toFixed(1)} / ${(recovery.capacity_bytes/1048576).toFixed(0)} MiB。`:''}</span></div>
      </section>

      <div className="workspace">
        <section aria-labelledby="layers-title"><div className="section-head"><h2 id="layers-title">三层优化</h2></div>
          <div className="layer-list">
            <Layer name="输入压缩" tool="UTK 原生" active={!!status?.headroom} detail={status?.headroom?'按内容处理；需要有效会话才能找回原文':'服务未连接'} />
            <Layer name="工具输出" tool="UTK 原生" active={!!status?.rtk} detail={coverage===null?'等待实际调用':`${coverage}% 命令进入压缩器`} />
            <Layer name="回答精简" tool="UTK 原生" active={!!status&&status.caveman!=='off'} detail={`当前 ${status?.caveman||'—'} 档`} />
          </div>
          <fieldset disabled={!status||busy==='config'||!status.profile_controlled}><legend>压缩档位{status&&!status.profile_controlled?'（旧外部代理尚未迁移）':''}</legend><div className="segmented">
            {['safe','aggressive','off'].map(v=><button key={v} className={status?.profile===v?'selected':''} aria-pressed={status?.profile===v} onClick={()=>updateConfig({profile:v})}>{({safe:'稳妥',aggressive:'积极',off:'关闭'} as Record<string,string>)[v]}</button>)}
          </div></fieldset>
          <label className="field">回答精简<select value={status?.caveman||'lite'} onChange={e=>updateConfig({caveman:e.target.value})} disabled={!status||busy==='config'}><option value="lite">Lite</option><option value="full">Full</option><option value="ultra">Ultra</option><option value="off">关闭</option></select></label>
        </section>

        <section aria-labelledby="clients-title"><div className="section-head"><h2 id="clients-title">客户端</h2></div>
          <div className="client-list">{status?.clients.map(client=><article className="client" key={client.name}><div><div className="client-name"><StatusDot ok={client.enabled}/><h3>{client.name==='codex'?'Codex':'Hermes Agent'}</h3></div><p>{!client.detected?'未检测到':client.enabled?'已接入数据代理':client.detail}</p></div><button disabled={!client.detected||!client.supported||busy===client.name} onClick={()=>toggleClient(client)}>{busy===client.name?'处理中…':client.enabled?'断开':'接入'}</button></article>)||<p className="empty">正在检测客户端…</p>}</div>
        </section>
      </div>

      <section aria-labelledby="events-title"><div className="section-head"><div><h2 id="events-title">最近活动</h2><p>只记录元数据，不保存提示词和回答正文</p></div></div>
        {events.length?<div className="table-wrap"><table><thead><tr><th>时间</th><th>层级</th><th>客户端</th><th>模型</th><th>耗时</th><th>结果</th></tr></thead><tbody>{events.map(item=><tr key={item.id}><td>{new Date(item.created_at*1000).toLocaleTimeString('zh-CN')}</td><td>{item.kind}</td><td>{item.client}</td><td>{item.model||'—'}</td><td>{item.duration_ms?`${item.duration_ms} ms`:'—'}</td><td><span className={item.success?'result ok':'result bad'}>{item.success?'成功':'失败'}</span></td></tr>)}</tbody></table></div>:<div className="empty-state"><strong>尚无活动记录</strong><p>客户端完成请求或通过 <code>utk exec --</code> 运行命令后，这里会显示真实记录。</p></div>}
      </section>
    </main>
    <footer><span>数据保存在本机</span><span>{status?.auto_start?'登录时自动启动':'未启用登录自启'}</span></footer>
  </>
}

function Metric({label,value,note}:{label:string,value:string,note:string}){return <article className="metric"><span>{label}</span><strong>{value}</strong><small>{note}</small></article>}
function StatusDot({ok}:{ok:boolean}){return <span className={ok?'dot on':'dot'} aria-label={ok?'已启用':'未启用'} />}
function Layer({name,tool,active,detail}:{name:string;tool:string;active:boolean;detail:string}){return <article className="layer"><StatusDot ok={active}/><div><h3>{name}</h3><p>{tool} · {detail}</p></div><span className="state">{active?'运行中':'未运行'}</span></article>}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>)

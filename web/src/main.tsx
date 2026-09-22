import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

type Client = {name:string; detected:boolean; enabled:boolean; supported:boolean}
type FeatureState = 'off'|'waiting'|'active'|'skipped'|'error'
type Status = {headroom:boolean;rtk:boolean;profile:string;profile_controlled:boolean;caveman:string;features?:{input:FeatureState;tools:FeatureState;response:FeatureState};clients:Client[]}
type Metrics = {model_requests:number;tool_commands:number;tool_optimized:number;input_tokens:number|null;output_tokens:number|null;cached_tokens:number|null;rtk_saved_tokens:number;headroom_saved_tokens:number}
type TimelinePoint = {start:number;consumed_tokens:number;saved_tokens:number;model_requests:number;failures:number}
type Breakdown = {name:string;requests:number;consumed_tokens:number;saved_tokens:number}
type Analytics = {granularity:'hour'|'day';timeline:TimelinePoint[];by_model:Breakdown[];by_client:Breakdown[];savings:{name:string;saved_tokens:number}[];outcomes:{name:string;count:number}[]}
type EventItem = {id:number;created_at:number;kind:string;client:string;model?:string;duration_ms?:number;success:boolean;saved_tokens:number|null;metadata:{optimized?:boolean;original_bytes?:number;rendered_bytes?:number;upstream_status?:number;request_class?:string;path?:string;error_category?:string}}
const format = (value:number|null|undefined) => value == null ? '—' : new Intl.NumberFormat('zh-CN').format(value)
const compact = (value:number) => new Intl.NumberFormat('zh-CN',{notation:'compact',maximumFractionDigits:1}).format(value)
const profiles:Record<string,string> = {safe:'稳妥',aggressive:'积极',off:'关闭'}
const modes:Record<string,string> = {lite:'轻度',off:'关闭',full:'精简（实验）',ultra:'极简（实验）','wenyan-lite':'文言简洁（实验）','wenyan-full':'文言精简（实验）','wenyan-ultra':'文言极简（实验）'}
const clientNames:Record<string,string> = {codex:'Codex',hermes:'Hermes',cli:'终端'}
const clientName = (name:string) => clientNames[name]||name

function App(){
  const [status,setStatus]=useState<Status|null>(null)
  const [metrics,setMetrics]=useState<Metrics|null>(null)
  const [analytics,setAnalytics]=useState<Analytics|null>(null)
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
        setStatus(s);setMetrics(m.local);setAnalytics(m.analytics);setEvents(e);setToken(c.session_token||'')
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
        setStatus(payload.status);setMetrics(payload.metrics.local);setAnalytics(payload.metrics.analytics);setEvents(e)
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
      <div className="top-actions"><label>时间范围<select value={hours} onChange={e=>setHours(Number(e.target.value))}><option value="24">日</option><option value="168">周</option><option value="720">月</option></select></label><button className="quiet" onClick={()=>setRefresh(v=>v+1)}>刷新</button></div>
    </header>
    <main id="main">
      {error&&<div className="alert" role="alert"><span>{error}</span><button onClick={()=>setRefresh(v=>v+1)}>重试</button></div>}
      <section aria-labelledby="overview-title">
        <div className="section-head"><h2 id="overview-title">用量与节省</h2><time>{updated?.toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'})||'加载中'}</time></div>
        <div className="metrics">
          <Metric label="模型请求尝试" value={format(metrics?.model_requests)} />
          <Metric label="输入 Token" value={format(metrics?.input_tokens)} />
          <Metric label="输出 Token" value={format(metrics?.output_tokens)} />
          <Metric label="输入节省（估算 Token）" value={format(metrics?.headroom_saved_tokens)} />
          <Metric label="工具节省（估算 Token）" value={format(metrics?.rtk_saved_tokens)} />
          <Metric label="已压缩 / 工具命令" value={metrics?`${format(metrics.tool_optimized)} / ${format(metrics.tool_commands)}`:'—'} />
        </div>
      </section>

      <AnalyticsDashboard data={analytics} hours={hours}/>

      <div className="workspace">
        <section aria-labelledby="layers-title"><div className="section-head"><h2 id="layers-title">功能</h2>{status&&!token&&<span className="state">只读</span>}</div>
          <div className="layer-list">
            <Layer name="输入压缩" state={status?.features?.input||(status?(status.profile==='off'?'off':'waiting'):null)} />
            <Layer name="工具输出" state={status?.features?.tools||(status?(status.rtk?'waiting':'off'):null)} />
            <Layer name="回答精简" state={status?.features?.response||(status?(status.caveman==='off'?'off':'waiting'):null)} />
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

function AnalyticsDashboard({data,hours}:{data:Analytics|null;hours:number}){
  const range=hours===24?'日':hours===168?'周':'月'
  const savingNames:Record<string,string>={input:'输入压缩',tool:'工具输出'}
  const outcomeNames:Record<string,string>={success:'成功',failure:'失败'}
  const modelRows=(data?.by_model||[]).map(item=>({name:item.name,value:item.consumed_tokens,detail:`${format(item.requests)} 次 · 已省 ${format(item.saved_tokens)}`}))
  const clientRows=(data?.by_client||[]).map(item=>({name:clientName(item.name),value:item.saved_tokens,detail:`消耗 ${format(item.consumed_tokens)}`}))
  const savingRows=(data?.savings||[]).map(item=>({name:savingNames[item.name]||item.name,value:item.saved_tokens}))
  const outcomeRows=(data?.outcomes||[]).map(item=>({name:outcomeNames[item.name]||item.name,value:item.count,tone:item.name==='failure'?'bad':undefined}))
  return <section aria-labelledby="analytics-title">
    <div className="section-head"><div><h2 id="analytics-title">趋势与分布</h2><p>{range}视图 · 单位 Token</p></div></div>
    <div className="chart-grid">
      <article className="chart-panel trend-panel"><ChartTitle title="消耗 / 节省趋势" legend/><TrendChart points={data?.timeline||[]} granularity={data?.granularity||'hour'}/></article>
      <article className="chart-panel"><ChartTitle title="节省来源"/><HorizontalBars rows={savingRows}/></article>
      <article className="chart-panel"><ChartTitle title="模型消耗"/><HorizontalBars rows={modelRows}/></article>
      <article className="chart-panel"><ChartTitle title="客户端节省"/><HorizontalBars rows={clientRows}/></article>
      <article className="chart-panel outcome-panel"><ChartTitle title="请求结果"/><HorizontalBars rows={outcomeRows}/></article>
    </div>
  </section>
}

function ChartTitle({title,legend=false}:{title:string;legend?:boolean}){return <div className="chart-title"><h3>{title}</h3>{legend&&<div className="chart-legend"><span className="legend-cost">消耗</span><span className="legend-saving">节省</span></div>}</div>}

function TrendChart({points,granularity}:{points:TimelinePoint[];granularity:'hour'|'day'}){
  const width=760,height=250,left=42,right=14,top=16,bottom=34
  const plotWidth=width-left-right,plotHeight=height-top-bottom
  const maximum=Math.max(1,...points.flatMap(point=>[point.consumed_tokens,point.saved_tokens]))
  const x=(index:number)=>left+(points.length<=1?plotWidth/2:index*plotWidth/(points.length-1))
  const y=(value:number)=>top+plotHeight-(value/maximum)*plotHeight
  const path=(key:'consumed_tokens'|'saved_tokens')=>points.map((point,index)=>`${index?'L':'M'} ${x(index)} ${y(point[key])}`).join(' ')
  const ticks=[0,.25,.5,.75,1]
  const labels=points.map((point,index)=>({point,index})).filter(({index})=>index===0||index===points.length-1||index===Math.floor((points.length-1)/2))
  const hasData=points.some(point=>point.consumed_tokens||point.saved_tokens)
  return <div className="trend-wrap">
    <svg className="trend-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Token 消耗与节省趋势">
      {ticks.map(tick=><g key={tick}><line x1={left} x2={width-right} y1={y(maximum*tick)} y2={y(maximum*tick)} className="grid-line"/><text x={left-8} y={y(maximum*tick)+4} textAnchor="end">{compact(Math.round(maximum*tick))}</text></g>)}
      {hasData&&<><path d={path('consumed_tokens')} className="trend-line cost"/><path d={path('saved_tokens')} className="trend-line saving"/>
        {points.map((point,index)=><React.Fragment key={point.start}><circle cx={x(index)} cy={y(point.consumed_tokens)} r="3" className="trend-dot cost"><title>{format(point.consumed_tokens)} Token 消耗</title></circle><circle cx={x(index)} cy={y(point.saved_tokens)} r="3" className="trend-dot saving"><title>{format(point.saved_tokens)} Token 节省</title></circle></React.Fragment>)}</>}
      {labels.map(({point,index})=><text key={point.start} x={x(index)} y={height-8} textAnchor={index===0?'start':index===points.length-1?'end':'middle'}>{new Date(point.start*1000).toLocaleString('zh-CN',granularity==='hour'?{hour:'2-digit'}:{month:'2-digit',day:'2-digit'})}</text>)}
    </svg>
    {!hasData&&<div className="chart-empty">暂无数据</div>}
  </div>
}

type BarRow={name:string;value:number;detail?:string;tone?:string}
function HorizontalBars({rows}:{rows:BarRow[]}){
  const maximum=Math.max(1,...rows.map(row=>row.value))
  if(!rows.length||rows.every(row=>row.value===0))return <div className="chart-empty compact-empty">暂无数据</div>
  return <div className="bar-chart">{rows.map(row=><div className="bar-row" key={row.name}>
    <div className="bar-label"><span>{row.name}</span><strong>{format(row.value)}</strong></div>
    <div className="bar-track"><span className={`bar-fill ${row.tone||''}`} style={{width:`${Math.max(row.value/maximum*100,row.value?2:0)}%`}}/></div>
    {row.detail&&<small>{row.detail}</small>}
  </div>)}</div>
}

function StatusDot({ok}:{ok:boolean}){return <span className={ok?'dot on':'dot'} aria-label={ok?'已开启':'未开启'} />}
const stateLabels:Record<FeatureState,string>={off:'已关闭',waiting:'等待请求',active:'已生效',skipped:'已跳过',error:'异常'}
function Layer({name,state}:{name:string;state:FeatureState|null}){return <article className="layer"><StatusDot ok={state==='active'}/><h3>{name}</h3><span className="state">{state===null?'加载中':stateLabels[state]}</span></article>}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>)

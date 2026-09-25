import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

type Client = {name:string; detected:boolean; enabled:boolean; supported:boolean}
type FeatureState = 'off'|'waiting'|'active'|'skipped'|'error'
type Status = {headroom:boolean;rtk:boolean;profile:string;profile_controlled:boolean;caveman:string;features?:{input:FeatureState;tools:FeatureState;response:FeatureState};clients:Client[]}
type Metrics = {model_requests:number;tool_commands:number;tool_optimized:number;input_tokens:number|null;output_tokens:number|null;cached_tokens:number|null;rtk_saved_tokens:number;headroom_saved_tokens:number}
type MoneyMap = Record<string,number>
type CostEstimate = {status:string;amount?:number;currency?:string;source?:string;checked_on?:string}
type TimelinePoint = {start:number;consumed_tokens:number;actual_input_tokens:number;actual_output_tokens:number;actual_cached_input_tokens:number;saved_tokens:number;model_requests:number;failures:number;usage_observations:number;input_usage_observations:number;output_usage_observations:number;cache_usage_observations:number;estimated_cost_by_currency?:MoneyMap;estimated_saved_cost_by_currency?:MoneyMap}
type Breakdown = {name:string;requests:number;consumed_tokens:number;saved_tokens:number;actual_input_tokens?:number;actual_output_tokens?:number;actual_cached_input_tokens?:number;usage_observations?:number;cache_usage_observations?:number;estimated_cost_by_currency?:MoneyMap;estimated_saved_cost_by_currency?:MoneyMap;cost_estimate_statuses?:Record<string,number>}
type Analytics = {granularity:'hour'|'day';timeline:TimelinePoint[];by_model:Breakdown[];by_client:Breakdown[];skip_reasons:{source:'tool'|'image';reason:string;count:number}[];measurement_basis?:{consumed_tokens:string;saved_tokens:string;money:string;cached_input_tokens:string};estimated_cost_by_currency?:MoneyMap;estimated_saved_cost_by_currency?:MoneyMap;price_catalog_status?:string;savings:{name:string;saved_tokens:number}[];outcomes:{name:string;count:number}[]}
type EventItem = {id:number;created_at:number;kind:string;client:string;model?:string;duration_ms?:number;success:boolean;saved_tokens:number|null;metadata:{optimized?:boolean;original_bytes?:number;rendered_bytes?:number;upstream_status?:number;request_class?:string;path?:string;error_category?:string;changed_tool_results?:number;candidate_tool_results?:number;changed_images?:number;tool_skip_reasons?:Record<string,number>;image_skip_reasons?:Record<string,number>;compression_fallback?:string|boolean;estimated_saved_tokens_basis?:string;cost_estimate_status?:string;estimated_cost?:CostEstimate;estimated_saved_cost?:CostEstimate}}
const format = (value:number|null|undefined) => value == null ? '—' : new Intl.NumberFormat('zh-CN').format(value)
const formatMoney = (value:number|null|undefined,currency:string) => value == null ? '—' : new Intl.NumberFormat('zh-CN',{style:'currency',currency,maximumFractionDigits:6}).format(value)
const moneyLabel = (quote:CostEstimate|undefined) => quote?.status==='estimated'&&quote.currency ? formatMoney(quote.amount,quote.currency) : '—'
const compact = (value:number) => new Intl.NumberFormat('zh-CN',{notation:'compact',maximumFractionDigits:1}).format(value)
const profiles:Record<string,string> = {safe:'稳妥',aggressive:'积极',off:'关闭'}
const modes:Record<string,string> = {lite:'轻度',off:'关闭',full:'精简（实验）',ultra:'极简（实验）','wenyan-lite':'文言简洁（实验）','wenyan-full':'文言精简（实验）','wenyan-ultra':'文言极简（实验）'}
const clientNames:Record<string,string> = {codex:'Codex',hermes:'Hermes',cli:'终端'}
const clientName = (name:string) => clientNames[name]||name
const costStatusNames:Record<string,string> = {no_price:'未配价格',price_not_recorded:'旧记录无价格快照',unavailable_no_price_catalog:'未配价格',usage_missing:'供应商用量缺失',invalid_cache_usage:'缓存用量异常',cache_pricing_unknown:'缓存价格未确认',cache_usage_missing:'缓存用量缺失',cache_policy_mismatch:'缓存规则不匹配',cache_effect_unknown:'缓存对差额影响未明'}
const skipReasonNames:Record<string,string> = {no_tool_result:'无工具结果',already_compressed:'已压缩',broker_unavailable:'压缩器不可用',disabled:'已关闭',missing_session:'缺少会话',not_smaller_or_memory_full:'压缩收益不足',compressor_not_ready:'压缩器未就绪',compression_error:'压缩失败',restored_original:'恢复原文',unchanged:'内容未变化',detail_task:'精细识别任务',unsupported_format_or_url:'不支持的格式或地址',invalid_base64:'图片编码无效',image_too_large:'图片过大',image_library_unavailable:'图像组件不可用',already_small:'图片较小',text_dense_or_diagram:'文字密集或图表',image_decode_error:'图片无法读取',insufficient_byte_savings:'体积收益不足'}
const errorNames:Record<string,string> = {upstream_http_error:'上游请求失败',upstream_stream_error:'上游流中断',upstream_websocket_error:'上游连接错误',upstream_incomplete:'上游未完成',upstream_cancelled:'请求已取消',websocket_interrupted:'连接中断，结果未知'}
const fallbackNames:Record<string,string> = {missing_session:'缺少会话',broker_unavailable:'压缩器不可用',compression_error:'压缩失败',compression_timeout:'压缩超时',compression_circuit_open:'压缩保护已开启',invalid_response_create:'请求格式未处理'}

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
          <Metric label="缓存输入 Token" value={format(metrics?.cached_tokens)} />
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
        {events.length?<div className="table-wrap"><table><thead><tr><th>时间</th><th>类型</th><th>客户端</th><th>模型 / 输出</th><th>节省 Token（估算）</th><th>费用估算</th><th>结果</th><th>详情</th></tr></thead><tbody>{events.map(item=>{
          const tool=['tool','rtk'].includes(item.kind)
          const {original_bytes:before,rendered_bytes:after}=item.metadata
          const size=before!=null&&after!=null?`${format(before)} → ${format(after)} B`:null
          const status=item.metadata.upstream_status
          const label=item.success?'成功':tool?'命令失败':status?`上游 ${status}`:'失败'
          return <tr key={item.id}><td>{new Date(item.created_at*1000).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'})}</td><td>{tool?'工具命令':'模型请求'}</td><td>{clientName(item.client)}</td><td>{tool?size||'—':item.model||'—'}</td><td>{format(item.saved_tokens)}</td><td>{tool?'—':moneyLabel(item.metadata.estimated_cost)}</td><td><span className={item.success?'result ok':'result bad'}>{label}</span></td><td><EventDetails item={item}/></td></tr>
        })}</tbody></table></div>:<div className="empty-state"><strong>{updated?'暂无活动':'加载中…'}</strong></div>}
      </section>
    </main>
  </>
}

function Metric({label,value}:{label:string;value:string}){return <article className="metric"><span>{label}</span><strong>{value}</strong></article>}

function EventDetails({item}:{item:EventItem}){
  const details:string[]=[]
  const requestClasses:Record<string,string>={model:'模型请求',probe:'能力探测',transport:'传输请求'}
  const safeErrors:Record<string,string>={invalid_request:'请求参数无效',authentication:'认证失败',not_found:'接口不存在',rate_limit:'额度限制',upstream_error:'上游错误'}
  const count=(value:number|undefined)=>Number.isSafeInteger(value)&&value!>=0?value!:null
  const requestClass=item.metadata.request_class
  if(requestClass)details.push(`类别：${requestClasses[requestClass]||'其他'}`)
  const error=item.metadata.error_category
  if(error)details.push(`错误：${errorNames[error]||safeErrors[error]||'其他错误'}`)
  const changedTools=count(item.metadata.changed_tool_results)
  const candidateTools=count(item.metadata.candidate_tool_results)
  if(changedTools!==null||candidateTools!==null)details.push(`工具结果：${format(changedTools)} / ${format(candidateTools)} 已压缩 / 候选`)
  const changedImages=count(item.metadata.changed_images)
  if(changedImages!==null)details.push(`已压缩图像：${format(changedImages)}`)
  for(const [source,reasons] of [['工具',item.metadata.tool_skip_reasons],['图像',item.metadata.image_skip_reasons]] as const){
    for(const [reason,value] of Object.entries(reasons||{})){
      const safeCount=count(value)
      if(skipReasonNames[reason]&&safeCount!==null&&safeCount>0)details.push(`${source}跳过：${skipReasonNames[reason]} × ${format(safeCount)}`)
    }
  }
  const fallback=item.metadata.compression_fallback
  if(fallback)details.push(`回退：${typeof fallback==='string'?fallbackNames[fallback]||'保留原内容':'保留原内容'}`)
  const costStatus=item.metadata.cost_estimate_status
  if(costStatus&&costStatus!=='estimated')details.push(`费用：${costStatusNames[costStatus]||'未估算'}`)
  if(!details.length)return <span>—</span>
  return <details className="event-details"><summary>查看</summary><ul>{details.map((detail,index)=><li key={`${index}-${detail}`}>{detail}</li>)}</ul></details>
}

function AnalyticsDashboard({data,hours}:{data:Analytics|null;hours:number}){
  const range=hours===24?'日':hours===168?'周':'月'
  const savingNames:Record<string,string>={input:'输入压缩',tool:'工具输出'}
  const outcomeNames:Record<string,string>={success:'成功',failure:'失败'}
  const modelRows=(data?.by_model||[]).map(item=>{
    const unavailable=Object.entries(item.cost_estimate_statuses||{}).filter(([status])=>status!=='estimated').map(([status,count])=>`${costStatusNames[status]||'金额未估'} ${format(count)} 次`).join(' · ')
    return {name:item.name,value:item.consumed_tokens,detail:`${format(item.requests)} 次 · ${item.usage_observations?`输入 ${format(item.actual_input_tokens)} / 输出 ${format(item.actual_output_tokens)}`:'实际用量未知'} / ${item.cache_usage_observations?`缓存 ${format(item.actual_cached_input_tokens)}`:'缓存用量未知'} · 节省 ${format(item.saved_tokens)}（估算）${unavailable?` · ${unavailable}`:''}`}
  })
  const modelSavingRows=(data?.by_model||[]).map(item=>({name:item.name,value:item.saved_tokens,detail:`${format(item.requests)} 次模型请求`}))
  const costRows=(data?.by_model||[]).flatMap(item=>Object.entries(item.estimated_cost_by_currency||{}).map(([currency,value])=>({name:`${item.name} · ${currency}`,value,display:formatMoney(value,currency),detail:`按提供商用量与价格表估算 · 输入费差额 ${formatMoney(item.estimated_saved_cost_by_currency?.[currency],currency)}`})))
  const currencies=[...new Set((data?.timeline||[]).flatMap(point=>Object.keys(point.estimated_cost_by_currency||{})))]
  const clientRows=(data?.by_client||[]).map(item=>({name:clientName(item.name),value:item.saved_tokens,detail:`消耗 ${format(item.consumed_tokens)}`}))
  const savingRows=(data?.savings||[]).map(item=>({name:savingNames[item.name]||item.name,value:item.saved_tokens}))
  const skipRows=(data?.skip_reasons||[]).map(item=>({name:`${item.source==='image'?'图像':'工具结果'} · ${skipReasonNames[item.reason]||'其他'}`,value:item.count}))
  const outcomeRows=(data?.outcomes||[]).map(item=>({name:outcomeNames[item.name]||item.name,value:item.count,tone:item.name==='failure'?'bad':undefined}))
  return <section aria-labelledby="analytics-title">
    <div className="section-head"><div><h2 id="analytics-title">趋势与分布</h2><p>{range}视图 · 金额按提供商用量和价格表估算{data?.price_catalog_status==='ready'||data?.price_catalog_status==='partial'?'':' · 未配置价格表'}</p></div></div>
    <div className="chart-grid">
      <article className="chart-panel trend-panel"><ChartTitle title="消耗 / 节省趋势（Token）" legend/><TrendChart points={data?.timeline||[]} granularity={data?.granularity||'hour'}/></article>
      {currencies.map(currency=><article className="chart-panel trend-panel" key={currency}><ChartTitle title={`费用趋势（${currency}）`} legend labels={['用量估价','输入费差额']}/><MoneyTrendChart points={data?.timeline||[]} granularity={data?.granularity||'hour'} currency={currency}/></article>)}
      <article className="chart-panel trend-panel"><ChartTitle title="请求与失败（次）" legend labels={['请求','失败']} legendType="request"/><RequestTrendChart points={data?.timeline||[]} granularity={data?.granularity||'hour'}/></article>
      <article className="chart-panel trend-panel"><ChartTitle title="供应商用量（Token）" legend labels={['输入','输出','缓存（输入子集）']} legendType="usage"/><UsageTrendChart points={data?.timeline||[]} granularity={data?.granularity||'hour'}/></article>
      <article className="chart-panel"><ChartTitle title="节省来源"/><HorizontalBars rows={savingRows}/></article>
      <article className="chart-panel"><ChartTitle title="模型节省（估算 Token）"/><HorizontalBars rows={modelSavingRows}/></article>
      <article className="chart-panel"><ChartTitle title="模型费用估算"/><HorizontalBars rows={costRows}/></article>
      <article className="chart-panel"><ChartTitle title="模型消耗"/><HorizontalBars rows={modelRows}/></article>
      <article className="chart-panel"><ChartTitle title="客户端节省"/><HorizontalBars rows={clientRows}/></article>
      <article className="chart-panel"><ChartTitle title="跳过原因"/><HorizontalBars rows={skipRows}/></article>
    <article className="chart-panel outcome-panel"><ChartTitle title="事件结果（模型与工具）"/><HorizontalBars rows={outcomeRows}/></article>
    </div>
  </section>
}

function ChartTitle({title,legend=false,labels=['实际用量','节省估算'],legendType='money'}:{title:string;legend?:boolean;labels?:string[];legendType?:'money'|'request'|'usage'}){
  const legendClasses={money:['legend-cost','legend-saving'],request:['legend-request','legend-failure'],usage:['legend-input','legend-output','legend-cache']}
  return <div className="chart-title"><h3>{title}</h3>{legend&&<div className="chart-legend">{labels.map((label,index)=><span key={label} className={legendClasses[legendType][index]}>{label}</span>)}</div>}</div>
}

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

type BarRow={name:string;value:number;display?:string;detail?:string;tone?:string}
function HorizontalBars({rows}:{rows:BarRow[]}){
  const maximum=Math.max(1,...rows.map(row=>row.value))
  if(!rows.length||rows.every(row=>row.value===0))return <div className="chart-empty compact-empty">暂无数据</div>
  return <div className="bar-chart">{rows.map(row=><div className="bar-row" key={row.name}>
    <div className="bar-label"><span>{row.name}</span><strong>{row.display||format(row.value)}</strong></div>
    <div className="bar-track"><span className={`bar-fill ${row.tone||''}`} style={{width:`${Math.max(row.value/maximum*100,row.value?2:0)}%`}}/></div>
    {row.detail&&<small>{row.detail}</small>}
  </div>)}</div>
}

function MoneyTrendChart({points,granularity,currency}:{points:TimelinePoint[];granularity:'hour'|'day';currency:string}){
  const width=760,height=250,left=62,right=14,top=16,bottom=34
  const plotWidth=width-left-right,plotHeight=height-top-bottom
  const value=(point:TimelinePoint,key:'estimated_cost_by_currency'|'estimated_saved_cost_by_currency')=>point[key]?.[currency]||0
  const maximum=Math.max(0.000001,...points.flatMap(point=>[value(point,'estimated_cost_by_currency'),value(point,'estimated_saved_cost_by_currency')]))
  const x=(index:number)=>left+(points.length<=1?plotWidth/2:index*plotWidth/(points.length-1))
  const y=(amount:number)=>top+plotHeight-(amount/maximum)*plotHeight
  const path=(key:'estimated_cost_by_currency'|'estimated_saved_cost_by_currency')=>points.map((point,index)=>`${index?'L':'M'} ${x(index)} ${y(value(point,key))}`).join(' ')
  const labels=points.map((point,index)=>({point,index})).filter(({index})=>index===0||index===points.length-1||index===Math.floor((points.length-1)/2))
  const hasData=points.some(point=>value(point,'estimated_cost_by_currency')||value(point,'estimated_saved_cost_by_currency'))
  return <div className="trend-wrap"><svg className="trend-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${currency} 费用估算趋势`}>
    {[0,.25,.5,.75,1].map(tick=><g key={tick}><line x1={left} x2={width-right} y1={y(maximum*tick)} y2={y(maximum*tick)} className="grid-line"/><text x={left-8} y={y(maximum*tick)+4} textAnchor="end">{Number(maximum*tick).toPrecision(2)}</text></g>)}
    {hasData&&<><path d={path('estimated_cost_by_currency')} className="trend-line cost"/><path d={path('estimated_saved_cost_by_currency')} className="trend-line saving"/>{points.map((point,index)=><React.Fragment key={point.start}><circle cx={x(index)} cy={y(value(point,'estimated_cost_by_currency'))} r="3" className="trend-dot cost"><title>{formatMoney(value(point,'estimated_cost_by_currency'),currency)} 用量估价</title></circle><circle cx={x(index)} cy={y(value(point,'estimated_saved_cost_by_currency'))} r="3" className="trend-dot saving"><title>{formatMoney(value(point,'estimated_saved_cost_by_currency'),currency)} 输入费差额</title></circle></React.Fragment>)}</>}
    {labels.map(({point,index})=><text key={point.start} x={x(index)} y={height-8} textAnchor={index===0?'start':index===points.length-1?'end':'middle'}>{new Date(point.start*1000).toLocaleString('zh-CN',granularity==='hour'?{hour:'2-digit'}:{month:'2-digit',day:'2-digit'})}</text>)}
  </svg>{!hasData&&<div className="chart-empty">暂无可估价数据</div>}</div>
}

function RequestTrendChart({points,granularity}:{points:TimelinePoint[];granularity:'hour'|'day'}){
  const width=760,height=250,left=48,right=14,top=16,bottom=34
  const plotWidth=width-left-right,plotHeight=height-top-bottom
  const maximum=Math.max(1,...points.flatMap(point=>[point.model_requests,point.failures]))
  const x=(index:number)=>left+(points.length<=1?plotWidth/2:index*plotWidth/(points.length-1))
  const y=(value:number)=>top+plotHeight-(value/maximum)*plotHeight
  const path=(key:'model_requests'|'failures')=>points.map((point,index)=>`${index?'L':'M'} ${x(index)} ${y(point[key])}`).join(' ')
  const labels=chartTimeLabels(points,granularity)
  const hasData=points.some(point=>point.model_requests>0||point.failures>0)
  return <div className="trend-wrap"><svg className="trend-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="模型请求与失败次数趋势">
    {[0,.25,.5,.75,1].map(tick=><g key={tick}><line x1={left} x2={width-right} y1={y(maximum*tick)} y2={y(maximum*tick)} className="grid-line"/><text x={left-8} y={y(maximum*tick)+4} textAnchor="end">{format(Math.round(maximum*tick))}</text></g>)}
    {hasData&&<><path d={path('model_requests')} className="trend-line request"/><path d={path('failures')} className="trend-line failure"/>{points.map((point,index)=><React.Fragment key={point.start}><circle cx={x(index)} cy={y(point.model_requests)} r="3" className="trend-dot request"><title>{format(point.model_requests)} 次请求</title></circle><circle cx={x(index)} cy={y(point.failures)} r="3" className="trend-dot failure"><title>{format(point.failures)} 次失败</title></circle></React.Fragment>)}</>}
    {labels.map(({point,index})=><text key={point.start} x={x(index)} y={height-8} textAnchor={index===0?'start':index===points.length-1?'end':'middle'}>{chartTimeLabel(point.start,granularity)}</text>)}
  </svg>{!hasData&&<div className="chart-empty">暂无请求数据</div>}</div>
}

function UsageTrendChart({points,granularity}:{points:TimelinePoint[];granularity:'hour'|'day'}){
  const width=760,height=250,left=48,right=14,top=16,bottom=34
  const plotWidth=width-left-right,plotHeight=height-top-bottom
  const series=[
    {key:'input',className:'input',label:'输入',values:points.map(point=>point.input_usage_observations>0?point.actual_input_tokens:null)},
    {key:'output',className:'output',label:'输出',values:points.map(point=>point.output_usage_observations>0?point.actual_output_tokens:null)},
    {key:'cache',className:'cache',label:'缓存输入',values:points.map(point=>point.cache_usage_observations>0?point.actual_cached_input_tokens:null)},
  ]
  const knownValues=series.flatMap(item=>item.values.filter((value):value is number=>value!==null))
  const maximum=Math.max(1,...knownValues)
  const x=(index:number)=>left+(points.length<=1?plotWidth/2:index*plotWidth/(points.length-1))
  const y=(value:number)=>top+plotHeight-(value/maximum)*plotHeight
  const path=(values:(number|null)[])=>{
    let connected=false
    return values.flatMap((value,index)=>{
      if(value===null){connected=false;return []}
      const command=connected?'L':'M'
      connected=true
      return [`${command} ${x(index)} ${y(value)}`]
    }).join(' ')
  }
  const labels=chartTimeLabels(points,granularity)
  const hasData=knownValues.length>0
  return <div className="trend-wrap"><svg className="trend-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="供应商实际输入、输出和缓存输入用量趋势">
    {[0,.25,.5,.75,1].map(tick=><g key={tick}><line x1={left} x2={width-right} y1={y(maximum*tick)} y2={y(maximum*tick)} className="grid-line"/><text x={left-8} y={y(maximum*tick)+4} textAnchor="end">{compact(Math.round(maximum*tick))}</text></g>)}
    {hasData&&series.map(item=><React.Fragment key={item.key}><path d={path(item.values)} className={`trend-line ${item.className}`}/>{item.values.map((value,index)=>value===null?null:<circle key={points[index].start} cx={x(index)} cy={y(value)} r="3" className={`trend-dot ${item.className}`}><title>{format(value)} Token {item.label}</title></circle>)}</React.Fragment>)}
    {labels.map(({point,index})=><text key={point.start} x={x(index)} y={height-8} textAnchor={index===0?'start':index===points.length-1?'end':'middle'}>{chartTimeLabel(point.start,granularity)}</text>)}
  </svg>{!hasData&&<div className="chart-empty">暂无实际用量</div>}</div>
}

function chartTimeLabels(points:TimelinePoint[],granularity:'hour'|'day'){
  return points.map((point,index)=>({point,index})).filter(({index})=>index===0||index===points.length-1||index===Math.floor((points.length-1)/2))
}
function chartTimeLabel(timestamp:number,granularity:'hour'|'day'){
  return new Date(timestamp*1000).toLocaleString('zh-CN',granularity==='hour'?{hour:'2-digit'}:{month:'2-digit',day:'2-digit'})
}

function StatusDot({ok}:{ok:boolean}){return <span className={ok?'dot on':'dot'} aria-label={ok?'已开启':'未开启'} />}
const stateLabels:Record<FeatureState,string>={off:'已关闭',waiting:'等待请求',active:'已生效',skipped:'已跳过',error:'异常'}
function Layer({name,state}:{name:string;state:FeatureState|null}){return <article className="layer"><StatusDot ok={state==='active'}/><h3>{name}</h3><span className="state">{state===null?'加载中':stateLabels[state]}</span></article>}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>)

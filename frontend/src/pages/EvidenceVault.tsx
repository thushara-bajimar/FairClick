import { Download, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Card, CategoryBadge, EmptyState, ErrorBanner, PageHeader, SeverityBadge, Spinner } from '../components/ui'
import { api } from '../lib/api'
import type { EvidenceRecord } from '../lib/api'
import { TASK_LABELS, dateTime, shortPath } from '../lib/format'
import { usePoll } from '../lib/usePoll'

function DetailDialog({ record, onClose }: { record: EvidenceRecord; onClose: () => void }) {
  const s = record.supporting as Record<string, unknown>
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-slate-900/50 p-4" role="dialog" aria-modal="true" aria-label="Evidence detail" onClick={onClose}>
      <div className="max-h-[92vh] w-full max-w-5xl overflow-y-auto rounded-xl bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
          <div className="flex items-center gap-2"><CategoryBadge name={record.pattern_name ?? record.category} /><SeverityBadge severity={record.severity ?? 'medium'} /></div>
          <button className="rounded p-1 text-slate-500 hover:bg-slate-100" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </div>
        <div className="grid gap-6 p-5 lg:grid-cols-3">
          <div className="lg:col-span-2">
            {record.screenshot_url
              ? <img src={record.screenshot_url} alt="Evidence screenshot; the offending element is outlined in red" className="w-full rounded-lg border border-slate-200" />
              : <p className="text-sm text-slate-500">No screenshot (capture disabled).</p>}
            <p className="mt-1 text-xs text-slate-500">Captured from the live browser; the related element is outlined in red.</p>
          </div>
          <dl className="space-y-3 text-sm">
            <div><dt className="text-xs font-semibold uppercase text-slate-500">Evidence</dt><dd className="text-slate-900">{record.evidence_text}</dd></div>
            <div><dt className="text-xs font-semibold uppercase text-slate-500">Explanation</dt><dd className="text-slate-700">{record.description.split(' Evidence:')[0]}</dd></div>
            <div><dt className="text-xs font-semibold uppercase text-slate-500">Location</dt><dd className="text-slate-700">{record.location}</dd></div>
            <div><dt className="text-xs font-semibold uppercase text-slate-500">URL</dt><dd className="break-all text-slate-700">{record.page_url}</dd></div>
            <div><dt className="text-xs font-semibold uppercase text-slate-500">Timestamp</dt><dd className="text-slate-700">{dateTime(record.timestamp)}</dd></div>
            <div><dt className="text-xs font-semibold uppercase text-slate-500">Confidence</dt><dd className="text-slate-700">{Math.round(record.confidence * 100)}% · {String(s.detection_method ?? '')}</dd></div>
            <div><dt className="text-xs font-semibold uppercase text-slate-500">Task</dt><dd><Link className="text-brand-700 hover:underline" to={`/app/sessions/${record.session_id}`}>{TASK_LABELS[record.task_type]} on {record.site_name}</Link></dd></div>
            <div><dt className="text-xs font-semibold uppercase text-slate-500">Recommended action</dt><dd className="text-slate-700">{record.recommendation}</dd></div>
            {Array.isArray(s.recent_agent_actions) && s.recent_agent_actions.length > 0 && (
              <div><dt className="text-xs font-semibold uppercase text-slate-500">Agent actions before capture</dt>
                <dd><ul className="list-disc pl-4 text-xs text-slate-600">{(s.recent_agent_actions as string[]).map((a, i) => <li key={i}>{a}</li>)}</ul></dd></div>
            )}
          </dl>
        </div>
      </div>
    </div>
  )
}

export default function EvidenceVault() {
  const [params, setParams] = useSearchParams()
  const category = params.get('category') ?? ''
  const site = params.get('site_id') ?? ''
  const taskId = params.get('task_id') ?? ''
  const { data: meta } = usePoll(api.meta, null)
  const { data: records, error, loading } = usePoll(() => api.evidence({ category, site_id: site, task_id: taskId }), 5000, [category, site, taskId])
  const [selected, setSelected] = useState<EvidenceRecord | null>(null)

  function setFilter(key: string, value: string) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value); else next.delete(key)
    setParams(next)
  }
  const exportQuery = taskId ? `&task_id=${encodeURIComponent(taskId)}` : ''

  return (
    <>
      <PageHeader title="Evidence vault" description="Every dark pattern the agent detected, captured from the live browser with screenshot, URL, timestamp and supporting text."
        action={
          <div className="flex gap-2">
            <a href={`/api/evidence/export?format=json${exportQuery}`} className="inline-flex items-center gap-2 rounded-lg bg-white px-3 py-2 text-sm font-medium text-slate-800 ring-1 ring-inset ring-slate-300 hover:bg-slate-50"><Download size={16} /> JSON</a>
            <a href={`/api/evidence/export?format=csv${exportQuery}`} className="inline-flex items-center gap-2 rounded-lg bg-white px-3 py-2 text-sm font-medium text-slate-800 ring-1 ring-inset ring-slate-300 hover:bg-slate-50"><Download size={16} /> CSV</a>
          </div>
        } />

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <label className="text-sm"><span className="block text-xs text-slate-500">Pattern category</span>
          <select value={category} onChange={(e) => setFilter('category', e.target.value)} className="mt-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm">
            <option value="">All categories</option>
            {meta?.taxonomy.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select></label>
        <label className="text-sm"><span className="block text-xs text-slate-500">Website</span>
          <select value={site} onChange={(e) => setFilter('site_id', e.target.value)} className="mt-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm">
            <option value="">All websites</option>
            {meta?.sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select></label>
        {taskId && <button className="rounded-lg bg-brand-50 px-3 py-2 text-xs font-medium text-brand-700" onClick={() => setFilter('task_id', '')}>Filtered to one task · clear</button>}
        <span className="ml-auto text-sm text-slate-500">{records?.length ?? 0} records</span>
      </div>

      {error && <ErrorBanner message={error} />}
      {loading && !records ? <Spinner /> : records && records.length === 0 ? (
        <Card><EmptyState title="No evidence yet" body="Evidence appears here as soon as an agent session detects a dark pattern." /></Card>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {records?.map((r) => (
            <li key={r.id}>
              <button className="w-full overflow-hidden rounded-xl border border-slate-200 bg-white text-left shadow-sm transition hover:border-brand-500" onClick={() => setSelected(r)}>
                {r.screenshot_url ? <img src={r.screenshot_url} alt={`Evidence of ${r.pattern_name}`} className="h-40 w-full object-cover object-top" loading="lazy" /> : <div className="h-40 bg-slate-100" />}
                <div className="space-y-1.5 p-4">
                  <div className="flex items-center gap-2"><CategoryBadge name={r.pattern_name ?? r.category} /><SeverityBadge severity={r.severity ?? 'medium'} /><span className="ml-auto text-xs text-slate-500">{Math.round(r.confidence * 100)}%</span></div>
                  <p className="line-clamp-2 text-sm text-slate-800">{r.evidence_text}</p>
                  <p className="text-xs text-slate-500">{r.site_name} · {shortPath(r.page_url).split('?')[0]} · {dateTime(r.timestamp)}</p>
                  <p className="text-xs text-slate-500">Task: {TASK_LABELS[r.task_type]}</p>
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}
      {selected && <DetailDialog record={selected} onClose={() => setSelected(null)} />}
    </>
  )
}

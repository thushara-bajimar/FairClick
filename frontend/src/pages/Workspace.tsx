import { AlertTriangle, Check, CheckCircle2, ExternalLink, FileText, Hand, Octagon, RotateCcw, ShieldAlert, X } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Button, Card, CardHeader, CategoryBadge, EmptyState, ErrorBanner, PageHeader, SeverityBadge, Spinner, StatusPill } from '../components/ui'
import { api } from '../lib/api'
import type { AgentAction, Approval, SessionDetail } from '../lib/api'
import { ACTIVE_STATUSES, SITE_LABELS, TASK_LABELS, dateTime, shortPath, timeAgo } from '../lib/format'
import { usePoll } from '../lib/usePoll'

const AGENT_STYLES: Record<string, string> = {
  navigator: 'bg-sky-50 text-sky-700', detector: 'bg-violet-50 text-violet-700', reasoner: 'bg-indigo-50 text-indigo-700',
  safety: 'bg-amber-50 text-amber-800', evidence: 'bg-emerald-50 text-emerald-700', human: 'bg-brand-50 text-brand-700',
  orchestrator: 'bg-slate-100 text-slate-700',
}
const AGENT_NAMES: Record<string, string> = {
  navigator: 'Navigation', detector: 'Detection', reasoner: 'Reasoning', safety: 'Safety', evidence: 'Evidence', human: 'You', orchestrator: 'Orchestrator',
}

export function WorkspaceIndex() {
  const { data: tasks, error } = usePoll(() => api.tasks(100), 3000)
  return (
    <>
      <PageHeader title="Agent workspace" description="Open a session to follow the agent live, review approvals and inspect its decisions." />
      {error && <ErrorBanner message={error} />}
      <Card>
        {tasks && tasks.filter((t) => t.latest_session_id).length === 0 ? (
          <EmptyState title="No sessions yet" action={<Link to="/app/new" className="rounded-lg bg-brand-700 px-4 py-2 text-sm font-medium text-white">Start new task</Link>} />
        ) : (
          <ul className="divide-y divide-slate-100">
            {tasks?.filter((t) => t.latest_session_id).map((t) => (
              <li key={t.id}>
                <Link to={`/app/sessions/${t.latest_session_id}`} className="flex flex-wrap items-center gap-3 px-5 py-3 hover:bg-slate-50">
                  <span className="min-w-48 flex-1 text-sm font-medium text-slate-900">{t.task_title} <span className="font-normal text-slate-500">on {t.site_name}</span></span>
                  {t.source === 'benchmark' && <span className="text-xs text-slate-500">benchmark</span>}
                  <span className="text-xs text-slate-500">{t.detection_count} patterns</span>
                  <StatusPill status={t.status} />
                  <span className="w-20 text-right text-xs text-slate-500">{timeAgo(t.created_at)}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  )
}

function ApprovalPanel({ approval, onDecided }: { approval: Approval; onDecided: () => void }) {
  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function decide(approved: boolean) {
    setBusy(true)
    setError(null)
    try {
      await api.decide(approval.id, approved, comment)
      onDecided()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }
  const hidden = approval.data.hidden_fields_set_by_website ?? []
  return (
    <Card className="mb-6 border-amber-300 ring-2 ring-amber-200">
      <div className="flex items-center gap-2 border-b border-amber-200 bg-amber-50 px-5 py-3 text-amber-900">
        <Hand size={18} /><h2 className="text-sm font-semibold">Your approval is required</h2>
        <span className="ml-auto text-xs">The agent is paused and will not continue until you decide.</span>
      </div>
      <div className="grid gap-6 p-5 lg:grid-cols-2">
        <div className="space-y-4 text-sm">
          <section><h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">1. What will happen</h3><p className="mt-1 font-medium text-slate-900">{approval.action_summary}</p></section>
          <section><h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">2. Why it is needed</h3><p className="mt-1 text-slate-700">{approval.reason}</p></section>
          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">3. Information that will be submitted</h3>
            {approval.data.fields.length === 0 ? <p className="mt-1 text-slate-600">No form fields - only the button press.</p> : (
              <dl className="mt-1 divide-y divide-slate-100 rounded-lg border border-slate-200">
                {approval.data.fields.map((f, i) => (
                  <div key={i} className="grid grid-cols-5 gap-2 px-3 py-1.5"><dt className="col-span-2 text-slate-500">{f.label}</dt><dd className="col-span-3 break-words font-medium text-slate-900">{f.value || <em className="font-normal text-slate-400">empty</em>}</dd></div>
                ))}
              </dl>
            )}
            {hidden.length > 0 && (
              <p className="mt-2 text-xs text-slate-500">Hidden values set by the website: {hidden.map((h) => `${h.name}=${h.value}`).join(', ')}</p>
            )}
          </section>
          <section><h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">4. Possible consequences</h3><p className="mt-1 text-slate-700">{approval.consequences}</p></section>
          <label className="block"><span className="text-xs text-slate-500">Note (optional, stored with your decision)</span>
            <input value={comment} maxLength={500} onChange={(e) => setComment(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" /></label>
          {error && <ErrorBanner message={error} />}
          <div className="flex flex-wrap gap-3">
            <Button onClick={() => decide(true)} disabled={busy}><Check size={16} /> Approve and submit</Button>
            <Button variant="danger" onClick={() => decide(false)} disabled={busy}><X size={16} /> Reject</Button>
          </div>
        </div>
        {approval.screenshot_url && (
          <figure>
            <img src={approval.screenshot_url} alt="The page as the agent sees it right before the action" className="w-full rounded-lg border border-slate-200" />
            <figcaption className="mt-1 text-xs text-slate-500">Page right before the action · {shortPath(approval.page_url)}</figcaption>
          </figure>
        )}
      </div>
    </Card>
  )
}

function actionText(a: AgentAction): string {
  if (a.action_type === 'observe') return `Observed ${shortPath(a.page_url)} - ${a.detail}`
  if (a.action_type === 'decide') return `Decided: ${a.outcome} ${a.target ?? ''} - ${a.detail ?? ''}`
  if (a.action_type === 'review') return `${a.outcome === 'blocked' ? 'Blocked' : 'Allowed'} ${a.target ?? ''} (${a.risk}) - ${a.detail ?? ''}`
  if (a.action_type === 'detected') return `${a.target}: ${a.detail ?? ''}`
  return `${a.action_type.replace(/_/g, ' ')} ${a.target ?? ''}${a.detail ? ` - ${a.detail}` : ''}`
}

function Timeline({ actions }: { actions: AgentAction[] }) {
  const [showAll, setShowAll] = useState(false)
  const visible = showAll ? actions : actions.filter((a) => a.action_type !== 'observe' && a.action_type !== 'review')
  return (
    <Card>
      <CardHeader title="Session activity" subtitle={`${actions.length} logged events from all agents`}
        action={<button className="text-xs font-medium text-brand-700" onClick={() => setShowAll(!showAll)}>{showAll ? 'Key events only' : 'Show every event'}</button>} />
      <ol className="max-h-[32rem] divide-y divide-slate-100 overflow-y-auto">
        {[...visible].reverse().map((a) => (
          <li key={a.id} className="flex gap-3 px-5 py-2 text-sm">
            <span className="w-8 shrink-0 pt-0.5 text-right text-xs tabular-nums text-slate-400">#{a.step}</span>
            <span className={`h-fit shrink-0 rounded px-1.5 py-0.5 text-xs font-medium ${AGENT_STYLES[a.agent] ?? AGENT_STYLES.orchestrator}`}>{AGENT_NAMES[a.agent] ?? a.agent}</span>
            <span className={`min-w-0 break-words ${a.outcome === 'blocked' || a.outcome === 'ignored' ? 'text-rose-700' : 'text-slate-700'}`}>{actionText(a)}</span>
          </li>
        ))}
      </ol>
    </Card>
  )
}

export default function Workspace() {
  const { sessionId = '' } = useParams()
  const navigate = useNavigate()
  const [interval, setIntervalMs] = useState<number | null>(1200)
  const { data, error, refresh } = usePoll<SessionDetail>(async () => {
    const d = await api.session(sessionId)
    setIntervalMs(ACTIVE_STATUSES.has(d.session.status) ? 1200 : null)
    return d
  }, interval, [sessionId])

  if (error && !data) return <ErrorBanner message={error} />
  if (!data) return <Spinner />
  const { session, task, detections, approvals, incidents, result, actions } = data
  const active = ACTIVE_STATUSES.has(session.status)
  const pending = approvals.find((a) => a.status === 'pending')
  const pages = actions.filter((a) => a.action_type === 'observe').map((a) => shortPath(a.page_url).split('?')[0])
  const journey = pages.filter((p, i) => p !== pages[i - 1])
  const browserActions = actions.filter((a) => a.agent === 'navigator' && a.action_type !== 'observe' && a.outcome?.startsWith('ok'))

  return (
    <>
      <PageHeader
        title={`${TASK_LABELS[task.task_type]} on ${SITE_LABELS[task.site_id]}`}
        description={`Session ${session.id} · started ${dateTime(session.started_at)} · mode: ${session.mode}`}
        action={
          <div className="flex items-center gap-3">
            <StatusPill status={session.status} />
            {active && <Button variant="secondary" onClick={() => api.stopSession(session.id).then(refresh)}><Octagon size={16} /> Stop agent</Button>}
            {!active && <Button variant="secondary" onClick={() => api.rerunTask(task.id).then((r) => navigate(`/app/sessions/${r.session_id}`))}><RotateCcw size={16} /> Run again</Button>}
          </div>
        } />

      {pending && <ApprovalPanel approval={pending} onDecided={refresh} />}

      {result && (
        <Card className={`mb-6 p-5 ${result.success ? 'border-emerald-200 bg-emerald-50/40' : 'border-slate-200'}`}>
          <div className="flex items-start gap-3">
            {result.success ? <CheckCircle2 className="mt-0.5 text-emerald-600" size={20} /> : <AlertTriangle className="mt-0.5 text-amber-600" size={20} />}
            <div className="min-w-0 flex-1">
              <p className="font-semibold text-slate-900">{result.summary}</p>
              <p className="mt-1 text-sm text-slate-600">
                {result.interactions} browser interactions · {result.pages_visited} pages · {result.duration_seconds}s · {result.patterns_detected} dark patterns · {result.approvals_requested} approval request(s)
              </p>
              {result.prepared_document && (
                <details className="mt-3">
                  <summary className="inline-flex cursor-pointer items-center gap-1 text-sm font-medium text-brand-700"><FileText size={16} /> Prepared summary document</summary>
                  <pre className="mt-2 whitespace-pre-wrap rounded-lg bg-white p-4 text-xs text-slate-800 ring-1 ring-slate-200">{result.prepared_document}</pre>
                </details>
              )}
            </div>
          </div>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader title="Live browser view" subtitle={session.current_url ? shortPath(session.current_url) : 'Waiting for the browser…'}
            action={session.current_url && <a className="inline-flex items-center gap-1 text-xs font-medium text-brand-700" href={session.current_url} target="_blank" rel="noreferrer">Open page <ExternalLink size={12} /></a>} />
          <div className="p-4">
            {session.live_screenshot_url
              ? <img src={`${session.live_screenshot_url}?step=${session.current_step}`} alt="Current page in the agent's browser" className="w-full rounded-lg border border-slate-200" />
              : <div className="grid h-64 place-items-center text-sm text-slate-500">{active ? <Spinner /> : 'No screenshot'}</div>}
            <p className="mt-2 text-xs text-slate-500">Step {session.current_step} · {session.status_detail}</p>
          </div>
        </Card>

        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader title="Navigation progress" subtitle={`${journey.length} screens · ${browserActions.length} actions performed`} />
            <ol className="space-y-1 px-5 py-3 text-sm">
              {journey.map((p, i) => (
                <li key={i} className="flex items-center gap-2"><span className="grid h-5 w-5 place-items-center rounded-full bg-slate-100 text-xs text-slate-600">{i + 1}</span><span className="truncate text-slate-700">{p}</span></li>
              ))}
              {journey.length === 0 && <li className="text-slate-500">Not started yet.</li>}
            </ol>
          </Card>
          <Card>
            <CardHeader title="Security incidents" subtitle="Website content treated as untrusted input" />
            {incidents.length === 0 ? <p className="px-5 py-3 text-sm text-slate-500">None detected.</p> : (
              <ul className="divide-y divide-slate-100">
                {incidents.map((i) => (
                  <li key={i.id} className="px-5 py-3 text-sm">
                    <p className="flex items-center gap-1 font-medium text-rose-700"><ShieldAlert size={14} /> Prompt injection ignored</p>
                    <p className="mt-1 italic text-slate-700">"{i.evidence_text}"</p>
                    <p className="mt-1 text-xs text-slate-500">{shortPath(i.page_url)} · {i.action_taken}</p>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>

      <Card className="mt-6">
        <CardHeader title="Detected dark patterns" subtitle={`${detections.length} findings with screenshot evidence`}
          action={<Link className="text-xs font-medium text-brand-700" to={`/app/evidence?task_id=${task.id}`}>Open in evidence vault</Link>} />
        {detections.length === 0 ? <p className="px-5 py-4 text-sm text-slate-500">{active ? 'Inspecting pages…' : 'No dark patterns detected.'}</p> : (
          <ul className="grid gap-4 p-5 md:grid-cols-2 xl:grid-cols-3">
            {detections.map((d) => (
              <li key={d.id} className="overflow-hidden rounded-lg border border-slate-200">
                {d.screenshot_url && <a href={d.screenshot_url} target="_blank" rel="noreferrer"><img src={d.screenshot_url} alt={`Evidence: ${d.pattern_name}`} className="h-36 w-full object-cover object-top" loading="lazy" /></a>}
                <div className="space-y-1.5 p-3 text-sm">
                  <div className="flex flex-wrap items-center gap-2"><CategoryBadge name={d.pattern_name} /><SeverityBadge severity={d.severity} /><span className="ml-auto text-xs text-slate-500">{Math.round(d.confidence * 100)}% conf.</span></div>
                  <p className="text-slate-800">{d.evidence_text}</p>
                  <p className="text-xs text-slate-500">{d.location} · {shortPath(d.page_url)}</p>
                  <p className="text-xs text-brand-700">{d.recommendation}</p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <div className="mt-6"><Timeline actions={actions} /></div>
    </>
  )
}

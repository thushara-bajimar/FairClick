import { CheckCircle2, Clock, ListChecks, ShieldAlert, Target } from 'lucide-react'
import { Link } from 'react-router-dom'
import { HBarChart } from '../components/charts'
import { Card, CardHeader, EmptyState, ErrorBanner, PageHeader, StatCard, StatusPill } from '../components/ui'
import { api } from '../lib/api'
import { SITE_LABELS, TASK_LABELS, timeAgo } from '../lib/format'
import { usePoll } from '../lib/usePoll'

const ACTIVITY_LABELS: Record<string, string> = {
  start: 'Session started', finish: 'Session finished', detected: 'Dark pattern detected',
  approval_requested: 'Approval requested', approval_approved: 'You approved', approval_rejected: 'You rejected',
  prompt_injection_ignored: 'Prompt injection ignored',
}

export default function Dashboard() {
  const { data: s, error } = usePoll(api.summary, 4000)
  const { data: tasks } = usePoll(() => api.tasks(8), 4000)

  return (
    <>
      <PageHeader title="Dashboard" description="Live overview of your agent sessions, detected dark patterns and decisions waiting for you."
        action={<Link to="/app/new" className="rounded-lg bg-brand-700 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600">Start new task</Link>} />
      {error && <ErrorBanner message={`Could not reach the FairClick backend: ${error}`} />}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <StatCard label="Total tasks" value={s?.total_tasks ?? '–'} icon={<ListChecks size={18} />} />
        <StatCard label="Completed" value={s?.completed_tasks ?? '–'} icon={<CheckCircle2 size={18} />} />
        <StatCard label="Dark patterns" value={s?.patterns_detected ?? '–'} hint={s ? `${s.evidence_records} evidence records` : undefined} icon={<ShieldAlert size={18} />} />
        <StatCard label="Pending approvals" value={s?.approvals.pending ?? '–'} icon={<Clock size={18} />} />
        <StatCard label="Success rate" value={s?.success_rate != null ? `${s.success_rate}%` : '–'}
          hint={s ? `${s.successful_runs} of ${s.attempted_runs} finished runs` : undefined} icon={<Target size={18} />} />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-5">
        <Card className="min-w-0 lg:col-span-3">
          <CardHeader title="Recent tasks" action={<Link className="text-xs font-medium text-brand-700" to="/app/workspace">All sessions</Link>} />
          {tasks && tasks.length === 0 ? (
            <EmptyState title="No tasks yet" body="Start your first task to see the agent at work."
              action={<Link to="/app/new" className="rounded-lg bg-brand-700 px-4 py-2 text-sm font-medium text-white">Start new task</Link>} />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
                  <tr><th className="px-5 py-2 font-medium">Task</th><th className="px-2 py-2 font-medium">Website</th><th className="px-2 py-2 font-medium">Status</th><th className="px-2 py-2 text-right font-medium">Patterns</th><th className="px-5 py-2 text-right font-medium">Created</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {tasks?.map((t) => (
                    <tr key={t.id} className="hover:bg-slate-50">
                      <td className="px-5 py-2.5 font-medium">
                        {t.latest_session_id ? <Link className="text-slate-900 hover:text-brand-700" to={`/app/sessions/${t.latest_session_id}`}>{t.task_title}</Link> : t.task_title}
                      </td>
                      <td className="px-2 py-2.5 text-slate-600">{t.site_name}</td>
                      <td className="px-2 py-2.5"><StatusPill status={t.status} /></td>
                      <td className="px-2 py-2.5 text-right tabular-nums">{t.detection_count}</td>
                      <td className="px-5 py-2.5 text-right text-slate-500">{timeAgo(t.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card className="min-w-0 lg:col-span-2">
          <CardHeader title="Recent activity" subtitle="Key events across all sessions" />
          <ul className="max-h-96 divide-y divide-slate-100 overflow-y-auto">
            {s?.recent_activity.length === 0 && <li className="px-5 py-6 text-sm text-slate-500">No activity yet.</li>}
            {s?.recent_activity.map((a, i) => (
              <li key={i} className="px-5 py-2.5 text-sm">
                <Link to={`/app/sessions/${a.session_id}`} className="block hover:text-brand-700">
                  <span className="font-medium">{ACTIVITY_LABELS[a.action_type] ?? a.action_type}</span>
                  {a.target && <span className="text-slate-600">: {a.target}</span>}
                  <span className="mt-0.5 block text-xs text-slate-500">{TASK_LABELS[a.task_type]} · {SITE_LABELS[a.site_id]} · {timeAgo(a.timestamp)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader title="Dark patterns detected by category" subtitle="All sessions, from the detection agent's evidence records" />
        <div className="p-4">
          {s && s.by_category.length > 0
            ? <HBarChart data={s.by_category.map((c) => ({ name: c.name, value: c.count }))} label="Detections" />
            : <EmptyState title="No detections yet" />}
        </div>
      </Card>
    </>
  )
}

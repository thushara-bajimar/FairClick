import { Activity, CheckCircle2, Clock, Hand, MousePointerClick, ShieldAlert } from 'lucide-react'
import { CompareChart, HBarChart } from '../components/charts'
import { Card, CardHeader, EmptyState, ErrorBanner, PageHeader, StatCard } from '../components/ui'
import { api } from '../lib/api'
import { SITE_LABELS, TASK_LABELS, dateTime } from '../lib/format'
import { usePoll } from '../lib/usePoll'

const SCENARIO_LABELS: Record<string, string> = {
  'cancel-streamplus': 'Cancel · StreamPlus', 'cancel-fitlife': 'Cancel · FitLife', 'tracking-cookieworld': 'Tracking · CookieWorld',
  'tracking-shopease': 'Tracking · ShopEase', 'refund-shopease': 'Refund · ShopEase', 'dispute-fitlife': 'Dispute · FitLife',
  'claim-travelquick': 'Claim · TravelQuick',
}

export default function Reports() {
  const { data: s, error } = usePoll(api.summary, 5000)
  const { data: bench } = usePoll(api.benchmark, null)
  const b = bench?.summary

  return (
    <>
      <PageHeader title="Reports & analytics" description="Measured results from your sessions (live database) and from the reproducible benchmark run." />
      {error && <ErrorBanner message={error} />}

      <h2 className="mb-3 text-sm font-semibold text-slate-900">Your sessions</h2>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-6">
        <StatCard label="Tasks completed" value={s?.completed_tasks ?? '–'} icon={<CheckCircle2 size={18} />} />
        <StatCard label="Success rate" value={s?.success_rate != null ? `${s.success_rate}%` : '–'} hint="completed / finished runs" icon={<Activity size={18} />} />
        <StatCard label="Patterns detected" value={s?.patterns_detected ?? '–'} icon={<ShieldAlert size={18} />} />
        <StatCard label="Avg. completion" value={s?.average_completion_seconds != null ? `${s.average_completion_seconds}s` : '–'} hint="successful runs" icon={<Clock size={18} />} />
        <StatCard label="Interactions" value={s?.total_interactions ?? '–'} hint={s?.average_interactions != null ? `${s.average_interactions} per successful run` : undefined} icon={<MousePointerClick size={18} />} />
        <StatCard label="Human approvals" value={s?.approvals.total ?? '–'} hint={s ? `${s.approvals.approved} approved · ${s.approvals.rejected} rejected` : undefined} icon={<Hand size={18} />} />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Detections by category" />
          <div className="p-4">{s && s.by_category.length ? <HBarChart data={s.by_category.map((c) => ({ name: c.name, value: c.count }))} label="Detections" /> : <EmptyState title="No data yet" />}</div>
        </Card>
        <Card>
          <CardHeader title="Detections by website" />
          <div className="p-4">{s && s.by_site.length ? <HBarChart data={s.by_site.map((c) => ({ name: c.name, value: c.count }))} label="Detections" /> : <EmptyState title="No data yet" />}</div>
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader title="Results by task type" subtitle="From the task_results table" />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-slate-500"><tr><th className="px-5 py-2">Task</th><th className="px-2 py-2 text-right">Runs</th><th className="px-2 py-2 text-right">Succeeded</th><th className="px-2 py-2 text-right">Success rate</th><th className="px-5 py-2 text-right">Avg. duration</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {s?.by_task.map((t) => (
                <tr key={t.task_type}><td className="px-5 py-2 font-medium">{t.title}</td><td className="px-2 py-2 text-right tabular-nums">{t.attempted}</td><td className="px-2 py-2 text-right tabular-nums">{t.succeeded}</td>
                  <td className="px-2 py-2 text-right tabular-nums">{t.attempted ? Math.round((100 * t.succeeded) / t.attempted) : 0}%</td><td className="px-5 py-2 text-right tabular-nums">{t.avg_duration?.toFixed(1)}s</td></tr>
              ))}
              {s?.by_task.length === 0 && <tr><td colSpan={5} className="px-5 py-4 text-slate-500">No finished runs yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>

      <h2 className="mb-3 mt-10 text-sm font-semibold text-slate-900">Benchmark: FairClick agent vs. manual workflow</h2>
      {!bench?.available || !b ? (
        <Card><EmptyState title="No benchmark results yet" body="Run `python -m benchmark.run_benchmark` from the backend folder to produce reproducible measurements." /></Card>
      ) : (
        <>
          <p className="mb-4 text-sm text-slate-600">Run {dateTime(b.generated_at)} · {b.scenarios} scenarios × {b.repeats} repeats = {b.agent_runs} agent runs.</p>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label="Agent success rate" value={`${b.agent_success_rate}%`} hint={`${b.agent_runs} measured runs`} />
            <StatCard label="Detection rate" value={b.detection_rate != null ? `${b.detection_rate}%` : '–'} hint={`${b.true_positives} TP · ${b.false_negatives} FN vs ground truth`} />
            <StatCard label="Detection precision" value={b.detection_precision != null ? `${b.detection_precision}%` : '–'} hint={`${b.false_positives} false positives`} />
            <StatCard label="Approvals requested" value={b.total_approvals_requested} hint={`${b.total_evidence} evidence records · ${b.total_security_incidents} injection incidents`} />
          </div>
          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader title="Interactions per task" subtitle="Agent: measured mean · Manual: counted by executing the scripted human path" />
              <div className="p-4">
                <CompareChart agentLabel="FairClick agent (measured)" manualLabel="Manual (scripted path)"
                  data={(bench.scenarios ?? []).map((sc) => ({ name: SCENARIO_LABELS[sc.scenario] ?? sc.scenario, agent: sc.agent_summary.avg_interactions, manual: sc.manual.interactions }))} />
              </div>
            </Card>
            <Card>
              <CardHeader title="Time per task (seconds)" subtitle="Agent: measured wall-clock · Manual: KLM estimate, not timed with people" />
              <div className="p-4">
                <CompareChart agentLabel="FairClick agent (measured)" manualLabel="Manual (KLM estimate)" unit="s"
                  data={(bench.scenarios ?? []).map((sc) => ({ name: SCENARIO_LABELS[sc.scenario] ?? sc.scenario, agent: sc.agent_summary.avg_duration_s, manual: sc.manual.estimated_time_s }))} />
              </div>
            </Card>
          </div>
          <Card className="mt-6">
            <CardHeader title="Per-scenario results" />
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
                  <tr><th className="px-5 py-2">Scenario</th><th className="px-2 py-2 text-right">Agent success</th><th className="px-2 py-2 text-right">Agent interactions</th><th className="px-2 py-2 text-right">Agent time</th><th className="px-2 py-2 text-right">Patterns</th><th className="px-2 py-2 text-right">Manual interactions</th><th className="px-2 py-2 text-right">Manual time (est.)</th><th className="px-5 py-2 text-right">Obstacles</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {bench.scenarios?.map((sc) => (
                    <tr key={sc.scenario}>
                      <td className="px-5 py-2 font-medium">{TASK_LABELS[sc.task_type]} · {SITE_LABELS[sc.site_id]}</td>
                      <td className="px-2 py-2 text-right tabular-nums">{sc.agent_summary.success_rate}%</td>
                      <td className="px-2 py-2 text-right tabular-nums">{sc.agent_summary.avg_interactions}</td>
                      <td className="px-2 py-2 text-right tabular-nums">{sc.agent_summary.avg_duration_s}s</td>
                      <td className="px-2 py-2 text-right tabular-nums">{sc.agent_summary.avg_detections}</td>
                      <td className="px-2 py-2 text-right tabular-nums">{sc.manual.interactions}</td>
                      <td className="px-2 py-2 text-right tabular-nums">{sc.manual.estimated_time_s}s</td>
                      <td className="px-5 py-2 text-right tabular-nums">{sc.manual.obstacles_encountered}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ul className="list-disc space-y-1 border-t border-slate-100 px-9 py-4 text-xs text-slate-500">
              {b.notes.map((n) => <li key={n}>{n}</li>)}
            </ul>
          </Card>
        </>
      )}
    </>
  )
}

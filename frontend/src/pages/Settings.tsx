import { useEffect, useState } from 'react'
import { Button, Card, CardHeader, ErrorBanner, PageHeader, Spinner } from '../components/ui'
import { api } from '../lib/api'
import type { SettingsResponse } from '../lib/api'

type Prefs = SettingsResponse['preferences']

function Toggle({ label, description, checked, onChange }: { label: string; description: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex cursor-pointer items-start justify-between gap-4 px-5 py-4">
      <span><span className="block text-sm font-medium text-slate-900">{label}</span><span className="block text-xs text-slate-500">{description}</span></span>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="mt-1 h-5 w-5 accent-teal-700" />
    </label>
  )
}

export default function SettingsPage() {
  const [data, setData] = useState<SettingsResponse | null>(null)
  const [prefs, setPrefs] = useState<Prefs | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.settings().then((d) => { setData(d); setPrefs(d.preferences) }).catch((e) => setError(String(e)))
  }, [])

  async function save() {
    if (!prefs) return
    setError(null)
    try {
      const d = await api.saveSettings(prefs)
      setData(d)
      setPrefs(d.preferences)
      setMessage('Settings saved.')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  async function clearHistory() {
    if (!window.confirm('Delete all finished tasks, their evidence records and screenshots? This cannot be undone.')) return
    try {
      const r = await api.clearHistory()
      setMessage(`Deleted ${r.deleted_tasks} finished task(s) and their evidence.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  if (!prefs || !data) return error ? <ErrorBanner message={error} /> : <Spinner />
  const set = <K extends keyof Prefs>(key: K, value: Prefs[K]) => { setPrefs({ ...prefs, [key]: value }); setMessage(null) }

  return (
    <>
      <PageHeader title="Settings" description="Preferences are stored locally in FairClick's SQLite database." />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="User preferences" />
          <div className="space-y-4 px-5 py-4">
            <label className="block text-sm"><span className="font-medium text-slate-900">Display name</span>
              <input value={prefs.display_name} maxLength={60} onChange={(e) => set('display_name', e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" /></label>
            <label className="block text-sm"><span className="font-medium text-slate-900">Delay between agent steps (ms)</span>
              <input type="number" min={0} max={3000} value={prefs.step_delay_ms} onChange={(e) => set('step_delay_ms', Number(e.target.value))} className="mt-1 w-40 rounded-lg border border-slate-300 px-3 py-2" />
              <span className="mt-1 block text-xs text-slate-500">Slow the agent down for demonstrations.</span></label>
          </div>
        </Card>

        <Card>
          <CardHeader title="Approval preferences" subtitle="Submitting refunds, claims, disputes and cancellations always requires your approval." />
          <div className="divide-y divide-slate-100">
            <Toggle label="Require approval for cookie/consent changes" description="Saving privacy choices is reversible. Leave on to approve it like any other submission."
              checked={prefs.require_approval_for_consent} onChange={(v) => set('require_approval_for_consent', v)} />
            <div className="px-5 py-4 text-xs text-slate-500">Purchases, upgrades and retention offers are always blocked and cannot be enabled. Approval requests expire after {Math.round(data.server.approval_timeout_s / 60)} minutes and are then treated as rejected.</div>
          </div>
        </Card>

        <Card>
          <CardHeader title="Privacy settings" />
          <div className="divide-y divide-slate-100">
            <Toggle label="Capture evidence screenshots" description="Screenshots are stored only on this machine." checked={prefs.capture_screenshots} onChange={(v) => set('capture_screenshots', v)} />
            <Toggle label="Store page text excerpts with evidence" description="Keeps up to 1,500 characters of visible page text next to each finding." checked={prefs.store_page_text} onChange={(v) => set('store_page_text', v)} />
            <Toggle label="Run browser headless" description="Turn off to watch the Chromium window (also requires FAIRCLICK_HEADLESS=false on the server)." checked={prefs.headless_browser} onChange={(v) => set('headless_browser', v)} />
          </div>
        </Card>

        <Card>
          <CardHeader title="Session history" />
          <div className="space-y-4 px-5 py-4 text-sm">
            <label className="block"><span className="font-medium text-slate-900">Keep history for (days)</span>
              <input type="number" min={1} max={3650} value={prefs.retain_history_days} onChange={(e) => set('retain_history_days', Number(e.target.value))} className="mt-1 w-40 rounded-lg border border-slate-300 px-3 py-2" />
              <span className="mt-1 block text-xs text-slate-500">Recorded preference; automatic deletion is not implemented in this MVP. Use the button below to clear history.</span></label>
            <Button variant="danger" onClick={clearHistory}>Clear finished session history</Button>
          </div>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader title="Agent environment" subtitle="Read-only, configured on the server through environment variables" />
          <dl className="grid gap-4 px-5 py-4 text-sm sm:grid-cols-3">
            <div><dt className="text-xs text-slate-500">Agent mode</dt><dd className="font-medium">{data.server.agent_mode}</dd></div>
            <div><dt className="text-xs text-slate-500">LLM provider</dt><dd className="font-medium">{data.server.llm_provider} {data.server.llm_key_configured ? '(key configured)' : '(no key - demo mode)'}</dd></div>
            <div><dt className="text-xs text-slate-500">Navigation allowlist</dt><dd className="font-medium break-all">{data.server.allowed_navigation}</dd></div>
          </dl>
        </Card>
      </div>
      <div className="mt-6 flex items-center gap-4">
        <Button onClick={save}>Save settings</Button>
        {message && <span className="text-sm text-emerald-700">{message}</span>}
        {error && <ErrorBanner message={error} />}
      </div>
    </>
  )
}

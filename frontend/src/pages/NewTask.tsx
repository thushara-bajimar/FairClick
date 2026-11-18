import { Ban, CreditCard, Plane, ReceiptText, ShieldOff, Star } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, ErrorBanner, PageHeader, Spinner } from '../components/ui'
import { api } from '../lib/api'
import { usePoll } from '../lib/usePoll'

const ICONS: Record<string, typeof Ban> = {
  cancel_subscription: Ban, reject_tracking: ShieldOff, request_refund: ReceiptText, dispute_charge: CreditCard, claim_compensation: Plane,
}

// Demo values matching the simulated accounts, offered as a convenience (never sent automatically).
const DEMO_VALUES: Record<string, Record<string, string>> = {
  request_refund: { order_number: 'ORD-1002', reason: 'Item arrived damaged', details: 'The left ear cup does not work.' },
  dispute_charge: { transaction_id: 'TXN-90545', reason: 'I did not authorise this charge', details: 'I never signed up for the Coach+ add-on.' },
  claim_compensation: { booking_reference: 'TQ7F3K', flight_number: 'TQ 482', flight_date: '2026-10-28', delay_hours: '4.2', passenger_name: 'Alex Morgan', contact_email: 'alex.morgan@example.com' },
  cancel_subscription: {},
  reject_tracking: {},
}

export default function NewTask() {
  const navigate = useNavigate()
  const { data: meta, error: metaError } = usePoll(api.meta, null)
  const [taskType, setTaskType] = useState('cancel_subscription')
  const [siteId, setSiteId] = useState('streamplus')
  const [inputs, setInputs] = useState<Record<string, string>>({})
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const task = useMemo(() => meta?.task_types.find((t) => t.id === taskType), [meta, taskType])

  function chooseTask(id: string) {
    setTaskType(id)
    setInputs({})
    setError(null)
    const rec = meta?.task_types.find((t) => t.id === id)?.recommended_sites[0]
    if (rec) setSiteId(rec)
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const clean = Object.fromEntries(Object.entries(inputs).filter(([, v]) => v.trim()))
      const { session_id } = await api.createTask({ task_type: taskType, site_id: siteId, inputs: clean })
      navigate(`/app/sessions/${session_id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setSubmitting(false)
    }
  }

  if (metaError) return <ErrorBanner message={`Could not load task types: ${metaError}`} />
  if (!meta || !task) return <Spinner />

  return (
    <form onSubmit={submit}>
      <PageHeader title="Start a new task" description="Choose what you want done and where. The agent navigates and prepares everything, but it will stop and ask you before submitting anything." />

      <h2 className="mb-3 text-sm font-semibold text-slate-900">1. What do you want to do?</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5" role="radiogroup" aria-label="Task type">
        {meta.task_types.map((t) => {
          const Icon = ICONS[t.id] ?? Ban
          const active = t.id === taskType
          return (
            <button type="button" role="radio" aria-checked={active} key={t.id} onClick={() => chooseTask(t.id)}
              className={`rounded-xl border p-4 text-left transition ${active ? 'border-brand-600 bg-brand-50 ring-1 ring-brand-600' : 'border-slate-200 bg-white hover:border-slate-300'}`}>
              <Icon size={20} className={active ? 'text-brand-700' : 'text-slate-500'} />
              <p className="mt-2 text-sm font-semibold text-slate-900">{t.title}</p>
              <p className="mt-1 text-xs text-slate-500">{t.objective}</p>
            </button>
          )
        })}
      </div>

      <h2 className="mb-3 mt-8 text-sm font-semibold text-slate-900">2. Which website? <span className="font-normal text-slate-500">(locally hosted simulations)</span></h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5" role="radiogroup" aria-label="Website">
        {meta.sites.map((site) => {
          const active = site.id === siteId
          const recommended = task.recommended_sites.includes(site.id)
          return (
            <button type="button" role="radio" aria-checked={active} key={site.id} onClick={() => setSiteId(site.id)}
              className={`rounded-xl border p-4 text-left transition ${active ? 'border-brand-600 bg-brand-50 ring-1 ring-brand-600' : 'border-slate-200 bg-white hover:border-slate-300'}`}>
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-slate-900">{site.name}</p>
                {recommended && <span className="inline-flex items-center gap-1 text-xs text-brand-700"><Star size={12} /> fits task</span>}
              </div>
              <p className="text-xs text-slate-500">{site.kind}</p>
              <p className="mt-2 text-xs text-slate-500">{site.patterns.slice(0, 2).join(' · ')}</p>
            </button>
          )
        })}
      </div>
      {!task.recommended_sites.includes(siteId) && (
        <p className="mt-2 text-xs text-amber-700">This website does not offer this task. The agent will explore and report that it could not find a path, rather than guess.</p>
      )}

      <h2 className="mb-3 mt-8 text-sm font-semibold text-slate-900">3. Details the agent needs</h2>
      <Card className="p-5">
        {task.fields.length === 0 ? (
          <p className="text-sm text-slate-600">No personal details are needed for this task.</p>
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-2">
              {task.fields.map((f) => (
                <label key={f.key} className="block">
                  <span className="text-sm font-medium text-slate-700">{f.label}{f.required && <span className="text-rose-600"> *</span>}</span>
                  {f.max > 200 ? (
                    <textarea rows={3} maxLength={f.max} value={inputs[f.key] ?? ''} onChange={(e) => setInputs({ ...inputs, [f.key]: e.target.value })}
                      className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-600 focus:outline-none focus:ring-1 focus:ring-brand-600" />
                  ) : (
                    <input required={f.required} maxLength={f.max}
                      value={inputs[f.key] ?? ''} onChange={(e) => setInputs({ ...inputs, [f.key]: e.target.value })}
                      className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-600 focus:outline-none focus:ring-1 focus:ring-brand-600" />
                  )}
                </label>
              ))}
            </div>
            {Object.keys(DEMO_VALUES[taskType] ?? {}).length > 0 && (
              <button type="button" className="mt-4 text-xs font-medium text-brand-700 hover:underline" onClick={() => setInputs(DEMO_VALUES[taskType])}>
                Fill with the simulated demo account's details
              </button>
            )}
          </>
        )}
        <p className="mt-4 rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
          FairClick never asks for passwords, card numbers or CVV codes, and only types the values above into matching fields.
          Starting a task is <strong>not</strong> approval of its final step: you will be asked before anything is submitted.
        </p>
      </Card>

      {error && <div className="mt-4"><ErrorBanner message={error} /></div>}
      <div className="mt-6 flex justify-end">
        <Button type="submit" disabled={submitting}>{submitting ? <><Spinner /> Starting…</> : 'Start agent'}</Button>
      </div>
    </form>
  )
}

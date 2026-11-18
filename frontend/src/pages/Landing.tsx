import { ArrowRight, Camera, Eye, FileCheck2, Hand, Lock, ScanSearch, ShieldAlert, Timer, Workflow } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Logo } from '../components/Layout'

const PATTERNS = [
  ['Hidden cancellation', 'The "cancel" link is grey, tiny and buried in a collapsed menu.'],
  ['Confirm-shaming', '"No thanks, I prefer losing all my benefits."'],
  ['Fake countdowns', 'A timer that restarts every time the page reloads.'],
  ['Pre-ticked tracking', 'Advertising and partner tracking switched on by default.'],
  ['Forced continuity', '"$1 for the first month" - then $119.99/year, automatically.'],
  ['Retention mazes', 'Three offer screens and a survey before you are allowed to leave.'],
]

const STEPS = [
  { icon: Workflow, title: 'Tell FairClick your goal', body: 'Pick a task - cancel, refuse tracking, request a refund, dispute a charge or claim compensation - and give only the details it needs.' },
  { icon: ScanSearch, title: 'Agents navigate and inspect', body: 'Five cooperating agents read the page structure, detect manipulative design and steer around offers and traps.' },
  { icon: Hand, title: 'You approve the final step', body: 'Before anything is submitted you see exactly what will be sent, why, and what happens next. Nothing irreversible happens without you.' },
  { icon: Camera, title: 'Evidence is preserved', body: 'Every dark pattern is captured with a screenshot, URL, timestamp and the visible text, ready to export.' },
]

const FEATURES = [
  { icon: ShieldAlert, title: '10-category dark pattern taxonomy', body: 'Confirm-shaming, obstruction, nagging, fake urgency, pre-selection, forced continuity and more - each with evidence and a confidence score.' },
  { icon: Timer, title: 'Proves fake urgency', body: 'Countdowns are observed, then re-checked after a reload. If the deadline resets, FairClick records it as fabricated.' },
  { icon: Lock, title: 'Resists prompt injection', body: 'Website text is untrusted data. Hidden "ignore previous instructions" messages are logged and ignored.' },
  { icon: FileCheck2, title: 'Human-in-the-loop by design', body: 'Navigation is automatic; submissions are not. Purchases and offers are blocked outright.' },
]

export default function Landing() {
  return (
    <div className="bg-white">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-5 sm:px-8">
        <Logo />
        <nav className="flex items-center gap-2 text-sm">
          <Link to="/app" className="hidden rounded-lg px-3 py-2 text-slate-600 hover:bg-slate-100 sm:block">Dashboard</Link>
          <Link to="/app/new" className="rounded-lg bg-brand-700 px-4 py-2 font-medium text-white hover:bg-brand-600">Start Agent</Link>
        </nav>
      </header>

      <section className="mx-auto grid max-w-6xl items-center gap-12 px-4 pb-16 pt-10 sm:px-8 lg:grid-cols-2 lg:pt-16">
        <div>
          <p className="mb-4 inline-flex rounded-full bg-brand-50 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-brand-700">Consumer-rights agent</p>
          <h1 className="text-4xl font-semibold tracking-tight text-slate-900 sm:text-5xl">Your Rights. Your Agent. Your Control.</h1>
          <p className="mt-5 text-lg leading-relaxed text-slate-600">
            FairClick navigates manipulative websites on your behalf, recognises dark patterns, completes the consumer-rights task you asked for,
            and keeps the evidence - while you approve every action that matters.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link to="/app/new" className="inline-flex items-center gap-2 rounded-lg bg-brand-700 px-5 py-3 font-medium text-white hover:bg-brand-600">
              Start Agent <ArrowRight size={18} />
            </Link>
            <Link to="/app" className="rounded-lg px-5 py-3 font-medium text-slate-700 ring-1 ring-inset ring-slate-300 hover:bg-slate-50">View dashboard</Link>
          </div>
          <p className="mt-4 text-xs text-slate-500">MVP runs against five locally hosted simulated websites. No real purchases, cancellations or payments are made.</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5 shadow-sm">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">What FairClick sees</p>
          <ul className="space-y-3">
            {PATTERNS.map(([title, body]) => (
              <li key={title} className="flex gap-3 rounded-lg bg-white p-3 ring-1 ring-slate-200">
                <Eye size={18} className="mt-0.5 shrink-0 text-brand-600" />
                <div><p className="text-sm font-semibold text-slate-900">{title}</p><p className="text-sm text-slate-600">{body}</p></div>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="border-y border-slate-200 bg-slate-50">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-8">
          <h2 className="text-2xl font-semibold tracking-tight text-slate-900">The problem</h2>
          <div className="mt-4 grid gap-6 text-slate-600 md:grid-cols-3">
            <p>Websites routinely make it easy to sign up and hard to leave: hidden cancel links, guilt-tripping buttons, invented deadlines and tracking switched on by default.</p>
            <p>Existing consumer tools usually support a fixed list of companies, and ordinary browser-automation agents can themselves be tricked by the same deceptive interfaces.</p>
            <p>FairClick treats every page as untrusted, reasons about your goal rather than the site's preferred path, and keeps you in control of the outcome.</p>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-16 sm:px-8">
        <h2 className="text-2xl font-semibold tracking-tight text-slate-900">How FairClick works</h2>
        <ol className="mt-8 grid gap-5 md:grid-cols-4">
          {STEPS.map(({ icon: Icon, title, body }, i) => (
            <li key={title} className="rounded-xl border border-slate-200 p-5">
              <div className="flex items-center gap-2 text-brand-700"><Icon size={20} /><span className="text-xs font-semibold">Step {i + 1}</span></div>
              <h3 className="mt-3 font-semibold text-slate-900">{title}</h3>
              <p className="mt-1 text-sm text-slate-600">{body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="mx-auto max-w-6xl px-4 pb-20 sm:px-8">
        <h2 className="text-2xl font-semibold tracking-tight text-slate-900">Key features</h2>
        <div className="mt-8 grid gap-5 sm:grid-cols-2">
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <div key={title} className="flex gap-4 rounded-xl border border-slate-200 p-5">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-brand-50 text-brand-700"><Icon size={20} /></span>
              <div><h3 className="font-semibold text-slate-900">{title}</h3><p className="mt-1 text-sm text-slate-600">{body}</p></div>
            </div>
          ))}
        </div>
        <div className="mt-12 flex flex-col items-start justify-between gap-4 rounded-2xl bg-brand-700 p-8 text-white sm:flex-row sm:items-center">
          <div><h3 className="text-xl font-semibold">Ready to see it work?</h3><p className="mt-1 text-brand-100">Run a cancellation against StreamPlus and watch every step.</p></div>
          <Link to="/app/new" className="inline-flex items-center gap-2 rounded-lg bg-white px-5 py-3 font-medium text-brand-700 hover:bg-brand-50">Start Agent <ArrowRight size={18} /></Link>
        </div>
      </section>
      <footer className="border-t border-slate-200 py-6 text-center text-xs text-slate-500">FairClick - academic MVP. General information only; not legal advice.</footer>
    </div>
  )
}

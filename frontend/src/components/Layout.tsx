import { BarChart3, FolderLock, LayoutDashboard, Menu, MonitorPlay, PlusCircle, Settings, ShieldCheck, X } from 'lucide-react'
import { useState } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { api } from '../lib/api'
import { usePoll } from '../lib/usePoll'

const NAV = [
  { to: '/app', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/app/new', label: 'Start new task', icon: PlusCircle },
  { to: '/app/workspace', label: 'Agent workspace', icon: MonitorPlay },
  { to: '/app/evidence', label: 'Evidence vault', icon: FolderLock },
  { to: '/app/reports', label: 'Reports & analytics', icon: BarChart3 },
  { to: '/app/settings', label: 'Settings', icon: Settings },
]

export function Logo({ className = '' }: { className?: string }) {
  return (
    <Link to="/" className={`flex items-center gap-2 font-semibold text-slate-900 ${className}`}>
      <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-700 text-white"><ShieldCheck size={18} /></span>
      <span className="text-lg tracking-tight">FairClick</span>
    </Link>
  )
}

export default function Layout() {
  const [open, setOpen] = useState(false)
  const { data: pending } = usePoll(() => api.approvals('pending'), 3000)
  const pendingCount = pending?.length ?? 0

  const nav = (
    <nav className="flex flex-col gap-1" aria-label="Main">
      {NAV.map(({ to, label, icon: Icon, end }) => (
        <NavLink key={to} to={to} end={end} onClick={() => setOpen(false)}
          className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${isActive ? 'bg-brand-50 text-brand-700' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'}`}>
          <Icon size={18} />
          <span className="flex-1">{label}</span>
          {to === '/app/workspace' && pendingCount > 0 && (
            <span className="rounded-full bg-amber-500 px-1.5 text-xs font-semibold text-white" title="Pending approvals">{pendingCount}</span>
          )}
        </NavLink>
      ))}
    </nav>
  )

  return (
    <div className="min-h-full lg:flex">
      <aside className="hidden w-64 shrink-0 flex-col border-r border-slate-200 bg-white px-4 py-5 lg:flex">
        <Logo className="mb-8 px-2" />
        {nav}
        <div className="mt-auto rounded-lg bg-slate-50 p-3 text-xs text-slate-500">
          Simulation mode: the agent can only open the five local demo sites. Nothing is ever submitted without your approval.
        </div>
      </aside>

      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3 lg:hidden">
        <Logo />
        <button type="button" className="rounded-lg p-2 text-slate-600 hover:bg-slate-100" onClick={() => setOpen(!open)} aria-label="Toggle menu">
          {open ? <X size={20} /> : <Menu size={20} />}
        </button>
      </header>
      {open && <div className="border-b border-slate-200 bg-white p-4 lg:hidden">{nav}</div>}

      <main className="min-w-0 flex-1">
        {pendingCount > 0 && (
          <div className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-900 sm:px-8">
            {pendingCount} action{pendingCount > 1 ? 's are' : ' is'} waiting for your approval.{' '}
            <Link className="font-semibold underline" to={`/app/sessions/${pending![0].session_id}`}>Review now</Link>
          </div>
        )}
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-8 sm:py-8">
          <Outlet />
        </div>
      </main>
    </div>
  )
}

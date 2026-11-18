export function timeAgo(iso: string): string {
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return `${Math.max(seconds, 0)}s ago`
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`
  return new Date(iso).toLocaleDateString()
}

export function dateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'medium' })
}

export function shortPath(url: string | null | undefined): string {
  if (!url) return ''
  const idx = url.indexOf('/sites/')
  return idx >= 0 ? url.slice(idx + 7) : url
}

export const TASK_LABELS: Record<string, string> = {
  cancel_subscription: 'Cancel subscription',
  reject_tracking: 'Reject tracking',
  request_refund: 'Request refund',
  dispute_charge: 'Dispute charge',
  claim_compensation: 'Claim compensation',
}

export const SITE_LABELS: Record<string, string> = {
  streamplus: 'StreamPlus', shopease: 'ShopEase', cookieworld: 'CookieWorld', fitlife: 'FitLife', travelquick: 'TravelQuick',
}

export const ACTIVE_STATUSES = new Set(['starting', 'running', 'awaiting_approval'])

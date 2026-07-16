import { Settings, LogOut, Shield, GitBranch } from 'lucide-react'
import { useAuth } from '@/lib/auth'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { PageHeader } from '@/components/shared/page-header'

const PIPELINE_STEPS = [
  { step: 1, label: 'Batch Upload', desc: 'Zip extraction, raw scan indexing' },
  { step: 2, label: 'Auto-Crop', desc: 'Contour detection + perspective warp' },
  { step: 3, label: 'Rotation Review', desc: 'Manual orientation confirmation' },
  { step: 4, label: 'Duplicate Detection', desc: 'pHash + color signature matching' },
  { step: 5, label: 'Card Log', desc: 'Permanent processed card record' },
]

export function SettingsPage() {
  const { user, logout } = useAuth()

  return (
    <div className="space-y-5">
      <PageHeader title="Settings" description="Account and system configuration." />

      <div className="grid max-w-xl gap-3">
        {/* Account card */}
        <Card>
          <CardContent className="p-0">
            <div className="flex items-center justify-between gap-4 px-4 py-4">
              <div className="min-w-0">
                <p className="truncate text-section text-primary">{user?.name ?? '—'}</p>
                <div className="mt-1 flex items-center gap-1.5">
                  <Shield className="h-3 w-3 shrink-0 text-muted-foreground" />
                  <p className="text-caption capitalize text-muted-foreground">{user?.role ?? '—'}</p>
                </div>
              </div>
              <Button
                variant="secondary"
                size="sm"
                onClick={logout}
                className="shrink-0 gap-2 border-accent-rose/60 text-accent-rose-foreground hover:bg-accent-rose hover:border-accent-rose"
              >
                <LogOut className="h-3.5 w-3.5" />
                Sign out
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* System info */}
        <Card>
          <CardContent className="p-0">
            <div className="flex items-center gap-2 border-b border-border px-4 py-3">
              <Settings className="h-3.5 w-3.5 text-muted-foreground" />
              <p className="text-card-title text-primary">System</p>
            </div>
            <div className="divide-y divide-border">
              {[
                { label: 'Application', value: 'CardFlow' },
                { label: 'Version', value: '1.0.0' },
                { label: 'API Base', value: '/api' },
                { label: 'Status', value: 'Operational', badge: 'mint' as const },
              ].map(({ label, value, badge }) => (
                <div key={label} className="flex items-center justify-between px-4 py-2.5">
                  <span className="text-caption text-muted-foreground">{label}</span>
                  {badge ? (
                    <Badge variant={badge}>{value}</Badge>
                  ) : (
                    <span className="text-body font-medium text-primary">{value}</span>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Pipeline info */}
        <Card>
          <CardContent className="p-0">
            <div className="flex items-center gap-2 border-b border-border px-4 py-3">
              <GitBranch className="h-3.5 w-3.5 text-muted-foreground" />
              <p className="text-card-title text-primary">Processing Pipeline</p>
            </div>
            <div className="px-4 pb-4 pt-3">
              <p className="text-caption leading-relaxed text-muted-foreground">
                CardFlow processes sports card scans through a 5-stage pipeline:
                batch upload → auto-crop → rotation review → duplicate detection → card log.
              </p>
              <div className="mt-4 space-y-0">
                {PIPELINE_STEPS.map(({ step, label, desc }, idx) => (
                  <div key={step} className="flex gap-3">
                    {/* Track column */}
                    <div className="flex flex-col items-center">
                      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent-lavender text-caption font-semibold text-accent-lavender-foreground">
                        {step}
                      </div>
                      {idx < PIPELINE_STEPS.length - 1 && (
                        <div className="w-px flex-1 bg-border my-1" />
                      )}
                    </div>
                    {/* Content */}
                    <div className={idx < PIPELINE_STEPS.length - 1 ? 'pb-4' : 'pb-0'}>
                      <p className="text-caption font-semibold text-primary leading-6">{label}</p>
                      <p className="text-caption text-muted-foreground">{desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

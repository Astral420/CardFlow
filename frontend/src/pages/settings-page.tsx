import { Settings, LogOut, User, Shield } from 'lucide-react'
import { useAuth } from '@/lib/auth'
import { Button } from '@/components/ui/button'
import { Avatar } from '@/components/ui/avatar'
import { Card, CardContent } from '@/components/ui/card'
import { PageHeader } from '@/components/shared/page-header'

export function SettingsPage() {
  const { user, logout } = useAuth()

  return (
    <div className="space-y-5">
      <PageHeader title="Settings" description="Account and system configuration." />

      {/* Account section */}
      <div className="grid max-w-xl gap-3">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-4">
              <Avatar name={user?.name ?? '?'} className="h-12 w-12 text-section" />
              <div className="flex-1">
                <p className="text-card-title text-primary">{user?.name ?? '—'}</p>
                <div className="mt-1 flex items-center gap-2">
                  <Shield className="h-3 w-3 text-muted-foreground" />
                  <p className="text-caption text-muted-foreground capitalize">{user?.role ?? '—'}</p>
                </div>
              </div>
              <Button
                variant="secondary"
                size="sm"
                onClick={logout}
                className="gap-2 text-accent-rose-foreground border-accent-rose hover:bg-accent-rose"
              >
                <LogOut className="h-3.5 w-3.5" />
                Sign out
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* System info */}
        <Card>
          <CardContent className="space-y-3 p-4">
            <div className="mb-3 flex items-center gap-2">
              <Settings className="h-4 w-4 text-muted-foreground" />
              <p className="text-card-title text-primary">System</p>
            </div>
            {[
              { label: 'Application', value: 'Card Tool V1' },
              { label: 'Version', value: '1.0.0' },
              { label: 'API Base', value: '/api' },
              { label: 'Status', value: 'Operational' },
            ].map(({ label, value }) => (
              <div key={label} className="flex items-center justify-between border-b border-border pb-3 last:border-0 last:pb-0">
                <span className="text-caption text-muted-foreground">{label}</span>
                <span className="text-body font-medium text-primary">{value}</span>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* Pipeline info */}
        <Card>
          <CardContent className="space-y-3 p-4">
            <div className="mb-3 flex items-center gap-2">
              <User className="h-4 w-4 text-muted-foreground" />
              <p className="text-card-title text-primary">Processing Pipeline</p>
            </div>
            <p className="text-body leading-relaxed text-muted-foreground">
              The Card Tool processes sports card scans through a 5-stage pipeline:
              batch upload → auto-crop → rotation review → duplicate detection → card log.
            </p>
            <div className="mt-3 space-y-2">
              {[
                { step: '1', label: 'Batch Upload', desc: 'Zip extraction, raw scan indexing' },
                { step: '2', label: 'Auto-Crop', desc: 'Contour detection + perspective warp' },
                { step: '3', label: 'Rotation Review', desc: 'Manual orientation confirmation' },
                { step: '4', label: 'Duplicate Detection', desc: 'pHash + color signature matching' },
                { step: '5', label: 'Card Log', desc: 'Permanent processed card record' },
              ].map(({ step, label, desc }) => (
                <div key={step} className="flex items-start gap-3">
                  <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-caption font-semibold text-muted-foreground">
                    {step}
                  </div>
                  <div>
                    <p className="text-caption font-semibold text-primary">{label}</p>
                    <p className="text-caption text-muted-foreground">{desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

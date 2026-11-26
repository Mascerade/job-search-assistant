import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { PageHeader } from '@/components/EmptyState'
import { JobForm } from '@/components/JobForm'
import { toJobInsert } from '@/lib/jobForm'
import { Card, CardContent } from '@/components/ui/card'
import { useCreateJob } from '@/lib/queries'

export function AddJobPage() {
  const navigate = useNavigate()
  const create = useCreateJob()

  return (
    <>
      <PageHeader
        title="Add a job"
        description="For postings you find yourself (Handshake, LinkedIn, a friend's referral). Automatic import from a link comes in a later milestone."
      />
      <Card>
        <CardContent>
          <JobForm
            submitLabel="Add job"
            pending={create.isPending}
            onSubmit={async (values) => {
              try {
                const job = await create.mutateAsync({ ...toJobInsert(values), source: 'manual' })
                toast.success(`Added ${job.title} at ${job.company}`)
                navigate(`/jobs/${job.id}`)
              } catch (e) {
                toast.error(`Couldn't add the job: ${(e as Error).message}`)
              }
            }}
          />
        </CardContent>
      </Card>
    </>
  )
}

/**
 * Master profile: the only source of facts the tailoring step may use.
 * Mirrors pipeline/jobsearch/profile.py (the Python side is authoritative).
 */
export interface Fact {
  id: string
  text: string
  tags?: string[]
}

export interface Entry {
  id: string
  title?: string
  org?: string
  name?: string
  location?: string
  start?: string
  end?: string
  stack?: string[]
  facts: Fact[]
}

export interface Profile {
  contact: { name: string; email: string; phone?: string; location?: string; links?: string[] }
  summaries?: Record<string, string>
  education: { id: string; school: string; degree: string; location?: string; end: string; details?: string[] }[]
  experience: Entry[]
  projects: Entry[]
  skills: { category: string; items: string[] }[]
  certifications?: string[]
  extra_facts?: Fact[]
}

/** Returns a list of human-readable problems; empty means valid. */
export function validateProfile(value: unknown): string[] {
  const errs: string[] = []
  if (!value || typeof value !== 'object' || Array.isArray(value)) return ['The profile must be a YAML mapping (key: value pairs).']
  const p = value as Partial<Profile>
  if (!p.contact?.name) errs.push('contact.name is required.')
  if (!p.contact?.email) errs.push('contact.email is required.')
  for (const key of ['education', 'experience', 'projects', 'skills'] as const) {
    if (!Array.isArray(p[key])) errs.push(`${key} must be a list.`)
  }
  const ids = new Set<string>()
  const checkFacts = (facts: unknown, where: string) => {
    if (!Array.isArray(facts)) {
      errs.push(`${where}.facts must be a list.`)
      return
    }
    facts.forEach((f, i) => {
      const fact = f as Partial<Fact>
      if (!fact?.id) errs.push(`${where}.facts[${i}] needs an id.`)
      else if (ids.has(fact.id)) errs.push(`Duplicate fact id "${fact.id}".`)
      else ids.add(fact.id)
      if (!fact?.text) errs.push(`${where}.facts[${i}] needs text.`)
      else if (/\[[^\]]*\]/.test(fact.text)) errs.push(`${fact.id ?? where}: remove the [placeholder] or fill it in.`)
    })
  }
  for (const key of ['experience', 'projects'] as const) {
    if (Array.isArray(p[key])) p[key]!.forEach((e, i) => checkFacts(e?.facts, `${key}[${i}]`))
  }
  if (p.extra_facts !== undefined) checkFacts(p.extra_facts, 'extra_facts')
  return errs
}

export function countFacts(p: Profile): number {
  return [...p.experience, ...p.projects].reduce((n, e) => n + (e.facts?.length ?? 0), 0) + (p.extra_facts?.length ?? 0)
}

const TOP_ORDER = ['contact', 'summaries', 'education', 'experience', 'projects', 'skills', 'certifications', 'extra_facts']
const ENTRY_ORDER = ['id', 'title', 'org', 'name', 'location', 'start', 'end', 'stack', 'facts']
const FACT_ORDER = ['id', 'text', 'tags']

function ordered(obj: Record<string, unknown>, order: string[]): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const k of order) if (k in obj) out[k] = obj[k]
  for (const k of Object.keys(obj)) if (!(k in out)) out[k] = obj[k]
  return out
}

/** Postgres jsonb doesn't keep key order; put the profile back in a readable order for editing. */
export function canonicalProfile(p: Profile): Record<string, unknown> {
  const entry = (e: Entry) =>
    ordered({ ...e, facts: e.facts.map((f) => ordered({ ...f }, FACT_ORDER)) }, ENTRY_ORDER)
  return ordered(
    {
      ...p,
      contact: ordered({ ...p.contact }, ['name', 'email', 'phone', 'location', 'links']),
      education: p.education.map((e) => ordered({ ...e }, ['id', 'school', 'location', 'degree', 'end', 'details'])),
      experience: p.experience.map(entry),
      projects: p.projects.map(entry),
      skills: p.skills.map((s) => ordered({ ...s }, ['category', 'items'])),
      ...(p.extra_facts ? { extra_facts: p.extra_facts.map((f) => ordered({ ...f }, FACT_ORDER)) } : {}),
    },
    TOP_ORDER,
  )
}

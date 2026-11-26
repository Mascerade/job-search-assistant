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

/** Standard answers for application forms (apply assist). null/missing = ask on each form. */
export interface ApplicationAnswers {
  work_authorized_us?: boolean | null
  sponsorship_now?: boolean | null
  sponsorship_future?: boolean | null
  over_18?: boolean | null
  preferred_name?: string | null
  pronouns?: string | null
  address?: string | null
  gpa?: string | null
  salary_expectation?: string | null
  willing_to_relocate?: boolean | null
  how_heard?: string | null
  links?: { linkedin?: string | null; github?: string | null; website?: string | null; portfolio?: string | null }
  demographics?: {
    gender?: string | null
    race_ethnicity?: string | null
    hispanic_latino?: string | null
    veteran?: string | null
    disability?: string | null
  }
  custom?: { question: string; answer: string }[]
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
  declined_skills?: string[]
  application?: ApplicationAnswers | null
}

// The pipeline rejects unknown keys (pydantic extra="forbid"); for the application answers a
// typo saved here would stop tailoring, so these keys are checked strictly on the site too.
const BOOL_ANSWERS = ['work_authorized_us', 'sponsorship_now', 'sponsorship_future', 'over_18', 'willing_to_relocate']
const TEXT_ANSWERS = ['preferred_name', 'pronouns', 'address', 'gpa', 'salary_expectation', 'how_heard']
const LINK_KEYS = ['linkedin', 'github', 'website', 'portfolio']
const DEMOGRAPHIC_KEYS = ['gender', 'race_ethnicity', 'hispanic_latino', 'veteran', 'disability']

function isMap(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === 'object' && !Array.isArray(v)
}

function checkApplication(value: unknown, errs: string[]) {
  if (value === null || value === undefined) return
  if (!isMap(value)) {
    errs.push('application must be a mapping (key: value pairs).')
    return
  }
  const allowed = new Set([...BOOL_ANSWERS, ...TEXT_ANSWERS, 'links', 'demographics', 'custom'])
  for (const [k, v] of Object.entries(value)) {
    if (!allowed.has(k)) errs.push(`application.${k} isn't a known answer (check the spelling).`)
    else if (BOOL_ANSWERS.includes(k) && v !== null && typeof v !== 'boolean') errs.push(`application.${k} must be true, false, or empty.`)
    else if (TEXT_ANSWERS.includes(k) && v !== null && typeof v !== 'string' && typeof v !== 'number')
      errs.push(`application.${k} must be text.`)
  }
  for (const [group, keys] of [['links', LINK_KEYS], ['demographics', DEMOGRAPHIC_KEYS]] as const) {
    const g = value[group]
    if (g === undefined || g === null) continue
    if (!isMap(g)) {
      errs.push(`application.${group} must be a mapping.`)
      continue
    }
    for (const [k, v] of Object.entries(g)) {
      if (!(keys as readonly string[]).includes(k)) errs.push(`application.${group}.${k} isn't a known field (check the spelling).`)
      else if (v !== null && typeof v !== 'string') errs.push(`application.${group}.${k} must be text.`)
    }
  }
  const custom = value.custom
  if (custom !== undefined && custom !== null) {
    if (!Array.isArray(custom)) errs.push('application.custom must be a list.')
    else
      custom.forEach((qa, i) => {
        if (!isMap(qa)) return errs.push(`application.custom[${i}] needs a question and an answer.`)
        for (const k of Object.keys(qa)) if (k !== 'question' && k !== 'answer') errs.push(`application.custom[${i}].${k} isn't allowed.`)
        if (!qa.question || typeof qa.question !== 'string') errs.push(`application.custom[${i}] needs a question.`)
        if (!qa.answer || typeof qa.answer !== 'string') errs.push(`application.custom[${i}] needs an answer.`)
      })
  }
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
  checkApplication((value as Record<string, unknown>).application, errs)
  return errs
}

export function countFacts(p: Profile): number {
  return [...p.experience, ...p.projects].reduce((n, e) => n + (e.facts?.length ?? 0), 0) + (p.extra_facts?.length ?? 0)
}

const TOP_ORDER = [
  'contact',
  'summaries',
  'education',
  'experience',
  'projects',
  'skills',
  'certifications',
  'extra_facts',
  'declined_skills',
  'application',
]
const APPLICATION_ORDER = [...BOOL_ANSWERS.slice(0, 4), ...TEXT_ANSWERS.slice(0, 4), 'salary_expectation', 'willing_to_relocate', 'how_heard', 'links', 'demographics', 'custom']
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
      ...(p.application ? { application: ordered({ ...p.application }, APPLICATION_ORDER) } : {}),
    },
    TOP_ORDER,
  )
}

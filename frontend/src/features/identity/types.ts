export interface OrganizationSummary {
  id: string
  name: string
  role: string
}

export interface CurrentUser {
  id: string
  username: string
  display_name: string
  first_name: string
  last_name: string
  email: string
  last_login: string | null
  organizations: OrganizationSummary[]
}

export interface OrganizationContext {
  id: string
  name: string
  base_currency: string
  timezone: string
  role: string
  role_code: string
  permissions: string[]
  section_ids: string[]
  branch_ids: string[]
}

export interface Section {
  id: string
  name: string
  code: string
}

export interface StaffMember {
  id: string
  user_id: number
  username: string
  first_name: string
  last_name: string
  email: string
  name: string
  role: string
  role_code: string
  role_name: string
  all_sections: boolean
  section_ids: string[]
  all_branches: boolean
  branch_ids: string[]
  active: boolean
  last_login: string | null
  created_at: string
  is_you: boolean
}

export interface Role {
  id: string
  code: string
  name: string
  is_system: boolean
  permissions: string[]
  member_count: number
}

export interface PermissionGroup {
  title: string
  permissions: { code: string; description: string }[]
}
export interface Branch {
  id: string
  name: string
}

export interface AuditEvent {
  id: string
  actor: number | null
  actor_name: string
  action: string
  entity_type: string
  entity_id: string
  summary: Record<string, unknown>
  request_id: string
  created_at: string
}

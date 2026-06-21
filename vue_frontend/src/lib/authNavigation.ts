import type { User } from '@/types/auth'

export function isStaffUser(user: User | null | undefined): boolean {
  return Boolean(user?.is_staff)
}

export function defaultAuthenticatedRoute() {
  return { name: 'profile' as const }
}

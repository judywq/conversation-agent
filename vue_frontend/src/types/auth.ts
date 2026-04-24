export interface User {
  pk: number;
  username: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  must_change_password: boolean;
  /** Conversation-system profile fields (may be missing in older cached auth state). */
  ocean?: Record<string, string>;
  cefr_level?: string | null;
}

export interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  loading: boolean;
  error: string | null;
}

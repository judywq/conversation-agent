export interface User {
  pk: number;
  username: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  must_change_password: boolean;
  is_staff?: boolean;
  /** Conversation-system profile fields (may be missing in older cached auth state). */
  ocean?: Record<string, string>;
  cefr_level?: string | null;
  profile_completed?: boolean;
  proficiency_reference_utterance?: string | null;
  cefr_sample_topic?: string | null;
  cefr_sample_choices?: Array<{
    level: string;
    text: string;
    audio_url?: string | null;
  }>;
  cefr_samples_status?: 'idle' | 'pending' | 'ready' | 'failed' | null;
  preferred_name?: string | null;
  avatar_id?: string | null;
  major?: string | null;
  discussion_category?: string | null;
  discussion_subtopic?: string | null;
  discussion_scenario?: string | null;
}

export interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  loading: boolean;
  error: string | null;
}

import api from '@/services/api'

export interface CefrSample {
  level: string
  text: string
  audio_url?: string | null
}

export interface NewsSubtopic {
  slug: string
  name: string
  keywords: string[]
}

export interface NewsCategory {
  slug: string
  name: string
  description: string
  subtopics: NewsSubtopic[]
}

export interface DiscussionArticleSummary {
  id: number
  title: string
  summary: string
  url: string
  full_text_fetched: boolean
}

export interface DiscussionScenarioResult {
  scenario: string
  category: string
  subtopic: string
  category_name: string
  subtopic_name: string
  article_id: number | null
  article_title: string
  article_ids: number[]
  articles: DiscussionArticleSummary[]
  web_context: string
  knowledge_source: 'articles' | 'web' | 'none'
  web_context_fetched: boolean
}

export interface ArgumentSummaryReason {
  text: string
}

export interface ArgumentSummaryExplanation {
  type: 'fact' | 'data' | 'example'
  text: string
}

export interface ArgumentSummaryPackage {
  type: 'argument' | 'counterargument'
  reason: ArgumentSummaryReason
  explanations: ArgumentSummaryExplanation[]
}

export interface ArgumentSummaryClaim {
  text: string
  arguments: ArgumentSummaryPackage[]
}

export interface ArgumentSummaryResult {
  status: 'pending' | 'ready' | 'failed' | 'empty'
  claims?: ArgumentSummaryClaim[]
}

export const PROFILE_ONBOARDING_CEFR_TOPIC = 'University life and learning English'

export class ConversationService {
  static async fetchNewsTaxonomy(): Promise<{ taxonomy_version: string; categories: NewsCategory[] }> {
    const res = await api.get<{ taxonomy_version: string; categories: NewsCategory[] }>('/news/taxonomy/')
    return res.data
  }

  static async generateDiscussionScenario(
    category: string,
    subtopic: string,
  ): Promise<DiscussionScenarioResult> {
    const res = await api.post<DiscussionScenarioResult>(
      '/conversation/discussion-scenario/',
      { category, subtopic },
      { timeout: 180000 },
    )
    return res.data
  }

  static async speechToText(audio: Blob): Promise<string> {
    const form = new FormData()
    form.append('audio', audio, 'recording.webm')

    const res = await api.post<{ text: string }>('/conversation/stt/', form, {
      headers: {
        // Let the browser set the correct multipart boundary
        'Content-Type': 'multipart/form-data',
      },
    })
    return res.data.text
  }

  static async uploadUserAudio(sessionId: string, audio: Blob): Promise<{ id: number; audio_url: string }> {
    const form = new FormData()
    form.append('session_id', sessionId)
    form.append('audio', audio, 'user_recording.webm')

    const res = await api.post<{ id: number; audio_url: string }>('/conversation/user-audio/', form, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    return res.data
  }

  static async generateCefrSamples(topic: string): Promise<{ topic: string; samples: CefrSample[] }> {
    const res = await api.post<{ topic: string; samples: CefrSample[] }>('/conversation/cefr-samples/', {
      topic,
    }, {
      timeout: 180000,
    })
    return res.data
  }

  static async fetchArgumentSummary(sessionId: number): Promise<ArgumentSummaryResult> {
    const res = await api.get<ArgumentSummaryResult>(
      `/conversation/sessions/${sessionId}/argument-summary/`,
      { timeout: 180000 },
    )
    return res.data
  }
}

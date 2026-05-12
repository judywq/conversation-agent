import api from '@/services/api'

export interface CefrSample {
  level: string
  text: string
  audio_url?: string | null
}

export class ConversationService {
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
}

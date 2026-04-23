import api from '@/services/api'

export interface LlmModel {
  id: number
  name: string
  display_name: string
  llm_type: string
  is_default: boolean
}

export class LlmService {
  static async listActiveModels(): Promise<LlmModel[]> {
    const res = await api.get<LlmModel[]>('/llm/models/')
    return res.data
  }
}


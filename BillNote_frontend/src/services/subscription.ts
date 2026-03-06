import request from '@/utils/request'

export interface SubscriptionGeneratePayload {
  channel_url: string
  model_name: string
  provider_id: string
  quality: 'fast' | 'medium' | 'slow'
  style?: string
  extras?: string
}

export interface SubscriptionBatchPayload extends SubscriptionGeneratePayload {
  count: number
}

export interface SubscriptionMergePayload {
  start_date: string
  end_date: string
  channel_url?: string
  summarize: boolean
  model_name?: string
  provider_id?: string
}

export const pullLatestSubscriptionNote = async (payload: SubscriptionGeneratePayload) => {
  return request.post('/subscription/pull_latest', payload)
}

export const fetchRecentSubscriptionNotes = async (payload: SubscriptionBatchPayload) => {
  return request.post('/subscription/fetch_recent', payload)
}

export const mergeSubscriptionNotes = async (payload: SubscriptionMergePayload) => {
  return request.post('/subscription/merge_export', payload)
}

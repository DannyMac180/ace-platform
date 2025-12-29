// API Types for ACE Platform

export interface User {
  id: string;
  email: string;
  subscription_tier: 'free' | 'pro' | 'enterprise';
  subscription_status: 'active' | 'past_due' | 'canceled' | 'none';
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface ApiKey {
  id: string;
  name: string;
  key_preview: string;
  scopes: string[];
  created_at: string;
  expires_at: string | null;
  last_used_at: string | null;
}

export interface ApiKeyCreate {
  name: string;
  scopes: string[];
  expires_in_days?: number;
}

export interface ApiKeyCreateResponse {
  id: string;
  name: string;
  key: string; // Full key, only shown once
  scopes: string[];
  expires_at: string | null;
}

export interface Playbook {
  id: string;
  name: string;
  description: string | null;
  status: 'active' | 'paused' | 'archived';
  source: 'user_created' | 'starter' | 'imported';
  created_at: string;
  updated_at: string;
  current_version: PlaybookVersion | null;
}

export interface PlaybookListItem extends Omit<Playbook, 'current_version'> {
  version_count: number;
  outcome_count: number;
}

export interface PlaybookVersion {
  id: string;
  version_number: number;
  content: string;
  bullet_count: number;
  diff_summary?: string | null;
  created_by_job_id?: string | null;
  created_at: string;
}

export interface PlaybookCreate {
  name: string;
  description?: string;
  initial_content?: string;
}

export interface PlaybookUpdate {
  name?: string;
  description?: string;
  status?: 'active' | 'paused' | 'archived';
}

export interface Outcome {
  id: string;
  task_description: string;
  outcome_status: 'success' | 'failure' | 'partial';
  notes: string | null;
  reasoning_trace: string | null;
  created_at: string;
  processed_at: string | null;
  evolution_job_id: string | null;
}

export interface OutcomeCreate {
  task_description: string;
  outcome: 'success' | 'failure' | 'partial';
  notes?: string;
  reasoning_trace?: string;
}

export interface EvolutionJob {
  id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  from_version_id: string | null;
  to_version_id: string | null;
  outcomes_processed: number;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface UsageSummary {
  total_tokens: number;
  total_cost_usd: number;
  total_operations: number;
  period_start: string;
  period_end: string;
}

export interface DailyUsage {
  date: string;
  tokens: number;
  cost_usd: number;
  operations: number;
}

export interface PlaybookUsage {
  playbook_id: string;
  playbook_name: string;
  tokens: number;
  cost_usd: number;
  operations: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

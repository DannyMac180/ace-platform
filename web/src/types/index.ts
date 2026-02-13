// API Types for ACE Platform

export interface User {
  id: string;
  email: string;
  is_active: boolean;
  is_admin: boolean;
  email_verified: boolean;
  subscription_tier: string | null;  // 'starter', 'pro', 'ultra', or null for free
  subscription_status: 'active' | 'past_due' | 'canceled' | 'unpaid' | 'none';
  has_used_trial: boolean;
  trial_ends_at: string | null;  // ISO date string if in trial
  has_payment_method: boolean;  // Whether user has a valid card on file
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
  key_prefix: string;
  scopes: string[];
  created_at: string;
  last_used_at: string | null;
  is_active: boolean;
}

export interface ApiKeyCreate {
  name: string;
  scopes: string[];
}

export interface ApiKeyCreateResponse {
  id: string;
  name: string;
  key: string; // Full key, only shown once
  key_prefix: string;
  scopes: string[];
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

export interface VersionCreate {
  content: string;
  diff_summary?: string;
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
  status: 'queued' | 'running' | 'completed' | 'failed';
  from_version_id: string | null;
  to_version_id: string | null;
  outcomes_processed: number;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface UsageSummary {
  start_date: string;
  end_date: string;
  total_requests: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  total_cost_usd: string | number;
}

export interface DailyUsage {
  date: string;
  request_count: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: string | number;
}

export interface PlaybookUsage {
  playbook_id: string;
  playbook_name: string;
  request_count: number;
  total_tokens: number;
  cost_usd: string | number;
}

// Evolution Statistics Types
export interface EvolutionSummary {
  start_date: string;
  end_date: string;
  total_evolutions: number;
  completed_evolutions: number;
  failed_evolutions: number;
  running_evolutions: number;
  queued_evolutions: number;
  success_rate: number;
  total_outcomes_processed: number;
}

export interface DailyEvolution {
  date: string;
  total_evolutions: number;
  completed: number;
  failed: number;
  running: number;
  queued: number;
}

export interface PlaybookEvolutionStats {
  playbook_id: string;
  playbook_name: string;
  total_evolutions: number;
  completed: number;
  failed: number;
  success_rate: number;
  last_evolution_at: string | null;
}

export interface RecentEvolution {
  id: string;
  playbook_id: string;
  playbook_name: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  outcomes_processed: number;
  from_version_number: number | null;
  to_version_number: number | null;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
}

// Audit log types
export interface AuditLogItem {
  id: string;
  event_type: string;
  severity: string;
  created_at: string;
  ip_address: string | null;
  user_agent: string | null;
  details: Record<string, unknown> | null;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// Admin types
export interface PlatformStats {
  total_users: number;
  active_users_today: number;
  signups_this_week: number;
  total_cost_today: string;
  tier_distribution: Record<string, number>;
}

export interface AdminUserItem {
  id: string;
  email: string;
  is_active: boolean;
  email_verified: boolean;
  is_admin: boolean;
  subscription_tier: string | null;
  subscription_status: string;
  playbook_count: number;
  total_cost_usd: string;
  created_at: string;
}

export interface AdminUserDetail {
  id: string;
  email: string;
  is_active: boolean;
  is_admin: boolean;
  email_verified: boolean;
  subscription_tier: string | null;
  subscription_status: string;
  has_used_trial: boolean;
  has_payment_method: boolean;
  created_at: string;
  updated_at: string;
  usage_summary: {
    total_requests: number;
    total_tokens: number;
    total_cost_usd: string;
    start_date: string;
    end_date: string;
  };
}

export interface DailySignup {
  date: string;
  count: number;
}

export interface TopUser {
  user_id: string;
  email: string;
  subscription_tier: string | null;
  total_cost_usd: string;
  cost_limit_usd: string | null;
  percent_of_limit: number | null;
}

export interface AdminAuditEvent {
  id: string;
  user_id: string | null;
  user_email: string | null;
  event_type: string;
  severity: string;
  ip_address: string | null;
  created_at: string;
  details: Record<string, unknown> | null;
}

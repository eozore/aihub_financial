import axios, { AxiosHeaders } from 'axios';
import { auth } from '../lib/firebase';

// Environment-aware API URL
// - Uses NEXT_PUBLIC_API_URL if set (from .env.local or build env)
// - Falls back to localhost in development, production URL otherwise
const getApiUrl = () => {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }
  // Client-side detection for dev environment
  if (typeof window !== 'undefined' && window.location.hostname === 'localhost') {
    return 'http://localhost:8000';
  }
  // In production, NEXT_PUBLIC_API_URL must be set at build time.
  // Falling back to empty string will cause requests to use relative paths.
  console.warn('NEXT_PUBLIC_API_URL is not set. API calls may fail.');
  return '';
};

const API_URL = getApiUrl();
const TENANT_HEADER_NAME = process.env.NEXT_PUBLIC_TENANT_HEADER_NAME || 'X-Tenant-ID';
const DEFAULT_TENANT_ID = process.env.NEXT_PUBLIC_DEFAULT_TENANT_ID || 'default';
const ACTIVE_WORKSPACE_KEY = 'finance_active_workspace_id';

export const api = axios.create({
  baseURL: API_URL,
});

const normalizeTenantId = (rawTenant?: string | null): string | null => {
  if (!rawTenant) return null;
  const trimmed = rawTenant.trim();
  if (!trimmed) return null;
  if (!/^[A-Za-z0-9_.-]{1,64}$/.test(trimmed)) return null;
  return trimmed;
};

const getTenantFromClaims = (claims: Record<string, unknown>): string | null => {
  const claimTenant = claims.tenant_id;
  if (typeof claimTenant === 'string') {
    return normalizeTenantId(claimTenant);
  }

  const firebaseClaim = claims.firebase;
  if (firebaseClaim && typeof firebaseClaim === 'object' && !Array.isArray(firebaseClaim)) {
    const firebaseTenant = (firebaseClaim as Record<string, unknown>).tenant;
    if (typeof firebaseTenant === 'string') {
      return normalizeTenantId(firebaseTenant);
    }
  }

  return null;
};

let cachedTenantId = normalizeTenantId(DEFAULT_TENANT_ID);
let tenantCacheUntil = 0;
let activeWorkspaceId: string | null = null;

const getStoredWorkspaceId = (): string | null => {
  if (typeof window === 'undefined') return null;
  return normalizeTenantId(window.localStorage.getItem(ACTIVE_WORKSPACE_KEY));
};

export const setActiveWorkspace = (workspaceId?: string | null) => {
  const normalized = normalizeTenantId(workspaceId || null);
  activeWorkspaceId = normalized;
  if (typeof window !== 'undefined') {
    if (normalized) {
      window.localStorage.setItem(ACTIVE_WORKSPACE_KEY, normalized);
    } else {
      window.localStorage.removeItem(ACTIVE_WORKSPACE_KEY);
    }
  }
};

export const getActiveWorkspace = () => activeWorkspaceId || getStoredWorkspaceId();

api.interceptors.request.use(async (config) => {
  const user = auth.currentUser;
  const requestHeaders: Record<string, string> = {};
  if (!activeWorkspaceId) {
    activeWorkspaceId = getStoredWorkspaceId();
  }

  if (user) {
    const now = Date.now();
    if (now >= tenantCacheUntil) {
      const tokenResult = await user.getIdTokenResult();
      cachedTenantId = getTenantFromClaims(tokenResult.claims as Record<string, unknown>) || normalizeTenantId(DEFAULT_TENANT_ID);
      tenantCacheUntil = now + 5 * 60 * 1000;
    }

    const token = await user.getIdToken();
    requestHeaders.Authorization = `Bearer ${token}`;
  } else {
    cachedTenantId = normalizeTenantId(DEFAULT_TENANT_ID);
    tenantCacheUntil = Date.now() + 5 * 60 * 1000;
  }

  const tenantToSend = normalizeTenantId(activeWorkspaceId) || cachedTenantId;
  if (tenantToSend) {
    requestHeaders[TENANT_HEADER_NAME] = tenantToSend;
  }

  const headers = AxiosHeaders.from(config.headers || {});
  for (const [key, value] of Object.entries(requestHeaders)) {
    headers.set(key, value);
  }
  config.headers = headers;

  return config;
});

export interface TransactionFilters {
  owner?: string;
  txType?: string;
}

export interface TransactionData {
  date: string;
  amount: number;
  merchant_clean: string;
  category: string;
  subcategory?: string;
  owner: string;
  type: string;
}

export interface WorkspaceSummary {
  id: string;
  name: string;
  owner_user_id: string;
  member_limit?: number;
  role?: string;
  member_count?: number;
}

export interface MeSummary {
  user_id: string;
  email?: string;
  plan_type: 'free' | 'paid';
  is_admin?: boolean;
  limits: {
    max_workspaces: number;
    max_members_per_workspace: number;
  };
  active_workspace_id?: string;
  workspace_count: number;
}

export const uploadInvoice = async (file: File, owner: string, monthRef: string) => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('owner', owner);
  formData.append('month_ref', monthRef);

  const response = await api.post('/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
};

export interface NetWorthSnapshot {
  owner?: string;
  month_ref: string;
  net_worth_total: number;
  salary?: number | null;
  other_income?: number | null;
  income_total?: number | null;
  expense_fixed?: number | null;
  expense_variable?: number | null;
  expense_total?: number | null;
  cash_end_balance?: number | null;
  debt_ratio?: number | null;
  notes?: string | null;
}

export const uploadNetWorth = async (file: File, owner: string) => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('owner', owner);

  const response = await api.post('/net-worth/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
};

export interface NetWorthValidationRow {
  month_ref: string;
  owner: string;
  income_bank: number;
  expense_bank: number;
  expense_card: number;
  suggested_income_total: number;
  suggested_expense_total: number;
  suggested_saved: number;
  manual_income_total?: number | null;
  manual_expense_total?: number | null;
  manual_net_worth_total?: number | null;
  is_partial: boolean;
}

export const uploadCurrentAccount = async (file: File, owner: string, monthRef: string) => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('owner', owner);
  formData.append('month_ref', monthRef);

  const response = await api.post('/current-account/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
};

export const getNetWorth = async (
  startMonth?: string,
  endMonth?: string,
  owner?: string
): Promise<{ data: NetWorthSnapshot[] }> => {
  const params = new URLSearchParams();
  if (startMonth) params.set('start', startMonth);
  if (endMonth) params.set('end', endMonth);
  if (owner) params.set('owner', owner);
  const qs = params.toString();
  const response = await api.get(`/net-worth${qs ? `?${qs}` : ''}`);
  return response.data;
};

export const updateNetWorthRow = async (
  monthRef: string,
  owner: string,
  payload: Partial<Omit<NetWorthSnapshot, 'month_ref'>>
) => {
  const response = await api.put(`/net-worth/${monthRef}?owner=${encodeURIComponent(owner)}`, payload);
  return response.data;
};

export const getNetWorthValidation = async (
  owner: string,
  startMonth?: string,
  endMonth?: string
): Promise<{ owner: string; data: NetWorthValidationRow[] }> => {
  const params = new URLSearchParams();
  params.set('owner', owner);
  if (startMonth) params.set('start', startMonth);
  if (endMonth) params.set('end', endMonth);
  const response = await api.get(`/net-worth/validation?${params.toString()}`);
  return response.data;
};

export const getDashboardSummary = async (
  startMonth: string,
  endMonth?: string,
  filters?: TransactionFilters
) => {
  const end = endMonth || startMonth;
  let url = `/dashboard-summary?start=${startMonth}&end=${end}`;
  if (filters?.owner) url += `&owner=${filters.owner}`;
  if (filters?.txType) url += `&tx_type=${filters.txType}`;
  const response = await api.get(url);
  return response.data;
};

export const getTransactions = async (
  startMonth: string,
  endMonth?: string,
  filters?: TransactionFilters,
  limit: number = 200,
  offset: number = 0,
) => {
  const end = endMonth || startMonth;
  let url = `/transactions?start=${startMonth}&end=${end}&limit=${limit}&offset=${offset}`;
  if (filters?.owner) url += `&owner=${filters.owner}`;
  if (filters?.txType) url += `&tx_type=${filters.txType}`;
  const response = await api.get(url);
  return response.data;
};

export const getTrendData = async (
  startMonth: string,
  endMonth?: string,
  filters?: TransactionFilters
) => {
  const end = endMonth || startMonth;
  let url = `/trend-data?start=${startMonth}&end=${end}`;
  if (filters?.owner) url += `&owner=${filters.owner}`;
  if (filters?.txType) url += `&tx_type=${filters.txType}`;
  const response = await api.get(url);
  return response.data;
};

export const updateTransaction = async (id: string, data: Partial<TransactionData>) => {
  const response = await api.put(`/transactions/${id}`, data);
  return response.data;
};

export const createTransaction = async (data: TransactionData) => {
  const response = await api.post('/transactions', data);
  return response.data;
};

export const deleteTransaction = async (id: string) => {
  const response = await api.delete(`/transactions/${id}`);
  return response.data;
};

export const syncToDatabase = async () => {
  const response = await api.post('/sync-firestore-to-bigquery');
  return response.data;
};

export const getMe = async (): Promise<MeSummary> => {
  const response = await api.get('/me');
  const data = response.data as MeSummary;
  if (data?.active_workspace_id) {
    setActiveWorkspace(data.active_workspace_id);
  }
  return data;
};

export const getOwners = async (): Promise<string[]> => {
  const response = await api.get('/owners');
  return response.data?.owners || [];
};

export const updatePlan = async (planType: 'free' | 'paid') => {
  const response = await api.put('/me/plan', { plan_type: planType });
  return response.data;
};

export const getWorkspaces = async (): Promise<{
  active_workspace_id?: string;
  workspaces: WorkspaceSummary[];
}> => {
  const response = await api.get('/workspaces');
  const data = response.data;
  if (data?.active_workspace_id) {
    setActiveWorkspace(data.active_workspace_id);
  }
  return data;
};

export const createWorkspace = async (name: string) => {
  const response = await api.post('/workspaces', { name });
  return response.data;
};

export const updateWorkspace = async (workspaceId: string, name: string) => {
  const response = await api.put(`/workspaces/${workspaceId}`, { name });
  return response.data;
};

export const deleteWorkspace = async (workspaceId: string) => {
  const response = await api.delete(`/workspaces/${workspaceId}`);
  if (response.data?.active_workspace_id) {
    setActiveWorkspace(response.data.active_workspace_id);
  }
  return response.data;
};

export const activateWorkspace = async (workspaceId: string) => {
  const response = await api.post(`/workspaces/${workspaceId}/activate`);
  if (response.data?.active_workspace_id) {
    setActiveWorkspace(response.data.active_workspace_id);
  } else {
    setActiveWorkspace(workspaceId);
  }
  return response.data;
};

export const getWorkspaceMembers = async (workspaceId: string) => {
  const response = await api.get(`/workspaces/${workspaceId}/members`);
  return response.data;
};

export const removeWorkspaceMember = async (workspaceId: string, memberUserId: string) => {
  const response = await api.delete(`/workspaces/${workspaceId}/members/${memberUserId}`);
  return response.data;
};

export const createWorkspaceInvite = async (
  workspaceId: string,
  inviteeEmail: string,
  inviteMode: 'shared' = 'shared'
) => {
  const response = await api.post(`/workspaces/${workspaceId}/invites`, {
    invitee_email: inviteeEmail,
    invite_mode: inviteMode,
  });
  return response.data;
};

export const getInvites = async () => {
  const response = await api.get('/invites');
  return response.data;
};

export const acceptInvite = async (inviteId: string) => {
  const response = await api.post(`/invites/${inviteId}/accept`);
  if (response.data?.workspace_id) {
    setActiveWorkspace(response.data.workspace_id);
  }
  return response.data;
};

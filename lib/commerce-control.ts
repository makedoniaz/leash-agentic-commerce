export type Currency = "CHF" | "USD" | "EUR";

export type ProductCategory =
  | "books"
  | "clothing"
  | "cosmetics"
  | "dining"
  | "electronics"
  | "food_delivery"
  | "fuel"
  | "gift_card"
  | "groceries"
  | "home_improvement"
  | "hotel"
  | "household"
  | "membership"
  | "sporting_goods"
  | "subscriptions"
  | "transport";

export interface ParsedPolicyDraft {
  raw_instructions: string;
  products: {
    items: Array<{
      name: string | null;
      category: ProductCategory | null;
      quantity: number | null;
      max_price_per_item: number | null;
    }> | null;
  };
  spending: {
    total_price_max: number | null;
    currency: Currency | null;
    period_in_days: number | null;
  };
  merchant: {
    blocklist: string[] | null;
    allowlist: string[] | null;
  };
  order_terms: {
    require_returnable: boolean | null;
    require_cancellable: boolean | null;
  };
  notes_for_customer: string | null;
}

export interface ParsePolicyResponse {
  walletId: number;
  policy: ParsedPolicyDraft;
  missingFields: string[];
  complete: boolean;
}

export interface WalletPolicy {
  raw_instructions: string;
  products: {
    items: Array<{
      name: string;
      category: ProductCategory;
      quantity: number;
      max_price_per_item: number | null;
    }>;
  };
  spending: {
    total_price_max: number | null;
    currency: Currency;
    period_in_days: number | null;
  };
  merchant: { blocklist: string[]; allowlist: string[] };
  order_terms: {
    require_returnable: boolean;
    require_cancellable: boolean;
  };
  notes_for_customer: string;
}

export const VERDICT_STORAGE_KEY = "wallet-mock-job";

export interface DecisionEvidence {
  rule_type: "hard" | "soft";
  field: string;
  operator: string;
  expected: unknown;
  actual: unknown | null;
  status: "pass" | "fail" | "unknown";
  source: string;
  message: string;
}

export interface PolicyRule {
  field: string;
  operator: string;
  value: number | string | string[];
  currency?: string | null;
  scope?: string | null;
  period_days?: number | null;
}

export interface MockPurchase {
  description: string | null;
  amount: number | null;
  currency: string | null;
  merchant_name: string | null;
  merchant_country: string | null;
  sequence: number;
  items: Array<{
    name: string;
    category: string;
    quantity: number;
    unit_price: number;
    currency: string;
    details: string | null;
  }>;
}

export interface MockTransactionResult {
  transaction_id: string;
  reference_id: string;
  system_decision: "approve" | "decline" | "step_up";
  final_decision: "approve" | "decline" | null;
  reason_codes: string[];
  customer_message: string;
  evidence: DecisionEvidence[];
  is_final: boolean;
  human_deadline_at: string | null;
  decision_latency_ms: number;
  purchase: MockPurchase;
  customer_resolution_message?: string;
  resolved_at?: string;
}

export interface MockPurchaseGroup {
  group_id: string;
  group_name: string;
  event_count: number;
  status: string;
  results: MockTransactionResult[];
}

export interface MockJobResponse {
  job_id: string;
  wallet_id: number;
  status:
    | "awaiting_confirmation"
    | "running"
    | "awaiting_customer"
    | "completed"
    | "failed";
  created_at: string;
  updated_at: string;
  draft: {
    draft_id: string;
    status: string;
    instruction: string;
    hard_rules: PolicyRule[];
  };
  groups: MockPurchaseGroup[];
  summary: {
    total: number;
    approve: number;
    decline: number;
    step_up: number;
    awaiting_customer: number;
  };
  error: string | null;
}

export function formatValidationDetail(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (!Array.isArray(detail)) return null;

  const messages = detail.flatMap((item) => {
    if (typeof item !== "object" || item === null) return [];
    const record = item as Record<string, unknown>;
    const message =
      typeof record.msg === "string"
        ? record.msg
        : typeof record.message === "string"
          ? record.message
          : null;
    if (!message) return [];

    const rawField = Array.isArray(record.loc)
      ? record.loc.filter((part) => part !== "body").map(String).join(".")
      : typeof record.field === "string"
        ? record.field.replace(/^body\./, "")
        : "";
    const field = rawField.replace(/^policy\./, "");
    return [field ? `${field}: ${message}` : message];
  });

  return messages.length > 0 ? messages.join(" ") : null;
}

export async function readErrorMessage(
  response: Response,
  fallback: string,
): Promise<string> {
  const contentType = response.headers.get("content-type") ?? "";

  if (contentType.includes("json")) {
    const body: unknown = await response.json().catch(() => null);
    if (typeof body === "object" && body !== null) {
      const record = body as Record<string, unknown>;
      const detail = formatValidationDetail(record.detail);
      if (detail) return detail;
      if (typeof record.message === "string") return record.message;
    }
  } else {
    const body = await response.text().catch(() => "");
    if (body.trim()) return body.trim();
  }

  return `${fallback} (HTTP ${response.status})`;
}

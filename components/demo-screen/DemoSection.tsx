const CASES = [
  {
    id: "DEMO-001",
    label: "Happy path",
    amount: "CHF 20.00",
    verdict: "APPROVE",
    color: "emerald",
    note: "Inside every rule in the wallet policy — resolved instantly, no interruption.",
  },
  {
    id: "DEMO-002",
    label: "Manipulation attempt",
    amount: "CHF 299.00",
    verdict: "DECLINE",
    color: "red",
    note: "Merchant item text tries to talk the agent past the spending limit. It's read as data, never authority.",
  },
  {
    id: "DEMO-003",
    label: "Genuine unknown",
    amount: "CHF 84.00",
    verdict: "STEP UP",
    color: "amber",
    note: "Return policy is unstated for this item — a real gap in information, so the customer is asked instead of guessed for.",
  },
];

const COLOR_MAP: Record<string, string> = {
  emerald: "border-authority/40 bg-authority-dim text-authority-strong",
  red: "border-decline/40 bg-decline-dim text-decline",
  amber: "border-review/40 bg-review-dim text-review",
};

export default function DemoSection() {
  return (
    <section className="max-w-5xl mx-auto px-4 py-20">
      <p className="text-authority-strong font-medium mb-3 text-center">
        Three generated purchases, three different outcomes
      </p>
      <h2 className="text-3xl md:text-4xl font-extrabold text-ink-0 tracking-tight text-center mb-12">
        The same wallet policy, tested against fictional demo data
      </h2>
      <div className="grid md:grid-cols-3 gap-6">
        {CASES.map((c) => (
          <div
            key={c.id}
            className={`rounded-2xl border p-6 ${COLOR_MAP[c.color]}`}
          >
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-mono uppercase tracking-wider text-ink-3">
                {c.id}
              </span>
              <span className="text-sm font-semibold text-ink-2">
                {c.amount}
              </span>
            </div>
            <p className="text-lg font-bold mb-2">{c.verdict}</p>
            <p className="text-sm font-semibold text-ink-1 mb-2">
              {c.label}
            </p>
            <p className="text-sm text-ink-2 leading-relaxed">{c.note}</p>
          </div>
        ))}
      </div>
      <p className="text-center text-xs text-ink-3 mt-8">
        All merchants, purchase IDs, amounts, and descriptions are fictional.
      </p>
    </section>
  );
}

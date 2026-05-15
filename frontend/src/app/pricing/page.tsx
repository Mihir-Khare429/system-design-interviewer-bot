import Link from "next/link";
import Navbar from "@/components/layout/Navbar";

const PLANS = [
  {
    name: "Free",
    price: "$0",
    per: "/ month",
    description: "Get started and practice the fundamentals.",
    cta: "Get started",
    href: "/auth/signup",
    highlight: false,
    features: [
      { text: "3 interviews per month", included: true },
      { text: "Junior & Mid difficulty", included: true },
      { text: "All 12 problems", included: true },
      { text: "AI scorecard after each session", included: true },
      { text: "Interactive whiteboard canvas", included: true },
      { text: "Senior & Staff difficulty", included: false },
      { text: "Interview history & archive", included: false },
      { text: "Priority AI responses", included: false },
    ],
  },
  {
    name: "Pro",
    price: "$19",
    per: "/ month",
    description: "For serious interview prep — unlimited practice, all levels.",
    cta: "Start 7-day free trial",
    href: "/auth/signup?plan=pro",
    highlight: true,
    features: [
      { text: "Unlimited interviews", included: true },
      { text: "All 4 difficulty levels", included: true },
      { text: "All 12 problems", included: true },
      { text: "AI scorecard after each session", included: true },
      { text: "Interactive whiteboard canvas", included: true },
      { text: "Senior & Staff difficulty", included: true },
      { text: "Interview history & archive", included: true },
      { text: "Priority AI responses", included: true },
    ],
  },
];

const FAQS = [
  {
    q: "Can I cancel anytime?",
    a: "Yes. Cancel from your account settings at any time. You keep access until the end of your billing period.",
  },
  {
    q: "What counts as an interview on the free plan?",
    a: "Each session you start counts as one interview, whether you complete it or end it early.",
  },
  {
    q: "Do I need a GPU or local setup?",
    a: "No. The AI interviewer runs on our servers. You just need a browser and a microphone.",
  },
  {
    q: "Which problems are available on the free plan?",
    a: "All 12 problems are available on both plans. The free plan limits which difficulty levels you can select.",
  },
  {
    q: "Is there a student discount?",
    a: "Yes — email us with your .edu address and we'll comp 3 months of Pro.",
  },
];

export default function PricingPage() {
  return (
    <div className="min-h-screen bg-[#0a0a0b]">
      <Navbar />

      <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6">
        {/* Header */}
        <div className="mb-14 text-center">
          <h1 className="text-3xl font-bold text-[#e8e8e8] sm:text-4xl">Simple, honest pricing</h1>
          <p className="mt-3 text-[#71717a]">Start free. Upgrade when you need more practice.</p>
        </div>

        {/* Plans */}
        <div className="mb-20 grid gap-4 sm:grid-cols-2 sm:max-w-2xl sm:mx-auto">
          {PLANS.map((plan) => (
            <div
              key={plan.name}
              className={`rounded-xl p-7 ${
                plan.highlight
                  ? "border-2 border-green-500/40 bg-green-500/5"
                  : "border border-[#27272a] bg-[#111113]"
              }`}
            >
              {plan.highlight && (
                <div className="mb-4">
                  <span className="rounded-full bg-green-500 px-2.5 py-0.5 text-xs font-semibold text-[#0a0a0b]">
                    Most popular
                  </span>
                </div>
              )}
              <div className="mb-1 text-xs font-medium uppercase tracking-widest text-[#71717a]">
                {plan.name}
              </div>
              <div className="mb-2 flex items-baseline gap-1">
                <span className="text-4xl font-bold text-[#e8e8e8]">{plan.price}</span>
                <span className="text-[#71717a]">{plan.per}</span>
              </div>
              <p className="mb-6 text-sm text-[#71717a]">{plan.description}</p>

              <ul className="mb-8 space-y-3">
                {plan.features.map((f) => (
                  <li key={f.text} className="flex items-center gap-2 text-sm">
                    <span className={f.included ? "text-green-400" : "text-[#3f3f46]"}>
                      {f.included ? "✓" : "✕"}
                    </span>
                    <span className={f.included ? "text-[#a1a1aa]" : "text-[#3f3f46]"}>
                      {f.text}
                    </span>
                  </li>
                ))}
              </ul>

              <Link
                href={plan.href}
                className={`block w-full rounded-lg py-2.5 text-center text-sm font-semibold transition-colors ${
                  plan.highlight
                    ? "bg-green-500 text-[#0a0a0b] hover:bg-green-400"
                    : "border border-[#27272a] text-[#e8e8e8] hover:border-[#3f3f46] hover:bg-white/5"
                }`}
              >
                {plan.cta}
              </Link>
            </div>
          ))}
        </div>

        {/* Feature comparison table */}
        <div className="mb-20">
          <h2 className="mb-8 text-center text-xl font-bold text-[#e8e8e8]">Full comparison</h2>
          <div className="overflow-hidden rounded-xl border border-[#27272a]">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#27272a] bg-[#111113]">
                  <th className="px-5 py-3 text-left font-medium text-[#71717a]">Feature</th>
                  <th className="px-5 py-3 text-center font-medium text-[#71717a]">Free</th>
                  <th className="px-5 py-3 text-center font-medium text-green-400">Pro</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#27272a] bg-[#0a0a0b]">
                {[
                  ["Interviews per month", "3", "Unlimited"],
                  ["Problem library", "All 12", "All 12"],
                  ["Junior & Mid difficulty", "✓", "✓"],
                  ["Senior & Staff difficulty", "—", "✓"],
                  ["AI scorecard", "✓", "✓"],
                  ["Whiteboard canvas", "✓", "✓"],
                  ["Interview history", "—", "✓"],
                  ["Scorecard archive", "—", "✓"],
                  ["Priority AI responses", "—", "✓"],
                ].map(([feature, free, pro]) => (
                  <tr key={feature}>
                    <td className="px-5 py-3 text-[#a1a1aa]">{feature}</td>
                    <td className="px-5 py-3 text-center text-[#71717a]">{free}</td>
                    <td className="px-5 py-3 text-center text-green-400 font-medium">{pro}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* FAQ */}
        <div className="mx-auto max-w-2xl">
          <h2 className="mb-8 text-center text-xl font-bold text-[#e8e8e8]">
            Frequently asked questions
          </h2>
          <div className="space-y-4">
            {FAQS.map((faq) => (
              <div key={faq.q} className="rounded-xl border border-[#27272a] bg-[#111113] p-5">
                <h3 className="mb-2 font-medium text-[#e8e8e8]">{faq.q}</h3>
                <p className="text-sm text-[#71717a] leading-relaxed">{faq.a}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

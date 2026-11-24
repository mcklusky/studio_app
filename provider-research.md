# Liberia Provider and Policy Discovery

**Status:** Preliminary public-source review; not a provider approval or commercial quote  
**Reviewed:** 2026-11-24  
**Scope:** Payment collection, customer messaging, local currency context, and decisions needed before the estimate can be fixed

## Summary

- Liberia uses both the Liberian dollar (LRD) and United States dollar (USD) as legal tender. The system will support both concurrently, with USD retained as the chosen reporting base.
- The Central Bank of Liberia (CBL) oversees payment systems in Liberia, including retail payment systems and the National Electronic Payment Switch. Public information reviewed here does not establish a merchant API, pricing, or onboarding eligibility for this business.
- Twilio publicly lists outbound SMS service to Liberia, but its listed per-segment price is high enough that it should be compared against local/operator options before selection.
- Meta's WhatsApp Business Platform offers a Cloud API. WhatsApp fees vary by recipient market and message category; an exact Liberia cost and the business's account eligibility still need confirmation. Twilio adds its own per-message fee when used as the WhatsApp provider.
- No payment gateway has been verified as suitable for a Liberia-registered merchant accepting LRD and USD. Provider availability, settlement currency, fees, API access, onboarding, and sandbox access must be confirmed in writing before the integrated-payment scope and fixed quote are approved.

## Preliminary provider matrix

| Need | Candidate / evidence | What is verified | Still needs written confirmation |
|---|---|---|---|
| Mobile-money collection | Contact the business's mobile network operator(s) and existing bank/acquirer first | CBL supervises private retail payment systems and the National Electronic Payment Switch | Operator/bank merchant eligibility, API or hosted checkout, LRD/USD acceptance, settlement currency, fees, callbacks, refunds, and sandbox |
| Card and bank collection | Existing business bank/acquirer; ask for hosted checkout or an approved payment aggregator | No provider was confirmed for this Liberia-registered business in this review | Merchant registration, card brands, local/international card support, USD/LRD settlement, chargebacks, fees, and integration access |
| SMS | Twilio is a technically reachable candidate | Twilio's Liberia pricing page lists outbound SMS at **US$0.2677 per segment** for international numbers and alphanumeric sender IDs; international numbers start at **US$1.15/month**. Carrier fees may be additional and prices can change. | Test delivery to the actual local carriers, sender ID registration, throughput, delivery receipts, current quote, and comparison with local SMS aggregators |
| WhatsApp | Meta WhatsApp Business Platform Cloud API (direct); Twilio as an alternative integration provider | Meta documents programmatic messaging and webhooks. Business-initiated messages are charged when delivered, with rate based on category and recipient market. Twilio lists a **US$0.005/message** handling fee in addition to Meta's applicable fees. | Verify business/phone-number onboarding, Liberia-specific Meta rate card, utility-template approval, consent rules, and whether direct Meta or Twilio is preferable |
| Email | Select a transactional email service after domain ownership is confirmed | No email provider or account was verified in this review | Domain authentication (SPF/DKIM/DMARC), account eligibility, delivery limits, pricing, and bounce/complaint handling |

### Cost note

At Twilio's listed **US$0.2677 per outbound SMS segment**, 1,000 one-segment messages would be about **US$267.70 before any additional carrier fees**. This is a published rate snapshot, not an offer or a recommendation to select Twilio. Long messages can consume multiple segments.

## Currency and rate policy

The CBL currency page says LRD is Liberia's official currency and USD is also legal tender and used alongside LRD. This supports the product requirement for concurrent LRD/USD transaction entry; it does not determine the exchange-rate policy for accounting reports.

Before implementation, the owner/accountant should approve:

1. The owner has selected an authorized owner/admin-entered daily rate as the provisional workflow. The accountant must approve the rate source (for example, a named published reference source or another documented source).
2. Which date/time the rate is tied to (transaction, payment, posting, or another approved point).
3. Who may enter/approve a rate and how corrections are audited.
4. Treatment of realized/unrealized FX differences and cross-currency payment allocations.

Do not treat the CBL's role as a confirmation that it publishes an appropriate operational rate for this business; verify a usable rate series and its accounting suitability separately.

## Decisions requiring owner/accountant input

- Applicable taxes, invoice/receipt requirements, and whether tax registration applies.
- The owner selected moving weighted-average inventory costing as the provisional MVP method; the accountant must approve it and the allocation of shipping/other landed costs.
- Revenue recognition for deposits and custom orders; refunds, returns, voids, and discounts.
- Treatment of provider fees, FX gains/losses, and cross-currency debt settlement.
- Organization time zone. `Africa/Monrovia` is the proposed setting, subject to owner confirmation.
- Customer channels and payment methods actually used, existing merchant/bank relationships, and whether the business already has merchant accounts. Do not share account numbers, credentials, or secrets in this planning document.

## Recommended next actions

1. Before financial reporting is treated as authoritative, ask the accountant to approve the owner/admin-entered daily FX rate source/effective-time rule and moving weighted-average costing details.
2. Proceed with MVP planning and implementation using manual payment recording; provider verification does not block this release.
3. Before a later integration release, ask which mobile-money services and banks customers use and which merchant accounts the business can access.
4. Request written merchant/API/sandbox/fee answers from those providers; compare gateways against direct operator and bank options.
5. Test SMS delivery and sender registration on local networks; compare Twilio's published rate with eligible local alternatives. Select a WhatsApp route only after checking account eligibility, Liberia pricing, templates, and total cost.
6. Revise the future integration estimate after provider verification.

## Ready-to-send provider questions

Send these to the business's bank, mobile-money provider, or payment gateway. Ask for written answers and a current fee schedule:

> We are planning a business management system for a business registered and operating in Liberia. Can you onboard this business for merchant payment collection? Which mobile-money networks, cards, and bank methods can customers use? Can we accept LRD and USD, and in which currency/currencies will funds settle to our business account? Please provide your merchant/API documentation, hosted-checkout options, sandbox access, transaction and settlement fees, minimum/maximum transaction amounts, refund/chargeback terms, settlement timing, webhook signing and retry documentation, and onboarding requirements. Please confirm whether these capabilities are available to a Liberia-registered business.

For SMS and WhatsApp providers, request:

> Please confirm delivery to the mobile networks our customers use in Liberia, required sender ID/phone-number registration, current message pricing and any carrier surcharges, delivery reports, throughput limits, opt-out support, and sandbox/test options. For WhatsApp, confirm business and phone-number onboarding, approved transactional templates, current Liberia utility-message pricing, and all provider fees in addition to Meta charges.

For transactional email, request domain authentication instructions, sending limits, bounce/complaint handling, delivery reporting, support terms, and recurring/usage fees.

## Accountant sign-off checklist

Ask the accountant to provide a written policy for the following before the financial calculations are treated as authoritative:

- The approved daily LRD/USD rate source, who enters/approves it, its effective date/time, and how historical corrections are recorded.
- Rounding/precision and exchange-rate application for sales, purchases, payments, and balances settled in a different currency.
- The selected moving weighted-average stock costing method, including how shipping and other landed costs are allocated and when cost of goods sold is recognized.
- Applicable tax registration, tax calculation, required invoice/receipt fields, and invoice numbering.
- How order deposits, refunds, returns, discounts, provider fees, and realized/unrealized FX differences affect revenue and profit reports.

## Sources

- [Central Bank of Liberia — Currency](https://www.cbl.org.lr/general/currency) — LRD official currency and USD legal tender used alongside it.
- [Central Bank of Liberia — Payment Systems Department](https://www.cbl.org.lr/general/payment-systems-department) — oversight responsibilities, including private retail payment systems and NEPS.
- [Twilio — Liberia SMS pricing](https://www.twilio.com/en-us/sms/pricing/lr) — displayed Liberia route, per-segment pricing, and number pricing; pricing can change.
- [Meta — WhatsApp Business Platform](https://developers.facebook.com/documentation/business-messaging/whatsapp/about-the-platform) — Cloud API capabilities and webhooks.
- [Meta — WhatsApp pricing](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing) — delivered-message charging and market/category-based rates.
- [Twilio — WhatsApp pricing](https://www.twilio.com/en-us/whatsapp/pricing) — Twilio handling fee plus Meta fees; published pricing can change.

## Limitations

This is desk research based on public information available on the review date. It does not confirm provider contracts, merchant acceptance, local regulatory compliance, account approval, service quality, or negotiated rates. Provider support and prices must be reconfirmed directly before procurement or a binding quotation.

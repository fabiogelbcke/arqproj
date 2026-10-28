# Costs per office (recurring)

**28 October 2026 · analysis for discussion, not decisions** · part of
[What Unio costs](README.md)

What each office adds to our monthly bill, and what grows with revenue (payment
fees, taxes). Fixed costs are in [fixed.md](fixed.md); one-off costs, including
building each extra, in [one-time.md](one-time.md). Every amount names its
currency, monthly unless marked; US$1 = R$5.50.

## As it is today

Files stay in **the office's own Google Drive**, so storage costs us nothing.
What grows with each office:

| Item | Per office, per month | Notes |
| --- | --- | --- |
| Download traffic | US$1.20–3.60 | The page streams files through Cloud Run: ~US$0.12/GB to the internet, for 10–30 GB a month. |
| Update emails | ~US$0.01–0.20 | A few hundred emails a month, once on a paid Resend plan. |
| Database and compute | ~US$0 | Until the database's next size ([fixed.md](fixed.md)). |
| **Total** | **~US$1.50–4 (R$8–22)** | The simulation gives each plan its own traffic: 5, 20 and 60 GB a month (R$4, R$14 and R$40 an office), R$14 on average. |

## Extras an office could add

Options, not decided. Each could be in a tier or sold as an add-on
([pricing-and-trials.md section 2](../pricing-and-trials.md#2-what-to-charge)).
The cost of building each is in [one-time.md](one-time.md#building-the-extras).

| Extra | Cost to us per office, per month | Source |
| --- | --- | --- |
| **Our own file storage** (Cloudflare R2) instead of Drive | US$0.75–2.25 for 50–150 GB stored. Downloads from R2 are free, so this **replaces** the US$1.20–3.60 of downloads above: about the same cost overall. | [storage-strategy.md](../storage-strategy.md#c-our-own-storage) |
| Own storage on Google Cloud Storage instead | ~US$5.90 for 100 GB stored and 20 GB downloaded (also replacing the downloads above) | same |
| **More cloud providers** (OneDrive, Dropbox) | ~US$0 | [storage-strategy.md](../storage-strategy.md#b-more-cloud-providers) |
| **WhatsApp updates** (Meta Cloud API) | ~US$1.30–2.60 for a busy office (160–320 utility messages at ~US$0.008 each); +US$0.005 a message through Twilio. The simulation uses US$2. | [whatsapp-updates.md](../whatsapp-updates.md#cost) |
| **AI assistant in the panel** | ~US$0.10–0.50 (1,000 questions a month across all offices cost US$10–20). The simulation uses US$0.30. | [ai-for-the-business.md](../ai-for-the-business.md#1-customer-support) |
| **The office's own domain** for its pages | ~US$0 (an hour of setup, [one-time.md](one-time.md)) | — |

## Payment fees

| Way of charging | Per payment | When |
| --- | --- | --- |
| Pix by hand | ~R$0 | The pilot, up to ~20 offices |
| Asaas (recurring Pix, boleto) | Pix R$0.99–1.99 received; boleto ~R$2–3, charged only when paid | From 15–20 paying offices. The simulation uses R$1.99 a month per office from 20. |
| Stripe (card) | ~2.9% + a fixed fee | Only if card or international offices matter |

Details in [pricing-and-trials.md section 3](../pricing-and-trials.md#3-taking-payments-in-brazil).

## Taxes (grow with revenue)

**The largest per-office cost.** Under Simples Nacional, a software service
company pays a share of revenue that rises with the last 12 months' revenue:

| Revenue in the last 12 months | Anexo III (effective) | Anexo V (effective) |
| --- | --- | --- |
| Up to R$180,000 (~70 offices at R$203 on average) | 6% | 15.5% |
| R$180,000–360,000 | 6–8.6% | 15.5–16.8% |
| R$360,000–720,000 | 8.6–11.1% | 16.8–18.1% |

Anexo III applies when payroll, including the owner's *pró-labore*, is at least
28% of revenue (the *Fator R*); otherwise Anexo V. A *pró-labore* is itself a
cost (with INSS on it), so the cheaper annex isn't free. ISS is included in
Simples. **Confirm the regime and rate with an accountant before setting
prices**: it moves the margin by about 9 points ([margin.md](margin.md)).

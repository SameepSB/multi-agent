---
title: 'Technical research: Global flight and hotel data provider selection'
type: technical
topic: Global flight and hotel data provider selection
decision: Choose a globally applicable live flight and hotel search data approach for a no-booking travel comparison app
source: native research
status: complete
preset: standard
validation: normal
claims_verified: 0
claims_unverified: 9
created: 2026-10-10
updated: 2026-10-10
---

# Global flight and hotel data provider selection

**Decision this research serves:** Choose a globally applicable live flight and hotel search data approach for a no-booking travel comparison app.

## Executive summary

**Recommended path:** Apply to Skyscanner's Travel API as the primary production candidate because its official partner page describes one Travel API for both flights and hotels. Its partner approval, India route/property coverage, and commercial terms are not confirmed publicly in the evidence reviewed; confirm those before implementation [1].

For an immediate, disposable proof of concept, SerpApi offers Google Flights and Google Hotels search endpoints and currently lists a free allowance of 250 searches/month. That is a search-engine-results service, not a direct airline or hotel inventory API. Treat its output as discovery results, not guaranteed or bookable quotes, and do not use it in production until its data-use and legal terms are confirmed [7][8][9].

Duffel is a credible flight API fallback with a self-serve test mode, but its own documentation warns that test offers are not realistic schedules or prices; its Stays product currently directs prospective users to contact sales [2][3][4]. Booking.com's accommodation Demand API is another later hotel option, but access requires managed-affiliate status and a signed contract [5][6].

No candidate can be called globally complete from public documentation alone. Before committing, get written answers and run searches for both domestic and cross-border routes involving India, plus hotel searches in India and another target market.

## Requirements and decision method

The user confirmed: worldwide destinations, including India; live search results/prices; no in-app booking for the first release; prioritize self-serve or free-to-try access, then global coverage, integration effort, and freshness.

Hard gates for a production provider:

- Licensed, documented API access for the intended displayed data and search/referral product.
- Both flight and lodging results in the first target scope, or a deliberate two-provider arrangement.
- Verified route, country, currency, and property coverage for India and at least one non-India market.
- Explicit treatment of price timestamp, taxes/fees, availability, and user redirection.
- A search/compare experience that does not require this app to book on the user's behalf.

The score below is a directional fit assessment, not a claim of independently measured coverage. Weights: free/self-serve start 35%, likely global fit 30%, integration fit 20%, freshness/availability semantics 15%. No in-app booking is a hard gate, not a preference score. An unknown is not evidence of coverage.

| Candidate | Access/start (35%) | Global fit (30%) | Integration (20%) | Freshness evidence (15%) | Weighted fit / 5 | Decision |
|---|---:|---:|---:|---:|---:|---|
| SerpApi Google Flights + Hotels | 5 | 3 | 5 | 4* | 4.25 | Best limited prototype only; production data rights and source/availability semantics need review. |
| Skyscanner Travel API | 2 | 4* | 5 | 3* | 3.35 | Best production application to make first; access, country coverage, and terms need confirmation. |
| Duffel Flights + Stays | 4* | 3* | 3 | 3* | 3.35 | Strong flight integration test path; not yet a confirmed global flights-and-hotels solution. |
| Booking.com Demand API | 1 | 4* | 1 | 3* | 2.20 | Hotel-only fallback after managed-affiliate approval; does not satisfy the flight requirement alone. |

`*` Provisional score based on product scope or request-time search capability, not independently validated freshness or market coverage. SerpApi's high prototype score does not clear the production data-rights hard gate. Production use is blocked until all hard gates are confirmed.

## Candidate findings

### Skyscanner Travel API — production candidate

Skyscanner's partner product page describes its Travel API for Flights, Hotels, and Car Hire, positioning it for businesses building their own travel search experience [1]. That makes it the cleanest one-provider candidate for the requested search-and-compare scope. The page is an application/partner path, not proof that an individual developer will receive credentials, a free tier, or access to every origin/destination.

**Ask Skyscanner before building:** Is a small comparison app eligible? Does API access cover flight and hotel price search with redirect links but no booking? What are fees/affiliate requirements, supported markets and currencies, India-origin and India-destination coverage, attribution requirements, and price/availability refresh semantics?

### SerpApi Google Flights + Hotels — prototype-only unless rights are cleared

SerpApi documents separate Google Flights and Google Hotels search endpoints. Its parameters include country localization (`gl`) and currency selection; Google Hotels also supports requested check-in/check-out dates [7][8]. Its pricing page, accessed 2026-10-10, lists a Free plan with 250 searches/month and 50 searches/hour; Starter is listed at $25/month for 1,000 searches [9].

These are scraped Google search results, as SerpApi's own product pages describe them [7][8]. This can help validate the UI and adapter shape quickly, but it does not establish that displayed rates remain available at the seller, include all taxes/fees, or are suitable for redistribution. The free plan lists no Legal Shield [9]. Obtain written terms/legal approval before product use; prefer an authorized travel partner API for production.

### Duffel — flight test path, live coverage to verify

Duffel advertises access to its Flights API and 300+ airlines [2]. Developers can sign up, create test tokens, and use a test mode. Its docs explicitly warn that the reliable Duffel Airways sandbox does **not** provide realistic schedules or prices, so test mode cannot validate the core live-price promise [3]. A live token is enabled only after account activation, and the dashboard is the stated place to inspect airlines live with Duffel [4].

Duffel also markets Stays as access to millions of properties, but its Stays page currently directs interested users to contact Duffel [4]. Public material reviewed here does not prove that an individual account gets live Stays search access, or that coverage is complete for India. Use Duffel as a flight alternative or later production comparison, conditional on written route coverage and live Stays access.

### Booking.com Demand API — hotel-only, partner-gated

Booking.com documents accommodation content, search, availability, and order capabilities, including a search-and-redirect flow [5]. Before testing, however, its prerequisites require registration as a **Managed Affiliate Partner**, access to Partner Centre provided by an account manager after signing the agreed contract, and generated credentials [6]. It is therefore not the quickest self-service option and cannot supply flight prices by itself.

## Cross-dimension insight

“Live” can mean either an up-to-date search-engine result or an offer from a travel supplier/authorized distribution API. Those are not interchangeable. For a trustworthy comparison, show provider, retrieved time, currency, taxes/fees status, and availability caveat per quote; never silently fill missing live results with the application's synthetic estimates.

## Recommendation and next steps

1. **First choice for production discovery:** Apply to Skyscanner Travel API for flight + hotel search/referral access. Do not start a large integration until access, allowed display/referral model, pricing, and market coverage are confirmed.
2. **Immediate technical experiment (optional):** Use SerpApi's free quota for a short-lived UI/API proof only. Keep this behind a provider adapter and label it clearly as search-engine-derived. Avoid persisting/reusing search results unless the provider's terms explicitly allow it.
3. **Fallback:** Sign up for Duffel test mode to learn the flight request/response lifecycle, but use fixtures for believable test data and do not represent Duffel Airways sandbox prices as live market prices. Check live India routes and Stays availability after account activation.
4. **Hotel alternative:** Apply for Booking.com's Managed Affiliate Partner program if Skyscanner access is declined or does not cover required hotel markets.
5. **Pilot acceptance checks:** Try at least Delhi–Mumbai, Mumbai–New York, London–Delhi, and hotel dates in Delhi and London; compare displayed amount/currency with the provider's click-through destination; record taxes/fees, timestamp, availability, and which suppliers returned results. Do not assert worldwide availability unless each supported market is explicitly established.
6. **Architecture changes before genuine quotes:** Keep provider credentials on the backend; add passenger count, room/guest count, currency and market inputs; support non-USD `Money`; distinguish live offers from estimates in the result contract; retain provider and observation time; and return “unavailable” rather than synthesizing a quote on live-provider failure. The current travel result shape represents one airfare and a nightly hotel amount, and the request contract fixes currency to USD, so it needs broadening for global live comparisons.

**Strongest argument against the recommendation:** Skyscanner may not approve this app or may impose commercial/traffic requirements, and the public product page does not prove India coverage or disclose terms. If rejected, there is no evidence-backed single replacement that guarantees both global flights and hotels with effortless free production access; proceed with a split-provider plan only after confirming rights and coverage.

## Open questions

- Will Skyscanner approve the app and grant both API product verticals, and what are its pricing/affiliate and attribution terms?
- Which exact flight markets, airlines, hotel markets, and currencies are enabled for the chosen account, especially for India?
- May provider results and price attributes be stored, cached, compared, and displayed to end users? What are the data-retention requirements?
- Are displayed fares inclusive of taxes and mandatory fees, and how often must availability be revalidated?

## Source appendix

All pages accessed 2026-10-10. Most provider documentation pages do not state a publication date; they are treated as live documentation, not dated research papers.

| # | Claim/finding supported | Publisher | Pub date | Accessed | Confidence |
|---|---|---|---|---|---|
| 1 | Skyscanner markets a Travel API for Flights, Hotels and Car Hire and a travel-search experience. | [Skyscanner Partners](https://www.partners.skyscanner.net/product/travel-api) | Not stated | 2026-10-10 | Medium, unverified independently; coverage and access conditions remain unverified. |
| 2 | Duffel advertises a Flights API and 300+ airlines. | [Duffel](https://duffel.com/flights) | Not stated | 2026-10-10 | Medium, unverified independently; market-specific coverage unverified. |
| 3 | Duffel test mode is sandbox; Duffel Airways test schedules/prices are not realistic. | [Duffel Documentation](https://duffel.com/docs/api/overview/test-mode/airline-sandboxes) | Not stated | 2026-10-10 | Medium, unverified independently. |
| 4 | Duffel Stays markets millions of properties and invites prospective users to contact Duffel. | [Duffel Stays](https://duffel.com/stays) | Not stated | 2026-10-10 | Medium, unverified independently; regional coverage unverified. |
| 5 | Booking.com Demand API supports accommodation search/availability and search-and-redirect. | [Booking.com Demand API overview](https://developers.booking.com/demand/docs/getting-started/overview) | Not stated | 2026-10-10 | Medium, unverified independently. |
| 6 | Booking.com testing requires Managed Affiliate Partner status and contract/Partner Centre access. | [Booking.com API prerequisites](https://developers.booking.com/demand/docs/getting-started/prerequisites) | Not stated | 2026-10-10 | Medium, unverified independently. |
| 7 | SerpApi's Google Flights endpoint exposes localization/currency and describes scraping Google Flights results. | [SerpApi Google Flights API](https://serpapi.com/google-flights-api) | Not stated | 2026-10-10 | Medium, unverified independently. |
| 8 | SerpApi's Google Hotels endpoint describes scraping Google Hotels results and accepts market/currency and stay dates. | [SerpApi Google Hotels API](https://serpapi.com/google-hotels-api) | Not stated | 2026-10-10 | Medium, unverified independently. |
| 9 | SerpApi currently lists a free 250-search/month tier and no Legal Shield on that tier. | [SerpApi pricing](https://serpapi.com/pricing) | Live pricing page | 2026-10-10 | Medium, unverified independently; recheck before signup. |

## Staleness map

- The provider pages do not state publication dates, so review intervals are anchored to the access date (2026-10-10), not represented as publication dates.
- Recheck pricing by **2027-01-10** (3 months); recheck API eligibility, coverage, and terms by **2027-04-10** (6 months). Confirm both directly before implementation or launch.

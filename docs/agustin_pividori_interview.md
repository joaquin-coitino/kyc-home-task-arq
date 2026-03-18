---
name: Agustín Pividori interview — identity verification landscape
description: Notes from a conversation with Agustín Pividori (FinCrime lead, Personal Pay) on Jumio, alternative providers, and LATAM KYC requirements
type: reference
---

# Interview Notes — Agustín Pividori, Personal Pay

**Role:** Leads FinCrime at Personal Pay (a fintech and Jumio customer)

---

## Jumio at Personal Pay

- Selected before Agustín joined (March) — decision driven primarily by **cost**
- Pricing: **$0.35 per onboarding**, **$0.05–$0.03 per challenge** (volume-based)
- Approximately **4× cheaper than FaceTec**
- Pain points:
  - High minimum contract requirements; enterprise-focused with long-term commitments
  - Document reader is **overly sensitive** → causes user friction and high abandonment rates during onboarding
  - False positives were a concern before SLA negotiations; now within agreed limits
- Recommends testing Personal Pay's current flow to experience the UX issues firsthand

---

## Competitor Landscape

### FaceTec
- Main competitor to Jumio
- Used extensively at **Mercado Libre** and banks
- Better market presence and reputation than Jumio
- ~4× more expensive than Jumio

### Didit — strongly recommended by Agustín
- **Charges only for successful transactions**, not attempts (key differentiator)
- Better designed platform and integration experience
- Suitable for smaller volumes initially
- Includes **biometric verification in a single solution**
- Also provides **anti-money laundering checks** (unlike Jumio)
- Contact: **Héctor at Didit** — has been trying to get into Personal Pay; Agustín willing to make an introduction

---

## Regulatory & Technical Requirements

### Argentina — BCRA 7783
Three mandatory steps:
1. Document verification against physical ID
2. Biometric face matching with document photo
3. **Face verification against RENAPER** (government biometric database) — mandatory for legal compliance
   - Requires document transaction number (sensitive data)
   - Recommended similarity threshold: **65–70%**
   - Prevents professional document forgery attempts

### Brazil
- Similar requirements to Argentina with their own government bureau integration

### Paraguay
- No government biometric database currently available

---

## Document Support

- **DNI (national ID)** is the standard and only universally required document type across all financial institutions in LATAM
- Passport, driver's license rarely supported by financial institutions
- Aligns with our dataset: ID_CARD is 86% of all attempts

---

## Regional Landscape & Future Trends

- **Government digital identity apps** exist in UAE and Saudi Arabia (direct auth via government platform) — not yet in LATAM
- **Passkey technology** on radar but not implemented; still requires initial document verification for onboarding
- **Money mule fraud** remains a concern across all verification methods

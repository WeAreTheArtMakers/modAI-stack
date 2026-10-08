# Incident Escalation Guidelines

> **FICTIONAL DEMO DOCUMENT.** Atlasnova Yazılım A.Ş. is an imaginary company. The roles, timings and tools in this document were written only for a modAI product demonstration; they do not belong to any real organization and are not presented as legal or regulatory requirements.

- **Document ID:** CS-PRS-004
- **Version:** 2.2 (current)
- **Effective date:** 15 February 2026
- **Owner:** Customer Support and Site Reliability

## 1. Scope

These guidelines describe how customer-reported incidents for AtlasDesk Cloud are escalated inside Atlasnova. Customer-facing response targets are defined in the Customer Support SLA (CS-SLA-001).

## 2. Classification

The support engineer on duty classifies each incident as Severity 1–4 using the definitions in CS-SLA-001. The Incident Commander may raise or lower the severity later.

## 3. Escalation rules

- **Severity 1:** escalate to the on-call **Incident Commander** within **15 minutes** of classification, using the PagerAtlas on-call tool.
- **Severity 2:** escalate to the **Support Team Lead** if there is no progress within **2 hours**.
- **Severity 3 and 4:** handled by the support team; escalate to the Team Lead only on customer request.

## 4. Communication during Severity 1

- Update the public status page every **30 minutes**.
- Send the customer a direct update every 2 hours (see CS-SLA-001).
- Do not share internal root-cause details before the postmortem is approved.

## 5. After a Severity 1 incident

A written **postmortem** is published within **5 business days** after the incident is resolved. It includes a timeline, root cause and follow-up actions with owners.

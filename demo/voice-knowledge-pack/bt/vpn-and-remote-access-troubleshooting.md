# VPN and Remote Access Troubleshooting Guide

> **FICTIONAL DEMO DOCUMENT.** Atlasnova Yazılım A.Ş. is an imaginary company. The procedures, limits and names in this document were written only for a modAI product demonstration; they do not belong to any real organization and are not presented as legal or regulatory requirements.

- **Document ID:** IT-KB-012
- **Version:** 4.2 (current)
- **Effective date:** 2 February 2026
- **Owner:** IT Operations

## 1. Before you connect

Use the **AtlasConnect** VPN client installed on your company laptop. Every connection requires multi-factor authentication (MFA) with the company authenticator app. Codes from the app expire after **30 seconds**. Never share an MFA code with anyone, including IT staff.

Email and the Atlas HR Portal work without VPN. All other internal applications require an active VPN connection.

## 2. Session rules

- You can be connected from at most **2 devices at the same time**.
- An idle session is disconnected after **30 minutes** without traffic.
- Every session ends after **12 hours**; you must sign in again with MFA.

## 3. Common problems

### 3.1 The connection drops every few minutes

1. Open AtlasConnect **Settings** and switch the protocol from UDP to **TCP mode**.
2. If you are at home, check that your router MTU is set to **1400**.
3. Restart the AtlasConnect client and connect again.

### 3.2 "Authentication failed" after entering the MFA code

Check that your laptop clock is set automatically. A clock that is more than 1 minute off makes codes invalid.

### 3.3 Error 809 on hotel or public networks

Some public networks block VPN traffic. Switch to TCP mode (see 3.1). If the error continues, use your phone's mobile hotspot.

### 3.4 Connected, but internal sites do not open

Disconnect, run **Repair DNS** from the AtlasConnect menu and connect again.

## 4. Still not working?

Open a ticket in **Atlas Destek** with the category **"Remote Access"**. Include the error code and the time of the failure. Do not include passwords or MFA codes in the ticket. Response times follow the IT Support and Escalation Procedure (BT-PRS-005).

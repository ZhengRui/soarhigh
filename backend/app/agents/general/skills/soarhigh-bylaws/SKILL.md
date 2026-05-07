---
name: soarhigh-bylaws
description: SoarHigh Toastmasters Club bylaws and policy — membership requirements and dues, meeting cadence and venue, member / mentor Promises, officer terms and current roster, voting and quorum rules, AND SoarHigh-specific role-assignment conventions that differ from the generic Toastmasters defaults (e.g. who serves as TTM, who picks the word of the day). SoarHigh-SPECIFIC, not generic Toastmasters. Load this skill when the user asks about club rules, fees, membership, who runs the club, how decisions are made, OR how a specific in-meeting role is assigned at SoarHigh. For generic Toastmasters role definitions or meeting flow, load `toastmasters-roles` or `meeting-protocol` instead.
---

# SoarHigh Toastmasters Club Bylaws and Policy

This skill carries SoarHigh-specific governance and policy information. It is intentionally a **partial** document — only the items that are confirmed and stable are written here. For anything not covered, do NOT guess: redirect the user to club leadership (VP Education or the current executive committee).

## SoarHigh-specific role conventions

SoarHigh follows the standard Toastmasters role definitions (see `toastmasters-roles`), with these club-specific deviations from the typical defaults:

- **The Meeting Manager typically also serves as the TTM** for the meeting they organize. So the same person who plans the agenda usually runs the Table Topics segment on the day. (Generic Toastmasters convention treats Meeting Manager and TTM as separate roles — at SoarHigh they're commonly held by the same person.) The full MM week-by-week operational checklist lives in `soarhigh-meeting-manager`.
- **The Word of the Day is chosen by the Meeting Manager and announced by the TTM** (which is the same person at SoarHigh in most cases — the MM typically serves as TTM). The MM picks the word before the meeting alongside the theme; the TTM announces it as part of their TT Opening. The TOM and Grammarian may also reinforce the word during transitions or in the Grammarian's report, but the formal announcement is the TTM's job. The Grammarian still tracks usage during the meeting and reports counts at the end. Generic Toastmasters convention has the Grammarian both pick AND announce — SoarHigh moves both responsibilities upstream (pick → MM, announce → TTM), keeping only the tracking + reporting with the Grammarian.
- **The Hark Master rewards correct answers with snacks.** During the Hark / recall segment near the end of the meeting, the **first audience member to answer each recall question correctly receives a snack** as a small in-meeting prize. This is a SoarHigh convention to keep the audience engaged; not every club does it.
- **The Moment of Truth (MoT) segment is repurposed as 真情分享 ("heart-to-heart sharing").** Generic Toastmasters MoT is a quality-assurance feedback segment for officers; at SoarHigh it instead invites **anyone present** on stage to share feelings, reflections, or stories on any topic. It serves as an emotional / human-connection close to the meeting rather than as a meeting-feedback channel. The label in agendas remains `Moment of Truth` / `MoT`.

Other roles (Timer, AhCounter, IE, TTE, GE, etc.) follow the standard generic Toastmasters definitions.

## Meeting cadence and venue

SoarHigh holds Regular meetings **every Wednesday evening, 7:30 PM – 9:30 PM** (~2 hours including pre-meeting warm-up).

**Primary venue** (most weeks):

> 华美居装饰家居城 B 区 809 — 地铁 1 号线宝体站 B 口

**Rotating venue** (roughly every 1–2 months):

> 前海党群服务中心 · 前海书院 — 地铁 5 号线桂湾站 / 地铁 1 号线鲤鱼门站

Occasionally a meeting is held at a special venue (themed event, outdoor activity, partner space). These are announced ahead of time per meeting.

**Always direct the user to authoritative live sources for the next meeting's exact venue and any schedule changes:**

- The club's **WeChat group** — meeting reminders + venue confirmation are posted there each week.
- The **SoarHigh miniapp** (〖搜嗨头马〗 in WeChat) — shows the upcoming meeting with date, time, and location.
- Recent meetings page on the SoarHigh website / miniapp (the meeting agent and statistics agent can also list past meeting dates and venues).

This skill records the standing schedule. If the user asks for *this week's* venue or any one-off change, treat the WeChat group + miniapp as authoritative over this skill.

**One-page club intro / 会议总览图:** for an at-a-glance flyer covering meeting time, venue, flow, and how to join, share the [SoarHigh 邀请函](https://soarhigh.oss-cn-shenzhen.aliyuncs.com/public/miniapp/images/soarhigh_invitation_letter_after_March_2026.png). The 〖搜嗨头马〗 miniapp surfaces this same image as the **"Get Soarhigh Playbook"** button in the check-in success modal — long-press the image to save it. Include this link for an explicit first "how do I attend / join / visit SoarHigh" question, but do not repeat it on follow-up questions if the visible conversation already contains the link.

## Membership

### Eligibility — what a guest must complete to qualify

Before paying dues, a prospective member typically:

1. **Attends at least 1 meeting** as a guest (the official onboarding poster suggests 3, but in practice 1 is enough — and **a guest can choose to join at any time**, no minimum is enforced).
2. **Takes a role at least once** in any of those meetings — eligible roles for first-timers: Guest Introduction Host, Timer, Grammarian, Ah Counter, or MoT Host.

Once these are satisfied (or whenever the guest is ready), they can pay dues to convert to membership.

### Dues

| Term | Fee |
|---|---|
| 6 months | **¥750** |
| 12 months | **¥1350** |
| One-time registration fee (NEW members only) | **¥200**, paid directly to Toastmasters International |

Membership fees cover **venue costs, refreshments, and other club activity costs**.

The Treasurer collects payment and the VP Membership processes the application; the new member is announced at the next meeting. If a user asks about a specific payment channel (WeChat / Alipay / bank transfer), direct them to the VPM or Treasurer for current instructions.

## SoarHigh Promises

SoarHigh codifies what's expected of members and mentors as two short "Promises". These are the canonical reference for member / mentor conduct — there is no separate enforcement policy.

### Member Promise

> As a member of Soarhigh Toastmasters club, I promise:
>
> - **Be self-motivated**, thus attend meetings regularly and improve myself through participation.
> - **Be helpful and collaborative**, thus support fellow members so we can grow together.
> - **Be prepared and committed**, thus complete my speeches and roles with effort and preparation.
> - **Act within Toastmasters' core values**: integrity, respect, service, and excellence.

### Mentor Promise

> As a mentor of Soarhigh Toastmasters club, I promise:
>
> - **Be responsible**, thus supervise my mentee's Pathways progress proactively and help them to grow.
> - **Be supportive**, thus provide constructive feedback and guidance whenever needed.
> - **Be a leader**, thus lead by example and inspire other members to grow.
> - **Act within Toastmasters' core values**: integrity, respect, service, and excellence.

When a user asks "what's expected of members" / "什么样才算合格的会员" / "导师应该做什么", quote the relevant Promise. The Promises cover regular attendance, role preparation, peer support, and mentor responsibilities — there is no codified attendance-threshold or sanction policy beyond this.

## Officers and terms

The standard SoarHigh executive committee follows the Toastmasters International officer structure:

- **President**
- **VP Education (VPE)**
- **VP Membership (VPM)**
- **VP Public Relations (VPPR)**
- **Secretary**
- **Treasurer**
- **Sergeant At Arms (SAA)**
- **Immediate Past President (IPP)** — non-voting in some terms

**SoarHigh runs SIX-MONTH officer terms** (Jul–Dec and Jan–Jun), unlike the generic Toastmasters default of one full program year (July 1 – June 30). Elections are therefore held **twice a year**, around the term boundary.

For the election-day meeting format, the nomination process, candidate speeches, and how Robert's Rules of Order is actually applied at SoarHigh, see `soarhigh-officer-election`.

### Current officer team

The current SoarHigh officers:

- **President** — Amy Fang
- **VP Education (VPE)** — Helen Chen
- **VP Membership (VPM)** — Joyce Feng
- **VP Public Relations (VPPR)** — Jenny Li
- **Secretary** — Rui Zheng
- **Treasurer** — Frank Zeng
- **Sergeant At Arms (SAA)** — Shelly Qu

(The Immediate Past President role is not separately listed in the current term roster.)

When asked "who is the current president / VPE / etc." and the answer is in this list, give the name. When asked about a role NOT in this list, decline to guess and direct the user to confirm with the club.

## Voting and decisions

This section is about **club governance / member votes**, not regular-meeting award voting. For regular-meeting awards, guests who are present may vote along with members; see `soarhigh-faq`.

For routine meeting matters (theme, schedule change, adding a workshop), the President or executive committee can decide.

For club-level decisions affecting bylaws, finances, officer elections, or membership policy, a **paid-member vote** is held — guests / non-members do not vote on these governance matters. These votes typically require a simple majority for routine motions and a two-thirds majority for bylaw changes.

A quorum (minimum number of members present for a vote to be valid) typically equals one-third of paid members or a number defined in the official bylaws. The exact quorum count for SoarHigh is NOT recorded in this skill — confirm with the **Secretary** if the user needs the precise number.

## How to find the authoritative bylaws

The full official SoarHigh bylaws document is maintained by the executive committee, not by this assistant. Members can request a copy from:

- The **Secretary** (canonical keeper of governance documents).
- The **President** (for interpretation questions).
- The **VP Education** (for education-related policy questions).

This skill is a quick reference, not a substitute for the official document.

## When you don't have an answer

If the user asks something policy-specific that is NOT explicitly answered in the body above, do NOT guess. Reply along the lines of:

> "我没有这条具体的俱乐部规定。请联系 VP Education 或者俱乐部执行委员会获取权威答复。"

or in English:

> "I don't have that specific club rule. Please contact the VP Education or the SoarHigh executive committee for an authoritative answer."

Treat anything outside the body of this skill as unknown rather than approximated.

---
name: toastmasters-role-scripts
description: >-
  Sample scripts (参考话术) for Toastmasters meeting roles, drawn from the
  SoarHigh role-guide post and SoarHigh-specific conventions. Covers what
  each role-taker actually SAYS during the meeting — opening lines,
  transitions, reports, and SoarHigh-specific moments like the Hark Master
  snack reward and the 真情分享 (Moment of Truth) sharing. Includes scripts for
  Sergeant At Arms, President / Opening Remarks, Timer, Grammarian, AhCounter,
  Hark Master, Guests Self Introduction Host, Table Topics Master, and
  Moment of Truth. Does NOT cover evaluator scripts (TTE / IE / GE),
  Toastmaster of the Meeting (TOM), Prepared Speaker, or Meeting Manager —
  those are intentionally omitted (evaluators write their own evaluations
  per speech; TOM / PS / MM scripts vary too much to template). Load this
  skill when the user asks "what do I say as X" / "X 怎么说" / "X 的话术" /
  "I'm doing TTM tonight, what's a good opening" / "give me a Timer opening
  script" type questions. For the role definitions themselves (what each
  role DOES), load `toastmasters-roles` instead. Often loaded together with
  `toastmasters-roles` for "what is X and what do they say".
---

# Toastmasters Role Sample Scripts (参考话术)

Companion to `toastmasters-roles` — that skill says what each role IS, this skill says what each role-taker SAYS. Most scripts here come directly from the SoarHigh role-guide post; a few SoarHigh-specific roles (AhCounter, Hark Master, Moment of Truth as 真情分享) were authored to fit SoarHigh conventions.

The order below roughly follows the meeting timeline so a Meeting Manager can read top-to-bottom while building the agenda.

**Roles intentionally NOT in this skill** (script not provided):
- **TTE / IE / GE** — evaluators write their own evaluations per speech; templating would defeat the goal of specific feedback.
- **TOM (Toastmaster of the Meeting)** — transitions vary too much by meeting; better to absorb the role's responsibilities and improvise.
- **Prepared Speaker** — the speech itself IS the script; project objectives differ per Pathways path.
- **Meeting Manager** — workflow lives in `soarhigh-meeting-manager`, not in-meeting speaking.
- **Workshop Speaker** — workshop content is the script.

---

## Sergeant At Arms (SAA) — meeting open

The first voice of the meeting. Introduces 4 ground rules and formally declares the meeting open.

> Good Evening, fellow Toastmasters and dear guests, my name is Rui and I will be the receptionist for tonight's meeting. I welcome you all to the **376th meeting** of the SoarHigh Toastmasters Club. Before starting the meeting, I would like to mention 4 ground rules we follow in our meeting:
>
> 1. Please turn off your mobile phones or put them on Silent mode.
> 2. As Toastmasters, we don't talk about sex, religion, and politics, so please refrain from discussing these topics.
> 3. Please do not move around and cross talk during the meeting.
> 4. We shake hands with people who invite us to stage, and do that again before we leave the stage.
>
> With this, I announce tonight's meeting as **open** and hand over the stage to the president **Jessica**.

(Replace the meeting number, your own name, and the President's name. The four ground rules and the formal "I announce tonight's meeting as open" closer are the load-bearing pieces — keep them.)

---

## President / Opening Remarks — TM + SoarHigh introduction

Delivers a brief introduction of Toastmasters International and the SoarHigh club. Below is a condensed reference; expand or trim to fit the time slot.

> Thanks to **[SAA's name]** for introducing tonight's meeting rules. Now I'd like to give a brief introduction about Toastmasters and our SoarHigh Toastmasters Club.
>
> *(Optional, if first-time guests are present: ask "Is this your first time at a Toastmasters meeting? How did you find SoarHigh?" — light interaction.)*
>
> **About Toastmasters:** Toastmasters is a non-profit organization that helps members improve **public speaking, communication, and leadership** skills. It's over 100 years old, with clubs in more than 140 countries — over 80 clubs just in Shenzhen.
>
> Three keywords matter at Toastmasters: **Network** — connect with people from all walks of life (some members even met their partners through TM); **Public speaking** — practice presenting and communicating with more confidence and impact; **Leadership** — join the club officer team to organize meetings and events, sharpening real-world leadership skills that have helped many members advance their careers.
>
> **About SoarHigh:** SoarHigh was established in 2014 by Shenzhen Airline as a corporate club, opened to the public in 2016, and became a fully English-speaking club in 2024 — we remain the only English-speaking club in 宝安区 today. Our slogan is **"Soarhigh, so high, takes me fly!"**
>
> Three keywords matter at SoarHigh: **Family atmosphere** — we're more than a club, we're a family that loves, cares, laughs, and inspires; **Fun** — beyond regular meetings we host outings every month and themed special meetings (speed dating, Halloween parties, etc. — visit soarhigh.top or our 〖搜嗨头马〗 miniapp for past events); **Growth** — SoarHigh is the perfect stage to test imperfect ideas, see real changes, and share the happiness of growing together. We support and cheer for each other.
>
> Now I'll hand the stage to tonight's Toastmaster, **[TOM's name]**, to kick off the meeting.

The "three keywords" structure (network / speaking / leadership for TM; family / fun / growth for SoarHigh) is the load-bearing scaffold — keep it even when shortening. SoarHigh's founding story (Shenzhen Airline 2014 → public 2016 → all-English 2024 → only English club in Bao'an) is also worth preserving.

---

## Timer — opening the timing rules

Introduces themselves, explains the bell rules, and (later) gives a timing report. From the SoarHigh role guide:

> **Opening:** I'm the Timer for today. My role is to keep track of the time for each speaker to ensure that the meeting runs smoothly. In Toastmasters, there are two types of speeches: Table Topics and Prepared Speeches. For **Table Topics**, the time limit is 2 minutes. I will raise the green card at 1 minute, the yellow card at 1.5 minutes, and the red card at 2 minutes. Speakers should conclude their speech within 30 seconds after the red card and before I ring the bell. For **Prepared Speeches**, the time limit is 7 minutes. I will raise the green card at 5 minutes, the yellow card at 6 minutes, and the red card at 7 minutes. Each speaker is allowed a grace period of 30 seconds to conclude their speech before I ring the bell.
>
> At the end of the meeting, I will provide a timing report for everyone. I hope everyone can stay within their time limits and enjoy today's meeting.

**Universal timing rule (cards are based on time REMAINING, not time used):**
- Speeches **≤ 3 min** (Table Topics at 2 min, IE at 3 min, AhCounter / Grammarian reports): green at **1 min remaining**, yellow at **30 s remaining**, red at end, bell at red + 30 s.
- Speeches **3–10 min** (Prepared Speech at 7 min, TTE / GE at up to 8 min, Hark at up to 5 min): green at **2 min remaining**, yellow at **1 min remaining**, red at end, bell at red + 30 s.
- Speeches **> 10 min** (long speeches, workshop sessions): green at **5 min remaining**, yellow at **2 min remaining**, red at end, bell at red + 30 s.

If the meeting uses non-standard speech lengths, apply the same rule scaled to the actual length and announce the cards explicitly in the opening. Full per-segment derived table is in `meeting-protocol`.

---

## Grammarian — opening + report

> **Opening:** Hello everyone, my name is Max, I'll be tonight's Grammarian. I'll pay close attention to all speakers, listening carefully to your language usage, taking notes on improper language as well as outstanding words, quotes, and thoughts. **Tonight's Word of the Day is "Resilience"** — please try to use it during the meeting. I'll track usage and report counts at the end. Now back to the Toastmaster.
>
> **Report:** As Grammarian, I'm delighted to share today's language highlights. Our Word of the Day "**resilience**" was used 8 times! 特别欣赏 Linda 在演讲中使用的隐喻："Life is like a bicycle..."。同时提醒注意第三人称单数使用，如 "He work" 应为 "He works"。今日最佳金句来自 Jack: "Failure is the tuition fee for success."

---

## AhCounter — opening + report

Tracks filler words ("um", "ah", "like", etc.) and reports counts at the end.

> **Opening:** Good evening everyone, my name is X and I'll be your AhCounter for tonight's meeting. My job is to listen for filler words — "ah", "um", "uh", "like", "you know", "actually", "so", and similar verbal pauses we use unconsciously when we're thinking out loud. I'll also note any unnecessary repetition of words. Please don't worry — this isn't about catching anyone out. The point is to help all of us become more aware of these speech habits so we can speak more clearly and confidently. I'll report my counts at the end of the meeting. Now back to our Toastmaster.
>
> **Report:** Thank you, Toastmaster. Here are tonight's filler-word observations:
> - **Joyce** — 3 "um", 2 "like" during her Prepared Speech.
> - **Frank** — 5 "ah", 1 "you know" during Table Topics.
> - **Liz** — clean delivery, no notable fillers — well done!
>
> Overall, our most common filler tonight was "**um**", with about 12 across all speakers. A small habit to watch: a brief silent pause is far more powerful than a filler — the audience reads silence as confidence, not hesitation. Back to you, Toastmaster.

---

## Hark Master — opening + pop-quiz close

SoarHigh-specific: rewards the first audience member to answer each recall question correctly with a snack.

> **Opening (early in the meeting):** Good evening everyone, my name is X and I'll be tonight's Hark Master. My job is the easiest one tonight: I just listen carefully — to every speech, every Table Topic answer, every announcement. At the end of the meeting I'll come back and ask the audience some questions to see who was paying attention. **And — at SoarHigh — the first person to answer each question correctly gets a snack.** So stay sharp, take in everything you hear tonight, and the snacks could be yours. Back to you, Toastmaster.
>
> **Pop quiz segment (near end of meeting):** All right, let's see who's been listening tonight. I have **[N]** questions, and the first correct answer to each gets a snack from me 🍫.
>
> 1. Our first Prepared Speaker, Joyce, mentioned a small object she always carries — what was it?
> 2. Frank's Table Topic answer included a city he'd never visited but wants to go to. Which city?
> 3. Tonight's Word of the Day was used most often by which speaker?
> 4. Our Grammarian called out a particularly nice metaphor — who said it, and what was it?
>
> *(After each question, take the first hand up; verify the answer is correct; hand a snack.)*
>
> Great memory tonight, everyone — back to you, Toastmaster.

(Tune the question count and difficulty to the audience. Mix specific factual recall — "what city did X mention" — with synthesizing questions — "what was the main message of Y's speech" — to keep it interesting.)

---

## Guests Self Introduction Host — invite guests up

From the SoarHigh role guide:

> Hi, everyone, it's my honor to be the host of this Guest Self-Introduction part. In this part, we'd like to invite all the new friends to come here to introduce yourself. **So if you're not our member of SoarHigh club, or if this is your first time here, please put up your hand**, come up, and make a 30-second introduction about yourself. You can tell us your name, job, hometown, hobby, and the reason why you came here tonight.
>
> OK, take myself as an example. I'm Libra, from Shandong province, my job is a consultant for startups, my hobby is reading... this is my second time at SoarHigh. That's my intro, thank you.
>
> Please notice that everyone has 30 seconds, and don't be shy — just let us know more about you. OK, let's start now.
>
> *(After each guest finishes, briefly thank them and invite the next. Note each name as they introduce themselves; at the end, briefly recap all guest names so the audience remembers them, and offer a group photo.)*

(The "I'm not a member, raise your hand if you're a guest" framing makes the guest definition concrete without being awkward. The 30-second time-box matters — without it, an enthusiastic first guest will speak for 3 minutes and the segment runs over.)

---

## Table Topics Master (TTM) — opening + first prompt

> Good evening everyone, I'll be your Table Topics Master tonight. Before we start, let me share **tonight's Word of the Day: "Resilience."** Try to use it in your responses where it fits — the Grammarian will track how often we use it.
>
> Tonight's table topic is about principle, inspired by Ray Dalio's book. Ray Dalio is a successful investor and entrepreneur; in the book *Principle* he explained his principles of work and life, and how those principles guided him and his team to success. I believe all of us, more or less, have some principles — consciously or sub-consciously — participating in our daily decisions and actions, thus steering our life directions. They are important parts of our 三观.
>
> Tonight, let's take this chance to reflect on these principles. I have 9 questions; you can pick any one and present your response within 2 minutes. **Anyone in the room who isn't the TTE is welcome to come up — guests and members alike.** Who is eager to kick us off?

Structural pieces — TTM intro → WoD announcement → theme framing → rules (9 questions, pick one, 2 min, non-TTE only) → invite first speaker. Adapt theme + WoD per meeting.

---

## Moment of Truth — SoarHigh 真情分享

At SoarHigh, MoT is repurposed from the generic "meeting feedback" segment into an open heart-to-heart sharing space.

> Good evening, everyone. We've come to my favorite part of the meeting — at SoarHigh we call it **真情分享, our Heart-to-Heart Sharing**. In agendas it's still labeled "Moment of Truth", but at SoarHigh the meaning is different from the standard Toastmasters version: it's not about giving feedback on the meeting. It's an open invitation for **anyone here — members, guests, anyone** — to come up and share whatever's on your heart. It can be a feeling tonight's meeting brought up, a story you've been carrying around, something you've been struggling with, something you're grateful for. Anything. There are no rules about topic, no time pressure (within reason), and no judgment.
>
> I'll start us off with a short share to make the space safe... *[deliver a brief 1-minute personal share to model the tone]*.
>
> Now I'd like to invite anyone who feels moved to come up. The stage is yours.
>
> *(Wait quietly — sometimes the silence stretches before the first person stands up. Let it. Trust the room.)*
>
> *(After each share: thank them sincerely without commenting / evaluating / advising — this isn't TT or PS, it's a sharing space. Just "Thank you for sharing." Then invite the next.)*
>
> *(Closing, when no one else moves to share or time runs short):* Thank you to everyone who shared tonight, and to everyone who held space for them. This is what SoarHigh is — a place where we get to be more than speakers, where we get to be human together. Back to you, Toastmaster.

(Critical norms: do NOT evaluate or advise after a share — just thank. Do NOT push a specific person to speak — wait until they choose. Do NOT enforce a strict topic — that would defeat the openness. The goal is emotional connection, not performance.)

---

## Resources

For more reference scripts beyond what's covered here, the **〖头马演讲助手Pro〗** miniapp (a separate, third-party miniapp — search in WeChat) has each officer's responsibilities and additional script variants. The original SoarHigh role-guide post is at https://www.soarhigh.top/posts/introduction-of-toast-masters-meeting-roles.

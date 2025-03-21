parse_meeting_agenda_image_system_prompt = """Read and parse an image of a Toastmasters meeting agenda. \
Extract information for each session/segment of the meeting along with relevant details and provide the \
output in a structured format.

# Steps

1. **Image Interpretation**: Analyze the image to recognize text and extract it in a readable format.
2. **Identify Segments**: Determine different sections within the Toastmasters agenda such as opening, speeches, \
evaluations, etc.
3. **Extract Details**: For each segment, identify details such as title, duration, speaker name, and description.
4. **Organize Information**: Structure the extracted information in a clear and organized manner for easy understanding.

# Schemas
Meeting:
- no (e.g., 389): The meeting number
- type (e.g., Regular, Workshop, Custom): The type of meeting
- theme: The theme for the meeting.
- manager: The person organizing/managing the meeting.
- date: The date of the meeting.
- start_time: The start time of the meeting.
- end_time: The end time of the meeting.
- location: The location where the meeting is held.
- segments: A list of Segments that the meeting is composed of.

Each Segment:
- id: A unique identifier for each segment of the meeting.
- role_taker: The attendee/attendees who is/are performing the segment.
- type (e.g., timer introduction, prepared speech 1, table topic evaluation etc): The type of segment.
- start_time: The start time of the segment.
- end_time: The end time of the segment.
- title (optional): The title of the speech or workshop, applicable if the segment is a prepared speech or workshop.
- duration: The duration of the segment.
- content (text): Detailed scripts or notes about the speech, evaluation, or activity, can be empty.
- related_segment_ids (text): A list of IDs of related segments, stored as a comma-separated string (e.g., "100,130"). \
This field allows a segment to reference multiple other segments if necessary. For example, in a prepared speech \
evaluation segment, this represents which speech segment is evaluated.

# Output
a meeting data structure that contains meeting infos with all detailed segments of the meeting

# Notes
- Title are only for prepared speech, workshop presentation type of segments that has a formal title.
- Members and guests registration, meeting or time rule introduction etc, these are all segment types, \
not segment title.
- There are two segment types related to table topic session, first is TTM opening, second is the table topic session, \
don't use WOT(word of the day) as the segment type, use table topic session as the type, and put WOT infos inside the \
segment content.
- In the prepared speech, there maybe also pathway informations on the left side (e.g. humor, leadership that end \
with digits), don't confuse it with the actual title of the speech (usually on the right). Use the actual speech title \
as this segment's title, and ignore the pathway.
- Ensure accuracy by verifying each extracted segment against the image content.
- If any details are missing or unreadable, leave the field as `null` or an empty string.
"""

plan_meeting_from_text_developer_prompt = """
I am trying to create an agenda for an around 2 hours toastmasters meeting. A toastmasters meeting is usually composed \
of different segments, and most segment has a role and requires a person to take the role. I will list out the common \
segments and you will help me generate an meeting agenda.

## Meeting type
- Regular: regular meeting is the most common type of meeting, usually contains 2-3 prepared speech segments.
- Workshop: depending on the length of workshop segment (usually 20-30 mins), it may have only one or may not have \
prepared speech segment.

## Segments (ordered by time)
- Guests Registration: required, at the first 15 mins of the meeting.
- SAA (or Meeting Rules Introduction): required, usually 2 mins, formally announce the begin of the meeting.
- Opening Remarks: required, usually 2 mins, brief introduction of toastmasters and the club.
- TOM (or Toastmaster of Meeting Introduction): required, usually 2 mins, brief introduction of meeting agenda
- Timer: required, usually 2 mins, brief introduction of meeting timing rule
- Grammarian: optional, usually 2 mins, brief notice attendees to use words properly
- Hark Master: optional, usually 1 mins, brief notice of game rule in the later Hark Master Pop Quiz segment
- Aha Counter: optional, usually 1 mins, brief notice attendees to be aware of using words like "ahh", "emm" etc
- Guests Introduction: required, usually 5-8 mins, invite all the guests to briefly introduce themselves
- TTM (Table Topic Master) Opening: required, usually 2-3 mins, brief introduction of table topic and rule for the \
following table topic session
- Table Topic Session: required, usually 20 mins, sometimes 18 mins, each speaker randomly pick 1 question out of 9 \
and deliver a 2 mins impromptu response
- Workshop: required in workshop meeting, usually 20-30 mins, workshop on one specific topic
- PS (Prepared Speech): required in regular meeting, usually 7 mins each, sometimes 5 mins.
- Tea Break & Group Photos: 8-12 mins, usually 10 mins
- TTE (Table Topic Evaluation): required, 5-8 mins, usually 7 mins, evaluate each speaker in table topic session
- IE (Prepared Speech Evaluation): required in regular meeting, every PS segment will have one IE segment for evaluation
- Grammarian Report: required if there is grammarian, usually 2-3 mins
- Aha Counter Report: required if there is Aha Counter, usually 2 mins
- Timer Report: required, usually 2-3 mins
- Hark Master Pop Quiz: required if there is Hark Master, usually 5 mins
- GE (General Evaluation): required, 7-8 mins, usually 8 mins, evaluate all roles
- Voting Section: required, usually 2mins, cast votes on best role taker for each category
- MOT (Moment of Truth): required, 5-8 mins, invite attendee to share feelings about the meeting
- Awards: required, 2-3 mins, present voted awards for each category
- Closing Remarks: required 1 min

## Club members
- Rui Zheng
- Joyce Feng
- Joseph Zhang
- Libra Lee
- Leta li
- Frank Zeng
- Max Long
- Julia Cao
- Jessica Peng
- Tina Zhang
- Phyllis Hao
- Owen Liang
- Danica Zhan
- Amy Fang
- Snow Xue
- Steve Choong

## Example

### Example 1
a regular meeting with 2 PS
#### Input
```plain
SOARHIGH 387th  meeting: Aging: It's an adventure
✍ Theme: Aging
💡 Word of Today: immortal
📅 Date: Nov. 6, 2024 (Wed)
⏰ Time: Wednesday 19:30 - 21:30
📍 **Location:** JOININ HUB, 6th Xin'an Rd,Bao'an (Metro line 1 Baoti / line 11 Bao'an)
👧MM: Rui Zheng

🌟Context: 🌟
Imagine a world where half the women you meet are over 50. Envision working until you're 75. As our global population \
ages and birth rates decline, Elon Musk warns that population collapse is civilization's greatest threat. Meanwhile, \
Mark Zuckerberg and his wife are striving to cure, prevent, or manage all diseases by the century's end. Similarly, \
Anthropic AI founder Dario Amodei believes that within the next 7 to 12 years, AI could help treat nearly all \
diseases. How can we and our parents age peacefully and gracefully in the coming decades? Join us at our meeting to \
discuss this vital topic!

【The true costs of ageing】 https://www.bilibili.com/video/BV1iLpaeaE4k

SAA:  Joyce
TOM: Rui
Timer: Max
Guests Intro: Joseph
Hark Master: Mia

TTM: Rui
TTE: Emily

PS1: Frank
IE1: Phyllis
PS2: Libra
IE2: Amanda(FSTT)

MOT: Leta
GE:Karman (Trainer)
```

#### Output
```json

{
  "no": 387,
  "type": "Regular",
  "theme": "Aging",
  "manager": "Rui Zheng",
  "date": "2024-11-05",
  "start_time": "19:15:00",
  "end_time": "21:30:00",
  "location": "JOININ HUB, 6th Xin'an Rd, Bao'an (Metro line 1 Baoti / line 11 Bao'an)",
  "introduction": "Imagine a world where half the women you meet are over 50. Envision working until you're 75. As \
our global population ages and birth rates decline, Elon Musk warns that population collapse is civilization's \
greatest threat. Meanwhile, Mark Zuckerberg and his wife are striving to cure, prevent, or manage all diseases by \
the century's end. Similarly, Anthropic AI founder Dario Amodei believes that within the next 7 to 12 years, AI could \
help treat nearly all diseases. How can we and our parents age peacefully and gracefully in the coming decades? Join \
us at our meeting to discuss this vital topic!\n\n【The true costs of ageing】 https://www.bilibili.com/video/BV1iLpaeaE4k",
  "segments": [
    {
      "type": "Guests Registration",
      "start_time": "19:15",
      "duration": "15",
      "role_taker": "All"
    },
    {
      "type": "Meeting Rules Introduction (SAA)",
      "start_time": "19:30",
      "duration": "3",
      "role_taker": "Joyce Feng"
    },
    {
      "type": "Opening Remarks",
      "start_time": "19:33",
      "duration": "2",
      "role_taker": ""
    },
    {
      "type": "TOM (Toastmaster of Meeting) Introduction",
      "start_time": "19:35",
      "duration": "2",
      "role_taker": "Rui Zheng"
    },
    {
      "type": "Timer",
      "start_time": "19:37",
      "duration": "3",
      "role_taker": "Max Long"
    },
    {
      "type": "Hark Master",
      "start_time": "19:40",
      "duration": "3",
      "role_taker": "Mia"
    },
    {
      "type": "Guests Self Introduction (30s per guest)",
      "start_time": "19:43",
      "duration": "8",
      "role_taker": "Joseph Zhang"
    },
    {
      "type": "TTM (Table Topic Master) Opening",
      "start_time": "19:52",
      "duration": "4",
      "role_taker": "Rui Zheng"
    },
    {
      "type": "Table Topic Session",
      "start_time": "19:56",
      "duration": "16",
      "role_taker": "All"
    },
    {
      "type": "Prepared Speech",
      "start_time": "20:13",
      "duration": "7",
      "role_taker": "Frank Zeng"
    },
    {
      "type": "Prepared Speech",
      "start_time": "20:21",
      "duration": "7",
      "role_taker": "Libra Lee"
    },
    {
      "type": "Tea Break & Group Photos",
      "start_time": "20:29",
      "duration": "12",
      "role_taker": "All"
    },
    {
      "type": "Table Topic Evaluation",
      "start_time": "20:42",
      "duration": "7",
      "role_taker": "Emily"
    },
    {
      "type": "Prepared Speech Evaluation",
      "start_time": "20:50",
      "duration": "3",
      "role_taker": "Phyllis Hao"
    },
    {
      "type": "Prepared Speech Evaluation",
      "start_time": "20:54",
      "duration": "3",
      "role_taker": "Amanda"
    },
    {
      "type": "Timer Report",
      "start_time": "20:58",
      "duration": "2",
      "role_taker": "Max Long"
    },
    {
      "type": "Hark Master Pop Quiz",
      "start_time": "21:01",
      "duration": "5",
      "role_taker": "Mia"
    },
    {
      "type": "General Evaluation",
      "start_time": "21:07",
      "duration": "4",
      "role_taker": "Karman"
    },
    {
      "type": "Voting Section",
      "start_time": "21:16",
      "duration": "2",
      "role_taker": ""
    },
    {
      "type": "Moment of Truth",
      "start_time": "21:19",
      "duration": "7",
      "role_taker": "Leta Li"
    },
    {
      "type": "Awards",
      "start_time": "21:27",
      "duration": "3",
      "role_taker": ""
    },
    {
      "type": "Closing Remarks",
      "start_time": "21:30",
      "duration": "1",
      "role_taker": ""
    }
  ]
}

```



### Example 2
a regular meeting with 3 PS
#### Input
```plain
SOARHIGH 390th  meeting:
✍ Theme: Different gen.different words
💡 Word of Today: gap
📅 Date: Nov. 27, 2024 (Wed)
⏰ Time: Wednesday 19:30 - 21:30
📍 **Location:** JOININ HUB, 6th Xin'an Rd,Bao'an (Metro line 1 Baoti / line 11 Bao'an)
👧MM: Leta

🌟Context: 🌟
When someone sends a smiling face sticker😊 on WeChat, it might evoke a few thoughts: Positive emotion, response cue, \
connection or just casual tone. However, for some Millennials and Generation Z, a smiling face sticker might come \
across as overly simplistic or dismissive, potentially leading to feelings of offense if the context of the \
conversation is more serious. I don't like seeing exclamation marks in chats, they make me feel like I'm being \
bossed around. Join us this Wednesday to share your thoughts and help bridge communication gaps between generations.

SAA:  Joseph
TOM: Leta
Timer: Julia Hu
Guests Intro: Joyce

TTM: Libra
TTE: Topher

PS1: Joseph
IE1: Phyllis
PS2:Max
IE2: Amy
PS3: Frank
IE3: Angela (Foresea)

MOT: Highlen Shao
GE:Jessica
```


#### Output
```json
{
  "no": 390,
  "type": "Regular",
  "theme": "Different Generations Different Words",
  "manager": "Leta Li",
  "date": "2024-11-27",
  "start_time": "19:15:00",
  "end_time": "21:30:00",
  "location": "JOININ HUB, 6th Xin'an Rd,Bao'an (Metro line 1 Baoti / line 11 Bao'an)",
  "introduction": "When someone sends a smiling face sticker[Smile] on WeChat, it might evoke a few thoughts:\n\
Positive emotion, response cue, connection or just casual tone. However, for some Millennials and Generation Z, \
a smiling face sticker might come across as overly simplistic or dismissive, potentially leading to feelings of \
offense if the context of the conversation is more serious. I don't like seeing exclamation marks in chats, they \
make me feel like I'm being bossed around. Join us this Wednesday to share your thoughts and help bridge \
communication gaps between generations.",
  "segments": [
    {
      "type": "Guests Registration",
      "start_time": "19:15",
      "duration": "15",
      "role_taker": "All"
    },
    {
      "type": "Meeting Rules Introduction (SAA)",
      "start_time": "19:30",
      "duration": "2",
      "role_taker": "Joseph Zhang"
    },
    {
      "type": "Opening Remarks",
      "start_time": "19:32",
      "duration": "2",
      "role_taker": ""
    },
    {
      "type": "TOM (Toastmaster of Meeting) Introduction",
      "start_time": "19:34",
      "duration": "3",
      "role_taker": "Leta Li"
    },
    {
      "type": "Timer",
      "start_time": "19:37",
      "duration": "2",
      "role_taker": "Julia Hu"
    },
    {
      "type": "Guests Self Introduction (30s per guest)",
      "start_time": "19:39",
      "duration": "5",
      "role_taker": "Joyce Feng"
    },
    {
      "type": "TTM (Table Topic Master) Opening",
      "start_time": "19:45",
      "duration": "2",
      "role_taker": "Libra Lee"
    },
    {
      "type": "Table Topic Session",
      "start_time": "19:48",
      "duration": "20",
      "role_taker": "All"
    },
    {
      "type": "Prepared Speech",
      "start_time": "20:09",
      "duration": "7",
      "role_taker": "Joseph Zhang"
    },
    {
      "type": "Prepared Speech",
      "start_time": "20:17",
      "duration": "7",
      "role_taker": "Max Long"
    },
    {
      "type": "Prepared Speech",
      "start_time": "20:25",
      "duration": "7",
      "role_taker": "Frank Zeng"
    },
    {
      "type": "Tea Break & Group Photos",
      "start_time": "20:33",
      "duration": "10",
      "role_taker": "All"
    },
    {
      "type": "Table Topic Evaluation",
      "start_time": "20:44",
      "duration": "8",
      "role_taker": "Topher"
    },
    {
      "type": "Prepared Speech Evaluation",
      "start_time": "20:52",
      "duration": "3",
      "role_taker": "Phyllis Hao"
    },
    {
      "type": "Prepared Speech Evaluation",
      "start_time": "20:55",
      "duration": "3",
      "role_taker": "Amy Fang"
    },
    {
      "type": "Prepared Speech Evaluation",
      "start_time": "20:58",
      "duration": "3",
      "role_taker": "Angela (Foresea)"
    },
    {
      "type": "Timer's Report",
      "start_time": "21:02",
      "duration": "2",
      "role_taker": "Julia Hu"
    },
    {
      "type": "General Evaluation",
      "start_time": "21:05",
      "duration": "8",
      "role_taker": "Jessica Peng"
    },
    {
      "type": "Voting Section",
      "start_time": "21:14",
      "duration": "2",
      "role_taker": ""
    },
    {
      "type": "Moment of Truth",
      "start_time": "21:17",
      "duration": "8",
      "role_taker": "Highlen"
    },
    {
      "type": "Awards",
      "start_time": "21:26",
      "duration": "3",
      "role_taker": ""
    },
    {
      "type": "Closing Remarks (President)",
      "start_time": "21:30",
      "duration": "1",
      "role_taker": ""
    }
  ]
}
```
"""

plan_meeting_from_text_user_prompt = """
## Question
Given the following input, generate the structured agenda for me
#### Input
```plain
{text}
```

## Important Notes
1. If the name match the first or the full name of a club member, then it is from our club. e.g. "Rui" refers to the \
club member "Rui Zheng", "Ray" and "Rui Zhang" both refer to a guest. In your output, please use full name if it \
matches to a member.
2. Between segments there can be a 1 min buffer, e.g. previous segment starts at 20:10 and duration is 2 min, the \
next segment can start at 20:12 or 20:13. Use this buffering mechanism to adjust time to fill in the whole 2 hours \
time window.
3. Above segments are ordered by time, you can add or remove some segments according to how many people registered but \
DO NOT change their orders.
4. Role taker for Opening Remarks, Awards, and Closing Remarks are always the president of the club Libra Lee.
5. Role taker for Voting Section is always the TOM (Toastmaster of Meeting Introduction).
6. Photographer is not required, so don't add a segment for photographer.


#### Output
"""

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
- meeting_type (e.g., Regular, Workshop, Custom): The type of meeting
- theme: The theme for the meeting.
- meeting_manager: The person organizing/managing the meeting.
- date: The date of the meeting.
- start_time: The start time of the meeting.
- end_time: The end time of the meeting.
- location: The location where the meeting is held.
- segments: A list of Segments that the meeting is composed of.

Each Segment:
- segment_id: A unique identifier for each segment of the meeting.
- role_taker: The attendee/attendees who is/are performing the segment.
- segment_type (e.g., timer introduction, prepared speech 1, table topic evaluation etc): The type of segment.
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

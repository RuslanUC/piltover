Here I'll describe updates implementation in this project.

Every **user** has its own **pts** counter (as described in official docs).
Each user **session** has its own **seq** counter.
For example, we have user 1 with two sessions: `u1s1` and `u1s2` and user2 with one session: `u2s1`.
User 1 has pts 1000, user 2 has pts 2000.

When a text message (say, id is 100) is sent (from session `u1s1`) to `u2s1`:
1. `u1s1` receives UpdateShortSentMessage (pts = 1001)
2. `u1s2` and `u2s1` receive UpdateShortMessage (pts = 1001 for `u1s2`, pts = 2001 for `u2s1`)

> [!NOTE]  
> No updates are saved to the database at this point cause new messages are returned as messages.Message in updates.getDifference and any updates that describe message creation (UpdateNewMessage, UpdateShortMessage, etc.) are ignored

When another text message (say, id is 101) is sent (from session `u1s1`) to `u1` (saved messages):
1. `u1s1` and `u1s2` receive three updates (`s1` as a response, `s2` as update):
   1. UpdateMessageID (has no pts): to notify a client which id was assigned to message
   2. UpdateNewMessage (pts = 1002): message itself
   3. UpdateReadHistoryInbox (pts = 1003): to mark chat as read

> [!NOTE]  
> Now, only UpdateReadHistoryInbox (pts 1003) is saved to a database

Now, if `u1` will request GetDifference(pts=1000), it will receive response with:
 - Two messages: id 100 and id 101
 - Two "other" updates: UpdateMessageID and UpdateReadHistoryInbox (pts 1003)

Then, `u1` edits message 101:
1. `u1s1` and `u1s2` receive one update:
   1. UpdateEditMessage (pts = 1004): updated message

> [!NOTE]  
> Now, UpdateReadHistoryInbox (pts 1003) and UpdateEditMessage (pts 1004) are saved to a database

If `u1` will request GetDifference(pts=1000), it will receive response with:
 - Two messages: id 100 and id 101 (edited)
 - Three "other" updates: UpdateMessageID, UpdateReadHistoryInbox (pts 1003) and UpdateEditMessage (pts 1004)

Then, `u1` deletes message 101:
1. `u1s1` and `u1s2` receive one update:
   1. UpdateDeleteMessages (pts = 1005): id of deleted message

> [!NOTE]  
> After this, UpdateEditMessage (pts 1004) is deleted from database
> Now, UpdateReadHistoryInbox (pts 1003) and UpdateDeleteMessages (pts 1005) are saved to a database

If `u1` will request GetDifference(pts=1000), it will receive response with:
 - One message: id 100
 - Three "other" updates: UpdateMessageID, UpdateReadHistoryInbox (pts 1003)

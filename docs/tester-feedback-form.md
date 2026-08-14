# Magneetar — Tester Feedback Form (G1)

Paste these questions into Google Forms / Typeform (or send as a WhatsApp
message) to each tester weekly. Target: **5 minutes per week, twice over the
2-week window**. Keep the tone plain — no jargon. The "approval" questions
at the end are the G1 exit signal.

> Google Forms: each question below is ready as a form item. Use "Linear
> scale" for the 1–5 ratings, "Short answer" for the free-text, "Multiple
> choice" for the yes/no. Do NOT ask for anything identifying beyond the
> device model + Android version (privacy-first brand).

---

## Weekly form (send at end of week 1 and week 2)

**Header:** Magneetar test — week N of 2. Thank you for doing this!

### Section 1 — Your phone
1. **What phone are you using?** *(short answer — model, e.g. "Tecno Spark 10")*
2. **What Android version?** *(short answer, e.g. "Android 13")*

### Section 2 — Did it stay alive?
3. **Over the last 7 days, how often did you have to open the app or do
   anything to "wake it up"?** *(multiple choice)*
   - Never — it just worked
   - Once or twice
   - Several times
   - Constantly — it kept dying
4. **Did you ever notice your phone NOT updating its location when it should
   have (e.g. you checked the dashboard and the map was stale)?**
   *(multiple choice)* — Never / Once / A few times / Didn't check

### Section 3 — Battery
5. **How has your battery been compared to before installing?** *(multiple
   choice)* — No difference / Slightly worse / Noticeably worse / Much worse
6. **Check Settings → Battery → Magneetar. What % of battery has it used
   today?** *(short answer, e.g. "8%")*

### Section 4 — Anything wrong?
7. **Did anything crash, freeze, or act weird?** *(multiple choice)* —
   No / Yes (described below)
8. **If yes, what happened, and roughly when?** *(paragraph)*
9. **Did you get any weird, missing, or repeated alerts?** *(paragraph)*

### Section 5 — The verdict (the G1 signal)
10. **Would you keep this app on your phone after the test?** *(multiple
    choice)* — Yes, definitely / Probably yes / Not sure / Probably not / No
11. **Would you recommend it to someone who has had a phone stolen?**
    *(multiple choice)* — Yes / No / Not sure
12. **Anything else we should know?** *(paragraph — open)*

---

## End-of-window form (day ~15, replaces the weekly form that week)

**Sections 1–4 identical** to the weekly form, then:

### Section 5 — Final verdict (this is the G2 sign-off seed)
13. **After 2 weeks of real use: is Magneetar ready for other people?**
    *(multiple choice)* — Yes, ship it / Close — fix the issues I reported
    first / No — it's not reliable enough yet
14. **Would you join the official closed testing on Google Play next?**
    *(multiple choice)* — Yes / No
15. **One thing that would make you trust it more?** *(paragraph)*

---

## Triage guide for the owner

| Report | Severity | Rule |
|---|---|---|
| App dies in background / stale `last_seen` | **P0** | Fix + redeploy before gate can pass |
| Theft response broken (no alert, no evidence, no recovery) | **P0** | Fix immediately — this is the product |
| Feature broken but workaround exists | P1 | Fix or owner-accept before G1 exit |
| Cosmetic / wording | P2 | Fix when convenient |
| Battery "noticeably worse" on a device | P1 | Measure against §3 of the tracker; investigate |
| "No" on Q10/Q11/Q13 | Signal | 2 or more → gate does not pass; dig into the why |

Every report gets a reply — even "it just worked" gets a thank-you. Testers
who feel heard stay for G2.

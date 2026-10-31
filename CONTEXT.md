# Product context

- A lesson has one question, one audience, a goal, an example, and learner exercise text.
- A source is a user-entered link plus attribution, license link, notes, version, and human review state. The app does not fetch source content.
- A claim is one sentence on a checklist. It points to one or more reviewed sources, or it is labeled as an inference with a reason.
- A claim review records a human note and the source versions that were reviewed. Editing its text or source version clears that review.
- A source edit increments its version. Only claims linked to that source lose review.
- Changing the worked values or teacher example note clears review on inference claims. Source-linked claims remain as reviewed.
- Revision rows preserve snapshots of saved lesson edits, review changes, and source changes.
- Exercises use bounded numeric lists and built-in mean/median arithmetic. Learner answers are compared as numbers; they are never evaluated as code.
- The readability panel reports word and sentence counts, Flesch Reading Ease, and Flesch-Kincaid grade as rough diagnostics.
- The fictional lesson fixture cites official Python documentation and includes original paraphrases, source credit, and a link to the documentation license.
- SQLite stores local work outside the checkout with owner-only directory and file permissions.
